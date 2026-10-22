#!/usr/bin/env python3
"""Strict SSBH shader records and named Nufx stage relationships, without ARC expansion.

The SSBH layouts follow the MIT-licensed ultimate-research/ssbh_lib definitions
at 08f8bc4470a7d480dfc9b64d7e08e97f3820fed7:
  ssbh_lib/src/formats/{shdr,nufx}.rs and ssbh_lib/src/lib.rs.
https://github.com/ultimate-research/ssbh_lib/tree/08f8bc4470a7d480dfc9b64d7e08e97f3820fed7
Original parsing implementation; no upstream source or game bytes are vendored.
GLSLC control/code validation follows shader_split.py's original NVN convention.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import struct

ARC_MAGIC = bytes.fromhex('1032547698efcdab')
CTL_MAGIC = bytes.fromhex('34127698')
GFX_MAGIC = bytes.fromhex('78563412')
CS_MAGIC = bytes.fromhex('79563412')
GLSLC_MAGIC = bytes.fromhex('91688619')
SHDR_STAGES = {0: 'vs', 3: 'gs', 4: 'ps', 5: 'cs'}
SPH_STAGES = {1: 'vs', 2: 'hs', 3: 'ds', 4: 'gs', 5: 'ps'}
STAGES = ('vs', 'hs', 'ds', 'gs', 'ps', 'cs')
MAX_RECORDS = 1_000_000
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_DIRECTORY_BYTES = 1024 * 1024 * 1024
MAX_STRING_BYTES = 4096


class ShaderFormatError(ValueError):
    """An unsupported or malformed structure must not silently lose a shader."""


class Reader:
    """Bound every traversed field, relative pointer, array and string."""

    def __init__(self, data, label):
        self.data, self.label = data, label

    def fail(self, message):
        raise ShaderFormatError(f'{self.label}: {message}')

    def span(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.data) or size > len(self.data) - offset:
            self.fail(f'range {offset:#x}+{size:#x} is out of bounds ({len(self.data):#x} bytes)')
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        self.span(offset, struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, offset)

    def array(self, field, stride, max_count=MAX_RECORDS):
        relative, count = self.unpack('<QQ', field)
        if count > max_count:
            self.fail(f'array at {field:#x} has excessive count {count}')
        if count and not relative:
            self.fail(f'nonempty array at {field:#x} has a null pointer')
        start = field + relative if relative else 0
        if relative or count:
            self.span(start, count * stride)
        return start, count

    def string(self, field, nonempty=False):
        relative, = self.unpack('<Q', field)
        if not relative:
            if nonempty:
                self.fail(f'null name at {field:#x}')
            return ''
        start = field + relative
        self.span(start, 1)
        end = self.data.find(b'\0', start, min(len(self.data), start + MAX_STRING_BYTES + 1))
        if end < 0:
            self.fail(f'unterminated or excessive string at {start:#x}')
        try:
            value = self.data[start:end].decode('utf-8')
        except UnicodeDecodeError as error:
            self.fail(f'invalid UTF-8 string at {start:#x}: {error}')
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            self.fail(f'control character in string at {start:#x}')
        if nonempty and not value:
            self.fail(f'empty name at {field:#x}')
        return value

    def header(self, magic, versions):
        if self.span(0, 4) != b'HBSS' or self.unpack('<QI', 4) != (64, 0):
            self.fail('unsupported SSBH header')
        if self.span(16, 4) != magic:
            self.fail(f'expected SSBH {magic.decode()}')
        version = self.unpack('<HH', 20)
        if version not in versions:
            self.fail(f'unsupported {magic.decode()} version {version[0]}.{version[1]}')
        return version


@dataclass(frozen=True)
class Shader:
    name: str
    stage: str
    control: bytes
    code: bytes
    source: str


@dataclass(frozen=True)
class Program:
    name: str
    render_pass: str
    stages: dict


@dataclass
class Bundle:
    shaders: dict
    pairs: set
    programs: int
    nushdb_files: int
    nufxlb_files: int


def glslc_parts(blob, stage, label):
    """Retain original control and complete code area, including c1 constants.

    Unlike the SSBH high-level decompiler view, do not strip the 0x30-byte code
    header or truncate the area to the instruction count. The native host hashes
    the original control+code and reads constant data from that same code area.
    """
    r = Reader(blob, label)
    if r.span(0, 4) != GLSLC_MAGIC:
        r.fail('shader binary is not a GLSLC compiler output')
    size, = r.unpack('<I', 0x44)
    if size != len(blob):
        r.fail(f'GLSLC declared length {size} differs from blob length {len(blob)}')
    control_start = blob.find(CTL_MAGIC)
    if control_start < 0 or blob.find(CTL_MAGIC, control_start + 4) >= 0:
        r.fail('GLSLC must contain exactly one original NVN control section')
    control_length, = r.unpack('<I', control_start + 0x20)
    if not 0x760 <= control_length <= MAX_BLOB_BYTES or control_length % 4:
        r.fail(f'invalid NVN control length {control_length:#x}')
    control = r.span(control_start, control_length)
    code_length, = r.unpack('<I', control_start + 0x704)
    if not code_length or code_length > MAX_BLOB_BYTES:
        r.fail(f'invalid NVN code length {code_length:#x}')
    code = r.span(control_start + control_length, code_length)
    constant_start, = struct.unpack_from('<I', control, 0x700)
    if constant_start > len(code):
        r.fail('c1 constant offset exceeds the original code area')
    if stage == 'cs':
        if code[:4] == GFX_MAGIC:
            r.fail('compute shader has a graphics code header')
        if not all(struct.unpack_from('<3I', control, 0x748)):
            r.fail('compute shader has a zero thread-group dimension')
        # SDK 6's compute output can be headerless. A present NVN header must
        # still have the compute magic; otherwise the first word is code.
        if code[:4] == CS_MAGIC and len(code) < 0x30:
            r.fail('truncated compute code header')
    else:
        if len(code) < 0x80 or code[:4] != GFX_MAGIC:
            r.fail('missing or truncated graphics code header')
        actual = SPH_STAGES.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 15)
        if stage != actual:
            r.fail(f'SSBH stage {stage} disagrees with NVN stage {actual}')
    return control, code


def parse_nushdb(data, label):
    """Parse RDHS 1.2 Shader[0x38] records and their original GLSLC blobs."""
    r = Reader(data, label)
    r.header(b'RDHS', {(1, 2)})
    start, count = r.array(24, 0x38)
    out = []
    for i in range(count):
        row = start + i * 0x38
        name = r.string(row, nonempty=True)
        stage_id, kind = r.unpack('<II', row + 8)
        if stage_id not in SHDR_STAGES or kind != 2:
            r.fail(f'shader {name}: unsupported stage {stage_id} / binary kind {kind}')
        blob_start, blob_length = r.array(row + 16, 1, MAX_BLOB_BYTES)
        declared_length, = r.unpack('<Q', row + 32)
        if not blob_length or declared_length != blob_length:
            r.fail(f'shader {name}: binary_size does not match the byte-buffer length')
        if r.span(row + 40, 16) != bytes(16):
            r.fail(f'shader {name}: nonzero reserved record padding')
        stage = SHDR_STAGES[stage_id]
        source = f'{label}#NUSHDB#{name}'
        control, code = glslc_parts(r.span(blob_start, blob_length), stage, source)
        out.append(Shader(name, stage, control, code, source))
    return out


def _material_parameters(r, field):
    start, count = r.array(field, 24)
    for i in range(count):
        # ParamId is opaque metadata, followed by a string and eight padding bytes.
        r.string(start + 24 * i + 8)
        if r.span(start + 24 * i + 16, 8) != bytes(8):
            r.fail('nonzero material parameter padding')


def parse_nufxlb(data, label):
    """Resolve declared stage names; also bound every auxiliary metadata array."""
    r = Reader(data, label)
    version = r.header(b'XFUN', {(1, 0), (1, 1)})
    stride = 96 if version == (1, 1) else 80
    start, count = r.array(24, stride)
    programs = []
    for i in range(count):
        row = start + stride * i
        name = r.string(row, nonempty=True)
        render_pass = r.string(row + 8)
        stages = {stage: r.string(row + 16 + 8 * k) for k, stage in enumerate(STAGES)}
        if stages['cs'] and any(stages[s] for s in STAGES if s != 'cs'):
            r.fail(f'program {name}: compute and graphics stages are mixed')
        if not any(stages.values()):
            r.fail(f'program {name}: no shader stage is declared')
        if version == (1, 1):
            attrs, nattrs = r.array(row + 64, 16)
            for j in range(nattrs):
                r.string(attrs + 16 * j)
                r.string(attrs + 16 * j + 8)
        _material_parameters(r, row + stride - 16)
        programs.append(Program(name, render_pass, stages))
    # Nufx's second array consists of named lists of strings (24-byte UnkItem).
    other, nother = r.array(40, 24)
    for i in range(nother):
        row = other + 24 * i
        r.string(row)
        strings, nstrings = r.array(row + 8, 8)
        for j in range(nstrings):
            r.string(strings + 8 * j)
    return programs


def named_bundle(shader_files, program_files):
    """Join exact shader names and emit only vertex/pixel pairs a program declares."""
    shaders = {}
    for label, data in shader_files:
        for shader in parse_nushdb(data, label):
            previous = shaders.get(shader.name)
            if previous is not None and (previous.stage, previous.control, previous.code) != (
                    shader.stage, shader.control, shader.code):
                raise ShaderFormatError(f'{label}: conflicting definition for shader name {shader.name}')
            shaders.setdefault(shader.name, shader)
    pairs, count = set(), 0
    for label, data in program_files:
        for program in parse_nufxlb(data, label):
            count += 1
            for stage, name in program.stages.items():
                if not name:
                    continue
                shader = shaders.get(name)
                if shader is None:
                    raise ShaderFormatError(f'{label}: program {program.name} references missing shader {name}')
                if shader.stage != stage:
                    raise ShaderFormatError(f'{label}: program {program.name} uses {name} as {stage}, not {shader.stage}')
            vertex, pixel = program.stages['vs'], program.stages['ps']
            if vertex and pixel:
                pairs.add((vertex, pixel))
    if not shaders or not count:
        raise ShaderFormatError('a Smash shader bundle requires both Nushdb shaders and Nufx programs')
    return Bundle(shaders, pairs, count, len(shader_files), len(program_files))


def load_directory(directory):
    """Read only targeted external .nushdb/.nufxlb files, never data.arc itself."""
    root = Path(directory).resolve(strict=True)
    source = Path(__file__).resolve().parents[3]
    if root.is_relative_to(source):
        raise ShaderFormatError('extracted game shaders must be outside the source checkout')
    if not root.is_dir():
        raise ShaderFormatError('Smash shader source must be a directory')
    shader_files, program_files, total = [], [], 0
    for path in sorted(root.iterdir()):
        if path.suffix not in ('.nushdb', '.nufxlb'):
            continue
        if not path.is_file():
            raise ShaderFormatError(f'{path.name}: shader source is not a regular file')
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_DIRECTORY_BYTES:
            raise ShaderFormatError('extracted shader input exceeds bounded directory/file size')
        target = shader_files if path.suffix == '.nushdb' else program_files
        target.append((f'/data.arc/{path.name}', path.read_bytes()))
    return named_bundle(shader_files, program_files)


def _nested_shader_sources(directory, operation, extension):
    """Verify a completed targeted manifest and bounded private shader carriers."""
    root = Path(directory).resolve(strict=True)
    source = Path(__file__).resolve().parents[3]
    if not root.is_dir() or root.is_relative_to(source):
        raise ShaderFormatError('nested shader input must be a private directory outside source')
    manifest = root / 'manifest.json'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 16 * 1024 * 1024:
        raise ShaderFormatError('nested shader manifest exceeds bounded size')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema') != 1 or data.get('operation') != operation:
        raise ShaderFormatError(f'nested shaders require a completed {operation} manifest')
    members = data.get('shader_members')
    if not isinstance(members, list) or not 0 < len(members) <= MAX_RECORDS:
        raise ShaderFormatError('invalid nested shader member count')
    files, total = {}, 0
    for member in members:
        if not isinstance(member, dict):
            raise ShaderFormatError('invalid nested shader member record')
        name, digest = member.get('output', ''), member.get('sha256', '')
        archive, label = member.get('archive_hash40', ''), member.get('member_path', '')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or name != digest + '.bnsh':
            raise ShaderFormatError('invalid nested shader payload name/hash')
        if not isinstance(archive, str) or not re.fullmatch('[0-9a-f]{10}', archive):
            raise ShaderFormatError('invalid nested shader archive identity')
        if not isinstance(label, str) or not label or '\\' in label or any(ord(c) < 32 for c in label) or any(p in ('', '.', '..') for p in label.split('/')):
            raise ShaderFormatError('invalid nested shader member path')
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ShaderFormatError('nested shader payload must be a regular local file')
        size = path.stat().st_size
        if size != member.get('decoded_bytes') or size > MAX_FILE_BYTES:
            raise ShaderFormatError('nested shader payload size mismatch/limit')
        if name not in files:
            total += size
            if total > MAX_DIRECTORY_BYTES:
                raise ShaderFormatError('nested shader payloads exceed bounded total size')
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ShaderFormatError('nested shader payload hash mismatch')
            files[name] = (str(path), f'data.arc/{archive}.{extension}/{label}')
    return [files[name] for name in sorted(files)]


def ui_shader_sources(directory):
    """Validate targeted SARC/BNSH extraction, retaining original member identity."""
    return _nested_shader_sources(directory, 'shader-archives', 'arc')


def effect_shader_sources(directory):
    """Validate EFFN/EFT2 GRSN/GRSC shader carriers without loading full effects.

    Layout reference: MIT EffectLibrary, d5491138d645221ec92189eeff3ded8c43fd0a1a,
    FileData/EFFN/NamcoEffectFile.cs and FileData/EFT2/{Structs,PtclFile,Shaders}.cs.
    https://github.com/KillzXGaming/EffectLibrary/tree/d5491138d645221ec92189eeff3ded8c43fd0a1a
    The Rust extractor validates the wrapper and section bounds; this consumer
    binds every retained original shader payload to its completed private manifest.
    """
    return _nested_shader_sources(directory, 'effect-shaders', 'eff')


def parse_nvn_capture(control, code, key, label):
    """Validate actual NVN dump bytes; never alias a captured key to another shader."""
    r = Reader(control, label)
    if not re.fullmatch('[0-9a-f]{16}', key) or r.span(0, 4) != CTL_MAGIC:
        r.fail('invalid captured key/control magic')
    own, = r.unpack('<I', 0x20)
    nctl = own if 0x760 <= own < 0x880 else 0x880
    if len(control) not in (nctl, 0x880):
        r.fail('capture control length disagrees with NVN hash convention')
    constant_start, length = r.unpack('<II', 0x700)
    if not 0 < length < 1 << 24 or length != len(code) or constant_start > length:
        r.fail('capture code/c1 length mismatch')
    if code[:4] == GFX_MAGIC:
        if len(code) < 0x80:
            r.fail('truncated captured graphics header')
        stage = SPH_STAGES.get((struct.unpack_from('<I', code, 0x30)[0] >> 10) & 15)
        if stage is None:
            r.fail('unrecognized captured graphics stage')
    else:
        stage = 'cs'
        if not all(r.unpack('<3I', 0x748)) or code[:4] == CS_MAGIC and len(code) < 0x30:
            r.fail('invalid captured compute header/dimensions')
    original = control[:nctl]
    if hashlib.sha256(original + code).hexdigest()[:16] != key:
        r.fail('capture filename does not match original control+code hash')
    return Shader(key, stage, original, code, f'{label}#NVN_CAPTURE#{key}')


def load_nvn_capture_directory(directory):
    """Bounded original .ctl/.code pairs observed in a version-gated local run.

    Registration captures include stages that were registered but never drawn;
    the separate census/producer receipt establishes the observation route.
    """
    root = Path(directory).resolve(strict=True)
    source = Path(__file__).resolve().parents[3]
    if not root.is_dir() or root.is_relative_to(source):
        raise ShaderFormatError('NVN captures must be outside the source checkout')
    files = {p.name: p for p in root.iterdir() if p.suffix in ('.ctl', '.code')}
    if not files or len(files) > 2 * MAX_RECORDS:
        raise ShaderFormatError('invalid NVN capture file count')
    total = 0
    for name, path in files.items():
        if not re.fullmatch('[0-9a-f]{16}\\.(ctl|code)', name) or path.is_symlink() or not path.is_file():
            raise ShaderFormatError('NVN capture contains an invalid/nonregular file')
        size = path.stat().st_size
        total += size
        if size > (0x880 if path.suffix == '.ctl' else (1 << 24) - 1) or total > MAX_DIRECTORY_BYTES:
            raise ShaderFormatError('NVN capture exceeds bounded file/directory size')
        if path.with_suffix('.code' if path.suffix == '.ctl' else '.ctl').name not in files:
            raise ShaderFormatError('NVN capture has an orphan control/code file')
    return [parse_nvn_capture(path.read_bytes(), path.with_suffix('.code').read_bytes(), path.stem,
                             f'/nvn_capture/{path.stem}') for name, path in sorted(files.items()) if path.suffix == '.ctl']


def validate_registration_census(directory: Path, expected_keys: set[str]) -> dict:
    """Reconcile an owned register-all run, without claiming unvisited coverage.

    The complete JSONL prefix is valid after an owned timeout: every observed
    program must have all its declared registration stages accounted for, every
    deferred stage must resolve, and every captured original must be present.
    The producer receipt separately binds this ledger and the original pairs.
    """
    root = Path(directory)
    path = root / 'registration-census.jsonl'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64 << 20:
        raise ShaderFormatError('registration census is missing, nonregular or oversized')
    names = ('programs', 'expected_stages', 'register_stages', 'mapped_stages',
             'deferred_stages', 'invalid_stages', 'draw_stages', 'captured_unique',
             'duplicates', 'unresolved_deferred', 'failures', 'bytes_written')
    totals = dict.fromkeys(names, 0)
    programs, registered, pending, captures = {}, set(), set(), {}
    lines = 0
    limits = None
    with path.open('rb') as stream:
        while line := stream.readline(2049):
            if len(line) > 2048 or not line.endswith(b'\n') or lines >= 262144:
                raise ShaderFormatError('registration census has a partial/oversized row or too many events')
            try:
                def unique_pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError('duplicate JSON property')
                        result[key] = value
                    return result
                row = json.loads(line, object_pairs_hook=unique_pairs)
            except (ValueError, UnicodeError) as error:
                raise ShaderFormatError('registration census contains invalid JSON') from error
            if not isinstance(row, dict) or type(row.get('schema')) is not int or row['schema'] != 1 or type(row.get('seq')) is not int or row['seq'] != lines:
                raise ShaderFormatError('registration census schema/sequence mismatch')
            event = row.get('event')
            if lines == 0:
                limits = row.get('limits')
                if event != 'begin' or row.get('mode') != 'register-all' or type(row.get('pid')) is not int or row['pid'] <= 0:
                    raise ShaderFormatError('registration census does not start with register-all')
                if limits != {'unique': 65536, 'events': 262144, 'bytes': 1 << 30, 'ledger_bytes': 64 << 20}:
                    raise ShaderFormatError('registration census has unsupported bounds')
            elif event == 'program':
                serial, count = row.get('serial'), row.get('stages')
                if type(serial) is not int or serial <= 0 or serial in programs or type(count) is not int or not 0 <= count <= 6:
                    raise ShaderFormatError('registration census has an invalid/repeated program')
                if not isinstance(row.get('program'), str) or not re.fullmatch('[0-9a-f]+', row['program']):
                    raise ShaderFormatError('registration census has an invalid program address')
                programs[serial] = count
                totals['programs'] += 1
                totals['expected_stages'] += count
            elif event == 'stage':
                serial, index, origin, status = (row.get(n) for n in ('serial', 'index', 'origin', 'status'))
                if type(serial) is not int or serial not in programs or type(index) is not int or not 0 <= index < programs[serial]:
                    raise ShaderFormatError('registration census stage is outside its declared program')
                stage = serial, index
                if origin == 'register':
                    if stage in registered:
                        raise ShaderFormatError('registration census repeats a registration stage')
                    registered.add(stage)
                    totals['register_stages'] += 1
                elif origin == 'draw':
                    if stage not in registered:
                        raise ShaderFormatError('registration census draws an unregistered stage')
                    totals['draw_stages'] += 1
                else:
                    raise ShaderFormatError('registration census has an invalid stage origin')
                for field in ('control_address', 'code_address'):
                    if not isinstance(row.get(field), str) or not re.fullmatch('[0-9a-f]+', row[field]):
                        raise ShaderFormatError('registration census has an invalid source address')
                nctl, ncode = row.get('control_bytes'), row.get('code_bytes')
                if type(nctl) is not int or not 0x760 <= nctl <= 0x880 or nctl % 4 or type(ncode) is not int or not 0 < ncode < 1 << 24:
                    raise ShaderFormatError('registration census has invalid original byte lengths')
                if status == 'deferred':
                    if row.get('key') != '' or row.get('sha256') != '':
                        raise ShaderFormatError('registration census assigns a key to unread deferred bytes')
                    if origin == 'register':
                        pending.add(stage)
                        totals['deferred_stages'] += 1
                        totals['unresolved_deferred'] += 1
                elif status in ('captured', 'duplicate'):
                    key, digest = row.get('key'), row.get('sha256')
                    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{16}', key) or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or not digest.startswith(key):
                        raise ShaderFormatError('registration census intrinsic key/digest mismatch')
                    if origin == 'register':
                        totals['mapped_stages'] += 1
                    if stage in pending:
                        pending.remove(stage)
                        totals['unresolved_deferred'] -= 1
                    original = digest, nctl, ncode
                    if status == 'captured':
                        if key in captures:
                            raise ShaderFormatError('registration census captures one intrinsic key twice')
                        captures[key] = original
                        totals['captured_unique'] += 1
                        totals['bytes_written'] += nctl + ncode
                    else:
                        if captures.get(key) != original:
                            raise ShaderFormatError('registration census duplicate differs from captured original')
                        totals['duplicates'] += 1
                else:
                    raise ShaderFormatError(f'registration census contains a failed stage: {status}')
            else:
                raise ShaderFormatError('registration census has an unsupported event')
            recorded = row.get('totals')
            if not isinstance(recorded, dict) or set(recorded) != set(names) or any(type(v) is not int or v < 0 for v in recorded.values()) or recorded != totals:
                raise ShaderFormatError('registration census cumulative counters disagree with its events')
            if totals['captured_unique'] > limits['unique'] or totals['bytes_written'] > limits['bytes']:
                raise ShaderFormatError('registration census exceeds its capture bounds')
            lines += 1
    if not programs or not registered or len(registered) != totals['expected_stages'] or pending:
        raise ShaderFormatError('registration census is incomplete or has unresolved deferred stages')
    if set(captures) != set(expected_keys):
        raise ShaderFormatError('registration census captured-key set differs from original pair files')
    for key, (digest, nctl, ncode) in captures.items():
        ctl, code = root / f'{key}.ctl', root / f'{key}.code'
        for file, size in ((ctl, nctl), (code, ncode)):
            if file.is_symlink() or not file.is_file() or file.stat().st_size != size:
                raise ShaderFormatError('registration census original is missing/nonregular or has a different length')
        h = hashlib.sha256(ctl.read_bytes())
        with code.open('rb') as stream:
            while block := stream.read(1 << 20):
                h.update(block)
        if h.hexdigest() != digest:
            raise ShaderFormatError('registration census original digest differs from the actual pair')
    return {'schema': 1, 'mode': 'register-all', 'events': lines, 'totals': totals,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size,
            'coverage': 'all observed valid mapped registrations; deferred stages resolved; unvisited gameplay is unproven'}
