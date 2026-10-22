"""Synthetic ARM64 instructions cover hoisted jump-table bases and clobbers."""
from pathlib import Path
import sys
import unittest

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dm/tools'))
from a64_tables import table_base


class TableBaseTests(unittest.TestCase):
    def instructions(self, middle=b''):
        # Original synthetic instructions: adrp x9,#0; add x9,x9,#0x80;
        # arbitrary gap; ldrsw x10,[x9,x11,lsl#2]. No game-derived fixture.
        code = bytes.fromhex('0900009029010291') + middle + bytes.fromhex('2a79abb8')
        decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
        decoder.detail = True
        return list(decoder.disasm(code, 0))

    def test_hoisted_beyond_old_window(self):
        instructions = self.instructions(bytes.fromhex('1f2003d5') * 400)
        self.assertEqual(table_base(instructions, len(instructions) - 1, 'x9'), 0x80)

    def test_word_write_clobbers_pointer(self):
        instructions = self.instructions(bytes.fromhex('e903002a'))  # mov w9,w0
        self.assertIsNone(table_base(instructions, len(instructions) - 1, 'x9'))

    def test_other_pointer_producer_is_rejected(self):
        instructions = self.instructions(bytes.fromhex('e90300aa'))  # mov x9,x0
        self.assertIsNone(table_base(instructions, len(instructions) - 1, 'x9'))

    def test_unrelated_write_does_not_clobber(self):
        instructions = self.instructions(bytes.fromhex('e80300aa'))  # mov x8,x0
        self.assertEqual(table_base(instructions, len(instructions) - 1, 'x9'), 0x80)

    def test_preserved_copy_survives_original_register_reuse(self):
        # mov x30,x9; mov x9,x0; mov x9,x30. Capstone names x30 "lr"
        # in its register-access metadata, so both aliases must be tracked.
        instructions = self.instructions(bytes.fromhex('fe0309aae90300aae9031eaa'))
        self.assertEqual(table_base(instructions, len(instructions) - 1, 'x9'), 0x80)

    def test_clobbered_preserved_copy_is_rejected(self):
        instructions = self.instructions(bytes.fromhex('fe0309aafe0300aae9031eaa'))
        self.assertIsNone(table_base(instructions, len(instructions) - 1, 'x9'))


if __name__ == '__main__':
    unittest.main()
