"""Game-free checks for the atomic, exact-build sparse-arena compatibility cut."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dm/tools'))
sys.path.insert(0, str(ROOT / 'tools'))
import smash_address_space as arena
import smash


class AddressSpaceTests(unittest.TestCase):
    def fixture(self):
        # Zero-filled synthetic storage contains instruction facts from the
        # source gate table, never an extracted executable or other game data.
        image = bytearray(max(offset for offset, *_ in arena.CUTS) + 4)
        for offset, word in [(offset, old) for offset, old, _, _ in arena.CUTS] + list(arena.CONSTITUENTS):
            struct.pack_into('<I', image, offset, word)
        struct.pack_into('<I', image, arena.UNRELATED_MASK_SITE, arena.UNRELATED_MASK_WORD)
        nso = b'NSO0' + bytes(0x3C) + bytes.fromhex(arena.MAIN_BUILD)
        return nso, image

    def admitted_fixture_hash(self):
        # Production always hashes the actual full original NSO. Only synthetic
        # unit fixtures replace that digest to reach the instruction gates.
        return mock.patch.object(arena.hashlib, 'sha256', return_value=SimpleNamespace(hexdigest=lambda: arena.MAIN_SHA256))

    def test_original_and_ipad_layouts_keep_metadata_and_units(self):
        old, new = arena.arena_layout(arena.ORIGINAL_ARENA), arena.arena_layout(arena.IPAD_ARENA)
        self.assertEqual(old['metadata_offset'], 0xF7F200000)
        self.assertEqual(old['initial_node_cursor'], 0xF7F20FFF0)
        self.assertEqual(old['free_page_units'], 0xF7F20)
        self.assertEqual(new['metadata_offset'], 0x77F200000)
        self.assertEqual(new['initial_node_cursor'], 0x77F20FFF0)
        self.assertEqual(new['free_page_units'], 0x77F20)
        self.assertEqual(new['metadata_bytes'], old['metadata_bytes'])
        self.assertEqual(new['free_page_units'] * 65536 + new['metadata_bytes'], arena.IPAD_ARENA)
        for invalid in (0, arena.METADATA_BYTES, arena.IPAD_ARENA + 1, (1 << 32) * 65536 + arena.METADATA_BYTES):
            with self.assertRaises(ValueError):
                arena.arena_layout(invalid)

    def test_group_changes_exactly_eight_words_and_keeps_unrelated_mask(self):
        nso, image = self.fixture()
        with self.admitted_fixture_hash() as digest:
            cuts = arena.apply_original(nso, image, 'main')
        digest.assert_called_once_with(nso)
        self.assertEqual(len(cuts), 8)
        for offset, _, replacement, _ in arena.CUTS:
            self.assertEqual(struct.unpack_from('<I', image, offset)[0], replacement)
        for offset, expected in arena.CONSTITUENTS + ((arena.UNRELATED_MASK_SITE, arena.UNRELATED_MASK_WORD),):
            self.assertEqual(struct.unpack_from('<I', image, offset)[0], expected)

    def test_each_changed_and_constituent_gate_is_atomic(self):
        nso, image = self.fixture()
        real_sha = hashlib.sha256
        for offset in [row[0] for row in arena.CUTS] + [row[0] for row in arena.CONSTITUENTS]:
            image[offset] ^= 1
            before = real_sha(image).digest()
            with self.admitted_fixture_hash(), self.assertRaisesRegex(ValueError, 'instruction mismatch'):
                arena.apply_original(nso, image, 'main')
            self.assertEqual(real_sha(image).digest(), before)
            image[offset] ^= 1

    def test_same_build_wrong_original_hash_rejected_and_other_titles_unchanged(self):
        nso, image = self.fixture()
        before = hashlib.sha256(image).digest()
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            arena.apply_original(nso, image, 'main')
        self.assertEqual(hashlib.sha256(image).digest(), before)
        self.assertEqual(arena.apply_original(nso[:0x40] + bytes(16), image, 'main'), [])
        self.assertEqual(arena.apply_original(nso, image, 'sdk'), [])
        self.assertEqual(hashlib.sha256(image).digest(), before)

    def test_reuse_rejects_old_or_partial_arena_and_accepts_complete_cut(self):
        nso, image = self.fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            binary = path / 'main.patched.bin'
            binary.write_bytes(image)
            (path / 'main.cuts.tsv').write_text('# synthetic\n')
            with self.assertRaisesRegex(ValueError, 'old 62 GiB caches.*Omit --rewritten'):
                arena.check_rewritten(path)
            # The human builder's reuse gate runs the same check before build.
            (path / 'main.obs.tsv').write_text('# synthetic\n')
            with mock.patch.object(smash, 'MODULES', {}), mock.patch.object(smash, 'GUARD_SITES', {}), mock.patch('smash_nro.catalog_names', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'old 62 GiB caches'):
                    smash.verify_rewritten(path, path, {})
            with self.admitted_fixture_hash():
                cuts = arena.apply_original(nso, image, 'main')
            binary.write_bytes(image)
            (path / 'main.cuts.tsv').write_text(''.join(f'{offset:#x}\t{old}\t{new}\t{why}\n' for offset, old, new, why in cuts))
            arena.check_rewritten(path)
            (path / 'main.cuts.tsv').write_text('')
            with self.assertRaisesRegex(ValueError, 'cut receipt'):
                arena.check_rewritten(path)


if __name__ == '__main__':
    unittest.main()
