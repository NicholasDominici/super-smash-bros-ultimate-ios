"""Only real AAPCS call boundaries admit scratch-register observation gates."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dm/tools'))
from a64_observers import is_call


class ObserverCallTests(unittest.TestCase):
    def test_direct_and_indirect_calls(self):
        for word in (0x94000000, 0x97ffffff, 0xd63f0000, 0xd63f0100, 0xd63f03c0):
            self.assertTrue(is_call(word), hex(word))

    def test_non_call_branches_and_plain_instructions(self):
        for word in (0x14000000, 0xd61f0100, 0xd65f03c0, 0x54000000, 0xb4000000, 0xd503201f, 0xf9407660):
            self.assertFalse(is_call(word), hex(word))


if __name__ == '__main__':
    unittest.main()
