"""Call boundaries and explicit full-state internal observation admission."""
import re


def is_call(word: int) -> bool:
    """Recognize BL and BLR, which may clobber the gate's scratch registers."""
    return word >> 26 == 0x25 or word & 0xfffffc1f == 0xd63f0000


def require_full_state_gate(source: str) -> None:
    """Reject internal-site use if the production800-byte gate loses state.

    Site stubs borrow only x29/x30, saving both before loading KGATE. The host
    entry must preserve every other guest GPR, all SIMD, flags and FP control.
    x18 is Apple's platform register; rewritten guest x18 lives in thread data.
    This static check complements the explicit real-assembly runtime fixture.
    """
    body = source.split('_dm_gate:', 1)[1].split('// 3)', 1)[0]
    lines = [re.sub(r'\s+', '', line.split('//', 1)[0]) for line in body.splitlines()]
    instructions = [line for line in lines if line]
    call = instructions.index('bl_gate_dispatch')
    saves, restores = instructions[:call], instructions[call+1:]
    required_save = ['subsp,sp,#800', 'strx30,[sp,#240]']
    required_restore = ['ldrx30,[sp,#240]', 'addsp,sp,#800', 'ret']
    for reg in range(0, 30, 2):
        required_save.append(f'stpx{reg},x{reg+1},[sp,#{reg*8}]')
        if reg != 18:
            required_restore.append(f'ldpx{reg},x{reg+1},[sp,#{reg*8}]')
    required_restore.append('ldrx19,[sp,#152]')
    for reg in range(0, 32, 2):
        offset = 256+reg*16
        required_save.append(f'stpq{reg},q{reg+1},[sp,#{offset}]')
        required_restore.append(f'ldpq{reg},q{reg+1},[sp,#{offset}]')
    for name, offset in [('nzcv',768), ('fpsr',776), ('fpcr',784)]:
        required_save.extend([f'mrsx9,{name}', f'strx9,[sp,#{offset}]'])
        required_restore.extend([f'ldrx9,[sp,#{offset}]', f'msr{name},x9'])
    if any(line not in saves for line in required_save) or any(line not in restores for line in required_restore):
        raise ValueError('Internal observation requires the complete production register frame')
