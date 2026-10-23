"""Run the actual UIKit movement methods against synthetic coalesced histories."""
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def method(source, signature):
    """Extract balanced method text so the test executes the current adapter."""
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


@unittest.skipUnless(platform.system() == 'Darwin', 'Foundation adapter fixture requires macOS')
class CoalescedSettingsAdapterTests(unittest.TestCase):
    def test_actual_movement_adapter_rejects_hidden_excursions(self):
        source = (ROOT / 'dm/ios/Sources/DmGamepad.m').read_text()
        fixture = (ROOT / 'dm/ios/tests/t_settings_coalesced.m.in').read_text()
        enum_start = source.index('enum { C_NONE')
        fixture = fixture.replace('/* ADAPTER_ENUM */', source[enum_start:source.index(';', enum_start) + 1])
        fixture = fixture.replace('/* MOVEMENT_HELPER */', method(source, '- (void)checkSettingsMovementForTouch:'))
        fixture = fixture.replace('/* TOUCHES_MOVED */', method(source, '- (void)touchesMoved:'))
        with tempfile.TemporaryDirectory(prefix='smash-coalesced-settings-') as temp:
            path = Path(temp)
            (path / 'adapter.m').write_text(fixture)
            subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fblocks', '-O1', '-g',
                            '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                            '-I', str(ROOT / 'dm/host'), '-framework', 'Foundation',
                            '-framework', 'CoreGraphics', str(path / 'adapter.m'),
                            '-o', str(path / 'adapter')], check=True, capture_output=True, text=True)
            result = subprocess.run([str(path / 'adapter')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('32 checks, 0 failed', result.stdout)


if __name__ == '__main__':
    unittest.main()
