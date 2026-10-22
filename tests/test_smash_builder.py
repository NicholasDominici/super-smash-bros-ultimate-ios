"""Player workflow safety checks with synthetic metadata and fake Metal files."""
from pathlib import Path
import hashlib
import json
import datetime
import plistlib
import os
import signal
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'dm/ios/tools'))
sys.path.insert(0, str(ROOT / 'dm/gfx/tools'))
import smash
import ios_metal


class SmashBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.chain = '123456789abc'
        self.profile = self.root / 'profile'
        self.profile.mkdir()
        self.mac = self.root / 'mac' / ('b-' + self.chain)
        self.ios = self.root / 'ios' / ('b-' + self.chain)
        self.mac.mkdir(parents=True)
        self.ios.mkdir(parents=True)
        self.manifest = self.mac / '_b_build.json'
        self.key = '123456789abcdef0'
        self.rows = [{'key': self.key, 'st': 'ok', 'err': ''}]
        self.map_line = f'vs_fixture.bin\t0\tvertex\t{self.key}\tsynthetic vertex\n'
        self.write_map()
        self.manifest.write_text(json.dumps(self.rows))
        for directory, record in ((self.mac, 'xcrun -sdk macosx metal -c -fpreserve-invariance; xcrun -sdk macosx metallib'), (self.ios, ios_metal.RECORD)):
            data = {'key': self.key + '_b', 'dm_ctl': self.key, 'route': 'B', 'chain': self.chain,
                    'stage': 'vs', 'chain_metal': record, 'bindings': [], 'drv_unfillable': []}
            (directory / (self.key + '_b.json')).write_text(json.dumps(data))
            self.library(directory / (self.key + '_b.metallib'))
        (self.mac / (self.key + '_b.metal')).write_text('// synthetic shader source\n')
        self.minimum = mock.patch.object(smash, 'MIN_SHADER_KEYS', 1)
        self.minimum.start()
        self.addCleanup(self.minimum.stop)

    def write_map(self):
        (self.profile / 'shader_map.tsv').write_text('package\tindex\tstage\tdm_ctl_sha16\tsource\n' + self.map_line)

    def library(self, path):
        data = bytearray(64)
        data[:4] = b'MTLB'
        struct.pack_into('<Q', data, 16, len(data))
        path.write_bytes(data)

    def check(self, allow=False):
        return smash.validate_shaders(self.profile, self.ios.parent, self.manifest, self.chain, allow)

    def reflection(self, directory, change):
        path = directory / (self.key + '_b.json')
        data = json.loads(path.read_text())
        data.update(change)
        path.write_text(json.dumps(data))

    def test_complete_corpus_requires_both_platforms(self):
        self.assertEqual(self.check()['compiled'], 1)
        (self.ios / (self.key + '_b.metallib')).unlink()
        with self.assertRaisesRegex(ValueError, 'sets'):
            self.check()

    def test_zero_exit_manifest_is_not_success(self):
        for rows in ([], self.rows * 2, [{'key': 'eeeeeeeeeeeeeeee', 'st': 'ok'}], [{'key': self.key, 'st': 'translation failed'}]):
            with self.subTest(rows=rows):
                self.manifest.write_text(json.dumps(rows))
                with self.assertRaises(ValueError):
                    self.check(True)

    def test_map_census_duplicate_and_unsupported_stage_fail(self):
        for text in (self.map_line * 2, self.map_line.replace('vertex', 'unsupported'), ''):
            (self.profile / 'shader_map.tsv').write_text(text)
            with self.assertRaises(ValueError):
                self.check()

    def test_stale_chain_platform_and_stage_fail(self):
        for change in ({'chain': 'old'}, {'chain_metal': 'mac only'}, {'stage': 'ps'}, {'dm_ctl': 'other'}, {'route': 'A'}):
            with self.subTest(change=change):
                original = (self.ios / (self.key + '_b.json')).read_bytes()
                self.reflection(self.ios, change)
                with self.assertRaisesRegex(ValueError, 'identity'):
                    self.check()
                (self.ios / (self.key + '_b.json')).write_bytes(original)

    def test_library_length_and_magic_are_validated(self):
        path = self.ios / (self.key + '_b.metallib')
        for data in (b'MTLB', b'wrong' * 30, path.read_bytes()[:-1]):
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'Metal library'):
                self.check()

    def test_fetch_variants_must_match_reflections(self):
        self.reflection(self.ios, {'fetch': {'calls': [{'fc': 0}]}})
        with self.assertRaises(ValueError):
            self.check()
        self.library(self.ios / (self.key + '_bf.metallib'))
        self.check()
        self.library(self.ios / 'eeeeeeeeeeeeeeee_bf.metallib')
        with self.assertRaisesRegex(ValueError, 'fetch'):
            self.check()

    def test_unknown_unfillable_or_undecoded_bindings_fail(self):
        for change in ({'drv_unfillable': ['unknown']}, {'bindings': [{'kind': '?'}]},
                       {'bindings': [{'kind': 'tex', 'reg': None}]}, {'bindings': [{'kind': 'cbuf', 'reg': -1}]},
                       {'bindings': [{}]}, {'bindings': None}):
            with self.subTest(change=change):
                original = (self.ios / (self.key + '_b.json')).read_bytes()
                self.reflection(self.ios, change)
                with self.assertRaisesRegex(ValueError, 'binding'):
                    self.check()
                (self.ios / (self.key + '_b.json')).write_bytes(original)

    def test_guard_tables_cannot_be_derived_from_missing_mac_msl(self):
        (self.mac / (self.key + '_b.metal')).unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_geometry_exception_is_exact_and_explicit(self):
        key = smash.KNOWN_GEOMETRY
        self.map_line += f'gs_fixture.bin\t0\tgeometry\t{key}\t/data.arc/37d50839a8.nushdb#NUSHDB#CharacterDamageModel2GS\n'
        self.write_map()
        self.manifest.write_text(json.dumps(self.rows + [{'key': key, 'st': 'metal failed', 'err': 'synthetic'}]))
        with self.assertRaisesRegex(ValueError, 'failed'):
            self.check()
        self.assertEqual(self.check(True)['known_geometry_gap'], [key])
        self.map_line = self.map_line.replace('CharacterDamageModel2GS', 'another shader')
        self.write_map()
        with self.assertRaisesRegex(ValueError, 'failed'):
            self.check(True)

    def test_truncated_or_wrong_original_nso_is_rejected(self):
        source = self.root / 'game'
        (source / 'ExeFS').mkdir(parents=True)
        (source / 'ExeFS/main').write_bytes(b'synthetic wrong executable')
        with self.assertRaisesRegex(ValueError, '13.0.5'):
            smash.verify_extraction(source)

    def test_hidden_nrr_directory_is_not_a_registration_file(self):
        source = self.root / 'merged'
        (source / 'ExeFS').mkdir(parents=True)
        nrrs = source / 'RomFS/.nrr'
        nrrs.mkdir(parents=True)
        (source / 'RomFS/data.arc').write_bytes(bytes.fromhex('1032547698efcdab') + bytes(64))
        modules = {}
        for index, name in enumerate(('main', 'subsdk0', 'sdk')):
            blob = bytearray(0x80)
            blob[:4] = b'NSO0'
            blob[0x40:0x50] = bytes([index + 1]) * 16
            (source / 'ExeFS' / name).write_bytes(blob)
            modules[name] = (hashlib.sha256(blob).hexdigest(), bytes(blob[0x40:0x50]).hex())
        for index in range(14):
            (nrrs / f'fixture-{index}.nrr').write_bytes(b'synthetic registration ' + bytes([index]))
        (nrrs / 'directory.nrr').mkdir()
        with mock.patch.object(smash, 'MODULES', modules), mock.patch('smash_nro.parse_nrr') as parse:
            record = smash.verify_extraction(source)
            self.assertEqual(len(record['nrr_sha256']), 14)
            self.assertEqual(parse.call_count, 14)

    def test_source_symlink_escape_and_old_work_rejected(self):
        link = self.root / 'checkout'
        link.symlink_to(ROOT)
        with self.assertRaises(ValueError):
            smash.outside(link / 'game-files')
        with self.assertRaisesRegex(ValueError, 'new directory'):
            smash.main(['--extracted-dir', str(self.root / 'game'), '--work', str(self.root), '--bundle-id', 'com.example.smash'])

    def test_cli_options_reject_ambiguous_inputs_and_cache_half_pairs(self):
        common = ['--extracted-dir', str(self.root / 'game'), '--work', str(self.root / 'new'), '--bundle-id', 'com.example.smash']
        for tail in (['--update', str(self.root / 'update.nsp')], ['--shaders', str(self.root / 'ios')], ['--jobs', '0'],
                     ['--capture-seconds', '0'], ['--capture-seconds', '601']):
            with self.assertRaises(ValueError):
                smash.main(common + tail)
        with self.assertRaisesRegex(ValueError, 'requires'):
            smash.main(['--base', str(self.root / 'base.xci'), '--work', str(self.root / 'new'), '--bundle-id', 'com.example.smash'])

    def test_capture_defaults_attempt_a_match_within_the_bounded_timeout(self):
        args = smash.parse_args(['--extracted-dir', '/private/fixture', '--work', '/private/new-build', '--bundle-id', 'com.example.smash', '--capture-runtime'])
        self.assertEqual((args.capture_route, args.capture_seconds), ('match', 105))
        script = smash.CAPTURE_ROUTES[args.capture_route]
        initial = ','.join(f'{second}:A' for second in range(5, 45, 3))
        self.assertEqual(len(initial.split(',')), 14)
        self.assertTrue(script.startswith(initial + ',50:LUp~0.45,51:LLeft~0.35,52:A,55:Plus,58:A,62:A'))
        actions = [(float(step.split(':')[0]), step.split(':')[1]) for step in script.split(',')]
        self.assertTrue(any(second >= 70 and action.startswith('A*') for second, action in actions))
        self.assertLess(max(second for second, _ in actions), args.capture_seconds)
        self.assertEqual(smash.CAPTURE_ROUTES['menus'], smash.MENU_CAPTURE_SCRIPT)
        menus = smash.parse_args(['--extracted-dir', '/private/fixture', '--work', '/private/new-build', '--bundle-id', 'com.example.smash',
                                  '--capture-runtime', '--capture-route', 'menus'])
        self.assertEqual(menus.capture_seconds, 32)

    def test_capture_environment_cannot_inherit_real_progress_or_watchdogs(self):
        with mock.patch.dict(os.environ, {'DM_SAVE': '/private/real-progress', 'DM_TEMP': '/private/real-temp', 'DM_KEYS': 'unsafe',
                                         'DM_WATCH': '1', 'DM_NVN_SHDUMP_REGISTER': '0', 'API_TOKEN': 'private', 'PATH': '/usr/bin:/bin'}, clear=True):
            env = smash.capture_runtime_environment(self.root / 'source', self.profile, self.mac.parent,
                                                    self.root / 'capture', self.root / 'disposable', 'match')
        self.assertEqual(env['DM_SAVE'], str(self.root / 'disposable/save'))
        self.assertEqual(env['DM_TEMP'], str(self.root / 'disposable/temp'))
        self.assertEqual(env['DM_NVN_SHMAP'], str(self.profile / 'shader_map.tsv'))
        self.assertEqual(env['DM_KEYS'], smash.MATCH_CAPTURE_SCRIPT)
        self.assertEqual(env['DM_NVN_SHDUMP_REGISTER'], '1')
        self.assertEqual(env['DM_BOOTPROF'], '1')
        self.assertNotIn('DM_WATCH', env)
        self.assertNotIn('API_TOKEN', env)
        self.assertNotIn('DM_NVN_SHOT', env)
        shots = self.root / 'capture-frames'
        with_shots = smash.capture_runtime_environment(self.root / 'source', self.profile, self.mac.parent,
                                                       self.root / 'capture', self.root / 'disposable', 'match', shots)
        self.assertEqual(with_shots['DM_NVN_SHOT'], '1200,2400,3600,4800:' + str(shots / 'frame-%d.png'))

    def test_cloud_and_profile_changes_are_private_and_default_off(self):
        original = (ROOT / 'dm/games' / smash.TITLE / 'game.tsv').read_bytes()
        profile = smash.make_profile(self.root / 'private', '', False)
        self.assertNotIn('cloud_container\t', (profile / 'game.tsv').read_text())
        self.assertIn('frame_generation\toff', (profile / 'game.tsv').read_text())
        self.assertFalse((profile / 'shader_map.tsv').is_symlink())
        cloud = smash.make_profile(self.root / 'private-cloud', 'iCloud.com.example.smash', True)
        self.assertIn('cloud_container\tiCloud.com.example.smash', (cloud / 'game.tsv').read_text())
        self.assertIn('frame_generation\t2x', (cloud / 'game.tsv').read_text())
        ipad = smash.make_profile(self.root / 'private-ipad', '', False, '4:3')
        self.assertIn('display_aspect\t4:3', (ipad / 'game.tsv').read_text())
        self.assertIn('display_aspect\t16:9', (profile / 'game.tsv').read_text())
        with self.assertRaisesRegex(ValueError, 'display aspect'):
            smash.make_profile(self.root / 'invalid-aspect', '', False, '21:9')
        self.assertFalse((self.root / 'invalid-aspect').exists())
        self.assertEqual((ROOT / 'dm/games' / smash.TITLE / 'game.tsv').read_bytes(), original)

    def test_original_display_reuses_inputs_without_creating_an_overlay(self):
        source, cache, work = (self.root / name for name in ('game', 'cache', 'new'))
        self.assertEqual(smash.prepare_display(source, cache, work, {}, '16:9'),
                         (cache, source / 'RomFS', None))
        self.assertFalse(work.exists())

    def test_display_clone_rejects_linked_resources_before_copying(self):
        source, cache, work = (self.root / name for name in ('game', 'cache', 'new'))
        (source / 'RomFS').mkdir(parents=True)
        cache.mkdir()
        (source / 'RomFS/linked-input').symlink_to(self.root / 'unrelated-private-file')
        with self.assertRaisesRegex(ValueError, 'Unsupported display input'):
            smash.prepare_display(source, cache, work, {}, '4:3')
        self.assertFalse(work.exists())

    @unittest.skipUnless(sys.platform == 'darwin', 'private APFS clone staging requires macOS')
    def test_ipad_display_preserves_reused_cache_and_complete_romfs(self):
        source, cache, work = (self.root / name for name in ('game', 'cache', 'new'))
        (source / 'RomFS/.nrr').mkdir(parents=True)
        (source / 'RomFS/data.arc').write_bytes(b'original synthetic archive')
        (source / 'RomFS/.nrr/fixture.nrr').write_bytes(b'registration')
        cache.mkdir()
        (cache / 'main.patched.bin').write_bytes(b'original cached main')
        (cache / 'nro_catalog.c').write_bytes(b'catalog identity')
        work.mkdir()

        def prepare(original, base, archive, output):
            self.assertEqual(original, source / 'ExeFS/main')
            self.assertEqual(archive, source / 'RomFS/data.arc')
            self.assertNotEqual(base, cache)
            (base / 'main.patched.bin').write_bytes(b'fresh main with UI gates')
            (output / 'romfs').mkdir(parents=True)
            (output / 'romfs/data.arc').write_bytes(b'corrected synthetic archive')
            receipt = output / 'receipt.json'
            receipt.write_text('{}')
            return SimpleNamespace(rewritten=base, romfs=output / 'romfs', receipt=receipt)

        with mock.patch.dict(sys.modules, {'smash_aspect': SimpleNamespace(prepare=prepare)}), mock.patch.object(smash, 'run') as rewrite:
            patched, romfs, receipt = smash.prepare_display(source, cache, work, {}, '4:3')
        self.assertEqual(rewrite.call_count, 1)
        self.assertEqual((cache / 'main.patched.bin').read_bytes(), b'original cached main')
        self.assertEqual((patched / 'nro_catalog.c').read_bytes(), b'catalog identity')
        self.assertEqual((source / 'RomFS/data.arc').read_bytes(), b'original synthetic archive')
        self.assertEqual((romfs / 'data.arc').read_bytes(), b'corrected synthetic archive')
        self.assertEqual((romfs / '.nrr/fixture.nrr').read_bytes(), b'registration')
        self.assertTrue(receipt.is_file())

    def test_arc_manifest_must_be_complete_and_match_bytes(self):
        directory = self.root / 'arc'
        directory.mkdir()
        path = directory / '1234567890.nro'
        path.write_bytes(b'synthetic NRO selection')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        data = {'schema': 1, 'operation': 'extract', 'region': 'us_en', 'archive_bytes': 123,
                'selected_extensions': ['nro'], 'selected_count': 1, 'entries': [
                    {'extension': 'nro', 'hash40': '1234567890', 'output': path.name, 'sha256': digest, 'decoded_bytes': path.stat().st_size}]}
        manifest = directory / 'manifest.json'
        manifest.write_text(json.dumps(data))
        smash.validate_arc_manifest(directory, {'nro': 1}, 123)
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            smash.validate_arc_manifest(directory, {'nro': 1}, 123)
        data['selected_count'] = 0
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            smash.validate_arc_manifest(directory, {'nro': 1}, 123)

    def test_effect_census_rejects_omitted_resources_members_and_retained_bytes(self):
        directory = self.root / 'effects'
        directory.mkdir()
        output = directory / ('1' * 64 + '.bnsh')
        output.write_bytes(b'synthetic retained shader')
        entries = [{'extension': 'eff', 'hash40': f'{index:010x}', 'sha256': 'a' * 64, 'offset': index * 10,
                    'stored_bytes': 5, 'decoded_bytes': 20 + index} for index in range(2)]
        members = [{'archive_hash40': '0000000000', 'member_path': 'GRSN/shader.bnsh', 'output': output.name},
                   {'archive_hash40': '0000000000', 'member_path': 'GRSN/GRSC/shader.bnsh', 'output': output.name},
                   {'archive_hash40': '0000000001', 'member_path': 'GRSN/shader.bnsh', 'output': output.name}]
        data = {'schema': 1, 'operation': 'effect-shaders', 'region': 'us_en', 'archive_bytes': 100,
                'selected_count': 2, 'selected_extensions': ['eff'], 'entries': entries, 'shader_members': members}
        census = {'archives': 2, 'references': 3, 'payloads': 1, 'decoded_bytes': 41, 'max_decoded_bytes': 21,
                  'retained_bytes': output.stat().st_size}
        def check():
            (directory / 'manifest.json').write_text(json.dumps(data))
            smash.validate_effect_manifest(directory, 100)
        with mock.patch.object(smash, 'EFFECT_CENSUS', census), mock.patch('smash_shaders.effect_shader_sources', return_value=[(str(output), 'synthetic')]):
            check()
            data['selected_count'] = 1
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                check()
            data['selected_count'] = 2
            members[2]['archive_hash40'] = '0000000009'
            with self.assertRaisesRegex(ValueError, 'missing from the census'):
                check()
            members[2]['archive_hash40'] = '0000000001'
            entries[1]['decoded_bytes'] = 19
            with self.assertRaisesRegex(ValueError, 'decoded census'):
                check()
            entries[1]['decoded_bytes'] = 21
            output.write_bytes(b'changed retained bytes')
            with self.assertRaisesRegex(ValueError, 'retained byte census'):
                check()

    def test_cached_shader_preparation_still_supplies_effects_to_static_split(self):
        for name in ('c1_full.tsv', 'cb_extent.tsv'):
            (self.profile / name).write_text('# chain b-' + self.chain + ' synthetic\n')
        effects = self.root / 'effect-shaders'
        with mock.patch.object(smash, 'run', return_value=self.chain) as run:
            result = smash.prepare_shader_corpus(self.root / 'source', self.root / 'ssbh', self.root / 'ui', effects,
                                                 self.profile, self.root, {}, False, 'fixture',
                                                 cached_ios=self.ios.parent, cached_manifest=self.manifest)
        command = run.call_args_list[0].args[0]
        self.assertEqual(command[command.index('--smash-effect-shaders') + 1], effects)
        self.assertEqual(result[3]['compiled'], 1)

    def test_staged_app_requires_resources_and_correct_private_metadata(self):
        source = self.root / 'product-source'
        (source / 'RomFS').mkdir(parents=True)
        (source / 'RomFS/data.arc').write_bytes(b'synthetic game archive')
        app = self.root / 'stage.app'
        (app / 'romfs').mkdir(parents=True)
        (app / 'romfs/data.arc').write_bytes((source / 'RomFS/data.arc').read_bytes())
        import shutil
        shutil.copytree(self.ios.parent, app / 'msl')
        (app / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.example.smash'}))
        metadata = {'BundleIdentifier': 'com.example.smash', 'CloudContainer': '',
                    'RequiresExtendedVirtualAddressing': True, 'GameTitleID': smash.TITLE}
        (app / 'NativeBuild.plist').write_bytes(plistlib.dumps(metadata))
        check = lambda: smash.validate_product(app, True, source, self.ios.parent, self.chain, 'com.example.smash', '')
        check()
        metadata['RequiresExtendedVirtualAddressing'] = False
        (app / 'NativeBuild.plist').write_bytes(plistlib.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'metadata'):
            check()
        (app / 'romfs/data.arc').unlink()
        with self.assertRaisesRegex(ValueError, 'regular file'):
            check()

    def test_owned_capture_timeout_and_crash_are_distinguished(self):
        log = self.root / 'owned.log'
        result = smash.run_owned_capture([sys.executable, '-c', 'import time; time.sleep(30)'], {}, log, .1)
        self.assertTrue(result['process_group_owned'])
        self.assertEqual(result['termination'], 'timeout')
        self.assertEqual(result['exit_code'], -signal.SIGTERM)
        with self.assertRaisesRegex(ValueError, 'failed with exit 2'):
            smash.run_owned_capture([sys.executable, '-c', 'raise SystemExit(2)'], {}, log, 1)

    def test_only_owned_preparation_scratch_is_released(self):
        work = self.root / 'scratch-work'
        for name in ('arc-modules', 'arc-shaders', 'ui-shader-sources', 'effect-shader-sources'):
            directory = work / name
            directory.mkdir(parents=True)
            (directory / 'manifest.json').write_text('{"synthetic": true}')
            (directory / 'payload').write_bytes(b'synthetic intermediate')
        for name in ('tools/rust', 'shader/initial/package', 'shader/captured/package', 'rewritten', 'runtime-capture', 'profiles'):
            (work / name).mkdir(parents=True)
            (work / name / 'keep-or-remove').write_bytes(b'synthetic output')
        smash.release_preparation_scratch(work)
        self.assertEqual(len(list((work / 'preparation-manifests').iterdir())), 4)
        self.assertFalse((work / 'arc-shaders').exists())
        self.assertFalse((work / 'tools/rust').exists())
        self.assertFalse((work / 'shader/captured/package').exists())
        for name in ('rewritten', 'runtime-capture', 'profiles'):
            self.assertTrue((work / name / 'keep-or-remove').exists())


class SmashCaptureReceiptTests(unittest.TestCase):
    """Synthetic producer files exercise trust boundaries, not game parsing."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.capture = self.root / 'capture'
        self.capture.mkdir()
        self.original = self.root / 'original'
        nrr = self.original / 'RomFS/.nrr/fixture.nrr'
        nrr.parent.mkdir(parents=True)
        nrr.write_bytes(b'synthetic registration')
        self.sources = self.root / 'source'
        self.sources.mkdir()
        (self.sources / 'host.c').write_bytes(b'synthetic host source')
        self.rewritten = self.root / 'rewrite'
        self.rewritten.mkdir()
        (self.rewritten / 'main.patched.bin').write_bytes(b'synthetic rewritten input')
        self.profile = self.root / 'profile'
        for name in ('game.tsv', 'dmsh_chain.h', 'shader_map.tsv', 'c1_full.tsv', 'cb_extent.tsv', '.generated/game_profile.h'):
            path = self.profile / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('synthetic profile ' + name)
        self.host = self.root / 'dmhost'
        self.host.write_bytes(b'synthetic host binary')
        control, code = bytes(0x760), b'synthetic instruction payload'
        self.original_digest = hashlib.sha256(control + code).hexdigest()
        self.key = self.original_digest[:16]
        for suffix, payload in (('ctl', control), ('code', code)):
            (self.capture / (self.key + '.' + suffix)).write_bytes(payload)
        self.extraction = {'modules': {name: {'sha256': digest, 'build_id': build} for name, (digest, build) in smash.MODULES.items()}}
        pair = lambda root: smash.paired_fingerprints(smash.fingerprint_files(root, (p for p in root.rglob('*') if p.is_file())), smash.fingerprint_files(root, (p for p in root.rglob('*') if p.is_file())))
        now = datetime.datetime.now(datetime.timezone.utc)
        self.data = {'schema': 1, 'kind': 'smash-nvn-shader-capture', 'title_id': smash.TITLE, 'build': 'v2031616',
            'modules': {name: dict(build_id=value['build_id'], sha256_before=value['sha256'], sha256_after=value['sha256']) for name, value in self.extraction['modules'].items()},
            'nrrs': [{'relative_path': '.nrr/fixture.nrr', 'sha256_before': smash.sha(nrr), 'sha256_after': smash.sha(nrr)}],
            'producer': {'host_binary': {'path': str(self.host), 'sha256_before': smash.sha(self.host), 'sha256_after': smash.sha(self.host)},
                'source_files': pair(self.sources), 'rewritten_root': str(self.rewritten), 'rewritten_files': pair(self.rewritten),
                'profile_root': str(self.profile), 'profile_files': pair(self.profile), 'command': [str(self.host), str(self.rewritten)],
                'environment': {'DM_NVN_SHDUMP': str(self.capture), 'DM_SAVE': str(self.root / 'disposable'),
                    'DM_ROMFS': str(self.original / 'RomFS'), 'DM_KEYS': '5:A'}},
            'bounded_run': {'started_at': now.isoformat(), 'ended_at': (now + datetime.timedelta(seconds=32)).isoformat(),
                'elapsed_seconds': 32, 'max_seconds': 32, 'max_frames': None, 'exit_code': 0, 'termination': 'timeout',
                'process_group_owned': True, 'disposable_save_created_fresh': True, 'disposable_save_path': str(self.root / 'disposable'), 'input_script': '5:A'},
            'captures': [{'key': self.key, 'control_sha256': smash.sha(self.capture / (self.key + '.ctl')),
                'code_sha256': smash.sha(self.capture / (self.key + '.code')), 'control_bytes': 13, 'code_bytes': 14}]}
        for suffix, field in (('ctl', 'control'), ('code', 'code')):
            self.data['captures'][0][field + '_bytes'] = (self.capture / (self.key + '.' + suffix)).stat().st_size
        for patch in (mock.patch.object(smash, 'REPO', self.sources), mock.patch.object(smash, 'CAPTURE_SOURCE_REQUIRED', {'host.c'}),
                      mock.patch.object(smash, 'verify_extraction', return_value=self.extraction), mock.patch.object(smash, 'verify_rewritten'),
                      mock.patch('smash_shaders.load_nvn_capture_directory', return_value=[SimpleNamespace(name=self.key)])):
            patch.start()
            self.addCleanup(patch.stop)

    def check(self):
        (self.capture / 'capture-provenance.json').write_text(json.dumps(self.data))
        return smash.validate_capture(self.capture, self.original, self.root / 'nros')

    def test_unchanged_local_producer_and_exact_payloads_are_accepted(self):
        self.assertEqual(self.check()['pairs'], 1)

    def test_registration_census_request_is_distinct_from_draw_only_evidence(self):
        self.assertFalse(self.check()['registration_census_requested'])
        self.enable_registration_census()
        self.assertTrue(self.check()['registration_census_requested'])

    def enable_registration_census(self):
        self.data['producer']['environment']['DM_NVN_SHDUMP_REGISTER'] = '1'
        totals = dict.fromkeys(('programs', 'expected_stages', 'register_stages', 'mapped_stages', 'deferred_stages',
                                'invalid_stages', 'draw_stages', 'captured_unique', 'duplicates', 'unresolved_deferred',
                                'failures', 'bytes_written'), 0)
        rows = [{'schema': 1, 'seq': 0, 'event': 'begin', 'mode': 'register-all', 'pid': 1,
                 'limits': {'unique': 65536, 'events': 262144, 'bytes': 1 << 30, 'ledger_bytes': 64 << 20}, 'totals': dict(totals)}]
        totals.update(programs=1, expected_stages=1)
        rows.append({'schema': 1, 'seq': 1, 'event': 'program', 'serial': 1, 'program': '1000', 'stages': 1, 'totals': dict(totals)})
        control, code = (self.capture / (self.key + '.' + suffix) for suffix in ('ctl', 'code'))
        totals.update(register_stages=1, mapped_stages=1, captured_unique=1, bytes_written=control.stat().st_size + code.stat().st_size)
        rows.append({'schema': 1, 'seq': 2, 'event': 'stage', 'origin': 'register', 'serial': 1, 'index': 0, 'status': 'captured',
                     'control_address': '2000', 'code_address': '3000', 'control_bytes': control.stat().st_size,
                     'code_bytes': code.stat().st_size, 'key': self.key, 'sha256': self.original_digest, 'totals': dict(totals)})
        (self.capture / 'registration-census.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        self.data['registration_census'] = smash.registration_census_proof(self.capture, {self.key})

    def test_registration_census_missing_tampered_or_unbound_stops_capture(self):
        self.enable_registration_census()
        self.check()
        ledger = self.capture / 'registration-census.jsonl'
        original = ledger.read_bytes()
        ledger.unlink()
        with self.assertRaises(ValueError):
            self.check()
        # Valid JSONL with semantically identical counters still has different
        # bytes and cannot be substituted for the producer-bound ledger.
        ledger.write_bytes(original.replace(b'"pid": 1', b'"pid": 2'))
        with self.assertRaisesRegex(ValueError, 'bound receipt'):
            self.check()
        ledger.write_bytes(original)
        self.data.pop('registration_census')
        with self.assertRaisesRegex(ValueError, 'bound receipt'):
            self.check()

    def test_changed_host_source_profile_rewrite_and_payload_are_rejected(self):
        for path in (self.host, self.sources / 'host.c', self.profile / 'game.tsv', self.rewritten / 'main.patched.bin', self.capture / (self.key + '.code')):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    self.check()
                path.write_bytes(original)

    def test_crash_unowned_or_non_disposable_run_is_not_certified(self):
        for field, value in (('exit_code', -14), ('exit_code', -9), ('process_group_owned', False),
                             ('disposable_save_created_fresh', False), ('input_script', 'different'), ('elapsed_seconds', 1000), ('max_frames', 0)):
            with self.subTest(field=field, value=value):
                original = self.data['bounded_run'][field]
                self.data['bounded_run'][field] = value
                with self.assertRaises(ValueError):
                    self.check()
                self.data['bounded_run'][field] = original

    def test_omitted_extra_duplicate_and_traversal_fingerprints_fail(self):
        records = self.data['producer']['source_files']
        for replacement in ([], records * 2, [dict(records[0], path='../dmhost')]):
            self.data['producer']['source_files'] = replacement
            with self.assertRaises(ValueError):
                self.check()
        self.data['producer']['source_files'] = records
        (self.capture / 'unrecorded.code').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'file set'):
            self.check()


if __name__ == '__main__':
    unittest.main()
