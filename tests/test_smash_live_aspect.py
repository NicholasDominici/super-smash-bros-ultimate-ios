"""Synthetic reflow plans preserve authored content and reject stale inputs."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

import test_smash_aspect_ui as fixtures

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dm/tools'))
import smash_live_aspect as live
from a64_observers import require_full_state_gate


class LiveAspectPlanTests(unittest.TestCase):
    def setUp(self):
        ui = fixtures.ui
        children = [fixtures.pane(name, pos=(10, 400, 0), size=(100, 40))
                    for name in ui._EDGE_GROUPS['info_melee']]
        children += [fixtures.pane('bg', b'pic1'),
                     fixtures.pane('portrait', b'pic1', size=(100, 80)),
                     fixtures.pane('label', b'txt1', size=(200, 40))]
        anim = fixtures.animation([('time', 1, [(0, 400, 2.5), (10, 420, -3.25)]),
                                   ('bg', 9, [(0, 1080, 12), (10, 1200, -6)])])
        self.original = fixtures.resource('info_melee.bflyt', fixtures.layout('info_melee', children),
                                         ('anim/info_melee_in.bflan', anim))
        self.key = '0000000001'
        self.admission = mock.patch.dict(ui._PROFILES, {self.key:
            (hashlib.sha256(self.original).hexdigest(), len(self.original), 'info_melee.bflyt')})
        self.admission.start()
        self.addCleanup(self.admission.stop)
        self.prepared, self.receipt = ui.transform_sarc(self.original, self.key)

    def test_endpoints_are_byte_exact_and_input_never_changes(self):
        before = hashlib.sha256(self.prepared).hexdigest()
        self.assertEqual(live.retarget(self.prepared, self.receipt, 4 / 3)[0], self.prepared)
        self.assertEqual(live.retarget(self.prepared, self.receipt, 16 / 9)[0], self.original)
        self.assertEqual(hashlib.sha256(self.prepared).hexdigest(), before)

    def test_duo_ratio_reflows_edges_and_fill_without_scaling_text_or_icons(self):
        ratio = 678 / 466
        target, fields = live.retarget(self.prepared, self.receipt, ratio)
        parsed = fixtures.ui._layout(fixtures.payload(target, 'blyt/info_melee.bflyt'))
        height = 1920 / ratio
        self.assertAlmostEqual(parsed.canvas[1], height, places=3)
        self.assertAlmostEqual(parsed.panes['bg'].size[1], height, places=3)
        for name, delta in fixtures.ui._EDGE_GROUPS['info_melee'].items():
            self.assertAlmostEqual(parsed.panes[name].position[1], 400 + delta * (height - 1080) / 360, places=3)
        self.assertEqual(parsed.panes['portrait'].size, (100, 80))
        self.assertEqual(parsed.panes['label'].size, (200, 40))
        self.assertEqual(fixtures.payload(target, 'timg/synthetic.bin'), bytes(range(64)))
        self.assertTrue(fields)

    def test_animated_position_slopes_preserved_and_fill_slopes_retargeted(self):
        ratio = 951 / 669
        target, _ = live.retarget(self.prepared, self.receipt, ratio)
        anim = fixtures.payload(target, 'anim/info_melee_in.bflan')
        for pane, channel, _, count, start, _ in fixtures.ui._tracks(anim):
            slope = struct.unpack_from('<f', anim, start + 8)[0]
            self.assertAlmostEqual(slope, 2.5 if pane == 'time' else 12 * live.target_factor(ratio), places=4)

    def test_repeated_fold_plans_are_identical_and_double_apply_rejected(self):
        a = live.retarget(self.prepared, self.receipt, 678 / 466)[0]
        b = live.retarget(self.prepared, self.receipt, 951 / 669)[0]
        self.assertNotEqual(a, b)
        for _ in range(50):
            self.assertEqual(live.retarget(self.prepared, self.receipt, 678 / 466)[0], a)
            self.assertEqual(live.retarget(self.prepared, self.receipt, 951 / 669)[0], b)
        with self.assertRaisesRegex(ValueError, 'identity'):
            live.retarget(a, self.receipt, 951 / 669)

    def test_tampered_receipts_wrong_owner_and_nonfinite_ratios_fail_closed(self):
        for value in (0, -1, .5, 5, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                live.retarget(self.prepared, self.receipt, value)
        for field, value in [('pane', 'other'), ('policy', 'unscoped'), ('offset', 1 << 30)]:
            receipt = copy.deepcopy(self.receipt)
            receipt['changes'][0][field] = value
            with self.assertRaises(ValueError):
                live.retarget(self.prepared, receipt, 678 / 466)
        receipt = copy.deepcopy(self.receipt)
        receipt['changes'].append(receipt['changes'][0])
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            live.retarget(self.prepared, receipt, 678 / 466)

    def test_all_receiving_code_facts_and_original_identity_are_required(self):
        with self.assertRaises(ValueError):
            live.admit_image(bytes(80), bytes(80))
        image = bytearray(max(offset for offset, _ in live.LIVE_FACTS) + 4)
        for offset, word in live.LIVE_FACTS:
            struct.pack_into('<I', image, offset, word)
        with mock.patch.object(live.preparation, '_identity'):
            live.admit_image(b'synthetic original', image)
            for offset, word in live.LIVE_FACTS:
                struct.pack_into('<I', image, offset, word ^ 1)
                with self.assertRaisesRegex(ValueError, 'word mismatch'):
                    live.admit_image(b'synthetic original', image)
                self.assertEqual(struct.unpack_from('<I', image, offset)[0], word ^ 1)
                struct.pack_into('<I', image, offset, word)
            with self.assertRaises(ValueError):
                live.admit_image(b'synthetic original', image[:64])

    def test_calculate_plan_keeps_drawself_sizes_and_game_animation_values_owned(self):
        ratio = 678 / 466
        plan = live.calculate_plan(self.prepared, self.receipt, ratio)
        fill = [p for p in plan if p['pane'] == 'bg']
        self.assertEqual([p['operation'] for p in fill], ['geometry_growth_y'])
        self.assertAlmostEqual(1440 * fill[0]['value'], 1920 / ratio, places=3)
        self.assertFalse(any(p['pane'] in ['portrait', 'label'] for p in plan))
        roots = [p for p in plan if p['operation'] == 'private_parent_canvas_height']
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]['kind'], 'pan1')
        edge = next(p for p in plan if p['pane'] == 'time')
        # A game-authored animation value at the moment of Calculate remains
        # the base. The plan supplies an additive offset, not a static position.
        self.assertEqual(edge['operation'], 'add_local_position_y')
        expected_delta = fixtures.ui._EDGE_GROUPS['info_melee']['time'] * ((1920 / ratio) - 1440) / 360
        self.assertAlmostEqual(731.25 + edge['value'], 731.25 + expected_delta, places=3)

    def test_rotated_fill_calculate_plan_is_uniform_and_origin_aware(self):
        raw = fixtures.resource('test.bflyt', fixtures.layout('test', [
            fixtures.pane('bg', b'pic1', rotation=(0, 0, 90), origin=4, pos=(0, 540, 0))]))
        with mock.patch.dict(fixtures.ui._PROFILES, {self.key:
                (hashlib.sha256(raw).hexdigest(), len(raw), 'test.bflyt')}):
            prepared, receipt = fixtures.ui.transform_sarc(raw, self.key)
            plan = live.calculate_plan(prepared, receipt, 951 / 669)
        scales = [p['value'] for p in plan if p['operation'].startswith('geometry_growth')]
        self.assertEqual(len(scales), 2)
        self.assertAlmostEqual(scales[0], scales[1], places=6)
        self.assertTrue(any(p['operation'].startswith('add_local_position') for p in plan))

    def test_runtime_rules_scope_primary_members_and_preserve_descendant_geometry(self):
        rule = live.runtime_layout_rule(self.prepared, self.receipt)
        panes = {pane['name']: pane for pane in rule['panes']}
        self.assertEqual(rule['name'], 'info_melee')
        self.assertEqual((rule['width'], rule['height']), (1920, 1440))
        self.assertEqual(panes['bg']['grow_y'], 1)
        self.assertEqual(panes['label']['grow_y'], 0)
        self.assertEqual(panes['RootPane']['grow_y'], 0)
        self.assertEqual(panes['time']['offset_y'], 4 * fixtures.ui._EDGE_GROUPS['info_melee']['time'])
        self.assertEqual(panes['time']['parent'], 'RootPane')
        header = live.emit_runtime_header([rule])
        self.assertIn('dm_smash_ui_layout_rule smash_ui_layouts[]', header)
        self.assertIn('"RootPane",NULL,', header)
        self.assertNotIn('temporary_root_height', header)


class LiveObservationProtocolTests(unittest.TestCase):
    """Synthetic FAR modules check the actual entry/stub/return admission."""
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='smash-observer-fixture-')
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.patch = -0x2000000
        self.file_size = 0x3800000
        self.image = bytearray(self.file_size + 512)
        for site, word in live.LIVE_FACTS:
            self.put(site, word)
        self.observers, self.gates = [], []
        for index, (site, number, original) in enumerate(live.LIVE_OBSERVERS):
            stub = self.patch + index * 64
            ret = stub + 24
            self.put(site, self.branch(site, stub))
            self.put(ret, 0xa8c17bfd)
            self.put(ret + 4, original)
            self.put(ret + 8, self.branch(ret + 8, site + 4))
            self.observers.append(f'{site:#x}\t{number}\t{original:08x}\n')
            self.gates.append(f'{ret:#x}\tobs\t{number}\t{site:#x}\n')
        (self.root/'main.fixups.tsv').write_text(
            f'# PATCH_OFF\t{self.patch:#x}\n# FILE_IMAGE_LEN\t{self.file_size:#x}\n')
        self.admission = mock.patch.object(live.preparation, 'check_rewritten')
        self.admission.start(); self.addCleanup(self.admission.stop)

    def put(self, address, word):
        offset = address if address >= 0 else self.file_size + address - self.patch
        struct.pack_into('<I', self.image, offset, word)

    @staticmethod
    def branch(address, target):
        assert -(1 << 27) <= target - address < 1 << 27
        return 0x14000000 | (((target - address) // 4) & 0x3ffffff)

    def verify(self):
        (self.root/'main.patched.bin').write_bytes(self.image)
        (self.root/'main.obs.tsv').write_text(''.join(self.observers))
        (self.root/'main.gates.tsv').write_text(''.join(self.gates))
        live.verify_live_rewritten(self.root)

    def test_negative_patch_offsets_and_all_five_observers_are_admitted(self):
        self.verify()
        live.preparation.check_rewritten.assert_called_once_with(self.root)

    def test_missing_or_duplicate_observer_and_registration_are_rejected(self):
        for collection in (self.observers, self.gates):
            original = collection[:]
            for changed in (original[:-1], original + original[:1]):
                collection[:] = changed
                with self.assertRaises(ValueError):
                    self.verify()
            collection[:] = original

    def test_entry_restore_original_and_return_corruption_are_rejected(self):
        site, _, _ = live.LIVE_OBSERVERS[1]
        ret = self.patch + 64 + 24
        for address in (site, ret, ret + 4, ret + 8):
            offset = address if address >= 0 else self.file_size + address - self.patch
            original = struct.unpack_from('<I', self.image, offset)[0]
            self.put(address, 0xd503201f)
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.verify()
            self.put(address, original)

    def test_adjacent_receiving_instruction_cannot_drift(self):
        self.put(0x4b660, 0xd503201f)
        with self.assertRaisesRegex(ValueError, 'adjacent fact'):
            self.verify()

    def test_internal_observer_requires_production_full_register_frame(self):
        source=(Path(__file__).resolve().parents[1]/'dm/host/entry.S').read_text()
        require_full_state_gate(source)
        body=source.split('_dm_gate:',1)[1].split('// 3)',1)[0]
        for line in body.splitlines():
            instruction=line.strip().split('//',1)[0].strip()
            if instruction.startswith(('stp ', 'ldp ', 'str ', 'ldr ', 'mrs ', 'msr ', 'sub sp', 'add sp')):
                with self.subTest(instruction=instruction),self.assertRaises(ValueError):
                    require_full_state_gate(source.replace(line,'',1))


if __name__ == '__main__':
    unittest.main()
