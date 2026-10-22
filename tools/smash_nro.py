#!/usr/bin/env python3
"""Prepare private, signed-at-build-time NRO images; never execute game input.

NROs use the same MOD0/ELF image as NSOs. This tool wraps their existing
segments in an uncompressed NSO carrier for the ordinary offline rewriter.
Only hashes listed in the supplied game's NRR registrations enter the catalog.
No original or rewritten game bytes may be placed in the source checkout.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_IMAGE = 256 * 1024 * 1024
MAX_MODULES = 512
CATALOG_FORMAT = 2
TITLE_ID = 0x01006A800016E000


def outside(path):
    """Reject source-local inputs and outputs, including symlink aliases."""
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('Game inputs and generated modules must stay outside the source checkout')
    return path


def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def parse_nro(data):
    """Validate a complete NRO and return its unchanged image segment layout."""
    if len(data) < 0x80 or data[0x10:0x14] != b'NRO0':
        raise ValueError('Not an NRO0 image')
    size, bss = u32(data, 0x18), u32(data, 0x38)
    if size != len(data) or not 0x80 <= size <= MAX_IMAGE or bss > MAX_IMAGE:
        raise ValueError('NRO image/BSS length is unsupported or does not match the file')
    segments = [struct.unpack_from('<II', data, off) for off in (0x20, 0x28, 0x30)]
    if segments[0][0] != 0 or segments[0][1] < 0x80:
        raise ValueError('NRO text must start at zero and contain its header')
    end = 0
    for offset, length in segments:
        if offset < end or length == 0 or offset + length > size or offset % 0x1000:
            raise ValueError('NRO segments overlap, exceed the image, or are not page aligned')
        end = offset + length
    mod0 = u32(data, 4)
    if mod0 + 0x1c > size or data[mod0:mod0 + 4] != b'MOD0':
        raise ValueError('NRO has no valid MOD0 header')
    object_offset = mod0 + struct.unpack_from('<i', data, mod0 + 0x18)[0]
    if object_offset < segments[2][0] or object_offset + 0xd0 > size + bss:
        raise ValueError('NRO SDK module object lies outside writable image/BSS')
    dynamic = mod0 + struct.unpack_from('<i', data, mod0 + 4)[0]
    if dynamic < 0 or dynamic + 16 > size:
        raise ValueError('NRO dynamic table is out of range')
    tags = {}
    for off in range(dynamic, min(size - 15, dynamic + 65536), 16):
        tag, value = struct.unpack_from('<qQ', data, off)
        if tag == 0:
            break
        tags[tag] = value
    else:
        raise ValueError('NRO dynamic table is not terminated')
    # This initial native loader uses explicit data/PLT relocations; unknown
    # relocation formats and module TLS must be implemented before admitting them.
    if any(tag in tags for tag in (17, 18, 19, 35, 36, 0x6ffffef6)):
        raise ValueError('NRO requires an unsupported REL/RELR/GNU-hash dynamic format')
    for start_tag, size_tag in ((7, 8), (23, 2)):
        start, length = tags.get(start_tag, 0), tags.get(size_tag, 0)
        if length % 24 or start > size or length > size - start:
            raise ValueError('NRO relocation table is out of range')
        for off in range(start, start + length, 24):
            target, info, _ = struct.unpack_from('<QQq', data, off)
            if info & 0xffffffff not in (0, 257, 1025, 1026, 1027):
                raise ValueError('NRO uses an unsupported relocation type')
            if not info & 0xffffffff:  # R_AARCH64_NONE does not reference target/symbol.
                continue
            if target < ((segments[0][1] + 0x3fff) & ~0x3fff) or target + 8 > size + bss:
                raise ValueError('NRO relocation targets signed code or lies outside data/BSS')
    symbol_start, string_start = tags.get(6, 0), tags.get(5, 0)
    if not 0 < symbol_start < string_start <= size or (string_start - symbol_start) % 24:
        raise ValueError('NRO dynamic symbol/string table layout is unsupported')
    if any((data[off + 4] & 15) == 6 for off in range(symbol_start, string_start, 24)):
        raise ValueError('NRO module TLS is not supported by this native loader')
    exports = []
    string_end = string_start + tags.get(10, size - string_start)
    if string_end > size:
        raise ValueError('NRO string table exceeds the original image')
    for off in range(symbol_start, string_start, 24):
        name, info, other, section, value, length = struct.unpack_from('<IBBHQQ', data, off)
        if not section or info >> 4 == 0 or other & 3 not in (0, 3):
            continue
        start = string_start + name
        end = data.find(b'\0', start, string_end)
        if start >= string_end or end < 0 or not start < end:
            raise ValueError('NRO exported symbol has an invalid string-table name')
        if info & 15 == 2 and value >= segments[0][1]:
            raise ValueError('NRO function export lies outside executable text')
        exports.append({'name': data[start:end].decode('ascii'), 'type': info & 15, 'offset': value})
    return {'image_size': size, 'bss_size': bss, 'segments': segments,
            'build_id': data[0x40:0x60].hex(), 'sha256': hashlib.sha256(data).hexdigest(), 'exports': exports}


def nso_carrier(data, info):
    """Add NSO container metadata without changing any byte of the NRO image."""
    header = bytearray(0x100)
    header[:4] = b'NSO0'
    header[0x40:0x60] = bytes.fromhex(info['build_id'])
    body = bytearray()
    for i, (offset, size) in enumerate(info['segments']):
        struct.pack_into('<III', header, 0x10 + i * 0x10, 0x100 + len(body), offset, size)
        struct.pack_into('<I', header, 0x60 + i * 4, size)
        body.extend(data[offset:offset + size])
    struct.pack_into('<I', header, 0x3c, info['bss_size'])
    return bytes(header + body)


def parse_nrr(data):
    """Read the NRR program and hash-list bounds, excluding its signed header."""
    if len(data) < 0x350 or data[:4] != b'NRR0' or u32(data, 0x338) != len(data):
        raise ValueError('Invalid NRR0 header or length')
    program = struct.unpack_from('<Q', data, 0x330)[0]
    offset, count = u32(data, 0x340), u32(data, 0x344)
    if program != TITLE_ID or offset < 0x350 or offset % 16 or count > 65536 or offset + count * 32 > len(data):
        raise ValueError('NRR program ID or hash-list bounds do not match Smash Ultimate')
    return {data[i:i + 32].hex() for i in range(offset, offset + count * 32, 32)}


def catalog_names(directory):
    """Validate generated metadata before passing module names to an assembler."""
    data = json.loads((Path(directory) / 'nro_catalog.json').read_text())
    if data.get('format') != CATALOG_FORMAT:
        raise ValueError('Outdated NRO catalog lacks exact deferred export metadata; regenerate the port without --rewritten')
    entries = data.get('modules', [])
    if not data.get('rewritten'):
        raise ValueError('NRO catalog has not been rewritten for native execution')
    if not 0 < len(entries) <= MAX_MODULES:
        raise ValueError('NRO catalog module count is out of range')
    names = [entry['name'] for entry in entries]
    if len(set(names)) != len(names) or any(not re.fullmatch(r'n[0-9a-f]{7}', n) for n in names):
        raise ValueError('NRO catalog module names are invalid or duplicated')
    for entry in entries:
        if not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise ValueError('Invalid NRO digest in catalog')
        for suffix in ('patched.bin', 'fixups.tsv', 'gates.tsv'):
            if not (Path(directory) / f'{entry["name"]}.{suffix}').is_file():
                raise ValueError(f'Missing rewritten NRO {entry["name"]}.{suffix}')
    expected = catalog_source(data)
    source = Path(directory) / 'nro_catalog.c'
    if not source.is_file() or source.read_text() != expected:
        raise ValueError('NRO catalog source differs from admitted export metadata; regenerate without --rewritten')
    return names


def prepare(source, output, nrr_dir, rewrite=False):
    """Build a deterministic, original-byte-identity catalog from private files."""
    source, output, nrr_dir = map(outside, (source, output, nrr_dir))
    spec = importlib.util.spec_from_file_location('nro_embed_layout', ROOT / 'dm/ios/tools/gen_embed.py')
    embed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(embed)
    nrrs, allowed = [], set()
    for p in sorted(p for p in nrr_dir.rglob('*.nrr') if p.is_file()):
        raw = p.read_bytes()
        allowed.update(parse_nrr(raw))
        nrrs.append({'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
    if not nrrs or not allowed:
        raise ValueError('No valid Smash NRR registrations supplied')
    if len(nrrs) > 64:
        raise ValueError('Too many NRR registrations for the native catalog')
    files = sorted(source.rglob('*.nro'))
    if not files:
        raise ValueError('No .nro files found')
    output.mkdir(parents=True, exist_ok=True)
    # A failed/interrupted rewrite must not leave an old ready catalog pointing
    # at a mixture of generations. Publish metadata only after every image passes.
    for filename in ('nro_catalog.json', 'nro_catalog.c'):
        (output / filename).unlink(missing_ok=True)
    modules, seen, names = [], set(), set()
    for path in files:
        raw = path.read_bytes()
        info = parse_nro(raw)
        digest = info['sha256']
        if digest not in allowed:
            raise ValueError(f'NRO {path.name} is absent from every supplied NRR')
        if digest in seen:
            continue
        name = 'n' + digest[:7]
        if name in names:
            raise ValueError('NRO short-name hash collision; catalog cannot be built')
        seen.add(digest)
        names.add(name)
        info['name'] = name
        info['source_name'] = str(path.relative_to(source))
        (output / f'{name}.nso').write_bytes(nso_carrier(raw, info))
        if rewrite:
            subprocess.run([sys.executable, str(ROOT / 'dm/tools/patch_nso.py'),
                            str(output / f'{name}.nso'), str(output), name], check=True)
            info['embed_sizes'] = [hi - lo for lo, hi in embed.module_parts(output, name)[2]]
        modules.append(info)
        if len(modules) > MAX_MODULES:
            raise ValueError('Too many distinct NRO images for the native catalog')
    catalog = {'format': CATALOG_FORMAT, 'title_id': f'{TITLE_ID:016X}', 'rewritten': bool(rewrite), 'modules': modules, 'registrations': nrrs}
    write_catalog(output, catalog)
    return catalog


def write_catalog(output, catalog):
    """Publish exact provider metadata after all image preparation succeeds."""
    output = outside(output)
    (output / 'nro_catalog.c').write_text(catalog_source(catalog))
    (output / 'nro_catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')


def catalog_source(catalog):
    """Generate C only from bounded, unambiguous original export identities."""
    modules, nrrs = catalog['modules'], catalog['registrations']
    exports = {}
    for index, module in enumerate(modules):
        if not isinstance(module.get('exports'), list):
            raise ValueError('NRO catalog lacks exact exports; regenerate without --rewritten')
        for entry in module['exports']:
            name, kind, offset = entry.get('name'), entry.get('type'), entry.get('offset')
            if not isinstance(name, str) or not re.fullmatch(r'[!-~]+', name) or type(kind) is not int or not 0 <= kind <= 15 or type(offset) is not int or not 0 <= offset < MAX_IMAGE * 2:
                raise ValueError('Invalid NRO export identity metadata')
            if kind == 2 and offset >= module['segments'][0][1]:
                raise ValueError('Admitted function export is outside original text')
            if name in exports:
                raise ValueError(f'Ambiguous NRO export provider: {name}')
            exports[name] = (index, kind, offset)
    if not 0 < len(exports) <= 65536:
        raise ValueError('NRO export catalog size is unsupported')
    def digest_array(h):
        return '{' + ','.join('0x' + h[i:i + 2] for i in range(0, 64, 2)) + '}'
    c = ['// Generated private NRO identity catalog. No executable bytes.', '#include "dm.h"',
         '#include <TargetConditionals.h>', '#if TARGET_OS_IPHONE || defined(DM_TEST_SIGNED_EMBED)']
    for m in modules:
        name = m['name']
        for part in ('x0', 'w', 'x1'):
            c.append(f'extern const uint8_t dm_nro_{name}_{part}[];')
        sizes = ','.join(f'{size}ull' for size in m.get('embed_sizes', (0, 0, 0)))
        c.append(f'#define DM_EMBED_{name} {{dm_nro_{name}_x0,dm_nro_{name}_w,dm_nro_{name}_x1,{sizes}}}')
    c.append('#else')
    for m in modules:
        sizes = ','.join(f'{size}ull' for size in m.get('embed_sizes', (0, 0, 0)))
        c.append(f'#define DM_EMBED_{m["name"]} {{NULL,NULL,NULL,{sizes}}}')
    c += ['#endif', 'const dm_nro_catalog_entry dm_nro_catalog[] = {']
    c += [f'    {{"{m["name"]}", {m["image_size"]}u, {m["bss_size"]}u, {digest_array(m["sha256"])}, DM_EMBED_{m["name"]}}},' for m in modules]
    c += ['};', f'const unsigned dm_nro_catalog_count = {len(modules)}u;',
          'const dm_nrr_catalog_entry dm_nrr_catalog[] = {']
    c += [f'    {{{n["size"]}u, {digest_array(n["sha256"])}}},' for n in nrrs]
    c += ['};', f'const unsigned dm_nrr_catalog_count = {len(nrrs)}u;',
          'const dm_nro_export_entry dm_nro_exports[] = {']
    c += [f'    {{{json.dumps(name)}, {index}u, {kind}u, {offset}ull}},' for name, (index, kind, offset) in sorted(exports.items())]
    c += ['};', f'const unsigned dm_nro_export_count = {len(exports)}u;', '']
    return '\n'.join(c)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--nrr-dir', type=Path, required=True)
    p.add_argument('--rewrite', action='store_true')
    p = commands.add_parser('names')
    p.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.command == 'names':
        print(' '.join(catalog_names(outside(args.output))))
    else:
        result = prepare(args.source, args.output, args.nrr_dir, args.rewrite)
        print(f'Prepared {len(result["modules"])} distinct private NRO images')


if __name__ == '__main__':
    main()
