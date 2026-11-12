# Repair mac80211 forward-path compilation on Linux 6.18.63

The updated backports 7.2 package expects `ctx->ieee80211` and
`DEV_PATH_IEEE80211`. The original source and 6.18.63 migration kit omitted
their native kernel companion. This kit adds both upstream patches, including
the prerequisite that passes the context into `dev_fill_forward_path()`, and
updates the legacy xt_FLOWOFFLOAD caller to the same interface.

Stop the failed build. Extract this kit, then pass the existing build root:

```sh
python3 mac80211-forward-path-fix/update.py /home/Debian/ops6.18 --check
python3 mac80211-forward-path-fix/update.py /home/Debian/ops6.18
```

The updater requires Python 3.8+, verifies recognised originals and payload
checksums, and backs up changed files under `.kernel-update-backups/`. It
preserves `.config`, feeds, downloads and compiled toolchains. Existing source
modifications to affected files are reported before any source is changed.
Inside a source checkout, the script is `updates/mac80211-forward-path/update.py`.

Rebuild the changed kernel and its wireless modules together:

```sh
cd /home/Debian/ops6.18
make target/linux/clean
make package/kernel/mac80211/clean
make package/kernel/mt76/clean
make target/linux/prepare -j1 V=s
make target/linux/compile -j2 V=s
make package/kernel/mac80211/compile -j1 V=s
make -j2 V=s
```

Point the updater at the root containing `rules.mk`, not the generated kernel
directory. The normal kernel prepare step applies the new patches. The kernel
remains 6.18.63 and the selected mt76 revision is retained.
