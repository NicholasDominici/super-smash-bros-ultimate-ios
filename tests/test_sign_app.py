"""Check app staging boundaries without certificates, accounts, or game files."""
import datetime
from pathlib import Path
import platform
import plistlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from sign_install import check_app, clone_app, validate_profile, MEMORY, EXTENDED_VA
from stage_app import stage_app


class AppStagingTests(unittest.TestCase):
    def app(self, root):
        app = root / 'Example.app'
        app.mkdir()
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'Example'}))
        (app / 'Example').write_bytes(b'original synthetic executable')
        return app

    def test_executable_cannot_escape_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self.app(Path(directory))
            for name in ['../other', '/tmp/other', '..', 'folder/program']:
                (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': name}))
                with self.assertRaises(ValueError): check_app(app)

    def test_symlink_is_rejected_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.app(root)
            (root / 'outside').write_text('private data')
            (app / 'link').symlink_to(root / 'outside')
            with self.assertRaises(ValueError): check_app(app)

    @unittest.skipUnless(platform.system() == 'Darwin', 'APFS clone staging requires macOS')
    def test_signing_stage_is_independent_of_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.app(root)
            (app / 'resource').write_text('original resource')
            check_app(app)
            staged = root / 'Signed.app'
            clone_app(app, staged)
            (staged / 'resource').write_text('changed in staging')
            (staged / 'Example').chmod(0o700)
            self.assertEqual((app / 'resource').read_text(), 'original resource')
            self.assertEqual((app / 'Example').read_bytes(), b'original synthetic executable')

    def test_required_extended_addressing_cannot_be_silently_dropped(self):
        profile = {'ExpirationDate': datetime.datetime(2099, 1, 1),
                   'TeamIdentifier': ['EXAMPLETEAM'],
                   'Entitlements': {'application-identifier': 'EXAMPLETEAM.com.example.game',
                                    'get-task-allow': True, MEMORY: True}}
        with self.assertRaisesRegex(ValueError, 'Extended Virtual Addressing'):
            validate_profile(profile, 'com.example.game', None, '', True)
        profile['Entitlements'][EXTENDED_VA] = True
        result = validate_profile(profile, 'com.example.game', None, '', True)
        self.assertIs(result[EXTENDED_VA], True)
        self.assertNotIn(EXTENDED_VA, validate_profile(profile, 'com.example.game', None, ''))

    @unittest.skipUnless(platform.system() == 'Darwin', 'APFS clone staging requires macOS')
    def test_resource_staging_preserves_inputs_and_rejects_recursive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = self.app(root)
            (app / 'embedded.mobileprovision').write_text('synthetic stale profile')
            shaders, romfs = root / 'b-synthetic', root / 'RomFS'
            shaders.mkdir()
            romfs.mkdir()
            (shaders / 'synthetic.metallib').write_text('synthetic shader fixture')
            (romfs / 'synthetic.arc').write_text('synthetic resource fixture')
            with self.assertRaises(ValueError):
                stage_app(app, romfs / 'Nested.app', shaders, romfs)
            output = root / 'Unsigned.app'
            stage_app(app, output, shaders, romfs)
            self.assertFalse((output / 'embedded.mobileprovision').exists())
            self.assertTrue((app / 'embedded.mobileprovision').exists())
            self.assertEqual((output / 'msl/b-synthetic/synthetic.metallib').read_text(), 'synthetic shader fixture')
            (output / 'romfs/synthetic.arc').write_text('changed')
            self.assertEqual((romfs / 'synthetic.arc').read_text(), 'synthetic resource fixture')


if __name__ == '__main__':
    unittest.main()
