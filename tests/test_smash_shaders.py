"""SSBH shader parsing with synthetic structures; no game bytes or device access."""
from pathlib import Path
import importlib.util
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dm/gfx/tools'))
import smash_shaders as ss


class Builder:
    """Construct offset-bearing fixtures instead of copying a game container."""

    def __init__(self, magic, version, root_size):
        self.data = bytearray(root_size)
        struct.pack_into('<4sQI4sHH', self.data, 0, b'HBSS', 64, 0, magic, *version)

    def allocate(self, size):
        self.data += bytes((-len(self.data)) % 8)
        start = len(self.data)
        self.data += bytes(size)
        return start

    def string(self, field, value):
        encoded = value.encode('utf-8') + b'\0'
        start = self.allocate(len(encoded))
        self.data[start:start + len(encoded)] = encoded
        struct.pack_into('<Q', self.data, field, start - field)

    def array(self, field, count, stride):
        if not count:
            return 0
        start = self.allocate(count * stride)
        struct.pack_into('<QQ', self.data, field, start - field, count)
        return start


def compiler_output(stage, marker=0):
    """A minimal NVN compiler output at offsets distinct from the real game."""
    control_start, control_length, code_length = 0x90, 0x850, 0x100
    blob = bytearray(control_start + control_length + code_length)
    blob[:4] = ss.GLSLC_MAGIC
    struct.pack_into('<I', blob, 0x44, len(blob))
    blob[control_start:control_start + 4] = ss.CTL_MAGIC
    struct.pack_into('<I', blob, control_start + 0x20, control_length)
    struct.pack_into('<II', blob, control_start + 0x700, 0x80, code_length)
    code_start = control_start + control_length
    if stage == 'cs':
        blob[code_start:code_start + 4] = b'\x11\x07\x20\xe2'  # headerless compute
        struct.pack_into('<3I', blob, control_start + 0x748, 4, 2, 1)
    else:
        blob[code_start:code_start + 4] = ss.GFX_MAGIC
        stage_id = {'vs': 1, 'gs': 4, 'ps': 5}[stage]
        struct.pack_into('<I', blob, code_start + 0x30, stage_id << 10)
    blob[code_start + 0x90] = marker
    return bytes(blob)


def nushdb(shaders):
    builder = Builder(b'RDHS', (1, 2), 40)
    start = builder.array(24, len(shaders), 56)
    for i, (name, stage, blob) in enumerate(shaders):
        row = start + 56 * i
        builder.string(row, name)
        struct.pack_into('<II', builder.data, row + 8, {'vs': 0, 'gs': 3, 'ps': 4, 'cs': 5}[stage], 2)
        binary = builder.array(row + 16, len(blob), 1)
        builder.data[binary:binary + len(blob)] = blob
        struct.pack_into('<Q', builder.data, row + 32, len(blob))
    return builder.data


def nufxlb(programs, version=(1, 1)):
    builder = Builder(b'XFUN', version, 56)
    stride = 96 if version == (1, 1) else 80
    start = builder.array(24, len(programs), stride)
    for i, (name, stages) in enumerate(programs):
        row = start + stride * i
        builder.string(row, name)
        builder.string(row + 8, 'synthetic-pass')
        for j, stage in enumerate(ss.STAGES):
            if stages.get(stage):
                builder.string(row + 16 + j * 8, stages[stage])
    return builder.data


class SmashShaderTests(unittest.TestCase):
    def assert_invalid(self, call):
        with self.assertRaises(ss.ShaderFormatError):
            call()

    def test_original_control_and_complete_code_are_preserved(self):
        blob = compiler_output('vs', marker=23)
        shader, = ss.parse_nushdb(nushdb([('vertex', 'vs', blob)]), 'fixture')
        self.assertEqual(shader.control, blob[0x90:0x8e0])
        self.assertEqual(shader.code, blob[0x8e0:])
        self.assertEqual(shader.code[0x90], 23)
        self.assertEqual(shader.stage, 'vs')
        self.assertIn('#NUSHDB#vertex', shader.source)

    def test_headerless_compute_and_geometry_have_explicit_metadata_stages(self):
        data = nushdb([('compute', 'cs', compiler_output('cs')), ('geometry', 'gs', compiler_output('gs'))])
        self.assertEqual([s.stage for s in ss.parse_nushdb(data, 'fixture')], ['cs', 'gs'])

    def test_ssbh_header_and_version_fail_closed(self):
        data = nushdb([('a', 'vs', compiler_output('vs'))])
        for field, value in [(0, b'WRNG'), (16, b'XFUN'), (20, b'\x01\x00\x03\x00')]:
            broken = bytearray(data)
            broken[field:field + len(value)] = value
            self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))

    def test_nonempty_arrays_need_bounded_nonnull_relative_pointers(self):
        data = nushdb([('a', 'vs', compiler_output('vs'))])
        for pointer, count in [(0, 1), (2**64 - 1, 1), (16, 2**64 - 1)]:
            broken = bytearray(data)
            struct.pack_into('<QQ', broken, 24, pointer, count)
            self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))

    def test_shader_name_pointer_encoding_and_termination_are_checked(self):
        data = nushdb([('a', 'vs', compiler_output('vs'))])
        row = 24 + struct.unpack_from('<Q', data, 24)[0]
        broken = bytearray(data)
        struct.pack_into('<Q', broken, row, 0)
        self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))
        for bad in [b'\xff\0', b'\t\0']:
            broken = bytearray(data)
            name = row + struct.unpack_from('<Q', data, row)[0]
            broken[name:name + 2] = bad
            self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))
        r = ss.Reader(struct.pack('<Q', 8) + b'x' * (ss.MAX_STRING_BYTES + 1), 'string')
        self.assert_invalid(lambda: r.string(0))

    def test_record_kind_size_padding_and_buffer_length_are_checked(self):
        data = nushdb([('a', 'vs', compiler_output('vs'))])
        row = 24 + struct.unpack_from('<Q', data, 24)[0]
        for offset, fmt, value in [(8, '<I', 99), (12, '<I', 3), (32, '<Q', 1), (40, '<I', 1)]:
            broken = bytearray(data)
            struct.pack_into(fmt, broken, row + offset, value)
            self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))
        broken = bytearray(data)
        struct.pack_into('<QQ', broken, row + 16, 2**64 - 1, 128)
        self.assert_invalid(lambda: ss.parse_nushdb(broken, 'fixture'))

    def test_glslc_magic_declared_length_control_and_code_lengths_are_checked(self):
        valid = compiler_output('vs')
        mutations = [(0, b'FAIL'), (0x44, struct.pack('<I', len(valid) - 1)),
                     (0x90, bytes(4)), (0x90 + 0x20, struct.pack('<I', 0x700)),
                     (0x90 + 0x704, struct.pack('<I', 0xffffffff)),
                     (0x90 + 0x700, struct.pack('<I', 0x101)),
                     (0x8e0, ss.CS_MAGIC)]
        for field, value in mutations:
            broken = bytearray(valid)
            broken[field:field + len(value)] = value
            self.assert_invalid(lambda: ss.glslc_parts(broken, 'vs', 'fixture'))

    def test_ambiguous_control_and_nvn_stage_disagreement_are_rejected(self):
        blob = bytearray(compiler_output('vs'))
        blob[0x8e0 + 0xa0:0x8e0 + 0xa4] = ss.CTL_MAGIC
        self.assert_invalid(lambda: ss.glslc_parts(blob, 'vs', 'fixture'))
        self.assert_invalid(lambda: ss.glslc_parts(compiler_output('vs'), 'ps', 'fixture'))
        blob = bytearray(compiler_output('cs'))
        struct.pack_into('<3I', blob, 0x90 + 0x748, 1, 0, 1)
        self.assert_invalid(lambda: ss.glslc_parts(blob, 'cs', 'fixture'))

    def test_both_nufx_versions_parse_exact_stage_names(self):
        for version in [(1, 0), (1, 1)]:
            program, = ss.parse_nufxlb(nufxlb([('pair', {'vs': 'v', 'ps': 'p'})], version), 'fixture')
            self.assertEqual(program.stages['vs'], 'v')
            self.assertEqual(program.stages['ps'], 'p')
            self.assertEqual(program.stages['gs'], '')

    def test_unused_nufx_metadata_arrays_are_still_bounds_checked(self):
        data = nufxlb([('pair', {'vs': 'v', 'ps': 'p'})])
        row = 24 + struct.unpack_from('<Q', data, 24)[0]
        for field in [40, row + 64, row + 80]:
            broken = bytearray(data)
            struct.pack_into('<QQ', broken, field, 2**64 - 1, 1)
            self.assert_invalid(lambda: ss.parse_nufxlb(broken, 'fixture'))

    def test_programs_cannot_mix_compute_and_graphics_or_have_no_stages(self):
        for stages in [{'vs': 'v', 'cs': 'c'}, {}]:
            self.assert_invalid(lambda: ss.parse_nufxlb(nufxlb([('bad', stages)]), 'fixture'))

    def test_pairing_joins_exact_names_and_never_creates_cross_pairs(self):
        shaders = [(name, stage, compiler_output(stage, i)) for i, (name, stage) in enumerate(
            [('va', 'vs'), ('pa', 'ps'), ('vb', 'vs'), ('pb', 'ps')])]
        programs = [('a', {'vs': 'va', 'ps': 'pa'}), ('b', {'vs': 'vb', 'ps': 'pb'}), ('pixel-only', {'ps': 'pa'})]
        bundle = ss.named_bundle([('shaders', nushdb(shaders))], [('programs', nufxlb(programs))])
        self.assertEqual(bundle.pairs, {('va', 'pa'), ('vb', 'pb')})
        self.assertEqual(bundle.programs, 3)

    def test_missing_shader_wrong_stage_and_conflicting_name_fail_closed(self):
        shaders = [('shaders', nushdb([('v', 'vs', compiler_output('vs'))]))]
        for stages in [{'vs': 'missing'}, {'ps': 'v'}]:
            self.assert_invalid(lambda: ss.named_bundle(shaders, [('programs', nufxlb([('bad', stages)]))]))
        conflicting = shaders + [('other', nushdb([('v', 'vs', compiler_output('vs', 42))]))]
        self.assert_invalid(lambda: ss.named_bundle(conflicting, [('programs', nufxlb([('a', {'vs': 'v'})]))]))

    def test_empty_or_incomplete_bundle_is_an_error(self):
        self.assert_invalid(lambda: ss.named_bundle([], []))
        self.assert_invalid(lambda: ss.named_bundle([('shaders', nushdb([('v', 'vs', compiler_output('vs'))]))], []))

    def test_directory_only_reads_selected_ssbh_sources(self):
        with tempfile.TemporaryDirectory(prefix='smash-shader-fixture-') as directory:
            root = Path(directory)
            (root / 'a.nushdb').write_bytes(nushdb([('v', 'vs', compiler_output('vs')), ('p', 'ps', compiler_output('ps'))]))
            (root / 'b.nufxlb').write_bytes(nufxlb([('program', {'vs': 'v', 'ps': 'p'})]))
            (root / 'data.arc').write_bytes(ss.ARC_MAGIC + b'not read as shader input')
            (root / 'manifest.json').write_text('{}')
            bundle = ss.load_directory(root)
            self.assertEqual(bundle.pairs, {('v', 'p')})
            self.assertEqual((bundle.nushdb_files, bundle.nufxlb_files), (1, 1))

    def test_shader_split_recognizes_arc_without_reading_payload(self):
        path = Path(ss.__file__).with_name('shader_split.py')
        spec = importlib.util.spec_from_file_location('smash_split_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {'DM_GAME': '0100000000010000', 'DM_GAMES_DIR': '', 'DM_GAMES_FIRST': ''}):
            spec.loader.exec_module(module)
        reads = []

        class HeaderOnly(io.BytesIO):
            def read(self, size=-1):
                reads.append(size)
                if size != 16:
                    raise AssertionError('data.arc payload was read')
                return super().read(size)

        with mock.patch('builtins.open', return_value=HeaderOnly(ss.ARC_MAGIC + bytes(8))):
            result = module.scan_file(('private.arc', 'data.arc'))
        self.assertEqual(result, ('data.arc', {}, set(), 'smash-arc'))
        self.assertEqual(reads, [16])

    def test_ui_payload_manifest_verifies_hash_size_and_source_identity(self):
        with tempfile.TemporaryDirectory(prefix='smash-ui-fixture-') as directory:
            root = Path(directory).resolve()
            blob = b'BNSH\0\0\0\0synthetic'
            digest = hashlib.sha256(blob).hexdigest()
            name = digest + '.bnsh'
            (root / name).write_bytes(blob)
            member = dict(archive_hash40='0123456789', member_path='bgsh/shader.bnsh', output=name, decoded_bytes=len(blob), sha256=digest)
            def write(m):
                (root / 'manifest.json').write_text(json.dumps(dict(schema=1, operation='shader-archives', shader_members=[m])))
            write(member)
            self.assertEqual(ss.ui_shader_sources(root), [(str(root / name), 'data.arc/0123456789.arc/bgsh/shader.bnsh')])
            for changes in [dict(output='../escape.bnsh'), dict(decoded_bytes=len(blob) + 1), dict(member_path='../escape'), dict(archive_hash40='invalid')]:
                write(dict(member, **changes))
                self.assert_invalid(lambda: ss.ui_shader_sources(root))
            write(member)
            (root / name).write_bytes(blob[:-1] + b'X')
            self.assert_invalid(lambda: ss.ui_shader_sources(root))

    def test_effect_payload_manifest_requires_its_own_operation_and_source_identity(self):
        with tempfile.TemporaryDirectory(prefix='smash-effect-fixture-') as directory:
            root = Path(directory).resolve()
            blob = b'BNSH\0\0\0\0synthetic-effect'
            digest = hashlib.sha256(blob).hexdigest()
            name = digest + '.bnsh'
            (root / name).write_bytes(blob)
            member = dict(archive_hash40='0123456789', member_path='GRSN/GRSC/shader.bnsh', output=name, decoded_bytes=len(blob), sha256=digest)
            manifest = dict(schema=1, operation='effect-shaders', shader_members=[member])
            (root / 'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(ss.effect_shader_sources(root), [(str(root / name), 'data.arc/0123456789.eff/GRSN/GRSC/shader.bnsh')])
            self.assert_invalid(lambda: ss.ui_shader_sources(root))
            manifest['operation'] = 'shader-archives'
            (root / 'manifest.json').write_text(json.dumps(manifest))
            self.assert_invalid(lambda: ss.effect_shader_sources(root))

    def test_sarc_names_do_not_copy_or_split_the_archive_tail(self):
        path = Path(ss.__file__).with_name('shader_split.py')
        spec = importlib.util.spec_from_file_location('smash_sarc_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {'DM_GAME': '0100000000010000', 'DM_GAMES_DIR': '', 'DM_GAMES_FIRST': ''}):
            spec.loader.exec_module(module)
        data = bytearray(136)
        struct.pack_into('<4sHHII', data, 0, b'SARC', 20, 0xfeff, len(data), 128)
        struct.pack_into('<4sHHI', data, 20, b'SFAT', 12, 1, 0)
        struct.pack_into('<IIII', data, 32, 0, 0x01000000, 0, 8)
        struct.pack_into('<4sHH', data, 48, b'SFNT', 8, 0)
        data[56:61] = b'name\0'
        data[128:] = b'BNSH\0\0\0\0'
        class BoundedBytes(bytes):
            def __getitem__(self, key):
                if isinstance(key, slice) and key.stop is None:
                    raise AssertionError('unbounded archive-tail copy')
                return super().__getitem__(key)
        self.assertEqual(list(module.sarc_members(BoundedBytes(data))), [('name', b'BNSH\0\0\0\0')])

    def test_nvn_captures_retain_executed_bytes_and_require_exact_hashes(self):
        for stage in ('vs', 'ps', 'cs'):
            control, code = ss.glslc_parts(compiler_output(stage), stage, 'fixture')
            key = hashlib.sha256(control + code).hexdigest()[:16]
            captured = ss.parse_nvn_capture(control + bytes(0x30), code, key, 'fixture')
            self.assertEqual((captured.stage, captured.control, captured.code), (stage, control, code))
            self.assert_invalid(lambda: ss.parse_nvn_capture(control, code, '0' * 16, 'fixture'))
            self.assert_invalid(lambda: ss.parse_nvn_capture(control, code[:-1], key, 'fixture'))
            broken = bytearray(control)
            struct.pack_into('<I', broken, 0x700, len(code) + 1)
            self.assert_invalid(lambda: ss.parse_nvn_capture(broken, code, key, 'fixture'))

    def test_capture_hash_prefix_merges_only_with_explicit_provenance(self):
        path = Path(ss.__file__).with_name('shader_split.py')
        spec = importlib.util.spec_from_file_location('smash_capture_merge_fixture', path)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {'DM_GAME': '0100000000010000', 'DM_GAMES_DIR': '', 'DM_GAMES_FIRST': ''}):
            spec.loader.exec_module(module)
        original, code = ss.glslc_parts(compiler_output('ps'), 'ps', 'fixture')
        full = bytearray(original + bytes(0x180))
        struct.pack_into('<I', full, 0x20, len(full))
        full[-1] = 37
        prefix = bytes(full[:0x880])
        key = module.skey(full, code)
        capture = ss.parse_nvn_capture(prefix, code, key, 'fixture')
        self.assertEqual(capture.control, prefix)
        self.assertFalse(module.same_shader((full, code), (prefix, code)))
        self.assertTrue(module.same_shader((full, code), (prefix, code), allow_key_prefix=True))
        self.assertTrue(module.same_shader((prefix, code), (full, code), allow_key_prefix=True))
        # Complete static records continue checking bytes beyond the hash span.
        changed_tail = bytearray(full); changed_tail[-1] ^= 1
        self.assertEqual(module.skey(changed_tail, code), key)
        self.assertFalse(module.same_shader((full, code), (changed_tail, code), allow_key_prefix=True))
        changed_prefix = bytearray(prefix); changed_prefix[0x100] ^= 1
        self.assertFalse(module.same_shader((full, code), (changed_prefix, code), allow_key_prefix=True))
        self.assertFalse(module.same_shader((full, code), (prefix[:-4], code), allow_key_prefix=True))
        self.assertFalse(module.same_shader((full, code), (prefix, code[:-1] + b'X'), allow_key_prefix=True))
        static_record = ('main#GLSLC@0x90', 'ps', bytes(full), code)
        capture_record = (capture.source, 'ps', prefix, code)
        self.assertIs(module.merge_shader_record(key, capture_record, static_record), static_record)
        self.assertIs(module.merge_shader_record(key, static_record, capture_record), static_record)
        with self.assertRaises(SystemExit):
            module.merge_shader_record(key, static_record, (capture.source, 'ps', changed_prefix, code))

    def test_nvn_capture_directory_rejects_orphans_and_bad_hashes(self):
        with tempfile.TemporaryDirectory(prefix='nvn-capture-fixture-') as directory:
            root = Path(directory)
            control, code = ss.glslc_parts(compiler_output('vs'), 'vs', 'fixture')
            key = hashlib.sha256(control + code).hexdigest()[:16]
            (root / (key + '.ctl')).write_bytes(control)
            self.assert_invalid(lambda: ss.load_nvn_capture_directory(root))
            (root / (key + '.code')).write_bytes(code)
            self.assertEqual(ss.load_nvn_capture_directory(root)[0].name, key)
            (root / (key + '.code')).write_bytes(code[:-1] + b'X')
            self.assert_invalid(lambda: ss.load_nvn_capture_directory(root))


if __name__ == '__main__':
    unittest.main()
