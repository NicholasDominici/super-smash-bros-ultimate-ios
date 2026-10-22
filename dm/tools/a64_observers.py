"""AAPCS call-boundary checks for offline observation gates."""


def is_call(word: int) -> bool:
    """Recognize BL and BLR, which may clobber the gate's scratch registers."""
    return word >> 26 == 0x25 or word & 0xfffffc1f == 0xd63f0000
