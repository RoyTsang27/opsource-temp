// SPDX-License-Identifier: GPL-2.0-only

use std::fs;
use std::io::{self, Read};
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

const REQUEST_LIMIT: usize = 128;
const CLIENT_TIMEOUT: Duration = Duration::from_secs(2);

/// One bounded, newline-terminated request with a deadline for the whole read.
pub fn read_request(mut stream: &UnixStream) -> io::Result<String> {
    let deadline = Instant::now() + CLIENT_TIMEOUT;
    let mut buffer = [0u8; REQUEST_LIMIT];
    let mut length = 0;
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(io::Error::new(io::ErrorKind::TimedOut, "control request deadline"));
        }
        stream.set_read_timeout(Some(remaining))?;
        let count = stream.read(&mut buffer[length..])?;
        if count == 0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "incomplete control request"));
        }
        if let Some(end) = buffer[length..length + count].iter().position(|byte| *byte == b'\n') {
            return String::from_utf8(buffer[..length + end + 1].to_vec())
                .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "invalid control request encoding"));
        }
        length += count;
        if length == REQUEST_LIMIT {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "control request is too long"));
        }
    }
}

pub struct ControlServer {
    socket_path: PathBuf,
}

impl ControlServer {
    pub fn start<F>(socket_path: &Path, handler: F) -> io::Result<Self>
    where
        F: Fn(UnixStream) -> io::Result<()> + Send + Sync + 'static,
    {
        prepare_socket_path(socket_path)?;
        let listener = UnixListener::bind(socket_path)?;
        fs::set_permissions(socket_path, fs::Permissions::from_mode(0o600))?;

        thread::Builder::new()
            .name("pon-control".to_owned())
            .spawn(move || {
                for stream in listener.incoming().flatten() {
                    if stream.set_write_timeout(Some(CLIENT_TIMEOUT)).is_err() {
                        continue;
                    }
                    let _ = handler(stream);
                }
            })
            .map_err(io::Error::other)?;

        Ok(Self {
            socket_path: socket_path.to_owned(),
        })
    }
}

impl Drop for ControlServer {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.socket_path);
    }
}

fn prepare_socket_path(socket_path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(socket_path) {
        Ok(metadata) if metadata.file_type().is_socket() => fs::remove_file(socket_path),
        Ok(_) => Err(io::Error::new(io::ErrorKind::AlreadyExists, "control path is not a socket")),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::net::Shutdown;

    #[test]
    fn reads_valid_request_and_rejects_oversized_or_incomplete_input() {
        for (input, valid) in [
            (b"STATUS 1\n".as_slice(), true),
            (b"EVENTS 1 18446744073709551615\n".as_slice(), true),
            (b"STATUS 1".as_slice(), false),
            ([b'x'; REQUEST_LIMIT + 1].as_slice(), false),
            (b"\xff\n".as_slice(), false),
        ] {
            let (reader, mut writer) = UnixStream::pair().unwrap();
            writer.write_all(input).unwrap();
            writer.shutdown(Shutdown::Write).unwrap();
            assert_eq!(read_request(&reader).is_ok(), valid);
        }
    }

    #[test]
    fn silent_client_cannot_hold_the_control_server_forever() {
        let (reader, _writer) = UnixStream::pair().unwrap();
        let start = Instant::now();
        assert!(read_request(&reader).is_err());
        assert!(start.elapsed() < Duration::from_secs(5));
    }

    #[test]
    fn refuses_to_remove_a_regular_file_or_symlink() {
        let directory = std::env::temp_dir().join(format!("pon-control-test-{}", std::process::id()));
        fs::create_dir(&directory).unwrap();
        let path = directory.join("control");
        fs::write(&path, b"keep me").unwrap();
        assert!(prepare_socket_path(&path).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"keep me");
        fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink(directory.join("missing"), &path).unwrap();
        assert!(prepare_socket_path(&path).is_err());
        fs::remove_file(path).unwrap();
        fs::remove_dir(directory).unwrap();
    }
}
