"""Game-free writer/consumer integration for exact NVN registration captures."""
from pathlib import Path
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('nvn_capture_parser_tests', ROOT / 'dm/gfx/tools/smash_shaders.py')
SHADERS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SHADERS
SPEC.loader.exec_module(SHADERS)


@unittest.skipUnless(platform.system() == 'Darwin', 'CommonCrypto writer requires macOS')
class RegistrationCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='nvn-capture-check-')
        cls.root = Path(cls.temporary.name)
        binary = cls.root / 'capture-tests'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-Wno-deprecated-declarations', str(ROOT / 'dm/host/tests/t_nvn_shader_capture.c'),
                        '-o', str(binary)], check=True, capture_output=True)
        cls.fixture = cls.root / 'original'
        result = subprocess.run([str(binary)], env={**os.environ, 'NVN_CAPTURE_TEST_OUTPUT': str(cls.fixture)},
                                text=True, capture_output=True, check=True)
        if '16 concurrent registrations passed' not in result.stdout:
            raise AssertionError('writer test did not complete')
        cls.keys = {path.stem for path in cls.fixture.glob('*.ctl')}
        cls.rows = [json.loads(line) for line in (cls.fixture / 'registration-census.jsonl').read_text().splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.directory = self.root / self._testMethodName
        shutil.copytree(self.fixture, self.directory)
        self.ledger = self.directory / 'registration-census.jsonl'

    def write_rows(self, rows):
        self.ledger.write_text(''.join(json.dumps(row, separators=(',', ':')) + '\n' for row in rows))

    def reject(self):
        with self.assertRaises(SHADERS.ShaderFormatError):
            SHADERS.validate_registration_census(self.directory, self.keys)

    def test_complete_originals_and_deferred_resolution(self):
        result = SHADERS.validate_registration_census(self.directory, self.keys)
        self.assertEqual(result['events'], 5)
        self.assertEqual(result['totals']['captured_unique'], 1)
        self.assertEqual(result['totals']['duplicates'], 1)
        self.assertEqual(result['totals']['unresolved_deferred'], 0)
        self.assertEqual(len(SHADERS.load_nvn_capture_directory(self.directory)), 1)

    def test_partial_last_line_rejected(self):
        self.ledger.write_bytes(self.ledger.read_bytes()[:-1])
        self.reject()

    def test_unfinished_program_rejected(self):
        self.write_rows(self.rows[:3])
        self.reject()

    def test_unresolved_stage_rejected(self):
        self.write_rows(self.rows[:-1])
        self.reject()

    def test_stage_failure_rejected(self):
        rows = json.loads(json.dumps(self.rows))
        rows[-1]['status'] = 'error'
        self.write_rows(rows)
        self.reject()

    def test_counter_tampering_rejected(self):
        rows = json.loads(json.dumps(self.rows))
        rows[-1]['totals']['captured_unique'] += 1
        self.write_rows(rows)
        self.reject()

    def test_sequence_tampering_rejected(self):
        rows = json.loads(json.dumps(self.rows))
        rows[-1]['seq'] += 1
        self.write_rows(rows)
        self.reject()

    def test_original_byte_tampering_rejected(self):
        code = next(self.directory.glob('*.code'))
        data = bytearray(code.read_bytes()); data[-1] ^= 1; code.write_bytes(data)
        self.reject()

    def test_orphan_original_set_rejected(self):
        with self.assertRaises(SHADERS.ShaderFormatError):
            SHADERS.validate_registration_census(self.directory, self.keys | {'0123456789abcdef'})

    def test_ledger_symlink_rejected(self):
        self.ledger.unlink()
        self.ledger.symlink_to(self.fixture / 'registration-census.jsonl')
        self.reject()

    def test_repeated_json_property_rejected(self):
        data = self.ledger.read_text().replace('"schema":1', '"schema":1,"schema":1', 1)
        self.ledger.write_text(data)
        self.reject()


if __name__ == '__main__':
    unittest.main()
