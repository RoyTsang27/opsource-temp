"""Exercise feed preparation and resolve generated package menus with real Kconfig."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_feeds', ROOT / 'scripts/prepare-feeds.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PrepareFeedsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'scripts').mkdir()
        for name in ('feeds', 'prepare-feeds.py', 'apply-feed-patches.py'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        self.commands = []
        self.feeds = [['example', 'src-link', 'local', '/custom/source']]
        (self.root / '.config').write_text('CONFIG_PACKAGE_my-choice=y\n')

    def runner(self, root, *arguments, capture=False):
        self.commands.append(arguments)
        if arguments[0] == 'update':
            if getattr(self, 'fail_index', False):
                raise subprocess.CalledProcessError(1, arguments)
            (root / 'feeds/example').mkdir(parents=True, exist_ok=True)
            (root / 'feeds/example/Makefile').write_text('# recipe\n')
            for suffix in ('.index', '.targetindex'):
                (root / 'feeds' / ('example' + suffix)).write_text('metadata\n')
        elif arguments[0] == 'install':
            directory = root / 'package/feeds/example'
            directory.mkdir(parents=True, exist_ok=True)
            if not (directory / 'utility').is_symlink():
                (directory / 'utility').symlink_to(root / 'feeds/example', target_is_directory=True)

    def prepare(self):
        with patch.object(prepare, 'configured_feeds', return_value=self.feeds), \
                patch.object(prepare, 'run', side_effect=self.runner):
            prepare.prepare(self.root)

    def test_first_menu_installs_catalog_and_next_menu_is_offline(self):
        self.prepare()
        self.assertEqual(self.commands, [('update', 'example'), ('install', '-a')])
        self.assertEqual((self.root / '.config').read_text(), 'CONFIG_PACKAGE_my-choice=y\n')
        self.commands.clear()
        self.prepare()
        self.assertEqual(self.commands, [])

    def test_recipe_or_patch_changes_reindex_without_fetching(self):
        self.prepare()
        (self.root / 'feeds/example/Makefile').write_text('# edited local recipe\n')
        self.commands.clear()
        self.prepare()
        self.assertEqual(self.commands, [('update', '-i', 'example'), ('install', '-a')])
        patches = self.root / 'config/feeds-patches/example'
        patches.mkdir(parents=True)
        (patches / '001.patch').write_text('updated patch\n')
        self.commands.clear()
        self.prepare()
        self.assertEqual(self.commands, [('update', '-i', 'example'), ('install', '-a')])

    def test_uninstalled_package_is_restored(self):
        self.prepare()
        (self.root / 'package/feeds/example/utility').unlink()
        self.commands.clear()
        self.prepare()
        self.assertIn(('install', '-a'), self.commands)

    def test_failed_feed_index_never_installs_an_incomplete_catalog(self):
        self.fail_index = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepare()
        self.assertNotIn(('install', '-a'), self.commands)
        self.assertFalse((self.root / 'tmp/.feeds-ready.json').exists())


class FeedIndexTests(unittest.TestCase):
    def test_make_failures_are_propagated_before_publishing_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'feeds/example').mkdir(parents=True)
            (root / 'feeds.conf').write_text('src-link example /unused\n')
            (root / 'bin').mkdir()
            make = root / 'bin/gmake'
            make.write_text('#!/bin/sh\n'
                            'case "$*" in *-v*) echo "GNU Make 4.4"; exit 0;; esac\n'
                            'case "$*" in *"$FAIL_PHASE"*) exit 1;; esac\n'
                            'exit 0\n')
            make.chmod(0o755)
            for phase in ('prepare-mk', 'SCAN_TARGET=packageinfo', 'SCAN_TARGET=targetinfo'):
                with self.subTest(phase=phase):
                    environment = dict(os.environ, TOPDIR=str(root), FAIL_PHASE=phase,
                                       PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'])
                    result = subprocess.run([str(ROOT / 'scripts/feeds'), 'update', '-i', 'example'],
                                            env=environment, capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse((root / 'feeds/example.index').is_symlink())


class PackageMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        sources = cls.root / 'config-tool'
        shutil.copytree(ROOT / 'scripts/config', sources,
                        ignore=shutil.ignore_patterns('*.o', 'conf', 'mconf', 'nconf', 'qconf'))
        subprocess.run(['make', '-C', str(sources), 'conf'], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.conf = sources / 'conf'

    def resolve(self, preset, alternatives=1):
        root = Path(tempfile.mkdtemp(dir=self.root))
        (root / 'package/base').mkdir(parents=True)
        (root / 'package/base/image-config.in').touch()
        metadata = ('Source-Makefile: package/default/Makefile\nPackage: default-provider\n'
                    'Title: Default provider\nCategory: Libraries\nProvides: virtual-api\n'
                    'Default-Variant: 1\nDepends: @FEATURE\nDescription: Default fixture\n@@\n\n'
                    'Source-Makefile: package/consumer/Makefile\nPackage: consumer\n'
                    'Title: Consumer\nCategory: Utilities\nDepends: +virtual-api\nDescription: Consumer fixture\n@@\n\n')
        for index in range(alternatives):
            metadata += (f'Source-Makefile: package/alt{index}/Makefile\nPackage: alt{index}\n'
                         'Title: Alternative provider\nCategory: Libraries\nProvides: virtual-api\n'
                         'Description: Alternative fixture\n@@\n\n')
        (root / 'packages.info').write_text(metadata)
        menu = subprocess.check_output([str(ROOT / 'scripts/package-metadata.pl'), 'config',
                                        'packages.info'], cwd=root, text=True)
        (root / 'packages.in').write_text(menu)
        (root / 'Kconfig').write_text('mainmenu "Package menu test"\n'
                                     'config MODULES\n\tmodules\n\tbool\n\tdefault y\n'
                                     'config FEATURE\n\tbool "Default provider feature"\n'
                                     'source "packages.in"\n')
        (root / 'preset').write_text(preset)
        result = subprocess.run([str(self.conf), '--fatalrecursive', '--defconfig=preset', 'Kconfig'],
                                cwd=root, env=dict(os.environ, KCONFIG_CONFIG=str(root / '.config')),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('menu "Utilities"', menu)
        return set((root / '.config').read_text().splitlines())

    def test_alternative_provider_keeps_consumer_selectable(self):
        for alternatives in (1, 2):
            with self.subTest(alternatives=alternatives):
                settings = self.resolve('CONFIG_PACKAGE_consumer=y\nCONFIG_PACKAGE_alt0=y\n', alternatives)
                self.assertIn('CONFIG_PACKAGE_consumer=y', settings)
                self.assertIn('CONFIG_PACKAGE_alt0=y', settings)
                self.assertNotIn('CONFIG_PACKAGE_default-provider=y', settings)

    def test_default_provider_requires_its_feature_and_is_selected(self):
        settings = self.resolve('CONFIG_FEATURE=y\nCONFIG_PACKAGE_consumer=y\n')
        self.assertIn('CONFIG_PACKAGE_consumer=y', settings)
        self.assertIn('CONFIG_PACKAGE_default-provider=y', settings)

    def test_consumer_stays_disabled_when_no_provider_can_work(self):
        settings = self.resolve('CONFIG_PACKAGE_consumer=y\n')
        self.assertNotIn('CONFIG_PACKAGE_consumer=y', settings)


if __name__ == '__main__':
    unittest.main()
