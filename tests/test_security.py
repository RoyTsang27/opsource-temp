import argparse
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import ssl
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


download = load_module('download', 'dl_github_archive.py')
release = load_module('release', 'check-release.py')
kernel = load_module('kernel', 'sync-kernel.py')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        (self.path / 'out').mkdir()

    def archive(self, entries):
        path = self.path / 'source.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, kind, target in [('root', tarfile.DIRTYPE, '')] + entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = target
                member.mode = 0o755
                data = b'valid source\n' if kind == tarfile.REGTYPE else b''
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        return str(path)

    def reject(self, entries):
        with mock.patch.object(download.subprocess, 'check_call') as extract:
            with self.assertRaises(download.PathException):
                download.Path.untar(self.archive(entries), into=str(self.path / 'out'))
            extract.assert_not_called()
        self.assertEqual(list((self.path / 'out').iterdir()), [])

    def test_regular_files_and_internal_symlinks_extract(self):
        path = self.archive([
            ('root/dir', tarfile.DIRTYPE, ''),
            ('root/file', tarfile.REGTYPE, ''),
            ('root/dir/link', tarfile.SYMTYPE, '../file'),
        ])
        self.assertEqual(download.Path.untar(path, into=str(self.path / 'out')), 'root')
        self.assertEqual((self.path / 'out/root/dir/link').read_bytes(), b'valid source\n')

    def test_parent_traversal(self):
        self.reject([('root/../../outside', tarfile.REGTYPE, '')])

    def test_absolute_path(self):
        self.reject([('/outside', tarfile.REGTYPE, '')])

    def test_symlink_escape(self):
        self.reject([('root/link', tarfile.SYMTYPE, '../../outside')])

    def test_absolute_symlink(self):
        self.reject([('root/link', tarfile.SYMTYPE, '/tmp')])

    def test_symlink_parent_before_or_after_file(self):
        for entries in (
            [('root/link', tarfile.SYMTYPE, '.'), ('root/link/file', tarfile.REGTYPE, '')],
            [('root/link/file', tarfile.REGTYPE, ''), ('root/link', tarfile.SYMTYPE, '.')],
        ):
            with self.subTest(entries=entries):
                self.reject(entries)

    def test_symlink_chain_with_parent_traversal(self):
        self.reject([
            ('root/link', tarfile.SYMTYPE, '.'),
            ('root/chain', tarfile.SYMTYPE, 'link/../outside'),
        ])

    def test_hardlink_escape(self):
        self.reject([('root/link', tarfile.LNKTYPE, '../outside')])

    def test_hardlink_to_symlink(self):
        self.reject([('root/link', tarfile.SYMTYPE, '.'),
                     ('root/hard', tarfile.LNKTYPE, 'root/link')])

    def test_devices_and_fifo(self):
        for kind in (tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                self.reject([('root/special', kind, '')])

    def test_duplicate_members(self):
        self.reject([('root/file', tarfile.REGTYPE, ''), ('root/file', tarfile.REGTYPE, '')])

    def test_multiple_roots(self):
        self.reject([('other/file', tarfile.REGTYPE, '')])


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        patch = mock.patch.object(download, 'TMPDIR_DL', str(self.path / 'work'))
        patch.start()
        self.addCleanup(patch.stop)

    def args(self, **changes):
        values = dict(dl_dir=str(self.path), url='https://github.com/example/project.git',
                      subdir='project-1.0', source='project-1.0.tar.gz',
                      version='a' * 40, hash=hashlib.sha256(b'repacked').hexdigest(),
                      submodules=None)
        values.update(changes)
        return argparse.Namespace(**values)

    def test_tls_validation_and_timeout(self):
        method = download.DownloadGitHubTarball(self.args())
        with mock.patch.object(download.urllib.request, 'urlopen') as open_url:
            method._make_request('/repos/example/project')
        context = open_url.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(open_url.call_args.kwargs['timeout'], 30)

    def test_reject_path_and_option_injection(self):
        for field in ('source', 'subdir'):
            for value in ('../outside', '/tmp/outside', '-C', 'name\nline'):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(download.DownloadGitHubError):
                        download.DownloadGitHubTarball(self.args(**{field: value}))

    def test_reject_invalid_url(self):
        for url in ('https://githubXcom/owner/repo', 'https://github.com/owner/repo/extra',
                    'https://github.com/owner/repo?x=1'):
            with self.subTest(url=url):
                with self.assertRaises(download.DownloadGitHubError):
                    download.DownloadGitHubTarball(self.args(url=url))

    def test_reject_weak_and_invalid_hashes(self):
        for checksum in ('a' * 32, 'g' * 64, 'skip', None):
            with self.subTest(checksum=checksum):
                with self.assertRaises(download.DownloadGitHubError):
                    download.DownloadGitHubTarball(self.args(hash=checksum))

    def test_hash_check_is_repeatable_and_rejects_tampering(self):
        path = self.path / 'repacked'
        path.write_bytes(b'repacked')
        method = download.DownloadGitHubTarball(self.args())
        method._hash_check(path)
        method._hash_check(path)
        path.write_bytes(b'tampered')
        with self.assertRaises(download.DownloadGitHubError):
            method._hash_check(path)

    def test_private_download_workspace_and_cleanup(self):
        method = download.DownloadGitHubTarball(self.args())
        def fetch(path):
            self.assertEqual(Path(path).parent.stat().st_mode & 0o777, 0o700)
            raise OSError('network failure')
        with mock.patch.object(method, '_init_commit_ts'), mock.patch.object(method, '_fetch', side_effect=fetch):
            with self.assertRaises(OSError):
                method.download()
        self.assertEqual(list((self.path / 'work').glob('github-*')), [])

    def test_corrupt_cache_and_recent_entry_retention(self):
        cache = download.GitHubCommitTsCache()
        Path(cache.cachef).write_text('broken\nold 123 1\ninvalid value integer\n')
        self.assertEqual(cache.get('old'), 123)
        with mock.patch.object(cache, '_GitHubCommitTsCache__cachen', 1):
            cache.set('new', 456)
        self.assertIsNone(cache.get('old'))
        self.assertEqual(cache.get('new'), 456)

    def test_scratch_directory_symlink_is_rejected(self):
        victim = self.path / 'victim'
        victim.mkdir()
        (self.path / 'work').symlink_to(victim, target_is_directory=True)
        with self.assertRaises(download.DownloadGitHubError):
            download.DownloadGitHubTarball(self.args())
        self.assertEqual(list(victim.iterdir()), [])

    def test_writable_by_others_scratch_directory_is_rejected(self):
        scratch = self.path / 'work'
        scratch.mkdir()
        scratch.chmod(0o777)
        with self.assertRaises(download.DownloadGitHubError):
            download.DownloadGitHubTarball(self.args())
        self.assertEqual(list(scratch.iterdir()), [])

    def test_cache_symlink_cannot_truncate_another_file(self):
        cache = download.GitHubCommitTsCache()
        victim = self.path / 'victim'
        victim.write_text('keep this data')
        Path(cache.cachef).symlink_to(victim)
        with self.assertRaises(OSError):
            cache.set('key', 1)
        self.assertEqual(victim.read_text(), 'keep this data')

    def test_world_writable_cache_is_rejected(self):
        cache = download.GitHubCommitTsCache()
        Path(cache.cachef).write_text('key 1 2\n')
        Path(cache.cachef).chmod(0o666)
        with self.assertRaises(download.DownloadGitHubError):
            cache.get('key')


class ReleaseTests(unittest.TestCase):
    def test_valid_tag(self):
        release.check_tag('v1.2.3-rc1')

    def test_invalid_tags(self):
        for tag in ('--repo', 'a..b', 'a.lock', 'x/y', 'x\nname', '$(id)', '', 'a' * 81):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    release.check_tag(tag)

    def test_locked_feeds(self):
        release.check_feeds(ROOT / 'feeds.conf.release', ROOT / 'feeds.conf.default')

    def test_unpinned_or_redirected_feeds_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'feeds'
            source = (ROOT / 'feeds.conf.release').read_text()
            for changed in (source.replace('^e731ba76764082d9db71de60f1ddac43f4114101', ''),
                            source.replace('github.com/immortalwrt/packages', 'github.com/attacker/packages'),
                            source + source.splitlines()[1] + '\n'):
                path.write_text(changed)
                with self.assertRaises(ValueError):
                    release.check_feeds(path, ROOT / 'feeds.conf.default')

    def test_effective_security_config_required(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '.config'
            settings = ['CONFIG_' + name + '=y' for name in release.REQUIRED_OPTIONS]
            path.write_text('\n'.join(settings))
            release.check_config(path)
            path.write_text('\n'.join(settings).replace('CONFIG_PACKAGE_ucert=y', '# CONFIG_PACKAGE_ucert is not set'))
            with self.assertRaises(ValueError):
                release.check_config(path)

    def test_missing_signing_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(['sh', str(ROOT / 'scripts/load-release-keys.sh')],
                                    cwd=temp, env={'PATH': os.environ['PATH']}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(temp).iterdir()), [])

    def test_unsigned_sysupgrade_rejected_by_device_policy(self):
        path = ROOT / 'package/base-files/files/lib/upgrade/fwtool.sh'
        script = '. "$1"; REQUIRE_IMAGE_SIGNATURE=1; fwtool() { return 1; }; v() { :; }; fwtool_check_signature image'
        result = subprocess.run(['sh', '-c', script, 'test', str(path)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_no_output_images_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'staging_dir/host/bin').mkdir(parents=True)
            usign = work / 'staging_dir/host/bin/usign'
            usign.write_text('#!/bin/sh\necho fingerprint\n')
            usign.chmod(0o755)
            (work / 'key-build.pub').write_text('public')
            (work / 'images').mkdir()
            result = subprocess.run(['bash', str(ROOT / 'scripts/verify-release.sh'), 'images'],
                                    cwd=temp, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'No sysupgrade images', result.stderr)

    def verify_images(self, images):
        # Substitute signing tools to test orchestration and fail-closed shell
        # behavior; cryptographic verification is done by usign/ucert in CI.
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            tools = work / 'staging_dir/host/bin'
            tools.mkdir(parents=True)
            scripts = {
                'usign': '#!/bin/sh\necho fingerprint\n',
                'fwtool': '''#!/bin/sh
case "$2" in
  -i) echo metadata > "$3" ;;
  -s) grep -q '^signed$' "$4" || exit 1; echo certificate > "$3" ;;
  -T) cat "$5"; grep -q '^tampered$' "$5" && exit 1; exit 0 ;;
  *) exit 1 ;;
esac
''',
                'ucert': '#!/bin/sh\ngrep -q "^signed$"\n',
            }
            for name, source in scripts.items():
                (tools / name).write_text(source)
                (tools / name).chmod(0o755)
            (work / 'key-build.pub').write_text('public')
            (work / 'images').mkdir()
            for name, data in images.items():
                (work / 'images' / name).write_text(data)
            return subprocess.run(['bash', str(ROOT / 'scripts/verify-release.sh'), 'images'],
                                  cwd=temp, capture_output=True)

    def test_all_bin_and_itb_images_are_checked(self):
        result = self.verify_images({'first device-sysupgrade.itb': 'signed\n',
                                     'second-sysupgrade.bin': 'signed\n'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'Verified 2 signed', result.stdout)

    def test_one_unsigned_image_fails_release(self):
        result = self.verify_images({'first-sysupgrade.itb': 'signed\n',
                                     'second-sysupgrade.bin': 'unsigned\n'})
        self.assertNotEqual(result.returncode, 0)

    def test_pipeline_error_fails_release_even_when_verifier_succeeds(self):
        result = self.verify_images({'device-sysupgrade.itb': 'signed\ntampered\n'})
        self.assertNotEqual(result.returncode, 0)

    def test_apk_build_installs_firmware_trust_anchor_and_policy(self):
        source = (ROOT / 'package/base-files/Makefile').read_text()
        start = source.index('ifneq ($(filter y,$(CONFIG_SIGN_FIRMWARE)')
        end = source.index('\nifeq ($(CONFIG_NAND_SUPPORT),)', start)
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'host/bin').mkdir(parents=True)
            usign = work / 'host/bin/usign'
            usign.write_text('''#!/bin/sh
if [ "$1" = -F ]; then echo fingerprint; exit 0; fi
while [ "$#" -gt 0 ]; do
  case "$1" in
    -s) shift; echo private > "$1" ;;
    -p) shift; echo public > "$1" ;;
  esac
  shift
done
''')
            usign.chmod(0o755)
            ucert = work / 'host/bin/ucert'
            ucert.write_text('#!/bin/sh\nwhile [ "$#" -gt 0 ]; do if [ "$1" = -c ]; then shift; echo certificate > "$1"; fi; shift; done\n')
            ucert.chmod(0o755)
            (work / 'public-key.pem').write_text('apk public key')
            makefile = '''CONFIG_USE_APK=y
CONFIG_SIGN_FIRMWARE=y
CONFIG_REQUIRE_IMAGE_SIGNATURE=y
STAGING_DIR_HOST=$(CURDIR)/host
BUILD_KEY=$(CURDIR)/key-build
BUILD_KEY_APK_PUB=$(CURDIR)/public-key.pem
CP=cp
'''
            makefile += source[start:end]
            makefile += '''\nall:
\t$(Build/Configure)
\t$(call Package/base-files/install-key,$(CURDIR)/root)
\t$(call Package/base-files/install-firmware-key,$(CURDIR)/root)
\t$(call Package/base-files/install-signature-policy,$(CURDIR)/root)
'''
            (work / 'Makefile').write_text(makefile)
            result = subprocess.run(['make'], cwd=temp, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((work / 'key-build.ucert').is_file())
            self.assertEqual((work / 'root/etc/opkg/keys/fingerprint').read_text(), 'public\n')
            self.assertEqual((work / 'root/etc/apk/keys/public-key.pem').read_text(), 'apk public key')
            self.assertEqual((work / 'root/lib/upgrade/require-signature.sh').read_text(), 'REQUIRE_IMAGE_SIGNATURE=1\n')
            self.assertFalse((work / 'root/key-build').exists())

    def run_image_signing_recipe(self, name, with_keys=False):
        source = (ROOT / 'include/image-commands.mk').read_text()
        body = source.split('define Build/' + name + '\n')[1].split('\nendef')[0]
        signing = body[body.index('\t$(if $(CONFIG_SIGN_FIRMWARE),'):]
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'bin').mkdir()
            for command, text in {
                'usign': '#!/bin/sh\nexit 1\n',
                'ucert': '#!/bin/sh\ntouch ucert-was-called\n',
                'fwtool': '#!/bin/sh\ntouch fwtool-was-called\n',
            }.items():
                (work / 'bin' / command).write_text(text)
                (work / 'bin' / command).chmod(0o755)
            (work / 'all').write_text('firmware')
            if with_keys:
                (work / 'key-build').write_text('private')
                (work / 'key-build.ucert').write_text('certificate')
            (work / 'Makefile').write_text('CONFIG_SIGN_FIRMWARE=y\nBUILD_KEY=key-build\n.PHONY: all\nall:\n' + signing + '\n')
            env = dict(os.environ, PATH=str(work / 'bin') + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['make'], cwd=temp, env=env, capture_output=True)
            self.assertFalse((work / 'ucert-was-called').exists())
            self.assertFalse((work / 'fwtool-was-called').exists())
            return result

    def test_image_recipes_refuse_missing_keys(self):
        for name in ('append-metadata', 'append-gl-metadata'):
            with self.subTest(recipe=name):
                result = self.run_image_signing_recipe(name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'Firmware signing requires', result.stderr)

    def test_image_recipes_propagate_signer_failure(self):
        for name in ('append-metadata', 'append-gl-metadata'):
            with self.subTest(recipe=name):
                result = self.run_image_signing_recipe(name, with_keys=True)
                self.assertNotEqual(result.returncode, 0)


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        (self.path / 'target/linux/airoha').mkdir(parents=True)
        (self.path / 'target/linux/generic').mkdir(parents=True)
        (self.path / 'target/linux/airoha/Makefile').write_text('KERNEL_PATCHVER:=6.18\n')
        self.details = self.path / 'target/linux/generic/kernel-6.18'
        self.details.write_text(self.content(52))
        self.root_patch = mock.patch.object(kernel, 'ROOT', self.path)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    @staticmethod
    def content(patch, checksum='a' * 64):
        return 'LINUX_VERSION-6.18 = .' + str(patch) + '\nLINUX_KERNEL_HASH-6.18.' + str(patch) + ' = ' + checksum + '\n'

    def sync(self, content, write=False, series='6.18'):
        responses = ['{"object":{"sha":"' + 'b' * 40 + '"}}',
                     'KERNEL_PATCHVER:=' + series + '\n', content]
        with mock.patch.object(kernel, 'fetch', side_effect=responses):
            return kernel.sync(write)

    def test_new_patch_level_update(self):
        self.assertTrue(self.sync(self.content(55), write=True))
        self.assertEqual(self.details.read_text(), self.content(55))

    def test_check_does_not_modify(self):
        self.assertTrue(self.sync(self.content(55)))
        self.assertEqual(self.details.read_text(), self.content(52))

    def test_already_current(self):
        self.assertFalse(self.sync(self.content(52), write=True))

    def test_reject_new_series_and_downgrade(self):
        for content, series in ((self.content(51), '6.18'), (self.content(55), '6.19')):
            with self.subTest(series=series):
                with self.assertRaises(ValueError):
                    self.sync(content, write=True, series=series)
                self.assertEqual(self.details.read_text(), self.content(52))

    def test_reject_same_version_checksum_change(self):
        with self.assertRaises(ValueError):
            self.sync(self.content(52, 'c' * 64), write=True)

    def test_reject_make_code_and_mismatched_checksum_version(self):
        for content in (self.content(55) + 'run := $(shell id)\n',
                        self.content(55).replace('HASH-6.18.55', 'HASH-6.18.54')):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    self.sync(content, write=True)

    def test_all_upstream_files_are_from_one_commit(self):
        calls = []
        responses = iter(['{"object":{"sha":"' + 'b' * 40 + '"}}',
                          'KERNEL_PATCHVER:=6.18\n', self.content(55)])
        def fetch(url):
            calls.append(url)
            return next(responses)
        with mock.patch.object(kernel, 'fetch', side_effect=fetch):
            kernel.sync()
        self.assertTrue(all('/' + 'b' * 40 + '/' in url for url in calls[1:]))


if __name__ == '__main__':
    unittest.main()
