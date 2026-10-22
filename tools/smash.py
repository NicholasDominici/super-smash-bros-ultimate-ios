#!/usr/bin/env python3
"""Build a private Smash Ultimate 13.0.5 iOS app from your own game files."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zipfile

sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[1]
TITLE = '01006A800016E000'
MODULES = {
    'main': ('eb79e639e47d9a0c79bcfe2ec50fc807afa9601800226627b58bd6a1a83dc52d', '21450c647b8c5940ed5b68218ea128fd'),
    'subsdk0': ('2ac9587ec0d20a2bda42d7a8f04574f18af3e047d9864a599070d57666b1811e', '60c6edbbfcebd4176cc301d5d9cb5a6f'),
    'sdk': ('8d20111b4f1dd9a301901ed9c2a0f31ce5678076f7b233bfb8bdbafe52f955f1', '5fd4f531c1195e9e5510c9e73f22cd39'),
}
STAGES = {'vertex': 'vs', 'pixel': 'ps', 'geometry': 'gs', 'compute': 'cs', 'hull': 'hs', 'domain': 'ds'}
KNOWN_GEOMETRY = 'ef507c559969bc0a'
MIN_SHADER_KEYS = 35012
GUARD_SITES = {'0x1750dd0': ('21', 'd10203ff'), '0x4def24': ('22', 'f9407660'), '0x6b92c0': ('23', 'd101c3ff')}
SLOT_KINDS = {'cbuf', 'samp', 'samp_tex', 'tex', 'img', 'tbuf', 'sbuf', 'ubo_ptr', 'sbuf_ubo', 'tex_ubo', 'samp_ubo', 'samp_id'}
CAPTURE_SOURCE_REQUIRED = {'dm/host/Makefile', 'dm/host/main.c', 'dm/host/loader.c', 'dm/host/hle.c',
                           'dm/host/hle_hid.c', 'dm/gfx/nvn/hle_nvn.c', 'dm/gfx/nvn/nvn_mtl.m',
                           'dm/tools/patch_nso.py', 'dm/tools/a64_tables.py', 'dm/tools/a64_observers.py',
                           'dm/gfx/metal/Makefile', 'dm/games/game.py'}
MENU_CAPTURE_SCRIPT = ','.join(f'{second}:A' for second in range(5, 30, 3))
# Register-all can change menu timing. Keep confirming before selecting a fighter;
# the later route is an attempt whose actual battle must be checked separately.
MATCH_CAPTURE_SCRIPT = (','.join(f'{second}:A' for second in range(5, 45, 3)) +
                        ',50:LUp~0.45,51:LLeft~0.35,52:A,55:Plus,58:A,62:A'
                        ',70:LRight~1,72:A*6/1,80:B*3/1,85:ZR~2,89:X')
CAPTURE_ROUTES = {'match': MATCH_CAPTURE_SCRIPT, 'menus': MENU_CAPTURE_SCRIPT}
CAPTURE_TIMEOUTS = {'match': 105, 'menus': 32}
CAPTURE_UNIQUE_LIMIT = 65536  # Match register-all writer; receipt/byte bounds also apply.
EFFECT_CENSUS = {'archives': 329, 'references': 654, 'payloads': 386,
                 'decoded_bytes': 1_523_130_680, 'max_decoded_bytes': 34_419_200, 'retained_bytes': 290_926_184}


def outside(path: Path) -> Path:
    """Keep input game bytes and all private output outside this checkout."""
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise ValueError('Game files, keys, caches and build output must be outside the source checkout')
    return path


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing regular file: {path}')


def run(command, work: Path, label: str, env: dict, capture=False) -> str:
    """Keep detailed tool output private, and stop on every nonzero exit."""
    print(f'[{label}]', flush=True)
    log = work / 'logs' / (label + '.log')
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, command)), cwd=REPO, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f'{label} failed (exit {result.returncode}); inspect {log}')
    return log.read_text() if capture else ''


def check_tools() -> None:
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Build on an Apple Silicon Mac')
    missing = [tool for tool in ('xcodebuild', 'xcodegen', 'dotnet', 'spirv-cross', 'zstd', 'cargo') if not shutil.which(tool)]
    if missing:
        raise ValueError('Missing tools: ' + ', '.join(missing) + '; see README installation steps')
    for module in ('lz4.block', 'capstone', 'fontTools'):
        try:
            __import__(module)
        except ImportError as error:
            raise ValueError('Activate .venv and run python -m pip install -r requirements.txt') from error
    version = subprocess.check_output(['xcodebuild', '-version'], text=True)
    match = re.search(r'Xcode (\d+)', version)
    if not match or int(match[1]) < 27:
        raise ValueError('Select Xcode 27 or newer under Xcode Settings > Locations > Command Line Tools')
    runtimes = subprocess.check_output(['dotnet', '--list-runtimes'], text=True)
    if not re.search(r'^Microsoft\.NETCore\.App 10\.', runtimes, re.M):
        raise ValueError('Install the .NET 10 SDK/runtime; newer major versions alone cannot run the pinned translator')


def verify_extraction(source: Path) -> dict:
    """Require all three exact original NSOs, an ARC, and valid NRR identities."""
    record = {}
    for name, (digest, build) in MODULES.items():
        path = source / 'ExeFS' / name
        regular(path)
        with path.open('rb') as stream:
            header = stream.read(0x60)
        if len(header) != 0x60 or header[:4] != b'NSO0' or header[0x40:0x50].hex() != build or sha(path) != digest:
            raise ValueError(f'{name}: requires the original Smash 13.0.5 module; see docs/INPUTS.md')
        record[name] = {'sha256': digest, 'build_id': build}
    arc = source / 'RomFS/data.arc'
    regular(arc)
    with arc.open('rb') as stream:
        if stream.read(8) != bytes.fromhex('1032547698efcdab'):
            raise ValueError('RomFS/data.arc has an unsupported header')
    import smash_nro
    nrr_root = source / 'RomFS/.nrr'
    if nrr_root.is_symlink() or not nrr_root.is_dir():
        raise ValueError('Missing regular RomFS/.nrr registration directory')
    nrrs = sorted(path for path in nrr_root.rglob('*.nrr') if path.is_file())
    if len(nrrs) != 14:
        raise ValueError(f'Expected 14 Smash NRR registrations, found {len(nrrs)}')
    for path in nrrs:
        regular(path)
        smash_nro.parse_nrr(path.read_bytes())
    return {'modules': record, 'archive_bytes': arc.stat().st_size, 'nrr_sha256': sorted(sha(p) for p in nrrs)}


def make_profile(work: Path, cloud: str, frame_generation: bool) -> Path:
    """Make mutable private tables; never regenerate the public profile in place."""
    target = work / 'profiles' / TITLE
    shutil.copytree(REPO / 'dm/games' / TITLE, target)
    path = target / 'game.tsv'
    text = re.sub(r'^cloud_container\t.*\n?', '', path.read_text(), flags=re.M)
    text = re.sub(r'^frame_generation\t.*$', 'frame_generation\t' + ('2x' if frame_generation else 'off'), text, flags=re.M)
    if not re.search(r'^extended_virtual_addressing\ton$', text, re.M):
        raise ValueError('Smash requires the Extended Virtual Addressing profile capability')
    if cloud:
        if not re.fullmatch(r'iCloud\.[A-Za-z0-9][A-Za-z0-9.-]+', cloud):
            raise ValueError('Use your own iCloud container ID, for example iCloud.com.yourname.smash')
        text += '\ncloud_container\t' + cloud + '\n'
    path.write_text(text)
    return target


def extract_packages(base: Path, update: Path, keys: Path, work: Path, env: dict) -> Path:
    """Compile LibHac extraction externally, with integrity checks left enabled."""
    destination = work / 'tools/nx_extract'
    # MSBuild's generated conditions break on apostrophes in intermediate paths.
    with tempfile.TemporaryDirectory(prefix='smash-extractor-') as temp:
        temp = Path(temp)
        project = temp / 'project'
        shutil.copytree(REPO / 'dm/tools/nx_extract', project, ignore=shutil.ignore_patterns('obj', 'bin'))
        run(['dotnet', 'build', project / 'nx_extract.csproj', '-c', 'Release',
             '-o', temp / 'bin', '-v', 'quiet', '-nologo'], work, 'extractor-build', env)
        regular(temp / 'bin/nx_extract')
        shutil.copytree(temp / 'bin', destination)
    result = work / 'extracted'
    run([destination / 'nx_extract', keys, base, update, result], work, 'extract-merged-game', env)
    return result


def arc_extract(source: Path, work: Path, env: dict) -> tuple[Path, Path, Path, Path]:
    """Extract native modules and all three verified static shader sources."""
    env = dict(env, CARGO_TARGET_DIR=str(work / 'tools/rust'))
    run(['cargo', 'build', '--locked', '--release', '--manifest-path', REPO / 'tools/smash_arc/Cargo.toml'], work, 'arc-tool-build', env)
    tool = work / 'tools/rust/release/smash-arc-tool'
    for name, extensions, counts in (('arc-modules', 'nro', {'nro': 98}),
                                     ('arc-shaders', 'nushdb,nufxlb', {'nushdb': 41, 'nufxlb': 4})):
        directory = work / name
        run([tool, 'extract', '--arc', source / 'RomFS/data.arc', '--region', 'us_en', '--extensions', extensions,
             '--out', directory], work, name, env)
        validate_arc_manifest(directory, counts, (source / 'RomFS/data.arc').stat().st_size)
    ui = work / 'ui-shader-sources'
    run([tool, 'shader-archives', '--arc', source / 'RomFS/data.arc', '--region', 'us_en', '--out', ui],
        work, 'arc-ui-shaders', env)
    validate_ui_manifest(ui, (source / 'RomFS/data.arc').stat().st_size)
    effects = work / 'effect-shader-sources'
    run([tool, 'effect-shaders', '--arc', source / 'RomFS/data.arc', '--region', 'us_en', '--out', effects],
        work, 'arc-effect-shaders', env)
    validate_effect_manifest(effects, (source / 'RomFS/data.arc').stat().st_size)
    return work / 'arc-modules', work / 'arc-shaders', ui, effects


def validate_ui_manifest(directory: Path, archive_bytes: int) -> None:
    """Require the full nested-archive census and verified retained payloads."""
    sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
    import smash_shaders
    files = smash_shaders.ui_shader_sources(directory)
    validate_nested_shader_manifest(directory, archive_bytes, 'arc', 'shader-archives', 362, 247, 124, files)


def validate_effect_manifest(directory: Path, archive_bytes: int) -> None:
    """Require every supported effect resource and its verified shader members."""
    sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
    import smash_shaders
    files = smash_shaders.effect_shader_sources(directory)
    validate_nested_shader_manifest(directory, archive_bytes, 'eff', 'effect-shaders',
                                    EFFECT_CENSUS['archives'], EFFECT_CENSUS['references'], EFFECT_CENSUS['payloads'], files)
    data = json.loads((directory / 'manifest.json').read_text())
    if sum(entry['decoded_bytes'] for entry in data['entries']) != EFFECT_CENSUS['decoded_bytes'] or max(entry['decoded_bytes'] for entry in data['entries']) != EFFECT_CENSUS['max_decoded_bytes']:
        raise ValueError('Effect resource decoded census differs from Smash 13.0.5')
    if sum(path.stat().st_size for path in directory.glob('*.bnsh')) != EFFECT_CENSUS['retained_bytes']:
        raise ValueError('Effect shader retained byte census differs from Smash 13.0.5')


def validate_nested_shader_manifest(directory: Path, archive_bytes: int, extension: str, operation: str,
                                    archives: int, references: int, payloads: int, files) -> None:
    """Reconcile all container identities and every retained shader payload."""
    data = json.loads((directory / 'manifest.json').read_text())
    entries, members = data.get('entries', []), data['shader_members']
    if (data.get('schema') != 1 or data.get('operation') != operation or data.get('archive_bytes') != archive_bytes or data.get('region') != 'us_en' or
            data.get('selected_count') != archives or len(entries) != archives or len(members) != references or len(files) != payloads or
            data.get('selected_extensions') != [extension]):
        raise ValueError('Incomplete nested ' + extension + ' archive/shader census for Smash 13.0.5')
    if any(not isinstance(entry, dict) or entry.get('extension') != extension or
           not re.fullmatch('[0-9a-f]{64}', entry.get('sha256', '')) or
           type(entry.get('offset')) is not int or type(entry.get('stored_bytes')) is not int or
           type(entry.get('decoded_bytes')) is not int or entry['offset'] < 0 or entry['stored_bytes'] <= 0 or
           entry['decoded_bytes'] <= 0 or entry['offset'] > archive_bytes - entry['stored_bytes'] for entry in entries):
        raise ValueError('Invalid nested ARC census entry')
    identities = [entry.get('hash40') for entry in entries]
    if len(set(identities)) != archives or any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{10}', value) for value in identities):
        raise ValueError('Invalid/duplicate nested ARC identities')
    if any(member['archive_hash40'] not in identities for member in members):
        raise ValueError('A retained shader references an archive missing from the census')
    if len({(member['archive_hash40'], member['member_path']) for member in members}) != len(members):
        raise ValueError('Duplicated shader archive/member reference')
    expected = {Path(path).name for path, _ in files} | {'manifest.json'}
    if {path.name for path in directory.iterdir()} != expected:
        raise ValueError('Nested shader extraction has missing or unlisted payloads')


def extraction_manifest_receipt(directory: Path) -> dict:
    path = directory / 'manifest.json'
    regular(path)
    data = json.loads(path.read_text())
    return {'manifest_sha256': sha(path), 'manifest_bytes': path.stat().st_size, 'operation': data['operation'],
            'selected_count': data['selected_count'], 'shader_member_references': len(data.get('shader_members', []))}


def validate_arc_manifest(directory: Path, counts: dict, archive_bytes: int) -> dict:
    """Require a completed manifest and byte-verify every selected output."""
    data = json.loads((directory / 'manifest.json').read_text())
    entries = data.get('entries', [])
    if (data.get('schema') != 1 or data.get('operation') != 'extract' or data.get('region') != 'us_en' or
            data.get('archive_bytes') != archive_bytes or data.get('selected_count') != sum(counts.values()) or
            len(entries) != sum(counts.values()) or set(data.get('selected_extensions', [])) != set(counts) or
            any(not isinstance(e, dict) for e in entries) or Counter(e.get('extension') for e in entries) != Counter(counts)):
        raise ValueError(f'Incomplete or unexpected ARC extraction manifest: {directory}')
    names = set()
    for entry in entries:
        name, digest = entry.get('output', ''), entry.get('sha256', '')
        if (not re.fullmatch(r'[0-9a-f]{10}\.(?:nro|nushdb|nufxlb)', name) or name in names or
                name != entry.get('hash40', '') + '.' + entry.get('extension', '') or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('Invalid or duplicate ARC extraction entry')
        names.add(name)
        path = directory / name
        regular(path)
        if path.stat().st_size != entry.get('decoded_bytes') or sha(path) != digest:
            raise ValueError(f'ARC extraction bytes disagree with the manifest: {name}')
    actual = {p.name for p in directory.iterdir() if p.name != 'manifest.json'}
    if names != actual:
        raise ValueError('ARC extraction has missing or unlisted files')
    return data


def verify_rewritten(directory: Path, original_nros: Path, extraction: dict) -> None:
    """Reject stale static builds, missing guard gates or mismatched NRO catalogs."""
    import smash_nro
    for name, (_, build) in MODULES.items():
        for suffix in ('patched.bin', 'fixups.tsv', 'gates.tsv', 'cuts.tsv', 'obs.tsv'):
            regular(directory / f'{name}.{suffix}')
        metadata = (directory / f'{name}.fixups.tsv').read_text()
        if not re.search(r'^# BUILD_ID\t' + build + r'$', metadata, re.M):
            raise ValueError(f'{name}: reused rewrite is for a different original module')
    sites = {}
    for line in (directory / 'main.obs.tsv').read_text().splitlines():
        if line and not line.startswith('#'):
            columns = line.split('\t')
            sites[columns[0]] = tuple(columns[1:3])
    if any(sites.get(offset) != pair for offset, pair in GUARD_SITES.items()):
        raise ValueError('Rewritten main lacks the current exact-build Smash guard observers; omit --rewritten')
    names = smash_nro.catalog_names(directory)
    catalog = json.loads((directory / 'nro_catalog.json').read_text())
    original = {sha(path) for path in original_nros.glob('*.nro')}
    if catalog.get('format') != smash_nro.CATALOG_FORMAT or catalog.get('title_id') != TITLE or len(names) != 98 or {entry['sha256'] for entry in catalog['modules']} != original:
        raise ValueError('Rewritten NRO catalog does not match all 98 extracted originals')
    admitted = {entry['sha256']: entry for entry in catalog['modules']}
    for path in original_nros.glob('*.nro'):
        actual = smash_nro.parse_nro(path.read_bytes())
        if admitted[actual['sha256']]['exports'] != actual['exports']:
            raise ValueError('NRO export/provider offsets differ from admitted original bytes; regenerate without --rewritten')
    if sorted(entry['sha256'] for entry in catalog['registrations']) != extraction['nrr_sha256']:
        raise ValueError('Rewritten NRO catalog uses different NRR registrations')
    regular(directory / 'nro_catalog.c')


def shader_rows(profile: Path) -> dict:
    rows = {}
    for line in (profile / 'shader_map.tsv').read_text().splitlines():
        if not line or line.startswith('#') or line.startswith('package\t'):
            continue
        columns = line.split('\t')
        if len(columns) != 5 or columns[2] not in STAGES or not re.fullmatch(r'[0-9a-f]{16}', columns[3]) or columns[3] in rows:
            raise ValueError('Invalid or duplicate shader-map row')
        rows[columns[3]] = {'stage': STAGES[columns[2]], 'source': columns[4]}
    if len(rows) < MIN_SHADER_KEYS:
        raise ValueError(f'Shader census is incomplete: expected at least {MIN_SHADER_KEYS:,} original keys, found {len(rows):,}')
    return rows


def valid_metallib(path: Path) -> None:
    regular(path)
    with path.open('rb') as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:4] != b'MTLB' or struct.unpack_from('<Q', header, 16)[0] != path.stat().st_size:
        raise ValueError(f'Invalid or truncated Metal library: {path}')


def validate_shaders(profile: Path, ios_root: Path, manifest: Path, chain: str, allow_gap: bool) -> dict:
    """CLI exit zero is insufficient: reconcile every key and both artifact sets."""
    expected, statuses = shader_rows(profile), {}
    data = json.loads(manifest.read_text())
    if not isinstance(data, list):
        raise ValueError('Shader build manifest must be the _b_build.json list from dmsh_build.py')
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError('Invalid shader manifest record')
        key = entry.get('key')
        if key not in expected or key in statuses or not isinstance(entry.get('st'), str):
            raise ValueError('Shader manifest contains extra, invalid or duplicate keys')
        statuses[key] = entry['st']
    if statuses.keys() != expected.keys():
        raise ValueError('Shader manifest does not account for every shader-map key')
    failed = {key for key, status in statuses.items() if status != 'ok'}
    accepted = failed == {KNOWN_GEOMETRY} and expected[KNOWN_GEOMETRY] == {
        'stage': 'gs', 'source': '/data.arc/37d50839a8.nushdb#NUSHDB#CharacterDamageModel2GS'}
    if failed and not (allow_gap and accepted):
        raise ValueError(f'{len(failed)} shader(s) failed; inspect {manifest}. Only the documented exact geometry gap can be explicitly allowed')
    successful = set(expected) - failed
    sys.path.insert(0, str(REPO / 'dm/ios/tools'))
    import ios_metal
    mac_dir, ios_dir = manifest.parent, ios_root / ('b-' + chain)
    if mac_dir.name != 'b-' + chain:
        raise ValueError('Shader manifest belongs to a different translation chain')
    summary = {'chain': chain, 'expected': len(expected), 'compiled': len(successful), 'known_geometry_gap': sorted(failed), 'platforms': {}}
    for label, directory, metal_record in (('mac', mac_dir, 'xcrun -sdk macosx metal -c -fpreserve-invariance; xcrun -sdk macosx metallib'),
                                           ('ios', ios_dir, ios_metal.RECORD)):
        if not directory.is_dir():
            raise ValueError(f'Missing shader chain directory: {directory}')
        reflection_keys = {path.name[:-7] for path in directory.glob('*_b.json')}
        library_keys = {path.name[:-11] for path in directory.glob('*_b.metallib')}
        if reflection_keys != successful or library_keys != successful:
            raise ValueError(f'{label}: reflection/library sets do not match the successful manifest keys')
        fetch = set()
        for key in sorted(successful):
            reflection = directory / (key + '_b.json')
            regular(reflection)
            record = json.loads(reflection.read_text())
            if not isinstance(record, dict):
                raise ValueError(f'{label}: invalid shader reflection: {key}')
            if any(record.get(field) != value for field, value in {
                    'key': key + '_b', 'dm_ctl': key, 'route': 'B', 'chain': chain,
                    'stage': expected[key]['stage'], 'chain_metal': metal_record}.items()):
                raise ValueError(f'{label}: wrong shader identity/stage/chain/platform: {key}')
            bindings = record.get('bindings')
            if not isinstance(bindings, list) or record.get('drv_unfillable') != [] or any(
                    not isinstance(b, dict) or b.get('kind') not in SLOT_KINDS | {'c1', 'drvcb', 'support'} or
                    (b.get('kind') in SLOT_KINDS and (type(b.get('reg')) is not int or b['reg'] < 0)) for b in bindings):
                raise ValueError(f'{label}: unsupported reflection or driver binding: {key}')
            valid_metallib(directory / (key + '_b.metallib'))
            if label == 'mac':
                regular(directory / (key + '_b.metal'))
            if record.get('fetch'):
                fetch.add(key)
                valid_metallib(directory / (key + '_bf.metallib'))
        if {path.name[:-12] for path in directory.glob('*_bf.metallib')} != fetch:
            raise ValueError(f'{label}: framebuffer-fetch variants do not match their reflections')
        summary['platforms'][label] = {'base_libraries': len(successful), 'fetch_libraries': len(fetch)}
    return summary


def validate_product(output: Path, app_only: bool, source: Path, ios: Path, chain: str, bundle: str, cloud: str) -> None:
    """A compiler-only product is not a staged app: verify packaged resources."""
    resources = {'romfs/data.arc': (source / 'RomFS/data.arc').stat().st_size}
    shader_dir = ios / ('b-' + chain)
    for path in shader_dir.iterdir():
        if path.name.endswith(('_b.json', '_b.metallib', '_bf.metallib')):
            resources['msl/' + shader_dir.name + '/' + path.name] = path.stat().st_size
    if app_only:
        regular(output / 'Info.plist')
        info = plistlib.loads((output / 'Info.plist').read_bytes())
        metadata = plistlib.loads((output / 'NativeBuild.plist').read_bytes())
        for name, size in resources.items():
            path = output / name
            regular(path)
            if path.stat().st_size != size:
                raise ValueError('Staged resource size differs from the verified input: ' + name)
    else:
        regular(output)
        with zipfile.ZipFile(output) as archive:
            prefix = 'Payload/DmIOS.app/'
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError('IPA has duplicate archive entries')
            info = plistlib.loads(archive.read(prefix + 'Info.plist'))
            metadata = plistlib.loads(archive.read(prefix + 'NativeBuild.plist'))
            for name, size in resources.items():
                if archive.getinfo(prefix + name).file_size != size:
                    raise ValueError('Packaged resource size differs from the verified input: ' + name)
    if info.get('CFBundleIdentifier') != bundle or metadata != {
            'BundleIdentifier': bundle, 'CloudContainer': cloud, 'RequiresExtendedVirtualAddressing': True, 'GameTitleID': TITLE}:
        raise ValueError('The built app metadata does not match the private game/signing profile')


def fingerprint_files(root: Path, paths) -> dict:
    """Capture byte identities without recording file contents or credentials."""
    result = {}
    for path in sorted(set(paths)):
        regular(path)
        result[path.relative_to(root).as_posix()] = sha(path)
    return result


def capture_source_files() -> list[Path]:
    paths = {REPO / name for name in CAPTURE_SOURCE_REQUIRED}
    for directory in ('dm/host', 'dm/gfx', 'dm/third_party'):
        paths.update(path for path in (REPO / directory).rglob('*') if path.is_file() and
                     path.suffix.lower() in ('.c', '.h', '.m', '.s', '.inc') and not any(
                         part in ('gen', 'Gen', 'tests', 'dmsh_xlate_bin', 'flip') for part in path.relative_to(REPO).parts))
    return sorted(paths)


def capture_snapshot(source: Path, rewritten: Path, profile: Path, host: Path) -> dict:
    extraction = verify_extraction(source)
    source_files = fingerprint_files(REPO, capture_source_files())
    rewritten_files = fingerprint_files(rewritten, [p for p in rewritten.iterdir() if p.is_file() and
        (p.name.endswith(('.patched.bin', '.fixups.tsv', '.gates.tsv', '.cuts.tsv', '.obs.tsv')) or p.name in ('nro_catalog.c', 'nro_catalog.json'))])
    return {'modules': extraction['modules'], 'nrrs': {p.relative_to(source / 'RomFS').as_posix(): sha(p)
            for p in (source / 'RomFS/.nrr').rglob('*.nrr') if p.is_file()}, 'host_binary': sha(host),
            'source_files': source_files, 'rewritten_files': rewritten_files,
            'profile_files': fingerprint_files(profile, [p for p in profile.rglob('*') if p.is_file()])}


def build_capture_host(profile: Path, rewritten: Path, work: Path, env: dict, jobs: int) -> Path:
    """Mirror the native host build with every object/header/binary external."""
    build = work / 'capture-build'
    include = profile / '.generated'
    include.mkdir(parents=True)
    build.mkdir(parents=True)
    run([sys.executable, REPO / 'dm/games/game.py', 'header', TITLE, include / 'game_profile.h'], work, 'capture-profile-header', env)
    vpx = REPO / 'dm/third_party/libvpx'
    objects, commands = [], []
    for source in sorted(vpx.rglob('*.c')):
        output = build / 'vpx' / source.relative_to(vpx).with_suffix('.o')
        output.parent.mkdir(parents=True, exist_ok=True)
        objects.append(output)
        commands.append(['clang', '-O2', '-g', '-I' + str(vpx), '-I' + str(vpx / 'config'), '-c', str(source), '-o', str(output)])
    print('[capture-vp9-build]', flush=True)
    with (work / 'logs/capture-vp9-build.log').open('w') as stream:
        def compile_one(command):
            return command, subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True)
        with ThreadPoolExecutor(jobs) as pool:
            results = list(pool.map(compile_one, commands))
        for command, result in results:
            stream.write(json.dumps(command) + '\n' + result.stdout + result.stderr)
        if any(result.returncode for _, result in results):
            raise ValueError('Capture host VP9 compilation failed; see logs/capture-vp9-build.log')
    library = build / 'libvpx.a'
    run(['ar', 'rcs', library, *objects], work, 'capture-vp9-library', env)
    host_dir = REPO / 'dm/host'
    sources = [host_dir / name for name in ('main.c', 'loader.c', 'hle.c', 'crash.c', 'probe.c', 'thread.c', 'memstat.m', 'front_mac.m', 'entry.S')]
    sources += sorted(host_dir.glob('hle_*.c')) + [rewritten / 'nro_catalog.c']
    for pattern in ('*.c', 'nvn/*.c', 'nvn/*.m', 'nvn/*.S', 'tex/*.c', 'tex/*.m', 'vk/*.m'):
        sources += sorted((REPO / 'dm/gfx').glob(pattern))
    host = build / 'dmhost'
    command = ['clang', '-O1', '-g', '-Wall', '-Wno-unused-function', '-fobjc-arc']
    for path in (host_dir, REPO / 'dm/gfx/nvn/include', REPO / 'dm/third_party/vulkan-headers/include',
                 include, profile, vpx, REPO / 'dm/third_party/stb_vorbis'):
        command.append('-I' + str(path))
    command += ['-o', str(host), *map(str, sources), str(library)]
    for name in ('Cocoa', 'QuartzCore', 'Metal', 'AudioToolbox', 'VideoToolbox', 'CoreMedia', 'CoreVideo', 'IOSurface', 'ImageIO', 'UniformTypeIdentifiers'):
        command += ['-framework', name]
    run(command, work, 'capture-host-build', env)
    regular(host)
    return host


def run_owned_capture(command: list[str], environment: dict, log: Path, seconds: float) -> dict:
    """Bound only our new process group; never attach to or kill another game."""
    started = datetime.datetime.now(datetime.timezone.utc)
    monotonic = time.monotonic()
    termination = 'exited'
    with log.open('w') as stream:
        process = subprocess.Popen(command, env=environment, cwd=log.parent, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            termination = 'timeout'
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise ValueError('Capture host required SIGKILL; partial capture is not accepted')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    ended = datetime.datetime.now(datetime.timezone.utc)
    if code != 0 and not (termination == 'timeout' and code == -signal.SIGTERM):
        raise ValueError(f'Capture host failed with exit {code}; inspect {log}')
    return {'started_at': started.isoformat(), 'ended_at': ended.isoformat(), 'elapsed_seconds': time.monotonic() - monotonic,
            'max_seconds': seconds, 'max_frames': None, 'exit_code': code, 'termination': termination, 'process_group_owned': True}


def paired_fingerprints(before: dict, after: dict) -> list[dict]:
    if before != after:
        raise ValueError('Capture inputs changed while the host was running')
    return [{'path': path, 'sha256_before': digest, 'sha256_after': after[path]} for path, digest in sorted(before.items())]


def checked_fingerprints(root: Path, records, path_field='path') -> dict:
    """Rehash actual files: a receipt's claims alone never admit game inputs."""
    if not isinstance(records, list) or len(records) > 20000:
        raise ValueError('Invalid capture fingerprint list')
    result = {}
    for item in records:
        name = item[path_field]
        relative = Path(name)
        if not isinstance(name, str) or relative.is_absolute() or '..' in relative.parts or name in result:
            raise ValueError('Invalid or duplicate capture fingerprint path')
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Capture fingerprint escapes its root')
        regular(path)
        digest = item['sha256_before']
        if not re.fullmatch('[0-9a-f]{64}', digest) or digest != item['sha256_after'] or sha(path) != digest:
            raise ValueError('Capture fingerprint differs from actual unchanged bytes: ' + name)
        result[name] = digest
    return result


def registration_census_proof(directory: Path, keys: set[str]) -> dict:
    """Reconcile the runtime ledger and bind its exact bytes into the receipt."""
    sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
    import smash_shaders
    return dict(smash_shaders.validate_registration_census(directory, keys), file='registration-census.jsonl')


def validate_capture(directory: Path, source: Path, nro_source: Path) -> dict:
    """Admit only bounded, exact-build captures with revalidated local evidence.

    The receipt is a local audit record, not an authenticity signature. Its
    producer, executable inputs and payloads must still exist unchanged.
    """
    directory = outside(directory)
    receipt = directory / 'capture-provenance.json'
    regular(receipt)
    if receipt.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Capture receipt exceeds its size bound')
    data = json.loads(receipt.read_text())
    if any(data.get(k) != v for k, v in {'schema': 1, 'kind': 'smash-nvn-shader-capture', 'title_id': TITLE, 'build': 'v2031616'}.items()):
        raise ValueError('Unsupported capture identity/schema')
    extraction = verify_extraction(source)
    if set(data['modules']) != set(MODULES):
        raise ValueError('Capture module set differs')
    for name, expected in extraction['modules'].items():
        entry = data['modules'][name]
        if entry.get('sha256_before') != expected['sha256'] or entry.get('sha256_after') != expected['sha256'] or entry.get('build_id') != expected['build_id']:
            raise ValueError('Capture original module identity differs')
    nrrs = checked_fingerprints(source / 'RomFS', data['nrrs'], 'relative_path')
    actual_nrrs = fingerprint_files(source / 'RomFS', (source / 'RomFS/.nrr').rglob('*.nrr'))
    if nrrs != actual_nrrs:
        raise ValueError('Capture NRR set differs')
    producer = data['producer']
    host_record = producer['host_binary']
    host = outside(Path(host_record['path']))
    checked_fingerprints(host.parent, [dict(host_record, path=host.name)])
    sources = checked_fingerprints(REPO, producer['source_files'])
    required_sources = {p.relative_to(REPO).as_posix() for p in capture_source_files()}
    if not required_sources.issubset(sources):
        raise ValueError('Capture is missing required source fingerprints')
    rewritten = outside(Path(producer['rewritten_root']))
    recorded_rewritten = checked_fingerprints(rewritten, producer['rewritten_files'])
    verify_rewritten(rewritten, nro_source, extraction)
    required_rewritten = {p.name for p in rewritten.iterdir() if p.is_file() and (
        p.name.endswith(('.patched.bin', '.fixups.tsv', '.gates.tsv', '.cuts.tsv', '.obs.tsv')) or p.name in ('nro_catalog.c', 'nro_catalog.json'))}
    if not required_rewritten.issubset(recorded_rewritten):
        raise ValueError('Capture is missing rewritten module fingerprints')
    profile = outside(Path(producer['profile_root']))
    profiles = checked_fingerprints(profile, producer['profile_files'])
    if not {'game.tsv', 'dmsh_chain.h', 'shader_map.tsv', 'c1_full.tsv', 'cb_extent.tsv', '.generated/game_profile.h'}.issubset(profiles):
        raise ValueError('Capture is missing frozen profile/header fingerprints')
    if profiles != fingerprint_files(profile, (p for p in profile.rglob('*') if p.is_file())):
        raise ValueError('Capture frozen profile file set differs')
    if producer['command'] != [str(host), str(rewritten)]:
        raise ValueError('Capture command does not identify its verified host/modules')
    environment, bounded = producer['environment'], data['bounded_run']
    if not isinstance(environment, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in environment.items()):
        raise ValueError('Invalid capture environment')
    if outside(Path(environment['DM_NVN_SHDUMP'])) != directory or outside(Path(environment['DM_SAVE'])) != outside(Path(bounded['disposable_save_path'])):
        raise ValueError('Capture output/disposable save paths differ from its command')
    # A matching original extraction can live at a different private path.
    producer_source = outside(Path(environment['DM_ROMFS'])).parent
    if verify_extraction(producer_source) != extraction:
        raise ValueError('Capture executed a different original game build')
    if bounded.get('process_group_owned') is not True or bounded.get('disposable_save_created_fresh') is not True or bounded.get('input_script') != environment.get('DM_KEYS', ''):
        raise ValueError('Capture lacks owned-process/disposable-save/input evidence')
    seconds, frames, elapsed = bounded['max_seconds'], bounded['max_frames'], bounded['elapsed_seconds']
    if type(seconds) not in (int, float) or not 1 <= seconds <= 600 or type(elapsed) not in (int, float) or not 0 <= elapsed <= seconds + 10 or (frames is not None and (type(frames) is not int or frames <= 0)):
        raise ValueError('Capture run bounds are invalid')
    start, end = (datetime.datetime.fromisoformat(bounded[k]) for k in ('started_at', 'ended_at'))
    if start.utcoffset() != datetime.timedelta(0) or end.utcoffset() != datetime.timedelta(0) or end < start or abs((end - start).total_seconds() - elapsed) > 2:
        raise ValueError('Capture run timestamps are inconsistent')
    code, termination = bounded['exit_code'], bounded['termination']
    if type(code) is not int or termination not in ('exited', 'timeout') or (termination == 'timeout' and elapsed < seconds - 1) or (code != 0 and not (termination == 'timeout' and code == -signal.SIGTERM)):
        raise ValueError('Crashing or forcibly killed captures are not accepted')
    captures = data['captures']
    if not isinstance(captures, list) or len(captures) > CAPTURE_UNIQUE_LIMIT:
        raise ValueError('Invalid capture payload count')
    registration_requested = environment.get('DM_NVN_SHDUMP_REGISTER') == '1'
    expected_files, keys, total_bytes = {'capture-provenance.json'}, set(), 0
    if registration_requested:
        expected_files.add('registration-census.jsonl')
    for entry in captures:
        key = entry['key']
        if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{16}', key) or key in keys:
            raise ValueError('Invalid or duplicate capture key')
        keys.add(key)
        for suffix, label in (('ctl', 'control'), ('code', 'code')):
            path = directory / (key + '.' + suffix)
            regular(path)
            size = path.stat().st_size
            total_bytes += size
            if not 0 < size <= (0x880 if suffix == 'ctl' else (1 << 24) - 1) or total_bytes > 1024 * 1024 * 1024:
                raise ValueError('Capture payload exceeds its size bound')
            if size != entry[label + '_bytes'] or sha(path) != entry[label + '_sha256']:
                raise ValueError('Capture payload differs from its recorded bytes')
            expected_files.add(path.name)
    if {p.name for p in directory.iterdir()} != expected_files:
        raise ValueError('Capture payload file set differs from its receipt')
    if keys:
        sys.path.insert(0, str(REPO / 'dm/gfx/tools'))
        import smash_shaders
        parsed = smash_shaders.load_nvn_capture_directory(directory)
        if {item.name for item in parsed} != keys:
            raise ValueError('Capture intrinsic keys differ from its receipt')
    census = registration_census_proof(directory, keys) if registration_requested else None
    if data.get('registration_census') != census:
        raise ValueError('Capture registration census differs from its bound receipt')
    return {'pairs': len(keys), 'receipt_sha256': sha(receipt), 'directory': str(directory),
            'source_files': len(sources), 'rewritten_files': len(recorded_rewritten), 'profile_files': len(profiles),
            'registration_census_requested': registration_requested, 'registration_census': census}


def capture_runtime_environment(source: Path, profile: Path, mac_root: Path, capture: Path, disposable: Path, route: str,
                                screenshots: Path | None = None) -> dict:
    """Allow only minimal environment and explicit disposable runtime paths."""
    runtime_env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'LOGNAME') if key in os.environ}
    runtime_env.update(DM_ROMFS=str(source / 'RomFS'), DM_SAVE=str(disposable / 'save'), DM_TEMP=str(disposable / 'temp'),
                       DM_MSL_DIR=str(mac_root), DM_NVN_SHMAP=str(profile / 'shader_map.tsv'), DM_NVN_SHDUMP=str(capture),
                       DM_NVN_SHDUMP_REGISTER='1', DM_BOOTPROF='1', DM_KEYS=CAPTURE_ROUTES[route], DM_NVN_FRAMES='0')
    if screenshots:
        runtime_env['DM_NVN_SHOT'] = '1200,2400,3600,4800:' + str(screenshots / 'frame-%d.png')
    return runtime_env


def capture_runtime(source: Path, rewritten: Path, profile: Path, mac_root: Path, work: Path, env: dict, jobs: int,
                    seconds: int, route: str = 'match', screenshots: bool = False) -> Path:
    """Run a bounded windowless match/menu route with disposable save/temp."""
    frozen = work / 'capture-profile' / TITLE
    shutil.copytree(profile, frozen)
    sources_before_build = fingerprint_files(REPO, capture_source_files())
    rewritten_before_build = fingerprint_files(rewritten, (p for p in rewritten.iterdir() if p.is_file()))
    build_env = dict(env, DM_GAMES_DIR=str(frozen.parent))
    host = build_capture_host(frozen, rewritten, work, build_env, jobs)
    capture = work / 'runtime-capture'
    capture.mkdir()
    disposable = work / 'capture-run'
    for name in ('save', 'temp'):
        (disposable / name).mkdir(parents=True)
    shots = work / 'capture-frames' if screenshots else None
    if shots:
        shots.mkdir()
    # An explicit small environment avoids inheriting real save/device paths,
    # watchdog alarms, capture switches or account credentials from the shell.
    runtime_env = capture_runtime_environment(source, frozen, mac_root, capture, disposable, route, shots)
    before = capture_snapshot(source, rewritten, frozen, host)
    if before['source_files'] != sources_before_build or rewritten_before_build != fingerprint_files(rewritten, (p for p in rewritten.iterdir() if p.is_file())):
        raise ValueError('Capture source/modules changed while its host was compiling')
    command = [str(host), str(rewritten)]
    print(f'[runtime-capture: {route} route; at most {seconds} seconds; disposable progress]', flush=True)
    bounded = run_owned_capture(command, runtime_env, work / 'logs/runtime-capture.log', seconds)
    after = capture_snapshot(source, rewritten, frozen, host)
    if before != after:
        raise ValueError('Capture host/source/game/profile identity changed during execution')
    bounded.update(input_route=route, input_script=runtime_env['DM_KEYS'], disposable_save_path=runtime_env['DM_SAVE'], disposable_save_created_fresh=True)
    captures = []
    for control in sorted(capture.glob('*.ctl')):
        code = control.with_suffix('.code')
        regular(code)
        captures.append({'key': control.stem, 'control_sha256': sha(control), 'code_sha256': sha(code),
                         'control_bytes': control.stat().st_size, 'code_bytes': code.stat().st_size})
    record = {'schema': 1, 'kind': 'smash-nvn-shader-capture', 'title_id': TITLE, 'build': 'v2031616',
        'modules': {name: {'build_id': value['build_id'], 'sha256_before': value['sha256'], 'sha256_after': after['modules'][name]['sha256']}
                    for name, value in before['modules'].items()},
        'nrrs': [{'relative_path': path, 'sha256_before': digest, 'sha256_after': after['nrrs'][path]} for path, digest in sorted(before['nrrs'].items())],
        'producer': {'host_binary': {'path': str(host), 'sha256_before': before['host_binary'], 'sha256_after': after['host_binary']},
                     'source_files': paired_fingerprints(before['source_files'], after['source_files']),
                     'rewritten_files': paired_fingerprints(before['rewritten_files'], after['rewritten_files']),
                     'profile_files': paired_fingerprints(before['profile_files'], after['profile_files']),
                     'profile_root': str(frozen), 'rewritten_root': str(rewritten), 'command': command, 'environment': runtime_env},
        'bounded_run': bounded, 'captures': captures,
        'registration_census': registration_census_proof(capture, {entry['key'] for entry in captures})}
    (capture / 'capture-provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    return capture


def prepare_shader_corpus(source: Path, shader_source: Path, ui_source: Path, effect_source: Path, profile: Path, work: Path,
                          env: dict, allow_gap: bool, label: str, capture: Path | None = None,
                          cached_ios: Path | None = None, cached_manifest: Path | None = None) -> tuple:
    """Split and reconcile one corpus, then generate guards from validated MSL."""
    root = work / 'shader' / label
    command = [sys.executable, REPO / 'dm/gfx/tools/shader_split.py', source / 'RomFS', source / 'ExeFS/main',
               root / 'package', profile / 'shader_map.tsv', profile / 'shader_facts.tsv', profile / 'shader_pairs.tsv',
               '--smash-shaders', shader_source, '--smash-ui-shaders', ui_source, '--smash-effect-shaders', effect_source]
    if capture:
        command += ['--nvn-shader-capture', capture]
    run(command, work, label + '-shader-split', env)
    run([sys.executable, REPO / 'dm/gfx/tools/dmsh_chain.py', '--check-tools'], work, label + '-shader-toolchain', env)
    chain = run([sys.executable, REPO / 'dm/gfx/tools/dmsh_chain.py', '--header'], work, label + '-shader-chain', env, True).strip()
    if not re.fullmatch(r'[0-9a-f]{12}', chain):
        raise ValueError('Shader chain command did not produce a valid chain identifier')
    ios = cached_ios or root / 'ios'
    manifest = cached_manifest or root / 'mac' / ('b-' + chain) / '_b_build.json'
    if not cached_ios:
        run([sys.executable, REPO / 'dm/gfx/tools/dmsh_build.py', root / 'package', root / 'mac'],
            work, label + '-shader-compile', dict(env, IOSOUT=str(ios)))
    completeness = validate_shaders(profile, ios, manifest, chain, allow_gap)
    (work / (label + '-shader-completeness.json')).write_text(json.dumps(completeness, indent=2) + '\n')
    for script, table in (('c1_guard.py', 'c1_full.tsv'), ('cb_extent.py', 'cb_extent.tsv')):
        run([sys.executable, REPO / 'dm/gfx/tools' / script, manifest.parent, profile / table], work, label + '-' + table[:-4], env)
        if not (profile / table).read_text().startswith('# chain b-' + chain + ' '):
            raise ValueError('Constant-buffer guard table has the wrong translation chain')
    return ios, manifest, chain, completeness


def release_preparation_scratch(work: Path) -> None:
    """Release only this fresh build's intermediates before large app staging."""
    manifests = work / 'preparation-manifests'
    manifests.mkdir()
    for name in ('arc-modules', 'arc-shaders', 'ui-shader-sources', 'effect-shader-sources'):
        directory = work / name
        if directory.exists():
            shutil.copyfile(directory / 'manifest.json', manifests / (name + '.json'))
            shutil.rmtree(directory)
    for directory in (work / 'tools/rust', work / 'shader/initial/package', work / 'shader/captured/package'):
        if directory.exists():
            shutil.rmtree(directory)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--base', type=Path, help='your base-game NSP or XCI; also requires --update and --keys')
    source.add_argument('--extracted-dir', type=Path, help='your complete merged 13.0.5 folder containing ExeFS/ and RomFS/')
    parser.add_argument('--update', type=Path, help='your update 13.0.5 NSP (v2031616)')
    parser.add_argument('--keys', type=Path, help='your prod.keys; required with --base')
    parser.add_argument('--work', type=Path, required=True, help='new private build directory outside the checkout and inputs')
    parser.add_argument('--bundle-id', required=True, help='your explicit App ID; retain it and the signing team for updates')
    parser.add_argument('--cloud-container', default='', help='opt into your own CloudKit container; off by default')
    parser.add_argument('--frame-generation', choices=('off', 'on'), default='off', help='optional generated frames; 60 Hz simulation remains unchanged')
    parser.add_argument('--show-fps', action='store_true')
    parser.add_argument('--app-only', action='store_true', help='stage an unsigned .app with APFS clones, avoiding an IPA round trip')
    parser.add_argument('--output', type=Path, help='new private .app or .ipa output; defaults inside --work')
    parser.add_argument('--shaders', type=Path, help='reuse an existing private iOS shader root containing b-CHAIN/')
    parser.add_argument('--shader-manifest', type=Path, help='corresponding Mac b-CHAIN/_b_build.json; required with --shaders')
    parser.add_argument('--rewritten', type=Path, help='reuse existing exact-build static modules and all 98 rewritten NROs')
    capture = parser.add_mutually_exclusive_group()
    capture.add_argument('--nvn-shader-capture', type=Path, help='reuse a bounded local Mac capture, including its unchanged producer and provenance receipt')
    capture.add_argument('--capture-runtime', action='store_true', help='build a private Mac host and capture original shader inputs using disposable progress')
    parser.add_argument('--capture-route', choices=tuple(CAPTURE_ROUTES), default='match', help='bounded Mac input route (default match); does not cover all fighters/stages')
    parser.add_argument('--capture-seconds', type=int, help='owned Mac capture timeout, 1–600 seconds (default match 105, menus 32); no frame-cap claim')
    parser.add_argument('--capture-screenshots', action='store_true', help='write four private route-check screenshots outside the shader-capture payload directory')
    parser.add_argument('--allow-known-geometry-gap', action='store_true', help='explicitly permit only the documented CharacterDamageModel2GS failure')
    parser.add_argument('--prepare-only', action='store_true', help='verify/extract/rewrite/prepare shaders and receipts, without building an app')
    parser.add_argument('--jobs', type=int, default=min(os.cpu_count() or 8, 8), help='parallel shader workers, 1–64 (default at most 8)')
    args = parser.parse_args(argv)
    if args.capture_seconds is None:
        args.capture_seconds = CAPTURE_TIMEOUTS[args.capture_route]
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', args.bundle_id):
        raise ValueError('Use a valid explicit bundle ID, such as com.yourname.smash')
    if not 1 <= args.jobs <= 64:
        raise ValueError('--jobs must be between 1 and 64')
    if not 1 <= args.capture_seconds <= 600:
        raise ValueError('--capture-seconds must be between 1 and 600')
    if args.base and not (args.update and args.keys):
        raise ValueError('--base requires --update and --keys')
    if args.extracted_dir and (args.update or args.keys):
        raise ValueError('--update and --keys apply only to --base input')
    if bool(args.shaders) != bool(args.shader_manifest):
        raise ValueError('--shaders and --shader-manifest must be provided together')
    paths = {name: outside(value) for name, value in vars(args).items() if isinstance(value, Path)}
    work = paths['work']
    if work.exists():
        raise ValueError('--work must be a new directory; previous builds are never overwritten')
    source_inputs = [path for name, path in paths.items() if name not in ('work', 'output')]
    if any(path == work or path.is_relative_to(work) or work.is_relative_to(path) for path in source_inputs):
        raise ValueError('Keep the new work directory separate from every input/cache path')
    output = paths.get('output', work / ('SuperSmashBrosUltimate-unsigned.app' if args.app_only else 'SuperSmashBrosUltimate-unsigned.ipa'))
    if output.exists() or output.suffix != ('.app' if args.app_only else '.ipa') or any(
            output == path or output.is_relative_to(path) for path in source_inputs):
        raise ValueError('Choose a new output path with the matching .app/.ipa suffix outside the inputs')
    for name in ('base', 'update', 'keys', 'shader_manifest'):
        if name in paths:
            regular(paths[name])
    if args.base and (paths['base'].suffix.lower() not in ('.nsp', '.xci') or paths['update'].suffix.lower() != '.nsp'):
        raise ValueError('Use an extracted base .nsp/.xci and update .nsp; unpack your own archives first')
    check_tools()
    # Use the inherited shared lock: both builders generate the same Gen/ link.
    with (REPO / '.odyssey-build.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another build is using this checkout; wait until it finishes') from error
        work.mkdir(parents=True)
        for name in ('logs', 'tmp', 'tools'):
            (work / name).mkdir()
        profile = make_profile(work, args.cloud_container, args.frame_generation == 'on')
        env = dict(os.environ, GAME=TITLE, DM_GAME=TITLE, DM_GAMES_DIR=str(profile.parent), DM_GAMES_FIRST='1',
                   DM_ROOT=str(work), WORK=str(work / 'tmp'), J=str(args.jobs), PYTHONDONTWRITEBYTECODE='1',
                   DM_BUNDLE_ID=args.bundle_id, DM_DISPLAY_NAME='Super Smash Bros. Ultimate', DM_APP_VERSION='13.0.5',
                   DM_SHOW_FPS='1' if args.show_fps else '0', AOC='', FONT_PY=sys.executable, GFXAPI='nvn',
                   DMSH_CAS=str(work / 'shader/cas'), XLATE_DEBUG='1', XLATE_REDUCED='1', DM_COMPILE_ONLY='0')
        # A previous game's shell environment must not inject captures, assets,
        # runtime diagnostics or signing metadata into this deterministic build.
        for name in ('DM_ENV_FILE', 'DM_GLSLC_CAPTURE', 'DM_UE_SHADERS', 'DM_SMASH_SHADERS',
                     'DM_SMASH_UI_SHADERS', 'DM_SMASH_EFFECT_SHADERS', 'DMSH_PREFILL', 'ODYSSEY_PRESET', 'ODYSSEY_CLOUD_CONTAINER'):
            env.pop(name, None)
        source = paths['extracted_dir'] if args.extracted_dir else extract_packages(paths['base'], paths['update'], paths['keys'], work, env)
        extraction = verify_extraction(source)
        nro_source, shader_source, ui_source, effect_source = arc_extract(source, work, env)
        source_manifests = {path.name: extraction_manifest_receipt(path) for path in (nro_source, shader_source, ui_source, effect_source)}
        rewritten = paths.get('rewritten', work / 'rewritten')
        if not args.rewritten:
            for module in MODULES:
                run([sys.executable, REPO / 'dm/tools/patch_nso.py', source / 'ExeFS' / module, rewritten, module], work, 'rewrite-' + module, env)
            run([sys.executable, REPO / 'tools/smash_nro.py', 'prepare', nro_source, rewritten,
                 '--nrr-dir', source / 'RomFS/.nrr', '--rewrite'], work, 'rewrite-98-nros', env)
        verify_rewritten(rewritten, nro_source, extraction)
        capture_path = paths.get('nvn_shader_capture')
        capture_record = validate_capture(capture_path, source, nro_source) if capture_path else None
        ios, manifest, chain, completeness = prepare_shader_corpus(source, shader_source, ui_source, effect_source, profile, work, env,
            args.allow_known_geometry_gap, 'initial', capture_path if capture_record and capture_record['pairs'] else None,
            paths.get('shaders'), paths.get('shader_manifest'))
        if args.capture_runtime:
            capture_path = capture_runtime(source, rewritten, profile, manifest.parent.parent, work, env, args.jobs,
                                           args.capture_seconds, args.capture_route, args.capture_screenshots)
            capture_record = validate_capture(capture_path, source, nro_source)
            if capture_record['pairs']:
                # Never mutate the frozen producer profile or supplied shader caches.
                final_env = dict(env, DMSH_PREFILL=str(manifest.parent.parent) + '=' + str(ios))
                ios, manifest, chain, completeness = prepare_shader_corpus(source, shader_source, ui_source, effect_source, profile, work,
                    final_env, args.allow_known_geometry_gap, 'captured', capture_path)
        # Inputs are read-only throughout preparation; repeat the original NSO
        # identity check before embedding any executable content in the app.
        if verify_extraction(source) != extraction:
            raise ValueError('Input identity changed during the build')
        receipt = {'format': 1, 'title_id': TITLE, 'version': '13.0.5', 'inputs': extraction,
                   'profile': str(profile), 'rewritten': str(rewritten), 'shaders': str(ios), 'shader_manifest': str(manifest),
                   'completeness': completeness, 'capture': capture_record, 'source_manifests': source_manifests,
                   'cloud_enabled': bool(args.cloud_container), 'app_built': False}
        if not args.prepare_only:
            release_preparation_scratch(work)
            output.parent.mkdir(parents=True, exist_ok=True)
            env.update(W=str(work / 'app-build'), PATCHED=str(rewritten), ROMFS=str(source / 'RomFS'), MSL_IOS=str(ios),
                       DM_APP_ONLY='1' if args.app_only else '0', DM_ICON=str(source / 'icon.jpg'))
            run(['bash', REPO / 'dm/ios/tools/build_ipa.sh', output], work, 'app-build', env)
            validate_product(output, args.app_only, source, ios, chain, args.bundle_id, args.cloud_container)
            receipt.update(app_built=True, output=str(output))
        (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(f'Prepared {completeness["compiled"]:,}/{completeness["expected"]:,} shaders; receipt: {work / "receipt.json"}')
        if completeness['known_geometry_gap']:
            print('The explicitly accepted geometry shader gap remains; see docs/VALIDATION.md')
        if not args.prepare_only:
            print(f'Unsigned {"app" if args.app_only else "IPA"}: {output}\nNext: python tools/sign_install.py --help')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'Build stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
