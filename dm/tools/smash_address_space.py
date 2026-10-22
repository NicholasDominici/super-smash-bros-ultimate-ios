"""Exact Smash 13.0.5 arena compatibility cut for the measured iPad VA limit.

Only the admitted original main is changed, on its private decompressed copy.
The 62 GiB sparse arena becomes 30 GiB; the 14 MiB metadata reservation and
64 KiB allocation units remain intact. All linked constants are checked before
any write. This does not claim that an unreserved address range exists.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

MAIN_BUILD = '21450c647b8c5940ed5b68218ea128fd'
MAIN_SHA256 = 'eb79e639e47d9a0c79bcfe2ec50fc807afa9601800226627b58bd6a1a83dc52d'
ORIGINAL_ARENA = 0xF80000000
IPAD_ARENA = 0x780000000
METADATA_BYTES = 0xE00000
PAGE_BYTES = 0x10000
UNRELATED_MASK_SITE = 0x34C428
UNRELATED_MASK_WORD = 0xB26113EA

# offset, original word, replacement word, reason. Five arena sizes, metadata
# cursor/base high halves, and the initial free range must change together.
CUTS = (
    (0x37C9A5C, 0xB26113E1, 0xB2610FE1, 'arena reservation size'),
    (0x37C9A9C, 0xB26113E9, 0xB2610FE9, 'initial metadata mapping end bound'),
    (0x37C9C50, 0xB26113E9, 0xB2610FE9, 'new free-range node metadata growth bound'),
    (0x37CA3CC, 0xB26113E8, 0xB2610FE8, 'allocation split metadata growth bound'),
    (0x37CAF68, 0xB26113E9, 0xB2610FE9, 'free/coalescing metadata growth bound'),
    (0x37C9A6C, 0xB27C7FE9, 0xB27C7BE9, 'metadata cursor high bits'),
    (0x37C9A78, 0xF2C001EB, 0xF2C000EB, 'metadata base high bits'),
    (0x37C9B9C, 0x72A001E1, 0x72A000E1, 'initial free 64 KiB unit count high bits'),
)
CONSTITUENTS = (
    (0x37C9A70, 0xD2AFE40B),  # metadata base low half: mov x11,#0x7f200000
    (0x37C9A74, 0xF2AFE409),  # cursor middle half: movk x9,#0x7f20,lsl#16
    (0x37C9B98, 0x528FE401),  # free-unit low half: mov w1,#0x7f20
)


def arena_layout(size: int) -> dict[str, int]:
    """Describe the original allocator's formulas, retaining its metadata pool."""
    if size <= METADATA_BYTES + PAGE_BYTES or size % PAGE_BYTES:
        raise ValueError('Arena must hold aligned data and metadata pages')
    metadata = size - METADATA_BYTES
    units = metadata // PAGE_BYTES
    if units >= 1 << 32:
        raise ValueError('Arena does not fit the original 32-bit page bookkeeping')
    return {'arena_bytes': size, 'metadata_bytes': METADATA_BYTES,
            'metadata_offset': metadata, 'initial_node_cursor': metadata + 0xFFF0,
            'initial_metadata_end': metadata + PAGE_BYTES, 'free_page_units': units}


def apply_original(nso: bytes, image: bytearray, module: str) -> list[tuple]:
    """Gate the entire group atomically, then change only the private image."""
    if module != 'main' or nso[0x40:0x50].hex() != MAIN_BUILD:
        return []
    if hashlib.sha256(nso).hexdigest() != MAIN_SHA256:
        raise ValueError('Smash address-space cut: original main SHA-256 mismatch')
    gates = [(offset, original) for offset, original, _, _ in CUTS] + list(CONSTITUENTS)
    for offset, expected in gates:
        if offset + 4 > len(image) or struct.unpack_from('<I', image, offset)[0] != expected:
            raise ValueError(f'Smash address-space cut: original instruction mismatch at {offset:#x}')
    # Validate every constituent before touching the first word. Original NSP,
    # NSO and previous rewritten outputs are never modified by this helper.
    for offset, _, replacement, _ in CUTS:
        struct.pack_into('<I', image, offset, replacement)
    return [(offset, struct.pack('<I', old).hex(), struct.pack('<I', new).hex(),
             'Smash 13.0.5 iPad VA: 62 GiB -> 30 GiB; ' + reason)
            for offset, old, new, reason in CUTS]


def check_rewritten(directory: Path) -> None:
    """Reject old or partial 62 GiB caches before any host/app build starts."""
    directory = Path(directory)
    error = ('Rewritten Smash main lacks the complete 30 GiB iPad arena cut; '
             'old 62 GiB caches cannot run on this iPad. Omit --rewritten to regenerate')
    expected = {offset: replacement for offset, _, replacement, _ in CUTS}
    expected.update(CONSTITUENTS)
    expected[UNRELATED_MASK_SITE] = UNRELATED_MASK_WORD
    try:
        with (directory / 'main.patched.bin').open('rb') as stream:
            for offset, word in expected.items():
                stream.seek(offset)
                if stream.read(4) != struct.pack('<I', word):
                    raise ValueError(error + f' (instruction {offset:#x})')
        rows = {}
        for line in (directory / 'main.cuts.tsv').read_text().splitlines():
            if line and not line.startswith('#'):
                columns = line.split('\t')
                if len(columns) >= 3:
                    rows[int(columns[0], 0)] = tuple(columns[1:3])
        for offset, old, new, _ in CUTS:
            if rows.get(offset) != (struct.pack('<I', old).hex(), struct.pack('<I', new).hex()):
                raise ValueError(error + f' (cut receipt {offset:#x})')
    except OSError as exc:
        raise ValueError(error) from exc
