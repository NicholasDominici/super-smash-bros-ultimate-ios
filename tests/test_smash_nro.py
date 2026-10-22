"""Synthetic NRO/NRR preparation and native loading lifecycle checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shlex
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import smash_nro


def put32(data, offset, value):
    struct.pack_into('<I', data, offset, value)


def adr(register, source, target):
    delta = (target - source) & 0x1fffff
    return 0x10000000 | (delta & 3) << 29 | (delta >> 2) << 5 | register


def synthetic_nro(dependent=False):
    """Original test code: return42, call host init/fini, optionally call provider."""
    data = bytearray(0xc000)
    data[0x10:0x14] = b'NRO0'
    put32(data, 4, 0x80)
    put32(data, 0x18, len(data))
    put32(data, 0x38, 0x1000)
    for off, segment in zip((0x20, 0x28, 0x30), ((0, 0x4000), (0x4000, 0x4000), (0x8000, 0x4000))):
        struct.pack_into('<II', data, off, *segment)
    data[0x40:0x60] = bytes([2 if dependent else 1]) * 32
    data[0x80:0x84] = b'MOD0'
    struct.pack_into('<6i', data, 0x84, 0x4000 - 0x80, 0xc000 - 0x80, 0xd000 - 0x80,
                     0x4400 - 0x80, 0x440c - 0x80, 0xc000 - 0x80)
    data[0x4400:0x4404] = bytes([1, 3, 3, 3])  # valid empty eh_frame_hdr
    put32(data, 0, 0x14000040)  # b +0x100, no execution falls through headers.
    # Export value function.
    instructions = ([adr(8, 0x100, 0x8010), 0xf9400108, 0xd61f0100] if dependent else [0x52800540, 0xd65f03c0])
    for i, instruction in enumerate(instructions):
        put32(data, 0x100 + i * 4, instruction)
    for code, target in ((0x120, 0x8000), (0x140, 0x8008)):
        instructions = [0xa9bf7bfd, adr(8, code + 4, target), 0xf9400108, 0xd63f0100, 0xa8c17bfd, 0xd65f03c0]
        for i, instruction in enumerate(instructions):
            put32(data, code + i * 4, instruction)
    names = ['', 'SyntheticInit', 'SyntheticFini', 'test_B' if dependent else 'test_value', 'provider']
    strings = bytearray()
    for i, name in enumerate(names):
        no = len(strings)
        strings.extend(name.encode() + b'\0')
        defined = i == 3 or (i == 4 and not dependent)
        struct.pack_into('<IBBHQQ', data, 0x4100 + i * 24, no, 0 if i == 0 else 0x12, 0, int(defined), 0x100 if defined else 0, 0)
    string_offset = 0x4100 + len(names) * 24
    data[string_offset:string_offset + len(strings)] = strings
    struct.pack_into('<II', data, 0x4200, 1, len(names))
    tags = [(6, 0x4100), (5, string_offset), (4, 0x4200), (7, 0x4300),
            (8, 72 if dependent else 48), (12, 0x120), (13, 0x140), (0, 0)]
    for i, tag in enumerate(tags):
        struct.pack_into('<qQ', data, 0x4000 + i * 16, *tag)
    for i, (target, symbol) in enumerate([(0x8000, 1), (0x8008, 2)] + ([(0x8010, 4)] if dependent else [])):
        struct.pack_into('<QQq', data, 0x4300 + i * 24, target, symbol << 32 | 1026, 0)
    return bytes(data)


def synthetic_nrr(images):
    data = bytearray(0x1000)
    data[:4] = b'NRR0'
    struct.pack_into('<Q', data, 0x330, smash_nro.TITLE_ID)
    put32(data, 0x338, len(data))
    put32(data, 0x340, 0x350)
    put32(data, 0x344, len(images))
    for i, image in enumerate(images):
        data[0x350 + i * 32:0x370 + i * 32] = hashlib.sha256(image).digest()
    return bytes(data)


class NroTests(unittest.TestCase):
    def test_romfs_registration_directory_is_not_read_as_an_nrr_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, registrations = root / 'modules', root / 'RomFS/.nrr'
            source.mkdir()
            registrations.mkdir(parents=True)
            image = synthetic_nro()
            (source / 'example.nro').write_bytes(image)
            (registrations / 'example.nrr').write_bytes(synthetic_nrr([image]))
            result = smash_nro.prepare(source, root / 'patched', registrations.parent)
            self.assertEqual(len(result['registrations']), 1)
            self.assertEqual(len(result['modules']), 1)

    def test_carrier_preserves_every_original_segment_and_build_id(self):
        image = synthetic_nro()
        info = smash_nro.parse_nro(image)
        carrier = smash_nro.nso_carrier(image, info)
        self.assertEqual(carrier[:4], b'NSO0')
        self.assertEqual(carrier[0x40:0x60], image[0x40:0x60])
        for i, (offset, length) in enumerate(info['segments']):
            file_offset, memory_offset, size = struct.unpack_from('<III', carrier, 0x10 + i * 16)
            self.assertEqual((memory_offset, size), (offset, length))
            self.assertEqual(carrier[file_offset:file_offset + size], image[offset:offset + size])

    def test_invalid_lengths_segments_mod0_and_code_relocations_rejected(self):
        original = synthetic_nro()
        for offset, value in [(0x18, len(original) - 1), (0x28, 0), (4, 0xffffff00), (0x4300, 0x100)]:
            data = bytearray(original)
            put32(data, offset, value)
            with self.assertRaises(ValueError):
                smash_nro.parse_nro(bytes(data))

    def test_none_relocation_ignores_target_and_symbol(self):
        data = bytearray(synthetic_nro())
        struct.pack_into('<QQq', data, 0x4300, 0xffffffffffffffff, 0xffffffff00000000, 0)
        self.assertEqual(smash_nro.parse_nro(bytes(data))['image_size'], len(data))

    def test_nrr_wrong_title_and_hash_bounds_rejected(self):
        image = synthetic_nro()
        nrr = synthetic_nrr([image])
        self.assertIn(hashlib.sha256(image).hexdigest(), smash_nro.parse_nrr(nrr))
        for offset, value in [(0x330, 0), (0x338, 0x400), (0x340, 0), (0x344, 0x100000)]:
            raw = bytearray(nrr)
            put32(raw, offset, value)
            with self.assertRaises(ValueError):
                smash_nro.parse_nrr(bytes(raw))

    def test_catalog_rejects_unregistered_input_and_source_local_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'input').mkdir()
            (path / 'nrr').mkdir()
            (path / 'input/a.nro').write_bytes(synthetic_nro())
            (path / 'nrr/a.nrr').write_bytes(synthetic_nrr([synthetic_nro(True)]))
            with self.assertRaisesRegex(ValueError, 'absent'):
                smash_nro.prepare(path / 'input', path / 'output', path / 'nrr')
            with self.assertRaisesRegex(ValueError, 'outside'):
                smash_nro.prepare(path / 'input', ROOT / 'generated', path / 'nrr')

    def test_names_rejects_injection_duplicates_and_missing_rewrites(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            for name in ['n1234567;echo', '../n12345', 'n12345678']:
                (path / 'nro_catalog.json').write_text(json.dumps({'format': smash_nro.CATALOG_FORMAT, 'rewritten': True, 'modules': [{'name': name, 'sha256': '0' * 64}]}))
                with self.assertRaises(ValueError):
                    smash_nro.catalog_names(path)
            (path / 'nro_catalog.json').write_text(json.dumps({'format': smash_nro.CATALOG_FORMAT, 'rewritten': True, 'modules': [{'name': 'n1234567', 'sha256': '0' * 64}]}))
            with self.assertRaisesRegex(ValueError, 'Missing rewritten'):
                smash_nro.catalog_names(path)

    def test_old_catalog_and_source_tampering_fail_closed(self):
        import smash
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            source, nrr, output = path / 'input', path / 'nrr', path / 'output'
            source.mkdir(); nrr.mkdir()
            image = synthetic_nro()
            (source / 'one.nro').write_bytes(image)
            (nrr / 'one.nrr').write_bytes(synthetic_nrr([image]))
            metadata = smash_nro.prepare(source, output, nrr)
            metadata['rewritten'] = True
            name = metadata['modules'][0]['name']
            for suffix in ('patched.bin', 'fixups.tsv', 'gates.tsv'):
                (output / f'{name}.{suffix}').write_bytes(b'fixture')
            smash_nro.write_catalog(output, metadata)
            self.assertEqual(smash_nro.catalog_names(output), [name])
            exports = metadata['modules'][0]['exports']
            self.assertTrue(all(entry['offset'] == 0x100 for entry in exports))
            (output / 'nro_catalog.c').write_text((output / 'nro_catalog.c').read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'source differs'):
                smash_nro.catalog_names(output)
            metadata['format'] = 1
            (output / 'nro_catalog.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, 'without --rewritten'):
                smash_nro.catalog_names(output)
            # Exercise the human builder's reuse gate: old catalogs fail before
            # any build or device operation, even when other reuse checks pass.
            (output / 'main.obs.tsv').write_text('# synthetic\n')
            with mock.patch.object(smash, 'MODULES', {}), mock.patch.object(smash, 'GUARD_SITES', {}):
                with self.assertRaisesRegex(ValueError, 'without --rewritten'):
                    smash.verify_rewritten(output, source, {})
            metadata['format'] = smash_nro.CATALOG_FORMAT
            metadata['modules'].append(dict(metadata['modules'][0]))
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                smash_nro.catalog_source(metadata)

    @unittest.skipUnless(platform.system() == 'Darwin' and platform.machine() == 'arm64', 'native fixture needs Apple Silicon')
    def test_native_lifecycle_and_gate_registry(self):
        if not importlib.util.find_spec('capstone') or not importlib.util.find_spec('lz4'):
            self.skipTest('offline rewriter dependencies not installed')
        with tempfile.TemporaryDirectory(prefix='smash-nro-test-') as temp:
            path = Path(temp)
            source, nrrs, patched = path / 'input', path / 'nrr', path / 'patched'
            source.mkdir()
            nrrs.mkdir()
            images = [synthetic_nro(), synthetic_nro(True)]
            for i, image in enumerate(images):
                (source / f'{i}.nro').write_bytes(image)
            (nrrs / 'fixture.nrr').write_bytes(synthetic_nrr(images))
            smash_nro.prepare(source, patched, nrrs, rewrite=True)
            self.assertEqual(len(smash_nro.catalog_names(patched)), 2)
            subprocess.run([sys.executable, str(ROOT / 'dm/games/game.py'), 'header', '0100000000010000', str(path / 'game_profile.h')], check=True)
            common = ['xcrun', 'clang', '-O1', '-std=c11', '-Wall', '-Wextra', '-Werror',
                      '-Wno-deprecated-declarations', '-I', str(path), '-I', str(ROOT / 'dm/host')]
            embed_assembly = path / 'NroEmbed.S'
            link_flags = subprocess.check_output([sys.executable, str(ROOT / 'dm/ios/tools/gen_embed.py'),
                                                str(patched), str(embed_assembly), *smash_nro.catalog_names(patched)], text=True)
            sections = {line.strip() for line in embed_assembly.read_text().splitlines() if '.section ' in line}
            self.assertEqual(sections, {'.section __TEXT,__dmnrox0', '.section __TEXT,__dmnrox1', '.section __DMNROW,__img'})
            # Exercise the actual assembler's n_sect representation at the real
            # title's 98-module scale, using repeated original test bytes.
            bulk = path / 'bulk'
            bulk.mkdir()
            seed = smash_nro.catalog_names(patched)[0]
            sizes = json.loads((patched / 'nro_catalog.json').read_text())['modules'][0]['embed_sizes']
            entries = []
            for i in range(98):
                name = f'n{i:07x}'
                for suffix in ('patched.bin', 'fixups.tsv'):
                    os.link(patched / f'{seed}.{suffix}', bulk / f'{name}.{suffix}')
                entries.append({'name': name, 'embed_sizes': sizes})
            (bulk / 'nro_catalog.json').write_text(json.dumps({'rewritten': True, 'modules': entries}))
            bulk_assembly, bulk_object = path / 'BulkEmbed.S', path / 'BulkEmbed.o'
            subprocess.run([sys.executable, str(ROOT / 'dm/ios/tools/gen_embed.py'), str(bulk), str(bulk_assembly),
                            *[entry['name'] for entry in entries]], check=True, stdout=subprocess.PIPE)
            subprocess.run(['xcrun', 'clang', '-c', str(bulk_assembly), '-o', str(bulk_object)], check=True)
            macho = bulk_object.read_bytes()
            self.assertEqual(struct.unpack_from('<I', macho)[0], 0xfeedfacf)
            offset, section_count, macho_sections = 32, 0, set()
            for _ in range(struct.unpack_from('<I', macho, 16)[0]):
                command, length = struct.unpack_from('<II', macho, offset)
                if command == 0x19:
                    count = struct.unpack_from('<I', macho, offset + 64)[0]
                    section_count += count
                    for i in range(count):
                        at = offset + 72 + i * 80
                        macho_sections.add(macho[at:at + 16].split(b'\0')[0].decode())
                offset += length
            self.assertLessEqual(section_count, 4)  # assembler also emits its empty default __text
            self.assertEqual(macho_sections - {'__text'}, {'__dmnrox0', '__dmnrox1', '__img'})
            for test, signed in [('t_nro_loader', False), ('t_nro_loader', True), ('t_nro_gates', False)]:
                command = common + (['-DDM_TEST_SIGNED_EMBED'] if signed else []) + [str(ROOT / 'dm/host/tests' / f'{test}.c')]
                if test == 't_nro_loader':
                    command += [str(patched / 'nro_catalog.c')]
                if signed:
                    command += [str(embed_assembly), *shlex.split(link_flags)]
                binary = path / (test + ('-signed' if signed else ''))
                subprocess.run(command + ['-o', str(binary)], check=True)
                subprocess.run([str(binary), str(patched), str(source), str(nrrs / 'fixture.nrr')], check=True)


if __name__ == '__main__':
    unittest.main()
