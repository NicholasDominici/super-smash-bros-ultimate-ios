"""Compile exact-build live-aspect research plans without changing game inputs.

This is a resource reflow planner, not an enabled runtime feature. It derives
new canvas, edge, fill and animation values from the canonical preparation.
No executable, archive, app, save, or running process is modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

import smash_aspect as preparation
import smash_aspect_ui as ui

# Independently traced in the supplied original 13.0.5 image. These are research
# admission facts, not new observation registrations or permission to patch code.
LIVE_FACTS = (
    (0x4ec800, 0xd103c3ff),   # common camera update: sub sp,sp,#0xf0
    (0x4ec820, 0x79425814),   # input camera flags +0x12c
    (0x4ee1f8, 0xbd412660),  # vertical FOV +0x124
    (0x4ee20c, 0xbd412a60),  # aspect +0x128
    (0x4ee21c, 0xbd013a69),  # vertical tangent +0x138
    (0x4ee220, 0xbd01366a),  # horizontal tangent +0x134
    (0x4ee230, 0xbd013e60),  # inverse horizontal projection +0x13c
    (0x4ee244, 0xbd014260),  # inverse vertical projection +0x140
    (0x3775ba0, 0xd63f0100), # layout animation update through vtable +0x58
    (0x3775ba4, 0xf9422f28), # candidate after-call site: owner layout +0x458
    (0x3775ba8, 0xf9400d00), # layout root pane +0x18
    (0x3775bcc, 0xbd403003), # pane position +0x30
    (0x3775bd4, 0x2d4a1800), # pane size +0x50/54
    (0x3775bdc, 0x2d491c01), # pane scale +0x48/4c
    (0x6fe6c, 0x9102c100),   # pane name +0xb0 in name lookup
    (0x4b620, 0xf9400c08),   # Layout Calculate entry: root pane +0x18
    (0x4b654, 0xf9006274),   # DrawInfo current-layout +0xc0
    (0x4b660, 0xf9404d08),   # root CalculateGlobalMatrix virtual +0x98
    (0x4b670, 0xd63f0100),   # execute root CalculateGlobalMatrix
    (0x4b674, 0xf9400288),   # root has returned; before post-calculate callback
    (0x4b684, 0xd63f0100),   # layout post-calculate virtual +0xa8
    (0x4b688, 0xf900627f),   # after-call restore candidate; clear current-layout
    (0x587bc, 0x94000079),   # base calls original Local after derived reflow
    (0x587c0, 0x39416268),   # normal global-matrix output boundary
    (0x588cc, 0xad038a61),   # authored UserMatrix path writes global rows0/1
    (0x588d0, 0x3d802660),   # authored UserMatrix path writes global row2
    (0x588d4, 0x320003f6),   # user/global path output boundary
)
LIVE_OBSERVERS = ((0x4ec800, 26, 0xd103c3ff),
                  (0x4b654, 27, 0xf9006274),
                  (0x4b674, 28, 0xf9400288),
                  (0x587c0, 29, 0x39416268),
                  (0x588d4, 30, 0x320003f6))


def target_factor(aspect: float) -> float:
    """Return logical canvas height relative to authored 16:9, in plan range."""
    if not math.isfinite(aspect) or not 1.0 <= aspect <= 4.0:
        raise ValueError('Aspect research requires a finite landscape ratio in [1,4]')
    return (16.0 / 9.0) / aspect


def admit_image(nso: bytes, image: bytes | bytearray) -> None:
    """Check original NSO identity and every independent receiving-code fact."""
    preparation._identity(nso)
    for offset, word in LIVE_FACTS:
        if offset + 4 > len(image) or struct.unpack_from('<I', image, offset)[0] != word:
            raise ValueError(f'Smash live-aspect research word mismatch at {offset:#x}')


def verify_live_rewritten(directory: Path) -> None:
    """Admit both transaction gates and the camera gate, including real stubs."""
    preparation.check_rewritten(directory)
    observations = preparation._rows(directory / 'main.obs.tsv')
    seen = {int(r[1], 0): (int(r[0], 0), int(r[2], 16)) for r in observations}
    if len(seen) != len(observations):
        raise ValueError('Duplicate live observation id')
    gate_rows = [r for r in preparation._rows(directory / 'main.gates.tsv') if r[1] == 'obs']
    gates = {(int(r[2], 0), int(r[3], 0)): int(r[0], 0) for r in gate_rows}
    if len(gates) != len(gate_rows):
        raise ValueError('Duplicate live observation registration')
    header = {}
    for line in (directory / 'main.fixups.tsv').read_text().splitlines():
        if line.startswith('# '):
            parts = line[2:].split('\t')
            if len(parts) == 2:
                header[parts[0]] = int(parts[1], 16)
    patch = header['PATCH_OFF']
    image = (directory / 'main.patched.bin').read_bytes()

    def word(address):
        offset = address
        if patch < 0 and address < 0:
            offset = header['FILE_IMAGE_LEN'] + address - patch
        if not 0 <= offset <= len(image) - 4:
            raise ValueError('Live observation stub outside module')
        return struct.unpack_from('<I', image, offset)[0]

    def branch_target(address):
        instruction = word(address)
        if instruction & 0xfc000000 != 0x14000000:
            raise ValueError('Live observation return/entry is not a branch')
        delta = instruction & 0x3ffffff
        if delta & 0x2000000:
            delta -= 0x4000000
        return address + delta * 4

    for site, number, original in LIVE_OBSERVERS:
        ret = gates.get((number, site))
        if seen.get(number) != (site, original) or ret is None:
            raise ValueError(f'Missing exact live observer {number}')
        stub = branch_target(site)
        if not patch <= stub < ret <= stub + 128:
            raise ValueError('Live observation entry differs from registered stub')
        if word(ret) != 0xa8c17bfd or word(ret + 4) != original or branch_target(ret + 8) != site + 4:
            raise ValueError('Live observation restore/original/return mismatch')
    observed_sites = {site for site, _, _ in LIVE_OBSERVERS}
    for offset, expected in LIVE_FACTS:
        if offset not in observed_sites and word(offset) != expected:
            raise ValueError(f'Live observation adjacent fact mismatch at {offset:#x}')


def _admit_resource(prepared: bytes, receipt: dict) -> tuple[bytes, dict]:
    """Undo the complete receipt, then reproduce the canonical preparation."""
    if not isinstance(prepared, bytes) or hashlib.sha256(prepared).hexdigest() != receipt.get('transformed_sha256'):
        raise ValueError('Prepared UI identity mismatch')
    members = {m.name: m for m in ui._members(prepared)}
    original = bytearray(prepared)
    touched = set()
    for change in receipt.get('changes', []):
        member, offset = members.get(change.get('member')), change.get('offset')
        if member is None or not isinstance(offset, int) or not 0 <= offset <= member.size - 4:
            raise ValueError('UI field receipt range mismatch')
        absolute = member.offset + offset
        span = set(range(absolute, absolute + 4))
        if span & touched:
            raise ValueError('Overlapping UI field receipt')
        touched.update(span)
        before, after = bytes.fromhex(change['before']), bytes.fromhex(change['after'])
        if len(before) != 4 or len(after) != 4 or prepared[absolute:absolute + 4] != after:
            raise ValueError('UI field receipt bytes mismatch')
        original[absolute:absolute + 4] = before
    original = bytes(original)
    canonical, expected = ui.transform_sarc(original, receipt.get('archive_hash40'))
    if canonical != prepared or expected != receipt:
        raise ValueError('UI field receipt differs from canonical preparation')
    return original, members


def retarget(prepared: bytes, receipt: dict, aspect: float) -> tuple[bytes, list[dict]]:
    """Compute a target resource and named field plan, preserving other bytes.

    Every current policy is affine in the height expansion: explicit edge
    offsets, full-screen dimensions, rotated fill origins and Hermite values
    and slopes. Interpolate declared fields only; text/icon geometry is absent
    from this change list. Re-admission prevents cumulative/double application.
    """
    factor = target_factor(aspect)
    original, members = _admit_resource(prepared, receipt)
    weight = (factor - 1.0) / (4.0 / 3.0 - 1.0)
    result = bytearray(prepared)
    fields = []
    for change in receipt['changes']:
        member = members[change['member']]
        endian = ui._endian(prepared[member.offset:member.offset + member.size], 4)
        old = struct.unpack(endian + 'f', bytes.fromhex(change['before']))[0]
        baseline = struct.unpack(endian + 'f', bytes.fromhex(change['after']))[0]
        value = old + (baseline - old) * weight
        if not math.isfinite(value):
            raise ValueError('Nonfinite target UI field')
        encoded = struct.pack(endian + 'f', value)
        # Keep the two admitted endpoints byte exact, including signed zeros.
        if aspect == 4.0 / 3.0:
            encoded = bytes.fromhex(change['after'])
        elif aspect == 16.0 / 9.0:
            encoded = bytes.fromhex(change['before'])
        absolute = member.offset + change['offset']
        result[absolute:absolute + 4] = encoded
        fields.append(dict(member=change['member'], pane=change['pane'],
                           field=change['field'], policy=change['policy'],
                           baseline=baseline, target=struct.unpack(endian + 'f', encoded)[0]))
    result = bytes(result)
    if aspect == 16.0 / 9.0 and result != original:
        raise ValueError('Authored endpoint failed exact reversal')
    return result, fields


def calculate_plan(prepared: bytes, receipt: dict, aspect: float) -> list[dict]:
    """Plan temporary local transforms for a future Calculate transaction.

    Picture/window size must remain intact for later DrawSelf calls. Express
    fill growth separately from content transforms so a future user-matrix
    transaction can compensate descendants, including rotated children.
    Target root dimensions apply only to private parent-origin calculations;
    no runtime pane, including RootPane, may change its size fields.
    Runtime tree validation, nesting, restoration and lifetime are not supplied
    by this resource-only function.
    """
    _, fields = retarget(prepared, receipt, aspect)
    members = {m.name: m for m in ui._members(prepared)}
    layouts = {m.name: ui._layout(prepared[m.offset:m.offset + m.size])
               for m in members.values() if m.name.endswith('.bflyt')}
    result = []
    for field in fields:
        if field['member'] not in layouts or not field['pane']:
            continue  # Canvas and animation source fields are not live panes.
        pane = layouts[field['member']].panes[field['pane']]
        policy, name = field['policy'], field['field']
        item = dict(member=field['member'], pane=pane.name, parent=pane.parent,
                    kind=pane.kind.decode(), policy=policy)
        if policy == 'screen_root' and name == 'height':
            if pane.name != 'RootPane' or pane.kind != b'pan1' or pane.parent is not None:
                raise ValueError('Private parent canvas requires the plain primary RootPane')
            item.update(operation='private_parent_canvas_height', value=field['target'])
        elif policy == 'full_screen_fill' and name in ('width', 'height'):
            if field['baseline'] <= 0 or field['target'] <= 0:
                raise ValueError('Fill scale requires positive admitted dimensions')
            item.update(operation='geometry_growth_' + ('x' if name == 'width' else 'y'),
                        value=field['target'] / field['baseline'])
        elif policy in ('edge_anchor', 'fill_origin') and name in ('x', 'y'):
            item.update(operation='add_local_position_' + name,
                        value=field['target'] - field['baseline'])
        else:
            raise ValueError('Unsupported live Calculate field policy')
        result.append(item)
    return result


def runtime_layout_rule(prepared: bytes, receipt: dict) -> dict:
    """Compile primary ownership and affine coefficients from an admitted SARC."""
    _, members = _admit_resource(prepared, receipt)
    return _runtime_layout_rule(prepared, receipt, members[receipt['primary_layout']])


def _runtime_layout_rule(prepared: bytes, receipt: dict, member) -> dict:
    """Compile one primary or Parts-owned member after complete SARC admission."""
    primary = member.name == receipt['primary_layout']
    layout = ui._layout(prepared[member.offset:member.offset + member.size])
    panes = {name: dict(name=name, parent=pane.parent, kind=pane.kind.decode(), parts=None,
                       offset_x=0.0, offset_y=0.0, grow_x=0, grow_y=0, visit_parts=0, edge_y=0)
             for name, pane in layout.panes.items()}
    data = prepared[member.offset:member.offset + member.size]
    ends = {start: end for _, start, end in ui._sections(data, b'FLYT')[1]}
    for name, pane in layout.panes.items():
        if pane.kind != b'prt1':
            continue
        # ResParts header follows the84-byte ResPane; each40-byte property
        # descriptor precedes the NUL-terminated child-layout filename. Both
        # magnify floats and the complete field stay inside this section.
        start, end = pane.offset, ends[pane.offset]
        if end-start < 97:
            raise ValueError('Short receiving ResParts header')
        count, magx, magy = struct.unpack_from(layout.endian+'Iff', data, start+84)
        offset = start+96+count*40
        if count > 4096 or offset >= end or not all(math.isfinite(v) and v>0 for v in (magx,magy)):
            raise ValueError('Invalid receiving ResParts descriptors')
        raw = data[offset:min(offset+96,end)]
        if b'\0' not in raw:
            raise ValueError('Unterminated receiving Parts layout name')
        target = raw.split(b'\0',1)[0].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', target):
            raise ValueError('Invalid receiving Parts layout name')
        panes[name]['parts'] = Path(target).stem if target.endswith('.bflyt') else target
    roots = [pane for pane in layout.panes.values() if pane.parent is None]
    root = roots[0] if len(roots) == 1 else None
    if root is None or root.kind != b'pan1' or primary and (root.name != 'RootPane' or root.size != layout.canvas):
        raise ValueError('Runtime rules require the plain matched primary RootPane')
    for change in receipt['changes']:
        if change['member'] != member.name or not change['pane']:
            continue
        pane = panes[change['pane']]
        field, policy = change['field'], change['policy']
        if policy == 'screen_root' and field == 'height':
            continue  # Private parent size only. Never write a runtime size.
        if policy == 'full_screen_fill' and field in ('width', 'height'):
            pane['grow_x' if field == 'width' else 'grow_y'] = 1
        elif policy in ('edge_anchor', 'fill_origin') and field in ('x', 'y'):
            old = struct.unpack(layout.endian + 'f', bytes.fromhex(change['before']))[0]
            baseline = struct.unpack(layout.endian + 'f', bytes.fromhex(change['after']))[0]
            # Target relative to prepared4:3: d=(4/3)/aspect-1. Canonical
            # preparation moves this field through one third of authored size.
            pane['offset_' + field] = 4 * (baseline - old)
            if policy == 'edge_anchor' and field == 'y':
                pane['edge_y'] = 1 if baseline > old else -1
        else:
            raise ValueError('Unsupported scoped runtime field policy')
    return dict(name=Path(member.name).stem, resource=receipt['archive_hash40'],
                root_name=root.name, primary=primary,
                width=layout.canvas[0], height=layout.canvas[1],
                panes=[panes[name] for name in sorted(panes)])


def runtime_layout_rules(prepared: bytes, receipt: dict) -> list[dict]:
    """Include every nested ownership link in its original archive namespace."""
    _, members = _admit_resource(prepared, receipt)
    result = [_runtime_layout_rule(prepared, receipt, member) for name, member in sorted(members.items())
              if name.endswith('.bflyt')]
    by_name = {layout['name']: layout for layout in result}
    if len(by_name) != len(result):
        raise ValueError('Duplicate child-layout basename in admitted archive')
    memo = {}
    def relevant(name, visiting):
        if name in memo:
            return memo[name]
        if name in visiting:
            raise ValueError('Recursive Parts ownership in admitted archive')
        layout = by_name[name]
        active = any(pane['offset_x'] or pane['offset_y'] or pane['grow_x'] or pane['grow_y']
                     for pane in layout['panes'])
        for pane in layout['panes']:
            if pane['parts']:
                candidates = [target for target in (pane['parts'], pane['parts']+'+us_en') if target in by_name]
                pane['visit_parts'] = int(any(relevant(target, visiting | {name}) for target in candidates))
                active |= bool(pane['visit_parts'])
        memo[name] = active
        return active
    for layout in result:
        relevant(layout['name'], set())
    return result


def emit_runtime_header(layouts: list[dict]) -> str:
    """Emit metadata only; callers save this game-derived table in private work."""
    def string(value):
        return 'NULL' if value is None else json.dumps(value, ensure_ascii=True)
    def number(value):
        if not math.isfinite(value):
            raise ValueError('Nonfinite runtime coefficient')
        return float(value).hex() + 'f'
    result = ['// Private exact-resource metadata. Do not publish this generated file.',
              '#include "smash_ui_rules.h"']
    for index, layout in enumerate(layouts):
        result.append(f'static const dm_smash_ui_rule smash_ui_panes_{index}[]={{')
        for pane in layout['panes']:
            kind = int.from_bytes(pane['kind'].encode(), 'little')
            result.append('{' + ','.join((string(pane['name']), string(pane['parent']), string(pane['parts']),
                str(kind), number(pane['offset_x']), number(pane['offset_y']),
                str(pane['grow_x']), str(pane['grow_y']), str(pane['visit_parts']), str(pane['edge_y']))) + '},')
        result.append('};')
    result.append('static const dm_smash_ui_layout_rule smash_ui_layouts[]={')
    for index, layout in enumerate(layouts):
        result.append('{' + ','.join((string(layout['name']), string(layout['resource']),
            string(layout['root_name']), number(layout['width']), number(layout['height']), f'smash_ui_panes_{index}',
            str(len(layout['panes'])), str(int(layout['primary'])))) + '},')
    result.extend(['};', 'static const size_t smash_ui_layout_count=sizeof smash_ui_layouts/sizeof *smash_ui_layouts;'])
    return '\n'.join(result) + '\n'


def compile_runtime_header(arc: Path, receipt_path: Path, output: Path) -> dict:
    """Verify the complete prepared ARC and generate one external rule header."""
    preparation.check_assets(arc, receipt_path)
    record = json.loads(receipt_path.read_text())
    layouts = []
    codec = preparation.Zstd()
    with arc.open('rb') as stream:
        for resource in record['resources']:
            stream.seek(resource['offset']); packed = stream.read(resource['stored_bytes'])
            if hashlib.sha256(packed).hexdigest() != resource['prepared_stored_sha256']:
                raise ValueError('Prepared ARC changed while compiling runtime rules')
            raw = packed if packed[:4] == b'SARC' else codec.decompress(packed, resource['decoded_bytes'])
            layouts.extend(runtime_layout_rules(raw, resource['ui']))
    output.write_text(emit_runtime_header(layouts))
    return dict(layouts=len(layouts), primary_layouts=sum(layout['primary'] for layout in layouts),
                nested_layouts=sum(not layout['primary'] for layout in layouts),
                panes=sum(len(layout['panes']) for layout in layouts),
                preparation_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                header_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                active_runtime=False, inputs_written=False)


def inspect_targets(arc: Path, receipt_path: Path, aspects: list[float]) -> dict:
    """Verify all prepared spans and compile current target hashes/field counts."""
    for aspect in aspects:
        target_factor(aspect)
    preparation.check_assets(arc, receipt_path)
    record = json.loads(receipt_path.read_text())
    codec = preparation.Zstd()
    targets = [dict(aspect=a, logical_canvas=[1920.0, 1920.0 / a],
                    resources=[], fields=0, calculate_operations=0, policies={}) for a in aspects]
    with arc.open('rb') as stream:
        for resource in record['resources']:
            stream.seek(resource['offset'])
            packed = stream.read(resource['stored_bytes'])
            if hashlib.sha256(packed).hexdigest() != resource['prepared_stored_sha256']:
                raise ValueError('Prepared ARC changed during planning')
            raw = packed if packed[:4] == b'SARC' else codec.decompress(packed, resource['decoded_bytes'])
            if hashlib.sha256(raw).hexdigest() != resource['prepared_decoded_sha256']:
                raise ValueError('Prepared decoded resource identity mismatch')
            for target in targets:
                output, fields = retarget(raw, resource['ui'], target['aspect'])
                operations = calculate_plan(raw, resource['ui'], target['aspect'])
                target['resources'].append(dict(hash40=resource['hash40'],
                    primary=resource['ui']['primary_layout'],
                    target_sha256=hashlib.sha256(output).hexdigest(), fields=len(fields)))
                target['fields'] += len(fields)
                target['calculate_operations'] += len(operations)
                for field in fields:
                    policy = field['policy']
                    target['policies'][policy] = target['policies'].get(policy, 0) + 1
    return dict(schema=1, title_id=record['title_id'], build_id=record['build_id'],
                preparation_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                runtime_enabled=False, inputs_written=False, targets=targets,
                qualification='Exact resource plans only; not loaded-pane, gameplay or presentation proof',
                remaining=['Guarded live camera observer', 'Loaded-pane identity and temporary Calculate transaction',
                           'Coherent game-frame/presentation aspect epoch', 'Actual-game camera/HUD visual checks'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arc', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--main', type=Path, required=True, help='player-supplied original main NSO')
    parser.add_argument('--aspect', type=float, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.absolute()
    if output.resolve().is_relative_to(repo) or output.resolve() in (args.arc.resolve(), args.receipt.resolve(), args.main.resolve()):
        raise ValueError('Research output must be outside source and separate from inputs')
    original = args.main.read_bytes()
    preparation._identity(original)
    # Identity is checked before decompression; do not trust an arbitrary NSO's
    # segment lengths. This loader is already a dependency of the normal survey.
    from nso_syms import load
    admit_image(original, load(args.main))
    result = inspect_targets(args.arc, args.receipt, args.aspect)
    result['original_main_sha256'] = hashlib.sha256(original).hexdigest()
    result['receiving_code_facts_verified'] = len(LIVE_FACTS)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name('.' + output.name + '.tmp')
    try:
        temporary.write_text(json.dumps(result, indent=2) + '\n')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'PASS: {len(result["targets"])} target resource plans; runtime remains disabled')


if __name__ == '__main__':
    main()
