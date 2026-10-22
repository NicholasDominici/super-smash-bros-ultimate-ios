"""Atomic exact-build Smash13.0.5 native4:3 private preparation.

Camera defaults and UI projection facts are independently verified against the
player-supplied main. Primary mod provenance is Fl4sh9174's13.0.4 aspect research:
https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods
No upstream patch implementation or game payload is included here. Physical
raster size and60Hz simulation are separate from the logical4:3 presentation.
"""
from __future__ import annotations
from dataclasses import dataclass
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import smash_address_space as arena

_LOADED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

MAIN_BUILD = arena.MAIN_BUILD
MAIN_SHA256 = arena.MAIN_SHA256
# offset, expected word, replacement word, reason. The UI input bounds pair at
#0x3743e60 is deliberately preserved: it is not a camera projection aspect.
CUTS = (
    (0x4f08bc, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x4f08c0, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x4f09ac, 0x5291c736, 0x52955576, 'camera default aspect16/9 to4/3'),
    (0x4f09b0, 0x72a7fc76, 0x72a7f556, 'camera default aspect16/9 to4/3'),
    (0x4fe3bc, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x4fe3c0, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x5050ec, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x5050f0, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x5145cc, 0x5291c729, 0x52955569, 'camera default aspect16/9 to4/3'),
    (0x5145d0, 0x72a7fc69, 0x72a7f549, 'camera default aspect16/9 to4/3'),
    (0x51465c, 0x5291c729, 0x52955569, 'camera default aspect16/9 to4/3'),
    (0x514660, 0x72a7fc69, 0x72a7f549, 'camera default aspect16/9 to4/3'),
    (0x147f0e0, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x147f0e4, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x1493090, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x1493094, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x14e5efc, 0x5291c729, 0x52955569, 'camera default aspect16/9 to4/3'),
    (0x14e5f00, 0x72a7fc69, 0x72a7f549, 'camera default aspect16/9 to4/3'),
    (0x14e6014, 0xf2d1c736, 0xf2d55576, 'camera default aspect16/9 to4/3'),
    (0x14e6018, 0xf2e7fc76, 0xf2e7f556, 'camera default aspect16/9 to4/3'),
    (0x14e64d4, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x14e64d8, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x29fabfc, 0x5291c72f, 0x5295556f, 'camera default aspect16/9 to4/3'),
    (0x29fac00, 0x72a7fc6f, 0x72a7f54f, 'camera default aspect16/9 to4/3'),
    (0x3158624, 0x5291c735, 0x52955575, 'camera default aspect16/9 to4/3'),
    (0x3158628, 0x72a7fc75, 0x72a7f555, 'camera default aspect16/9 to4/3'),
    (0x354e2bc, 0xd291c72c, 0xd295556c, 'camera default aspect16/9 to4/3'),
    (0x354e2c0, 0xf2a7fc6c, 0xf2a7f54c, 'camera default aspect16/9 to4/3'),
    (0x361d3a4, 0x5291c728, 0x52955568, 'camera default aspect16/9 to4/3'),
    (0x361d3a8, 0x72a7fc68, 0x72a7f548, 'camera default aspect16/9 to4/3'),
    (0x4472c5c, 0x3fe38e39, 0x3faaaaab, 'shared camera fit and perspective aspect'),
    (0x44689f4, 0x3af2b9d6, 0x3ab60b61, 'orthographic logical height1080 to1440'),
    (0x374e114, 0x52973ac9, 0x52816c29, 'common UI cached projection logical height1440'),
    (0x374e118, 0x72a75e49, 0x72a756c9, 'common UI cached projection logical height1440'),
 )
OBSERVERS = ((0x44d60, 24, 0xf9400428), (0x378f140, 25, 0xf81d0ff5))
HAPTIC_OBSERVERS = ((0x1750dd0,21,0xd10203ff),(0x4def24,22,0xf9407660),(0x6b92c0,23,0xd101c3ff))
# Unmodified adjacent facts admit the SDK copy and pass-rectangle contracts.
CONSTITUENTS = ((0x44d64, 0xf9400c29), (0x378f144, 0xa9014ff4),
                (0x3775a1c, 0x9100c3e1), (0x3775a20, 0x97233cd0),
                (0x3743e60, 0xd2d1c728), (0x3743e64, 0xf2e7fc68))

@dataclass(frozen=True)
class PreparedAspect:
    """New private cache, RomFS overlay, and machine-readable complete receipt."""
    rewritten: Path
    romfs: Path
    receipt: Path

def _u32(image: bytes | bytearray, offset: int) -> int:
    if offset < 0 or offset +4 > len(image):
        raise ValueError(f'Smash aspect image range at{offset:#x}')
    return struct.unpack_from('<I', image, offset)[0]

def _identity(nso: bytes) -> None:
    if len(nso) <0x50 or nso[:4] != b'NSO0' or nso[0x40:0x50].hex() != MAIN_BUILD:
        raise ValueError('Smash aspect original main build ID mismatch')
    if hashlib.sha256(nso).hexdigest() != MAIN_SHA256:
        raise ValueError('Smash aspect original main SHA-256 mismatch')

def apply_image(nso: bytes, image: bytearray) -> list[tuple]:
    """Validate every constituent, then change only a caller-owned private image."""
    _identity(nso)
    for offset, expected, *_ in CUTS:
        if _u32(image,offset) != expected:
            raise ValueError(f'Smash aspect original word mismatch at{offset:#x}')
    for offset, expected in CONSTITUENTS:
        if _u32(image,offset) != expected:
            raise ValueError(f'Smash aspect constituent mismatch at{offset:#x}')
    for offset, _, replacement, _ in CUTS:
        struct.pack_into('<I',image,offset,replacement)
    return [(a,struct.pack('<I',old).hex(),struct.pack('<I',new).hex(),why)
            for a,old,new,why in CUTS]

def _rows(path: Path) -> list[list[str]]:
    return [line.split('\t') for line in path.read_text().splitlines()
            if line and not line.startswith('#')]

def verify_observers(directory: Path) -> None:
    """Require both exact observation sites and their gate registrations."""
    observations=[row for row in _rows(directory/'main.obs.tsv') if len(row)>=3]
    seen = {int(row[1],0):(int(row[0],0),int(row[2],16)) for row in observations}
    if len(seen)!=len(observations):
        raise ValueError('Smash aspect duplicate observation manifest entry')
    gates = {(int(row[2],0),int(row[3],0)) for row in _rows(directory/'main.gates.tsv')
             if len(row)>=4 and row[1]=='obs'}
    for address, number, original in OBSERVERS+HAPTIC_OBSERVERS:
        if seen.get(number)!=(address,original) or (number,address) not in gates:
            raise ValueError(f'Smash aspect missing exact observer{number} at{address:#x}; regenerate main from original')

def check_rewritten(directory: Path) -> None:
    """Reject incomplete aspect/arena caches before a native host can be built."""
    directory=Path(directory)
    arena.check_rewritten(directory)
    verify_observers(directory)
    with (directory/'main.patched.bin').open('rb') as stream:
        for address,_,new,_ in CUTS:
            stream.seek(address)
            if stream.read(4)!=struct.pack('<I',new):
                raise ValueError(f'Smash aspect incomplete4:3 group at{address:#x}')
        for address,expected in CONSTITUENTS:
            stream.seek(address)
            if stream.read(4)!=struct.pack('<I',expected):
                raise ValueError(f'Smash aspect changed unrelated constituent at{address:#x}')
    receipt={int(row[0],0):tuple(row[1:3]) for row in _rows(directory/'main.cuts.tsv') if len(row)>=3}
    for address,old,new,_ in CUTS:
        if receipt.get(address)!=(struct.pack('<I',old).hex(),struct.pack('<I',new).hex()):
            raise ValueError(f'Smash aspect missing cut receipt at{address:#x}')

class Zstd:
    """Bounded local libzstd adapter; does not install or fetch dependencies."""
    def __init__(self):
        import ctypes.util
        name=ctypes.util.find_library('zstd')
        if not name:
            raise ValueError('Smash aspect preparation needs the existing local libzstd')
        self.lib=ctypes.CDLL(name)
        for name in ('ZSTD_compress','ZSTD_decompress'):
            fn=getattr(self.lib,name)
            fn.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]+([ctypes.c_int] if name=='ZSTD_compress' else [])
            fn.restype=ctypes.c_size_t
        self.lib.ZSTD_compressBound.argtypes=[ctypes.c_size_t]
        self.lib.ZSTD_compressBound.restype=ctypes.c_size_t
        self.lib.ZSTD_isError.argtypes=[ctypes.c_size_t]
        self.lib.ZSTD_isError.restype=ctypes.c_uint
        self.lib.ZSTD_getErrorName.argtypes=[ctypes.c_size_t]
        self.lib.ZSTD_getErrorName.restype=ctypes.c_char_p
    def _check(self,value: int) -> int:
        if self.lib.ZSTD_isError(value):
            raise ValueError('Smash aspect Zstandard: '+self.lib.ZSTD_getErrorName(value).decode())
        return value
    def compress(self,data: bytes,level: int=19,window_log: int | None=None,checksum: bool=False) -> bytes:
        out=ctypes.create_string_buffer(self.lib.ZSTD_compressBound(len(data)))
        if window_log is None and not checksum:
            n=self._check(self.lib.ZSTD_compress(out,len(out),data,len(data),level))
            return out.raw[:n]
        self.lib.ZSTD_createCCtx.restype=ctypes.c_void_p
        self.lib.ZSTD_freeCCtx.argtypes=[ctypes.c_void_p]
        self.lib.ZSTD_CCtx_setParameter.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
        self.lib.ZSTD_CCtx_setParameter.restype=ctypes.c_size_t
        self.lib.ZSTD_compress2.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
        self.lib.ZSTD_compress2.restype=ctypes.c_size_t
        context=self.lib.ZSTD_createCCtx()
        if not context:
            raise ValueError('Smash aspect Zstandard context allocation failed')
        try:
            self._check(self.lib.ZSTD_CCtx_setParameter(context,100,level))
            if window_log is not None:
                self._check(self.lib.ZSTD_CCtx_setParameter(context,101,window_log))
            self._check(self.lib.ZSTD_CCtx_setParameter(context,201,int(checksum)))
            n=self._check(self.lib.ZSTD_compress2(context,out,len(out),data,len(data)))
            return out.raw[:n]
        finally:
            self.lib.ZSTD_freeCCtx(context)
    def decompress(self,data: bytes,size: int) -> bytes:
        if size<0 or size>256*1024*1024:
            raise ValueError('Smash aspect SARC exceeds bounded256MiB decode')
        out=ctypes.create_string_buffer(size)
        n=self._check(self.lib.ZSTD_decompress(out,size,data,len(data)))
        if n!=size:
            raise ValueError(f'Smash aspect decoded size mismatch:{n} !={size}')
        return out.raw

def _last_block(data: bytes) -> tuple[int,int]:
    """Validate one standard Zstd frame; return last-block and checksum offsets.

    Primary format: https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md
    Empty raw/RLE blocks emit zero bytes. Inserting them before the checksum
    retains ONE frame, its content size/checksum and exact decompressed payload.
    No skippable-frame or concatenated-frame behavior is assumed of the game.
    """
    if len(data)<8 or data[:4]!=bytes.fromhex('28b52ffd'):
        raise ValueError('Smash aspect requires one standard Zstandard frame')
    descriptor=data[4]
    if descriptor&0x18:
        raise ValueError('Smash aspect reserved Zstandard frame-header flags')
    single=bool(descriptor&0x20);flag=descriptor>>6
    fcs=(1 if single else 0,2,4,8)[flag]
    pos=5+(not single)+(0,1,2,4)[descriptor&3]+fcs
    if pos>len(data):
        raise ValueError('Smash aspect truncated Zstandard frame header')
    while True:
        if pos+3>len(data):
            raise ValueError('Smash aspect truncated Zstandard block header')
        last=pos;header=int.from_bytes(data[pos:pos+3],'little');pos+=3
        kind=(header>>1)&3;size=header>>3
        if kind==3 or size>128*1024:
            raise ValueError('Smash aspect invalid Zstandard block')
        pos+=1 if kind==1 else size
        if pos>len(data):
            raise ValueError('Smash aspect truncated Zstandard block')
        if header&1:
            break
    checksum=pos
    if descriptor&4:
        pos+=4
    if pos!=len(data):
        raise ValueError('Smash aspect multiple/trailing Zstandard frames rejected')
    return last,checksum

def pad_frame(data: bytes,target_size: int) -> bytes:
    """Pad one valid frame with empty blocks to keep ARC offsets/sizes unchanged."""
    last,checksum=_last_block(data)
    gap=target_size-len(data)
    if gap==0:
        return data
    if gap<0 or gap in (1,2,5):
        raise ValueError('Smash aspect compressed frame does not fit exact ARC span')
    raw=(-gap)%4
    rle=(gap-3*raw)//4
    if rle<0:
        raise ValueError('Smash aspect compressed padding is not representable')
    result=bytearray(data[:checksum]);result[last]&=0xfe
    blocks=[b'\x00\x00\x00']*raw+[b'\x02\x00\x00\x00']*rle
    if not blocks:
        raise ValueError('Smash aspect empty padding block list')
    blocks[-1]=bytes([blocks[-1][0]|1])+blocks[-1][1:]
    result.extend(b''.join(blocks));result.extend(data[checksum:])
    if len(result)!=target_size:
        raise ValueError('Smash aspect internal compressed span mismatch')
    _last_block(result)
    return bytes(result)

# Exact original compressed ARC spans; identity metadata, never resource payloads.
ARC_BYTES = 17600880952
ARCHIVE_SPANS = {
    '250df1a9c5': (7267750920, 270627, 2070588, '2a2c96ec120c53827916b57b7aafabb99322b68002a064a0c895f393b613b08d'),
    '254e6ddb52': (7327876936, 82937, 345628, '084e07b7e157ffd38325b5b0e286b5467ef3f4a9885ff971169526763b96cd96'),
    '255d184b77': (7729700968, 1241, 17160, '65b19f5d90f1bbe2fb93d5f19a4031882e7231515895df8c05705e033f15adfc'),
    '275f6c4da2': (7876574216, 21783, 307772, 'df1772a20d88a1b1587b9754dd376af106004258b7ea20c7f51dd910cbe15eb7'),
    '27b55d3a3d': (7439399544, 2196252, 11063084, 'f138d1f55d9acec7a6db4cb54a933a67ea3376c643221ea44a03ba35402e0990'),
    '2a6b7ecbb3': (7951941080, 870, 16488, '5d2b80207e60870a9698558189db58d1a6becf6b704d8f13137d683be9097480'),
    '2b2b9f0223': (7930389608, 1594632, 7439252, '9be946587f188b62dc266202a45fce19b89c6f5a0171df557c493286b2b66ac9'),
    '2ba6c9aa0b': (8948330584, 1059320, 3123520, '3b584b29527218ee1744f1cecbe65689ba2d18744c549505425dec60a47e51f2'),
    '2bdb1e876d': (7903370648, 25845, 594748, '4ffe47f78363d45bc27431267a3ee66b2481f47add63d35c3d41114b626b9dc2'),
    '2bfb1f41f0': (8641921768, 23894, 396504, '5cb167fdbd99851e3ccad797f34ee4c50fbce02d93a6ce8c49ca71dfc8b36f64'),
    '2bfc74d7fa': (7942521768, 1303051, 5111872, '6e3fa2ffd2acc3e44b0ecb3fe71fffada60111a88b61f8ad31c0822f9f62fa78'),
    '2d0e6e5ffe': (8859612472, 16772479, 58184864, '8f022e584d3f55caa4a6fb515c693e5a9a91ea618e0b9a051c0503e1d9e9bd7e'),
    '2d1be83c18': (8678064440, 11102980, 16444128, '6ec22caa745812a0f327184220acfad99d00a0fd0ed72889f518bc7b8aa2d451'),
    '2d3d443a7b': (8653229384, 37866, 382256, '35a77825e76e22dbd7aee0d0af8a2378cc6022958f011b9f384ee7470932e344'),
    '2d4ebc1123': (8949389912, 582025, 3144780, '80339d75371b4e7ac45a97edc78d7a4080a96dba30ec9dea70ccac89402055af'),
    '2d50bcbca9': (8813260840, 45264, 665120, 'bbd42815f1c1c42afdc1cc556cabb0c60780d4f743f6cb2ee76987f4112d8b36'),
    '2d8bafca90': (8952543304, 46297, 592244, '222c47ac250da281a10343c5ce56e51beb83d0065e28e16f4b8e0a4376fd36e2'),
    '2d9315c5be': (8689167432, 5541, 79912, '22a926eaa5aacb28f76047261aba941f673b73301c8d268cd92a2f44c7c9f995'),
    '2d97bbf8fe': (8948293352, 816, 16488, 'd3d30ad2a10c9af5548fede7678c6fb5d4c6acbd34307f4f25cee9028ec9d7af'),
    '2d9c008b43': (9001103896, 25636, 605084, 'f46f7264d2b8ec4ea127caf3aa7887bf48b3c85b58869628e20f60cbcd964beb'),
    '2db57f2c97': (9158564216, 91972, 1244060, '64dd190a9b82f3a2503b2e8c2fe36febb07e7519282e041859da8730369f4d19'),
    '2e6a0daddb': (9173354088, 48810, 740396, 'e363f7f54adcb39f30ffe1330492ea01b5307d4bcf076be1138f6475db5c3870'),
    '2f1277ec63': (9333537192, 122967, 3311196, '075aa7e2c61e57a25622cc3a1672845bac8c170c755ab824c69f8bb569fce07f'),
    '2f26ff8cc2': (9223064696, 325734, 2166040, 'a84bbec44e33d827d0cf4ccd1e2fbd4fc5e0815ac5e9fae620b171cbb725334e'),
    '2f3886bdf2': (9225200312, 6331, 48572, '3cc4fb7e9fa1d6893664ba7cd80bd604ad4689e8dce56a2d7ec1cc22e3fc0902'),
    '2f38c6d388': (9275355880, 118461, 1544556, 'e0d52c7bc44e8f3c8e21d520310d2e4b50c30af47b88dfdf6cdcf61340cbc78d'),
    '2f5299234e': (9225816696, 27090, 680748, '7a5e8f119b6ca414516960a5f03489d7a63c3855e3bde880b2e9b092895f15c2'),
    '2f55f1180f': (9225206648, 59355, 1652244, '276fbeb07410945aca1849376fd27e2a6423fc97d4a377483f3e9d24c852ebe2'),
    '2f75229853': (9206292056, 3109972, 17616848, '50e9cefc0cb1759634fd58e771e886feb71b8b4eb833851533af10e0a4052912'),
    '2fe6646ba0': (9206269960, 8964, 93804, '325ffb2b0723e60fb6afd4079039a8d6bb92e19346575230df91d861c3fbe3b5'),
    '2fe9aecbea': (9245409880, 7321, 54000, '50f26acc22ebe9746408dfd17dddd1628309dfba3b0d65ea060ec90698b17427'),
    '310432d388': (9341461288, 28140, 1350980, '3f385d303d9d30133cd1e0e4abcace1a5d2998aed2cd07e50c1e359cfd8fe1b3'),
    '3106282e51': (9376357688, 264978, 2008580, '59779b523c1914e365f86c27897efc33e696f1c928ce790251b43c68ae2a2247'),
    '3111c836d0': (9337794536, 3666737, 18858220, '44639de818b37c6857f24d912ad4721373b73a9a9bb1a56af348dda7bd6551ca'),
    '311b13943e': (9418845272, 113883, 1441264, 'a1bfda367440b93e7bc867b2a8f9ff264fc58a9da07d623ad5d2b97b70943a2a'),
    '312a83c62d': (9374638232, 58856, 589532, '19dfe1532d37e755ace420d3164766d6f64022aa130fdf120067acae93782f78'),
    '312c926f5e': (9355044328, 247339, 2691980, 'e01954440e3079104cca04b1d81aac877940d9b99c04f8b0ba2edb5d0e3f838e'),
    '31312e13ab': (9424286280, 24344, 540800, 'e3ef491bf82de535d2c8f26290919c145a245aebb7ca85a38d36dec5dced09aa'),
    '313cbe0d89': (9413171832, 17924, 203132, '924748e5d1b33981976fbd409002a288baa0827caa94ca696cb845b87d7d4449'),
    '3178454adf': (9418967800, 183029, 1810220, 'c911c9a939a58a3a26e8e81b334869ae076fca6db78db3e1a09a3ca5dad48d0c'),
    '317e38232c': (9355370712, 1142092, 1939940, '3eeff060790f6221ecf13e895d12b2d8917e4a21be4310b96a806520a8eac4dd'),
    '31845c7b37': (9388752280, 1789423, 15493932, '5507679539e21699a11cea77cde4ac8f0a33c46d88f8957e170e6560ff2adc00'),
    '3198d343d5': (9438659064, 102632, 1883208, 'b83c694525f1175224fbaaac97699b09f05cf38e6ee37c533d7beec64016b2d4'),
    '319a04e456': (9413190984, 3460, 41328, '5a2a32104316420348815326ad97803835c0ac567d5aec1f8bb7b1cdccc3b2c3'),
    '319f3ef6b3': (9347278616, 1094141, 2017116, 'dfc37e81d39881fbd48f1945b86ba45ceb6527ffb4bc7c41b0cf58ac960aa6da'),
    '31a68ae130': (9376622680, 42824, 755692, 'fa8d46497e391eaa71f4a04246c7790cc6c993a4bdc9e83275ace36486b39a36'),
    '31d245d743': (9356621064, 26912, 215876, '7adc8aebd56a881d1b6af49ac5522f367e7e4027b48f206cb5990e59db051270'),
    '32e952a229': (9445963128, 123161, 3310316, '67ee80a560cfdc3b548a14a46d058ddf6392177c0cbcc0d6694506b60ec38219'),
    '3310aa5c82': (9444853704, 132615, 1284116, '3b4077265adf76a66ca1c0591032485908e691686a85728b74b0ce2cacda9695'),
    '3341dbe94e': (9582422008, 2816213, 9821168, '728c7d436fee31b833777354aeb04474e05f363ca5265baafcc0371841a93708'),
    '334bc51f0a': (9539387304, 4070168, 23275952, 'e90280831e9984cbf74016366bff6aad01373606f0e5ffcb7ad59dbd275e6584'),
    '334d1d711c': (9445181528, 42401, 910248, 'b73779c9e08b27a7b2e3431c64e2fc79485c49698e6b2b18217767e824046e86'),
    '3350b16a9a': (9563635432, 596, 16488, 'cee61daf38921fd2ba180f79808ba48a35db55aacc19e67ced651e79a074823d'),
    '335f9d670d': (9515678648, 1003225, 7369612, '5468f003b45f911dfef5d5e06f149202db5213ae4de55c7460df9c1c5dc2b9ad'),
    '33686d61ef': (9504532936, 251830, 2193276, 'e3e92be8724e405d6ec3305893e6e927d164b74adb2bb22179762061654463e1'),
    '3373b1a8b5': (9604724104, 2175825, 5892156, '42199399cd9496032cb4034c2238adad72350f27fd29251e84066d66655dbea7'),
    '338310ff39': (9594655896, 10995, 304668, '2be5905b3d39f2a4ebfe35f7dd8a3c421511b4b6eb9e0026c4413d29b7a5c330'),
    '3399c376cf': (9556486792, 1150826, 4303120, '98a90c4ec586e875c5a6208181c749b5bc1e7a21d35e59a84c7b2f979a4107a7'),
    '33a37454ac': (9599983192, 2492, 25884, 'bd0935669d2b64fd17c8737fa3068b1c2c91430042dbcc8c52dbf8cc31876bfe'),
    '33a4789b3b': (9566804504, 15808, 884864, '61506c063786dfd5ffab94ac9dd8887979c946183e461a37c5e480a1398f9b65'),
    '33af85fd78': (9563636264, 15999, 139384, '61679228673e725ed2b5afe8bd437f68aacc6624beeb366f8204f8bc0676099a'),
    '33b1720916': (9507473816, 1982706, 8806528, 'bd8b5a8d8850d9d485e058fdbcad773f4958a571dfa6ce5204a12ddf376d0a64'),
    '33b3e63b93': (9606989496, 15333, 188536, '8a17dd5c1302c1d611fcf8290e9062be0ce20e1c2967df5d57a20d023f224588'),
    '33cf7359b3': (9544846504, 78651, 960796, '1823391e60c93f2702af0b2eed6ee63200db7bb178a436fc341a813d7dd6ac9d'),
    '33d402e4f7': (9470953032, 463508, 17748320, '06648156a6cb70820e22ad4c9ce5dd64d835037721b0d5001b5312ff2b375ee4'),
    '33e107300f': (9511290920, 13226, 389692, '5dccc78d85528a4c92e868cf22ef94b14c1c33f4b01ed392a648338b240ed307'),
    '33f1290769': (9591304392, 3065, 28800, '930dedbef72b2f72876ad81c61d4766b9054fb41d3927539abf7a6eee66e380a'),
    '34abdc74f3': (9788101320, 35632, 283420, '787666c4e6dfc75095c8675befc0a50a4d84f8be9e21b3bd80b782d487a7a19a'),
    '35000fb5c8': (9955443192, 1918, 29700, '57ac59981512dc3f61f86cc60bc9747b059064ca17d364519d1aeba7ad7df82b'),
    '350126176d': (10006435528, 6675, 49496, '29b3e3ba8945a581e03c8d6a6ed54f7765e9124800af8122aeaabeb352915195'),
    '3509e1cc55': (9864262184, 225140, 2042272, '7d7e8c466c7275bb13c030ae3820f8cfcba8cb76097f382b094153c28d09dd13'),
    '350c3e4c44': (9889841592, 54336, 927100, 'ba688caebc44264aa815c10727257d5d88956c131c39c0749f2807a9c11d47be'),
    '350d896cba': (9781960328, 493236, 1423900, '37441dcc4c46bb5820f45eaa3407b63ff098b0b7b1c6c44921c90c90b06a5f53'),
    '350f9f743b': (9761747752, 38475, 1441356, '0c712935b278709f8fc0048036b9affb7bc1e8a76822c38a44a41d571fce6d11'),
    '353b7ed6c2': (9906825768, 16538, 553104, 'be9a1ab1ada2ee62381eef21dbdcef7ff8644311601c49066944712ac040dda4'),
    '3541981a99': (9751417320, 2104404, 7844608, '4f59877b6aa53cc26e15c6d68162380e4e286f8e48dc24f8e740ba83f525d80e'),
    '3575fbb045': (9856633432, 55779, 451604, 'baaca5ee8041282619135546e7662b9d02608d8c747e686c4a742412a126b769'),
    '35a2351c7c': (9858007528, 5762, 81440, '1fd8fa1ff4e30116866941abab8cc87d746c6be07da30680f419cba81372f6e1'),
    '35a50a2779': (9738107192, 533180, 3642460, '7724318142f77176e2a4096e8a534965ecaf7af45cdb3f57372405ce5e3d2a55'),
    '35c47c560f': (9738640376, 11358, 112288, '4c74123a89081158ae413523f198a447509abb17bef3c1bcee06ff54da0cc80c'),
    '35c6cdb612': (9876845304, 771805, 2961512, 'c3552f53ccf6b363593bfd17a2c08c4c9a16a217e401ccf82827d596448004ee'),
    '35ce9b62c8': (9740150696, 59201, 1869908, '825583ae0ca52f43b1d369d73581e533b4610686f8111cd7f5ca1a3e2e47832d'),
    '35d719f9b1': (9815949144, 3086, 49828, '365d71c2cb4265f988d12fa5deef6365a8c1d2545068106f5861457a86d249a5'),
    '35df562d59': (9768193288, 30055, 1401084, '56ada19f54461c920b9c7b80da3b56a7c1e9b39084117097314891376d7cf20d'),
    '35f3dcfa3a': (9841562200, 18046, 163244, '45d0a3b55931f817465cd38bf25867923f5cbbd36f149ca668d8a6a1d453e09d'),
    '35fa0acb25': (9761861464, 3280, 41080, '01a41d1e3b31259862a0cf064a41f6b474a3b230ca6660fa0eafc07ce3b779b6'),
    '35fd4513ff': (9747554360, 8272, 1187968, '5d3d5959648b87a15f5204fe239968b94b2f8447573bd930be0178fdb5fb5b80'),
    '365ea14f67': (9951978072, 4421, 43084, 'd0ebd77130c114266287311ea4bf4c3a5efa3b2c0bba24be4cb1668dbf892727'),
    '36de21e188': (9963926344, 1002581, 7371248, 'c4313f423831260042f5e7becdd372ccdda417b33d98456fc11fa5d9b7c5fbcd'),
    '37099023ac': (9991818040, 10746, 174324, '5546f424fcdfc3f90c34efb8f791194dd9066c921a07feeddc7ff78a8a528909'),
    '3714c2f488': (9920214088, 1071080, 6895324, 'ba024d806a9223b6ab30fc42bc67aa83471cea03e005ef8f204ec300587778ef'),
    '375f417130': (10021536440, 22395, 561404, '9948061b5eb78139a1306b86d09cbb130a891bfa4c35b08db98e88744c912220'),
    '377b0d2f98': (9998303672, 553305, 3782764, 'c25e0cc0eacad2fed07875edd402f52ea8858517644b3e3f003234f7708dc909'),
    '379db955b2': (10092229048, 9980, 69036, '4dbbd20420316392188cb2f48c088e9d0d0abbd745139fe720d4da3863839101'),
    '37baf75a42': (10000380408, 459060, 903772, 'ac5d570437ed3e8721ae660f303305f49363c5b6cb6807f6e6ab1da3a9491df6'),
    '37cd10cd62': (9946725960, 31890, 648684, 'ede7e8145a6ad638a359882dee1d4c8e951d5af3535f443b2d31780532344d9e'),
    '37ce244cc9': (10008388744, 13086203, 19102148, 'fbaabb528725c904e21529c90f4edc5f4380abf6463714449b3a5faaeb7cfa87'),
    '37d50d9ee7': (9916080616, 163084, 826412, '4fb8c090955f9c31cbd4b43baf55f241371073201ffd8a8156ca832e2c77e9e7'),
    '37da301aac': (9991915192, 391066, 1584732, '5554b5cf94672b9451536b6311f0ea06e0ca301ad363aae4b6b01746804384c5'),
    '37f0e0f18f': (9913100760, 59473, 885212, '2b88dd58090fabeacfc28e46f46aa293dee4bdb43efcd4a178f12f212a42aafd'),
    '37f34925ba': (9963316520, 416986, 4154652, 'e0ddaadff64deccbc2e692ac1ed90e5b7ee1a2aac2e0f57898e9a6292618129c'),
    '38bacd96e6': (10045165224, 50090, 641908, '9b1f64dd531232378f14fc342685476c7dee92cd4d2b048b58b949b5727da54e'),
    '391459062e': (10101437256, 1740, 21401, 'db39b04050390378165dd71d5a39c04bdedbd9d2a2320534a17d730b4c15364c'),
    '392fce4443': (10054062856, 106116, 1876012, 'c19ef2d12e97be4a010fda04dbe22757893e682be6f69e3ee874853a19eed930'),
    '393637fc03': (10121377832, 2181051, 8315928, 'faa63cdc3cab34bb10a0bb92e57e70ad54b0599d9bbbbc0c0b106df8a401e4ba'),
    '393915b6e6': (10126965336, 19434, 231276, 'a2376f5ccf702aa352640ef56e5af6c9622f3c98f9cf8733b60ee09caa2ec55f'),
    '393ce26fc5': (10071458280, 72878, 477948, '2d88c0aff69ec381dfbda436687d7a2f86acb8a65ad2a69af2618ad29390b0b4'),
    '396e222ec2': (10106320216, 554438, 2205788, '1e986799bd711f625117a9b5f0b345e527ff4e1acb12f582a1376b72074225c0'),
    '397a15f3ad': (10101717192, 423113, 1328796, '72be77a8d48af2e7f4bdcc62f641e53291e6f6b9f65f1e13efd7b66d63049c34'),
    '397f9478b2': (10104849624, 73582, 530652, 'aa0a4d8a138da154493e1da9a6378bd6c1e2cb9e6c0666d9945a22889a2dbf04'),
    '398d8abe9b': (10035187080, 7209, 425864, 'b931aad48bbd6893c4db900d8fc0aedffff6e881e3aedab168f8ed8b1b37522a'),
    '398fc65fdb': (10123611592, 48172, 473436, '171d5831cadc7c9bb529ba6be54d237a3463f7f462ba4d711a059e30d54de597'),
    '39968c34ab': (10097297480, 628798, 1325388, '5bcf88df2d8cc14b1a55a5df8f240274d22f3f2a195dc08e5203c378b8f9cb6b'),
    '39a2132b2a': (10033126664, 18915, 539564, 'edac7bcd8e0b7e1455d5ee203e4ea8c025fce031a3facd760fb3823af09c5de0'),
    '39ac14cabf': (10125610520, 47689, 425040, '44506c6e74b4f916f2b2d0eeea0327ad8b48828637dacd4c64aeb0f4438cc8d6'),
    '39d730bdfa': (10028579080, 351001, 2736092, 'b06b5701983783d66007075f6f7d23e4cd096867a0ae05b87230eb76d1d32cdd'),
    '39fcfc8799': (10106882520, 493184, 1056644, 'aa17124cf557f45e2cfb306633eb9c12cf5cf052f6eab3692c36fd4b38c1d766'),
    '3a1b755c17': (9946768984, 683, 17700, '0395cd10ae13a2d975d2a1eec7178a61adc570ec8152e53e62c5cd4139557614'),
    '3acae43226': (10265654200, 76309, 543296, 'bb49ea650ff6c27ab4e560b9bc71690b642a6ac31b3a2c09a5942579ac14dae0'),
    '3adaf18201': (10215849768, 24071, 257228, '54a96bbc6e6e2e437d386f64b8b42d53924a1c329031a53f4dddf91712110e23'),
    '3af589be42': (10245093896, 751425, 2525368, 'c15fbad6a6fd80af4fff32ac5cce54c23771fc7c6c027eafe162ccc283c5c746'),
    '3af82ecdb8': (10166163784, 91879, 315520, 'ad3d68a71e952dfd183c5c1fe3fe0ae3c8ffa57d35726c1508434a895e4de20a'),
    '3b0cf76306': (10283069944, 34431, 528576, '06842669a2b96eb778b468897e929096e92ee9ddc4533e0d1759e60f2c64aece'),
    '3b0ed63c57': (10260548392, 370329, 3374156, '12b592e9a2489de313377bd8a905b336ea9625d63351c30acd2150985d09db02'),
    '3b1e6d22cc': (10242718808, 2366689, 7041060, '17a9e0ac91bf56d6f42b3dbc17b33bca4e292157bbe8d64de9d9ece5c4dc7e7e'),
    '3b2c7f8958': (10199511992, 61478, 717452, 'e457c72806e5829b7ce9771c5eb41f22707c514a1a4b2a1d46c21c1ae5f50a25'),
    '3b341ebd51': (10194422552, 3693, 39000, 'ce2e2efbd3160e328c363d96ce219eaa3098e6701fee62f34cb973ab92abe101'),
    '3b516bf921': (10187111224, 34431, 218016, '5c1bdb05a72b879bb5c49a7bf0f50134b1cb9e275121260c5d05189eca9c1dad'),
    '3b5b8ce560': (10220051272, 137102, 1625448, '71547648638252497afcdd781ab90578c8d9eccf7782493eadcd71c6f85dfd49'),
    '3b6f0143b9': (10237348008, 4636, 67024, '98bc1e03d3b8dcfa4c14733f390c241fa94f940a2bbe18dcd3b4491bc98d9b2a'),
    '3ba4545276': (10245086024, 7872, 429500, '605d7d028f00e731fa0f1f88717266b48a31051206245530517319f44a5a7aa0'),
    '3baed998b7': (10170785992, 2455133, 7787044, '29c866b76e9ef03efcf1d2e5eddf2b7fb8e2e5d2eba90372740fa545ea0681d6'),
    '3bba4333c3': (10249185784, 1281, 16912, '4ad8f01737d20e19077bd797e85314b13dc72f8118c50c556914b5471a2b3a6b'),
    '3bc424606f': (10132620888, 93837, 681564, '69a61f816bbb668294b1b7a28d6650deedfb4c91641f6182d387c846717f9771'),
    '3bc531526b': (10142103480, 3935, 25204, '1f3fb986e6b90005a8841603c0f2cafe60216f4f81554a74ce01f1d03bda59e3'),
    '3bceaae1ed': (10252470840, 435220, 1442380, '8338ab6f63187bbea2534f24e63aeb6567ac6d6c8b02e680ce68c5aa186b2087'),
    '3bda7eab0b': (10285478344, 38090, 723436, 'bbc3fc30183c9b159c4fabc6c5d4d62cbd53a0d64eb1967b0237d49acb69c8af'),
    '3bdab3a457': (10190703336, 202745, 1713644, '3f247d279bda0b8112ce3cfdc5dc6fecfa777bf4734b9a2e3c7d78db69373bde'),
    '3bed60f89c': (10155811832, 2991007, 15251308, 'e91c5ba0785879dcf0388c353fd891511086604d96801aa49adbcd4e0551f817'),
    '3bf6841187': (10159063384, 59855, 930772, 'ea44fc3b1515627f07f05b3406893551e1bdb1fb1b389a08ba17cf423c13e3d3'),
    '3bfb21ee54': (10168820792, 802, 16488, '00f533e7724dba304f93484f9060f75dcf11d9bd7af35b8419ce9725587561d1'),
    '3c43cedbd7': (10409348088, 27670, 362332, '0a63ec16b76744ea193ca0b2b468e4351fbcbdca1f6f7f8497254def82c65d7a'),
    '3c647f731d': (10364508408, 33809, 1442460, 'e27fde1f7f99d1facdec50a1d8a454cb890e770842f2251b0c682b92e70e0641'),
    '3d02fdbd08': (10396758232, 9437126, 11119956, 'cd50563746b7649686c417a44c5325b5687e4357bf1f9ccacd317134829c5041'),
    '3d0aa70e98': (10460835992, 3201, 36984, '6c005c6d4c83ed9681383655189f8bffb6af3c67530f55ad9e88b91f8372efed'),
    '3d0e501bcc': (10444586840, 1792562, 9182268, 'f2ebec2c683bf1e3740bc0be0892699a141dceeea856b0f2643671b2bc085b92'),
    '3d16d801e2': (10343680968, 7429, 85000, '6fba492f94a684df8a7e43b024f5b8a2c75ddaea953d27a7e7830bf87d13f195'),
    '3d2068ef4c': (10360801096, 20211, 244060, '21800686f7393f38b764097c1fcfde9503fda1c8f55cb392112fa3c03b646ff5'),
    '3d2f50bc31': (10334420696, 165640, 484968, '3f11b50fc91d1b45630b9bec93283045b01001a0388805212dca5d1402fa2436'),
    '3d33c927d4': (10454035448, 291773, 3785636, '0a6f2fdebb254d4d06162a40fe36fa15dd306d18eabef8cfa4dae7ec0408a4c3'),
    '3d359133e0': (10387927608, 136846, 601936, '16b769b5caa4b382cad1059594a57cd386ebb9d3b5eaa9ab66be6af7e0c566c3'),
    '3d3c064949': (10361552728, 11984, 185248, '57783e0c9376e6b25e74d6a7f031520de31aaf24cc45d0cbacdf4b086b1917cc'),
    '3d577f81f0': (10478349848, 446063, 4559696, '1656e6f5021095f82e94d10d156bd08ba65d0546130b1f4f8dbe0605098757a1'),
    '3d6357eea0': (10301325144, 20737, 332108, '87b5badc336b2a44bfe73fda6d6f2f3cd629b1ef1a1a339fffc984e8cdc83c43'),
    '3d707fed33': (10392820712, 26536, 257860, '1c84f7d4905b2cf276a98ffff65d0d145399b8bfab40b9735c042bbc52132b79'),
    '3d78dd8b8c': (10301347944, 1082172, 2672556, '6a9ad7e95f5e4f8235df9b694981e97f49c7d0b5c6bbf10022e19d1a9f3ad52e'),
    '3d8742de99': (10458866376, 27729, 1369260, '200d0f1a25e65698acca4f88f45d416b4a1b0fb9ecfde3dc77f1ecc5f6ead1ca'),
    '3d878ca466': (10368631736, 574, 16488, 'f29d8975d89add5a3efea9fce578bbc2e653b36bae7d416529a217ac71d94eaf'),
    '3d8e900587': (10424885960, 928970, 10209952, '43f97369f25595f94c012bab175fa45f62d86b5ccc078c77cf7d0821dc6595e3'),
    '3da52974bf': (10327887896, 930372, 3167472, '9a2ce62833631399822612113939ae057643e62294e862bd8df1ea3eb3014102'),
    '3db5a395d9': (10309786728, 677112, 3108984, 'ba9b17a6951d50a99a6afb8bdb64d112bf7254c0902b9e77f9f332c625022c37'),
    '3dc77b89ba': (10366469992, 34257, 712284, '24566c3dd427ddacb234a731dfac06c29e4e4b83ad62a567608baf23fc28d8bd'),
    '3df660a75e': (10421722024, 570770, 2726268, '9f65d96d05c9500036ba07270607d366b9a7bbec59b66a493f1cf4d8a74847e4'),
    '3df83a365c': (10349440376, 74875, 759420, 'e0580e65cfb9386c1acb2634a8b50865e91ba46e312605c95daacdb0b4e7ef35'),
    '3df8e39733': (10457246568, 17983, 1386108, 'f1170bb892b72dbfac00924abb84f9f0011330d73f0ea04264f8c26c6d91a20a'),
    '3e00b806da': (10512802248, 18460, 218168, '2d0161f6ecf4ec50421450ac913273b12be8522952bfbe3a7a4dc71166c46e1f'),
    '3e25e799b6': (10508634584, 60884, 1798252, '518ff7c7b6eac95d7d01967d610d0965372f1a65ff9fb302030ee4e5b3ccd5a6'),
    '3e3802d641': (10220224344, 16916, 403584, '9673405094277bcdfd7049d8d1570eb79ad4938a4b28b5885b787273203c8fd7'),
    '3e3b04ed3e': (10220517768, 6919, 51704, '941191f4c3be530d0da61f053c81245a979947508e0d18109f6257ff81c856af'),
    '3e490561f8': (10518649832, 77564, 960316, '2a8027b2dbb22a930aa90f14b5da194c98131e7b7ca585d7865577a00664e2bf'),
    '3e4f9c04b1': (10220241272, 127930, 1102388, '02b81b13c5059aa1ddbc697f50a11f26395d16377ba7368d2cd59be9b60c2c1e'),
    '3ea0a1a151': (10220370984, 146783, 832452, 'f35c9034a13a4e8811555442e77df8e2eadb3b7b385f836447748ec422839c69'),
    '3ea3a79a2e': (10220188376, 35968, 165608, 'c891a44948bb9e3678c03474259d8dcca5dfc0bee8a44fc552dc622aedece10e'),
    '3ead5249cd': (10477856920, 492925, 2338544, '13704b4fc8f83c68b6a5923922afbe7faed31c7f08091b44607c5765232b12f2'),
    '3ecca5faac': (10577057544, 37971, 737340, '25c81ef40a61c0a73a70316dc85ece6d6be477796366018e435bce7f1db75e31'),
    '3ed43948de': (10220369208, 1763, 25588, '8488d4672c35a754bf1d31cdcf968267e5bac5889f80d2b401ddf42c4e0e44e3'),
    '3ee1af3551': (10569538792, 187098, 2676724, 'edba13ee1f3d67136f38efb4166ae536b9ddf495c240d9cd8b536b31d54bde02'),
    '3ef06055d1': (10517692632, 37058, 319628, '0037a83351b30137e65e58d639bf5f5619820f5a9cf9d9b5c201ed3e491fea28'),
    '3efe2c4748': (10520654024, 11757, 206764, 'c18abb7e3786c956cf9117bfdfa9223e8200c1d334e648072ba9d9ac94050c15'),
    '3f1a6d9b4a': (10520233144, 420872, 1310316, '922c55bba7e087cc02c6eb92029f8041d18684f65cab8955072148ae2823125d'),
    '3f359f7e8c': (10582074840, 43156, 516336, '923bdb6cc0f91acac892cd83a96f8c762a50cf88111ec68fb24caa09a2ed96fb'),
    '3f476cbe84': (10335616216, 53847, 2369060, '72a83651daae0819e1b41d8d486f3217ab3ae11e00cc2f5735a27df3b870a7cf'),
    '3f8c418d00': (10571722200, 4023, 45912, 'e641dd493445b00a3059187280c0425c1273f7297a1169d3440c799206c37880'),
    '3f9b5ccdf4': (10479183688, 483114, 2433152, 'aabcfebfed7157e6ae0c345a9c1be76b9b1e4cda56520e8edf1f538d431f43f2'),
    '3f9ea4d7fb': (10465091992, 36010, 389988, '0e16b5d3da6444a37bfadc955fcafd6a4b93b9fa3689ad19f15d05494aa2e728'),
    '3fa1931e1d': (10476868664, 3190, 33848, '6b3053099ff42e21d689bf55d53e48e214e6a5a7d33e23eb849fc44582c70ab7'),
    '3fac74814f': (10483031272, 423586, 7925088, '2ce3c1337fadc7406f375dc44645a2554acd12ec702e22992b04e1143eb5ed2f'),
    '3faeac80a7': (10548507704, 480543, 1935008, '7ba8add14a4f0297fcbed8b49a286669eb1d63a03ba6757d1c8c1002a6ce9afc'),
    '3fb39efa9a': (10470380840, 35356, 373708, '2c1e910858d7fcb87fb2b6a02597fe4928e2594bc6cc845407cc38035accbd9c'),
    '3fc9bbddde': (10523299816, 1819991, 8561084, 'f7afebcf326edc4aa3a9b8ce7b4d0940f4132e35b8f14d40113e0288804b528b'),
    '3fd1fd20ca': (10482002520, 45659, 1601420, '51ba0a1566de34640c3330cb50d0936a3c061ffdd93b37e473f3b9a4b351ffe9'),
    '3fdcc9f2eb': (10335463704, 152508, 7299200, '4113a85d8b81b03f4f49f72b8511b37e5a6283477d6929d1c516ec63196194bd'),
    '4021f162c1': (10645078200, 38390, 293452, '8e76c1103c11bde3337780e0a7377fd22232d1bcbcf17ceabd1f741e13ee8df3'),
    '404e9211f9': (10766539272, 991997, 5372716, 'c3a84e75ce73c75c544c72692f0255850e987f529e73a7e16cccda9ab48802bd'),
    '40613bbc3a': (10909988920, 91343, 866264, '5854329f7a3f90af310a4844c0546f5c0df2b544c6517b9a525840ec8831e1b5'),
    '409651e111': (10750229176, 94786, 687436, '6f28241928dbf30e379b089459c2b1e18e24f4dae196f947ffaf27821b738046'),
    '40b4b3c67f': (10729316040, 38384, 296028, '74601f943508433f2807851e6cd471d811679c6a0b735ac276a3edbeacb8b37d'),
    '40d0052dfc': (10950193208, 38325, 293052, '41b30f0b778f6fe61407162220ed8588117da338a82b0d6857052cf295cb212f'),
    '411e6b1ee9': (10847819800, 295378, 1676972, 'd067ebdb31c6722ca6e23232317a6eb898c85049224cd77b930d57ea4f47fa83'),
    '413e9b5662': (10673858872, 439922, 1536128, '7d919b91796254956b098992ee83ebb06bcad03258c84d14bdfb2aff366e86b3'),
    '4146ea3fd1': (10813165368, 212619, 2583772, '3d24a3e4cffbffe2a5bd4d34f4b2bc9caced61d475ad95f710a3549a29dac434'),
    '4147f8a0bc': (10813377992, 226185, 1305124, 'e7795c969356422b2fd9aba5d5a1c5a31f8e1ae40c79405a2c4dfcd89cda073f'),
    '414e41f7e4': (10756428008, 83733, 3489416, 'd230ec8ca6b4a7f896c9712b03159b237129a41d7b655ce40397a6dd831ff53f'),
    '41526185ef': (10904976968, 8596, 155396, 'a7755a8aa18f3ca383dd732e66fa0e2b36cadf1766679ca6ffff4aebc45117e3'),
    '4166dae98a': (10935671928, 1785074, 8632588, 'f1c44336e7e8d9cc5a1cedd435714c22bd035b52c01bb191b748163fc547ee93'),
    '416e26f809': (10649994776, 66070, 910680, '953c82b048bbf4b744c657d6c9d482064f869c19ca6086e882da887321c58960'),
    '41779f48bc': (10792499288, 1133501, 1812436, 'c5ec0e012315fc4943e5fe3f3aaaf2000160aeb82abcd914dd46e6ca90731407'),
    '418f9f9a84': (10707951944, 48181, 781356, '4b4bc068d564391135e11a94ee1032ef7c59edcf67bcf903c9c102f8499c1e93'),
    '41adecaf3a': (10840450648, 1019, 17080, '86cb9d318f6f1ae8d96459121de3f5b5e3ff29cebf7055f7beefa454991ea037'),
    '41ddb7ad8b': (10692895720, 1103539, 3552376, '78d181ee0749209b68bd7e138ccdb8bcc07749ed2a8547a8c3174566af7e36ac'),
    '41e03b7842': (10934083128, 1457257, 8356256, '9f096cf42d52a8e68fb4b6192f7d68049ecd076508fb646630af893a1ddbab4b'),
    '4208ea30d4': (11093456200, 1133015, 1945548, '81f140d0ea9433492f0a557619aba27e0a75e3592f661b4a06b17cb5c37b1ca5'),
    '422e809b4b': (11089932632, 29069, 286800, 'db0efff60d05792b1f1735cb7e33361323e84650e79b59054961a47895c88683'),
    '4231d5ef4f': (10969939064, 97141, 1273820, 'dd93083cac916d734ff0e60acfceed71922f9a95cdc8baf2de23c81c4d792288'),
    '42dd32ab34': (11083005752, 23882, 275748, '6b14515fd7a08b1b6acd23e92cc8016963c67b511fc9f2844e66668e5f8a1dd3'),
    '42edff6864': (11089929752, 753, 17372, 'e5c6838e4e4f19dfd2d7033947c790dba089447a5841de49217d0b111f380e5f'),
    '42efa94c4f': (11080134856, 35918, 386396, '39eeeecda45e262dd9e4f79a26f86c306e7f4da13ed956ed2f8ed3f13d1e45fa'),
    '43000f1b76': (11148481512, 9682, 98720, 'f26b283384bf83d97084559f8dfb5a3318dc2dc3b09852fac98796c662eaf744'),
    '433ebfc1d9': (11081071400, 37657, 576508, '7e54b83335c1ac95bc24fb71c4c33c8868c8a2db393f6c0674bd876ec536191f'),
    '433f6cd68c': (11171298408, 2122, 24896, 'c6efb961e639547c7f3647b06ee6b504b63171c121563b8c7cd74787c010af68'),
    '435f56443d': (11091959832, 1985, 24704, 'b464774d132d62be305d7f6e55559872ecc1c87f9c87dcc148a2c2bef93a7561'),
    '4366792c99': (11185722248, 2523156, 9714804, 'ff62452b4559ef018134e4bd02354b8ef9eb82972505aace68bb946cea5228bd'),
    '436fdca0fb': (11079107176, 5796, 39772, '88aa093edb4900cb8fb94f6741b49c6685e131ddad3e30412c3d5df282204b7d'),
    '4378fcac41': (11159438456, 963470, 3113276, 'd2150a41c9d1b31d88b797a29005ee25503bbdd31fbfa312dc592803f35a3cda'),
    '4386fef4f2': (11119610744, 622645, 3403700, '50b73b044e5c122000c1fa5dbb18b84d06bcf9428efc29afce0ee7d778eeef58'),
    '43a1bce805': (11123463064, 60487, 1985524, 'c4faff74039b071f6c9880912650c35b4e46d088efd546d5896859df4b9d6fdd'),
    '43b0f7ba88': (11016185016, 6155, 62272, '788100f72c3d59187090b768d0cb22426ec3259f3d85fb2878f3599e30f16df8'),
    '43d97493d8': (11081131192, 1742, 29380, '16ab08e7636094a1ddb67bee4bce93740877b6d5e2541ccb431a77a6205d37c4'),
    '43fa4398b0': (11032409944, 27993, 230280, 'ea2c5a5affd4321f64425001f6091cac1d31813a0b02598d262c1e3549ac8c84'),
    '441336e080': (11207248104, 771809, 2961512, 'f22cbfdfd6d3a83ebcb3e49980d8f29f4c9e3f5375133568d159632387ac4cb0'),
    '4476569044': (11361098440, 967645, 2084540, '633b4ab67f0fda00d65af4794f880b3e86a4e59fb7e7dda74d3b0204dcee21d4'),
    '448c3b5047': (11307186248, 4588, 45184, '62d18104cd02ef230f2e83f12a88870ec4191ac9b9901b37b7650a304b83065e'),
    '44cdb100d1': (10558506168, 4806, 69752, '15603a2e08cc3d9b2586a08f22edd9d9347b0563bb0eee8df5b9364d8e1328a0'),
    '44e152f14f': (11206125432, 1122667, 3111804, '0e47a9e8cac4a811f944b307d802e0e2cfdaaffd867761eb35a4f6314a6fcf47'),
    '44f2b848ee': (11203481800, 3925, 44300, '53a2fbf0341cc35573a3e7dd566604715e7d36027f84b50369652a5b3291fa31'),
    '44f4a0013f': (11300270264, 10182, 87896, '818e1d9c13daaece1dd2ba1b63e2ef4624625a34692df0ad4df01c84a3902d36'),
    '45148b3c3f': (11339540632, 2304581, 11645912, 'd2529b2ee917fba6c45f4d56e9ce54a8a5e8845fcffc34ec2fd208cc39a95cb6'),
    '452703a0eb': (11366520104, 726350, 848764, 'b085168b11784812ceabafe68ec97ce7801832d774c28a3584e7d5fa24a626fe'),
    '452dd70eac': (11288670088, 151737, 649160, '124b720393c52ee261041836683b7788b682eed4360fbbedadd8c3874e74a975'),
    '453da8ae7c': (11294682408, 587722, 2014652, '1657372807e51afd6fe6a5a917a2e506dd682007aabd1a99184e96bfe38d3e5a'),
    '454365a87b': (11307036760, 8471, 75444, 'f24a619d354c1af5dde8871fe74f03fe39c7431ed2ba3f01bb2f2e112bf92844'),
    '45452b661d': (11398303240, 760, 760, '09eb70a393a5c82c93c8ca2e92f93e33a34e9431f62331272677c5a2f40443cb'),
    '456265477d': (11335604808, 46475, 330408, '29dc009a0c7ef1cd1ea1e93a55502d9fcb28c6efef7991382fe418467a868caa'),
    '4567472f56': (11244951720, 2359853, 7695140, '0ec1f2808cda8f2c58379d518461acb1e25c83e32d032b96d682d2851dab23ef'),
    '458e89612b': (11393075416, 99821, 650436, 'e0c8418c0260551d4032545b49cbbb58d4ac97878a990d2430794481097da6a8'),
    '45a14ead0b': (10220524696, 852, 17476, '7da7f105e62623aa6b4f08049469125f4657e8c504300832de87c800310b52e7'),
    '45c8bb4781': (11265485416, 1085731, 6687620, '2e386ce84379af4de4304746bd8418446ccbe3018eaf0d48f958fb8bb0b411b4'),
    '4610b6a1e5': (11511627224, 812613, 5853340, '6b24ff2bea6a0a695a306ed4e8f339e29e29e15f9be3354a141f7a983a4809c4'),
    '4649a1bf3f': (11544720104, 1575299, 8059600, 'd7f68afe3061ab133f2b25f3f8f4492cc0e500e5f8c3dc897a09c14bdd078be8'),
    '46aa9c30a5': (11425113160, 1745446, 6096636, 'f2a7f8dca7880cade6eaf29a04d37f9297b7e2c51d883410d772a1f87f9a4c11'),
    '4711f69ee5': (11421561624, 32045, 350924, 'afefb213abf8b0c54d0cdc075459c10159b581cc63b2d2df824d3fb96f1ec032'),
    '4734f2e022': (11410728856, 328196, 2961512, '8373231fbab07d35c0f39568bc6729db13dbade63ba783261c62a58b5d61ee35'),
    '4738b237b3': (11410192136, 7278, 47760, 'ee37eb9cb44d7eade207e0eca2a9d5a55edb8dc387a717142abd892fdd5c57b6'),
    '4763b2296e': (11475011208, 140825, 295040, 'd92b8a585295e351aa9553df97554dbe1a68cc30b519128d229d4c303b6c3157'),
    '47709fa93f': (11475168472, 1776, 25416, 'd7cefaa4adb05dbd386cadb729c72bfe1288b642b105b328e7a3397da5f6c1ac'),
    '4789f3c551': (11553511000, 316841, 2453764, 'bf61efcb7e91fe24f151c47bb920b23f8aae9f0c30373eb0d96ee087194739d6'),
    '47980de932': (11439580040, 31612, 389900, '22d268cfaf10013003466ae13811821c38cb09043773b86b7eeef72d5f52a600'),
    '479dc7e274': (11548279848, 15623, 129884, '40053ddc7c94eca3eb14b370aa4c251c41ed9700db3017167874c0e36125f5f5'),
    '479f15c45c': (11411061160, 23134, 386712, '639133b2d49950b25ad664beb6e5ba8dea70778f78d64180ea2cba464a5e65af'),
    '47bed0a29e': (11416949608, 71415, 639484, '56556171b98a987b14ea6cc17dc2825683319d0f971a3e0742a628b4a4cee2d6'),
    '47eb02034f': (11446897736, 3070276, 10663896, 'd31d069f378cbde84773546bdea8e6065326e898a562bdd47b25dc5f0dc79935'),
    '47f4497116': (11544691880, 28210, 288532, 'adcf20a5156aadf20f36eb3e3d2fa12eb7c6efcfb652e0a5e31277adc10dd4de'),
    '47fba52e05': (11402943320, 529043, 3109372, '09cc4363fc63f8e9293136ae8949876aadb577d01a0b7bb56acdfdaa11621998'),
    '4801f37a9e': (11691199176, 83917, 849504, 'f2c7de6b98f2a28c4b77fea903a81706e64091dc76e28e69c2ee3af33a4e1364'),
    '48a2c514bc': (11625377080, 325977, 1327564, '93668eee58a6a6410f3de68cec9e1b87e1b3d7c7f843ba8d3e9f4fd790bfd316'),
    '48de88ba51': (11695842776, 99267, 1145836, '5b75b3d1c2879c383a78373eaacd1ba37fb66a55d33913b1e228a7f60c62c0af'),
    '4903b52dc2': (11624333976, 626614, 3434404, 'ec3b12ff3e66b198e2ac038044c55809f661202855c9dffeee9cf3f376e36196'),
    '491dea2f10': (11640631000, 32393, 290164, '5204c817d987769b86b00054faaa6f132c3297f6b20a2f561fa6fe96ea4e7076'),
    '4932c70acc': (11582794328, 631799, 3446500, '0660ff23e925505c44868f7d2cba5225de95540e9640ecbc7229ca826b7622d7'),
    '49335f878d': (11619603496, 34486, 341744, 'd5a859e7918fba44a13fa1e4c9645235e02029311255e6a621f6cc4f24faf810'),
    '49369b22ed': (11685191256, 106106, 877956, 'bb393bded6967bebec2e19d88d0c3d2d358bedce096f8e91aac2359d3538a948'),
    '493fc894a1': (11697318424, 7509, 174028, 'dda738438da9e24b3a7d6076b98d5d9487c3ac88783f8d761ca03e6e5c9a5c6a'),
    '4943f49a02': (11705363128, 501255, 3749536, 'baa0bf83912d7924532be9887bb2f5a8480775910cca7ab282058a9e416bfac7'),
    '49595ec70a': (11630539464, 22216, 208812, 'c9cd03e16245b4704e020e321d5850e95f29f4cb3fa93ee753739652922dd5b0'),
    '495fd95785': (11702869064, 272408, 2207420, '191eed4d71944fa51782adf76f9061b83a19b8fdf76ef1fb3ed9a9d827751372'),
    '49a71bdcca': (11646865992, 44882, 1329404, '7bb3fd8739e4f0918a4b46d6c3808d8d7526e8a686ab84327f5670abfd334b3e'),
    '49cd92cf70': (11691283096, 54916, 1441372, '82d4a0645cff6529bc38079e76d219a860b43efaece0134f8f10ea871dda61c8'),
    '49e1642d97': (11627356728, 430256, 1395408, '42ab399b9be6f0662547f79183b40a896a64508a6289dd90fd49135e50417067'),
    '49fdb49b23': (11636409432, 401208, 3624704, 'd981f1f987f45d090ee7d9409d74fcc84a5fd3d6e329705fb72a645d86228810'),
    '4a1ae2c5a8': (11711127768, 18851, 216076, '6364e2961073120b611665b867e69a6cd76866f3eadd4912441aa443d192fb5e'),
    '4a63c310ba': (11737859688, 53439, 1645228, 'da899f79b442aa9c79fb776c12816a653daadf2d6f5ec41cbb67ed3313b0b853'),
    '4a771f3646': (11711110936, 16821, 241084, '78eab56679aec684f517db08012ba8c0c3ab52930e69ffb69e52d9fbd8351bc0'),
    '4a7ee45c24': (11801263496, 10900, 312740, 'd755f106bec1d4606accdff8d78991984cae0e3e0523b6c27bc1163015f73a08'),
    '4ae8252885': (11771611016, 118438, 1131360, '68678def36e98cc4b3038580954efe1cc7a0959db2db009c232bd2229c3339ee'),
    '4b05fa11e0': (11749933048, 102585, 506460, '5b61a206325e9d5905eb54f987efa1416818947764a6e3778e7ec18a109d9136'),
    '4b065a9f13': (11776015160, 577, 16488, '3a1a48d618c25f6b4cd1990b7a17cf6bc4477f90361b9d670a736e5dd8b7e4db'),
    '4b1cde7800': (11840859592, 156381, 1189140, 'fcbb15ed5d4b205f459b6be3b3fe620eaa5bb67d39aeb4f0c42634374f184426'),
    '4b1d14344d': (11742721128, 622131, 3206368, '5593ec9bef843ef08d94d2ae0565c74cc0d57aa86fd80e88f3d9a3b9a3946c52'),
    '4b3edaf864': (11840543704, 290670, 1791404, '2dd4ccb6c23de9797508385a69d7e6dade2faed1f92647b9e53effb65ee7affa'),
    '4b74330ddf': (11776995544, 74127, 444548, '5018e643c96acbabed9ecce70a3f53601ed4ac6a40d844a9eb2af7d6dde5ce2a'),
    '4b916b03cd': (11761715736, 335775, 3577088, '17969585886b779597e7b82de06a05112107e27e813f8443f582d94d4381f84f'),
    '4b99b6925c': (11775678440, 185053, 1318332, '1be01c247896d5aeace2cca323d427ab66a5c34026a4309e10a3050f5651e9e4'),
    '4cab523283': (11983234264, 12311, 55116, 'e3b51e31cdb85cec2e1f9620e05654322633cb2590cb70c783c1d705685dd251'),
    '4cd49feead': (11867086632, 127003, 2153596, 'b1cd601a745e4fd08185926a6b0f01fc60092b07b99d7c840e14bd198468a4b5'),
    '4cd8f28383': (12042900184, 849, 16488, '2d82253758a40de9377bef1a4844e99f29628955760a6937c1cadf81c7212350'),
    '4ce88c921c': (11869106120, 906111, 3057316, 'bb8b23653c7e3993555f0bd72bba0097d56a9949531d898399ed636a33abc1a0'),
    '4d07360250': (12012059896, 759, 16488, '76ae71c43deeb56db885d619e472867b7d45b220bf59aaaf29c502e52ac92ba2'),
    '4d08ba44cc': (11848792280, 1097222, 4469420, 'bb9bdee2a0e8a2e353cfaf0815004f0b840a4db007fb08e1a57099095346c0fe'),
    '4d0c9b0fc1': (11986596040, 550632, 6174620, '9b76054332a34249bdf6a7e95a0b93e07a0011e8b064d1404c26c9a76f80e3c5'),
    '4d0db0094d': (11853191544, 1106300, 4665232, '3db766ad5db74317b0ad92e1c0ec3c84df0ee08e6b2fe93f3a2eca08a0e5337d'),
    '4d13a2120e': (11983189176, 41148, 430688, 'fbde8f5e98e36bbe3674a3de32a9f43a509321b56b1d96db62b63c715d99ac04'),
    '4d377d8b90': (11909736568, 23741, 274980, '8329f87affdb69459c5345c5a3c313331d4d9032926c61d2fffbb43d8316c6da'),
    '4d489a29f7': (11977045304, 8682, 82176, 'd916b0214ed6cc1760be269a4a532a000b5fb708d85a371a3d2d08514f69568e'),
    '4d7c22ad43': (11847688872, 1103406, 4756476, 'e18b401e01d47139cd1616c2f6a3ef9fa2ac6d895d256dd516562f5a244aa03f'),
    '4d7f24963c': (11852087448, 1104091, 4773404, '251244fad978c5d7db9fdb74eac830f69b402f62a1dd7cef21cf79496a3a17c6'),
    '4d901933dc': (11845491736, 1100077, 4530236, '9382013f0d991ec570dee55a44b4563bce3fc7b0ebd4df85814388bd1a766c0d'),
    '4d931f08a3': (11849889512, 1100566, 4538428, '95bf32d0c81b80967ac111ed61d2775a4709befc1c3f6b7cc023df74b09082f7'),
    '4d96154522': (11854297848, 1106512, 4673968, 'a3840abd21b2d95f4ca66e22684f15ae4ca6b42d235aa9add126cd9622901d6e'),
    '4dcde6f58f': (11909768552, 1709126, 4877904, 'c8ea15ea5c25ae78eee4f6eb53d7689d4b59bb7e9c72480df25206046c20129a'),
    '4dd62aa636': (11855404360, 1106821, 4681616, '70c1fb0833a023fa39f2da0668ca90797a827c14375bc1a8bf7b3183e1283440'),
    '4de481da53': (11850990088, 1097351, 4480156, 'ebeacdff76eca40ddedbe9c1ae4ddd91c860d9e228dbe4b8ccaf096c89149c17'),
    '4de76d7d78': (12033915288, 1475609, 2236588, 'e948af50c6b2c7490791b9851dc956f61b198ffbe138c2c2208f84714305d361'),
    '4de787e12c': (11846591816, 1097041, 4465868, 'a46e7263f1586c6291903c1b05515bef0b5866c1d55c7f48bab6ae4d5368c7f9'),
    '4df41442c6': (12012363896, 48390, 581756, 'a0c73ceab503c7b2e7d26782174c1a89d7bc30d5282dbbbc2e7b3bcf15e2f018'),
    '4e4756720b': (12079076536, 73239, 1623324, '0c4c1960de580fa49fe4f78c3358f40f509814ec173a16340c73634a95be922d'),
    '4e5d97a91a': (12135472344, 483223, 2437248, '2e5beacf5f5ff34ea06e91fce8f5a453781e23d2f05226b324119ac01e0fd92c'),
    '4ec389037c': (12230993368, 65254, 718288, '5435df21e7d05ca29d220cf05e14fdf13c6eb536052b11b36dbc856d209d61aa'),
    '4f3c72ccda': (11801274408, 10220, 143264, '85a584b4060079ad03efeaba44aa2707ca01ad28ecce5db5db61b9340ab204c2'),
    '4f74162dca': (12130527448, 60204, 649900, '8cc5bc5d3269ac483abd40ca222c8edb2e6f89b5e0c5d904655f35220a7a500a'),
    '4f8a07adb9': (12283235672, 39319, 2070828, '6d954f3af990b12d7311a1fb1d03ce4ebe34999cbe87967eecb1398897473410'),
    '4f9662039c': (12269269896, 523790, 1687660, '6af4593e09e5d343effab24358d7b3e739e8c172254958b60e7652ddf0fabc21'),
    '4f9b5db6c0': (12228364680, 21391, 303628, 'b3f365e8bbb881bd89d2e512ce4f6956ebe9ffddbdd7200079ae1c944ab0f65f'),
    '4fe8f3fdfb': (12124568616, 458326, 697040, 'd32d83e88042bcbadcba571158189c9d80a109ca5db4e986ae7086e666f2b66e'),
    '4fed728efb': (12197375112, 2906274, 7944548, 'c9ad948612b111f5ff314f3360ac7e294171961ba5484a85bbcadc11ffafe1d2'),
    '50b9b705a3': (12356472584, 867919, 3994036, 'cafa507d8467423c6dc77c7cca440ef0c06685087cb988e8ca9dd2a820a1add0'),
    '50edc40603': (12560329688, 756282, 1151452, 'ef2eac1f3f572a56990e583cb8848689c83bf48b8c9c66a7e611ea724709dbae'),
    '512245379c': (12513429288, 194221, 664620, '0580a4b39714ace01d62e196c2e9fd9bdf00224a718432884c112258ac4bd5ee'),
    '51d70335cd': (12453390440, 22391, 236476, '6d8ce8924e6b3ddf98143e54f522dedc5667dc74bd7820f7d25d3725ee744aa6'),
    '52108de542': (12727875160, 2493991, 6100012, 'de05b27ef5258a1c483c8f7dde1a54b1b98bebfdbfb2a681abda3bc1567ac366'),
    '5211ed724e': (12840965048, 3004010, 7357540, '961973ff9b1549fdc47acfcb28ed71ca696b0cb5ee501fbe8ab355724f2fd368'),
    '52250cac66': (12721552056, 1072263, 4693788, '6b7fcf91035c5fae092fa5f90b745809e7882fd59770733fc155c0a478cebd30'),
    '5235e85210': (12675928728, 503804, 3377872, '20b3a56ab44dd482b5cea8f5f00b783ada63380db899b61b69a99556cfe36d10'),
    '524ccf1036': (12667570760, 3141821, 6555608, 'e37627686116ffdffb1f154ed4f132047b51994d2c6d71a69217df0e089d06bd'),
    '5259735b67': (12717607144, 2614696, 6713564, 'd9ca4bf6b30bc7ac201a31a4f61b0ab2e969b9b67e3e417841e97479c6286422'),
    '526d92854f': (12803019064, 2877371, 5785864, 'fdc8c5db60cbee0eadbe2a27d57bbcbd0848998513be016800b7fa3c65cda5da'),
    '52782ece1e': (12638301144, 141152, 544896, 'b9858855c23e6bd5a1e7a49592b045fa6f9bc4cf0ae0e1d60f9106fa3115d3c6'),
    '529ba62cd9': (12767024584, 3955629, 6203484, 'bbe2eb8bea88c0d4b40ca48f6025b13a08e9b34cb901605a9354ce7dd81d27f7'),
    '529e45f90c': (12708860296, 5692, 42620, 'a424443e5e432ed5e50e1c8af117c87322da3a8419e0ca6c9c388b4f040b09a6'),
    '529f486896': (12661353672, 5167097, 9752472, '54ace5ca829269648d12fad297b68b0bc68958802a355c6e405f20f4217e1348'),
    '52aba9b6be': (12638450360, 3425812, 8769320, '3113add7d80cc6e2516c31fd0657446f7f873ab318a199defa2f49f71accd31b'),
    '52b2512ee8': (12857438936, 26615, 617092, '8005e71ec8ecee4c709b5263468295df3800928e203cf722c37e01e82e647008'),
    '52c26a0aee': (12836788040, 1375358, 5017620, '59de173fe0abaa69552776ae82c1636b3f844ed8c8d5ba261e2c4316cd22aae6'),
    '52f68bd4c6': (12725522984, 1891172, 3012080, '2d14778119b602c5cf5e97ce94395ea3a936784716f3b4bdc2a7fd5cad3b31c7'),
    '534da69c80': (12634478920, 15961, 1241004, 'e44baee1c878b3106d9ac94e7ca769d5316da0bae0942390661f4f79b87564ec'),
    '5369b5e37e': (12599404200, 28152, 303756, '2c48b437c280f1349709cfce1a83f78ea55ba326e35d2676b1c8ae867230fdaa'),
    '539d438a2d': (12752069064, 1202, 16748, '26b26d5a88decfb7d4a73a8bd7aece01b1264a4ebf3dd007aa2e0931a6e1168b'),
    '53d17467ca': (12773148584, 76110, 1550988, '7a0d2b2a528326a360292038605b50837a6883d4bc8354a9b9afd22cd2e412f8'),
    '53ddfc83e5': (11983246584, 1748, 21812, 'aaabbe288f4a824a492bb21db93b4617b9304a7d4dfa4633e10809acba38adef'),
    '548788c82c': (13047862744, 117591, 2171836, '9c83585f70c4bafcc95b91159aef450577c33b90951188bf8e236ce091aeaf9f'),
    '54c5bb333d': (12990193672, 7818, 54344, 'fdadd6f9baa7a97f00de658cbb54564bb5dae25b46440f3348d12cb5fc3ca46c'),
    '5563f03110': (12357340504, 874277, 4051252, '5b3dd06fe91c8f50ac6d8c4d51d36ef8aee13136197ff6bf806b350e0745ba8f'),
    '55a3c772f1': (12936443928, 124915, 574892, '84599ed4fbe5519515878c6215241afd56c9685d380b9f70df90e865658bf704'),
    '578978b603': (13235144664, 18729, 280876, '72ef2759b6e2071a5de5a3bd6deae106c89df70f60a871fba2dd5cb8c30a8f4f'),
    '57eb43ce08': (13282061576, 1701776, 4010556, 'ee4529a6dfd81c5af72539c74a6a6deef8566ab96ff57336ef58018062fdcf65'),
    '57f9f05b13': (13088000056, 81493, 584188, '2b1239ee5bdd39523e2207d5050bc996bcf8358b7d981e3f86775cc3ba0263bb'),
    '58b7130393': (13464000216, 133323, 190552, '07e500d376fd143affab3bf7816d67f1c17507b6bd844e38e1af6c72d55c871d'),
    '59b49dd6a9': (13560253720, 42722, 478092, 'f9225b65d50f837d5f2c5d367245456feb8212f6adf05b56e6e452d92195a17c'),
    '5acfa31190': (13640404840, 851, 16504, 'f3388e16c8e1f6301b48bb3a212cda5de0375ca5d12d393796e639b5f4ae0471'),
    '5d9ec02d38': (14024572904, 11660, 76136, '9abf6b93ac0bf513e5fe623784fb2becbe45e70df544c475ad708c30815f8d6a'),
    '6081935383': (14382439112, 75891, 933648, '6386a55ce13e53369fccd4e633816eddf489f8bf24fc03f27d72edbdc2479258'),
    '644456d2cc': (14723869560, 713366, 852568, '8efdacf70fedb9f1388e694cb7c9560f9f69713f35bec70ea1ef7e7c8c7e372e'),
    '66d690d369': (14872193624, 18843, 278052, 'ccdfc14123351bb67d57328e2600760f41049929e41bab228c0b4050d6a8c8cb'),
}

def frame_window(data: bytes) -> int:
    """Read a validated frame's decoder-window requirement without payload decode."""
    _last_block(data)
    descriptor=data[4];single=bool(descriptor&0x20);flag=descriptor>>6
    if not single:
        window=data[5];base=1<<((window>>3)+10)
        return base+(base//8)*(window&7)
    pos=5+(0,1,2,4)[descriptor&3]
    count=(1,2,4,8)[flag]
    return int.from_bytes(data[pos:pos+count],'little')+(256 if count==2 else 0)

def fixed_span_frame(codec: Zstd,data: bytes,original: bytes) -> tuple[bytes,dict]:
    """Recompress into the unchanged ARC span as one decoder-compatible frame."""
    window=frame_window(original)
    window_log=max(10,min(30,max(1,window).bit_length()-1))
    for level in (1,3,6,9,12,15,19,22):
        compressed=codec.compress(data,level,window_log,bool(original[4]&4))
        try:
            padded=pad_frame(compressed,len(original))
        except ValueError:
            continue
        if frame_window(padded)>window or codec.decompress(padded,len(data))!=data:
            raise ValueError('Smash aspect recompressed frame failed decoder/identity validation')
        return padded,{'compression_level':level,'compressed_content_bytes':len(compressed),
            'span_bytes':len(original),'padding_bytes':len(padded)-len(compressed),
            'decoder_window_bytes':frame_window(padded),'original_decoder_window_bytes':window,
            'one_frame':True,'empty_blocks_emit_no_output':True}
    raise ValueError('Smash aspect modified SARC cannot fit its unchanged ARC index span')

def _clone_file(source: str | Path,destination: str | Path) -> str:
    """Use APFS clones when available, with a conventional copy fallback."""
    source,destination=Path(source),Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Smash aspect refuses to overwrite clone destination:{destination}')
    clone=getattr(ctypes.CDLL(None,use_errno=True),'clonefile',None)
    if clone is not None:
        clone.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_int]
        clone.restype=ctypes.c_int
        if clone(os.fsencode(source),os.fsencode(destination),0)==0:
            return str(destination)
        error=ctypes.get_errno()
        if error not in (errno.ENOTSUP,errno.EXDEV,errno.EINVAL,errno.ENOSYS):
            raise OSError(error,os.strerror(error),str(destination))
    shutil.copy2(source,destination)
    return str(destination)

def _private_output(output: Path,rewritten: Path,data_arc: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError('Smash aspect output directory already exists')
    output=output.resolve()
    repo=Path(__file__).resolve().parents[2]
    for forbidden in (repo,rewritten.resolve(),data_arc.resolve()):
        if output==forbidden or forbidden in output.parents:
            raise ValueError('Smash aspect output must be a new private directory outside source/input')
    if output.exists() or output.is_symlink():
        raise ValueError('Smash aspect output directory already exists')
    if not output.parent.is_dir():
        raise ValueError('Smash aspect output parent must already exist')

def prepare(original_main: Path,rewritten: Path,data_arc: Path,output: Path) -> PreparedAspect:
    """Create a complete private4:3 cache and fixed-span data.arc overlay atomically.

    Input caches, NSO and data.arc are never modified. All original compressed
    spans are gated before staging begins; the final output name appears only
    after every transformed SARC, cut, observer and arena check succeeds.
    The overlay contains data.arc only; the builder merges it over its complete
    staged RomFS, preserving .nrr and unrelated files. No shaders are regenerated.
    """
    import stat
    import tempfile
    import smash_aspect_ui as ui
    UI_ARCHIVES,transform_sarc=ui.UI_ARCHIVES,ui.transform_sarc
    sources={Path(__file__).name:(Path(__file__),_LOADED_SOURCE_SHA256),
             Path(ui.__file__).name:(Path(ui.__file__),ui._LOADED_SOURCE_SHA256)}
    source_hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,(path,_) in sources.items()}
    if any(source_hashes[name]!=loaded for name,(_,loaded) in sources.items()):
        raise ValueError('Smash aspect helper changed after import; start a fresh preparation process')
    raw_output=Path(output).absolute()
    if raw_output.exists() or raw_output.is_symlink():
        raise ValueError('Smash aspect output directory already exists')
    original_main,rewritten,data_arc,output=map(lambda p:Path(p).resolve(),
                                               (original_main,rewritten,data_arc,raw_output))
    _private_output(output,rewritten,data_arc)
    nso=original_main.read_bytes();_identity(nso)
    arena.check_rewritten(rewritten);verify_observers(rewritten)
    original_binary=(rewritten/'main.patched.bin').read_bytes()
    binary_hash=hashlib.sha256(original_binary).hexdigest()
    image=bytearray(original_binary);cuts=apply_image(nso,image)
    if data_arc.stat().st_size!=ARC_BYTES or set(UI_ARCHIVES)!=set(ARCHIVE_SPANS):
        raise ValueError('Smash aspect exact ARC size/catalog mismatch')
    ordered=sorted(ARCHIVE_SPANS.items(),key=lambda row:row[1][0])
    previous_end=0
    with data_arc.open('rb') as stream:
        for key,(offset,stored,decoded,digest) in ordered:
            if offset<previous_end or stored<1 or decoded<1 or offset+stored>ARC_BYTES:
                raise ValueError('Smash aspect overlapping/invalid exact ARC spans')
            previous_end=offset+stored
            stream.seek(offset);source=stream.read(stored)
            if len(source)!=stored or hashlib.sha256(source).hexdigest()!=digest:
                raise ValueError(f'Smash aspect original compressed ARC identity mismatch:{key}')
    source_stat=data_arc.stat()
    codec=Zstd();resources=[]
    with tempfile.TemporaryDirectory(prefix='.smash-aspect-',dir=output.parent) as temp:
        stage=Path(temp);spans=stage/'spans';spans.mkdir()
        with data_arc.open('rb') as stream:
            for key,(offset,stored,decoded,digest) in ordered:
                stream.seek(offset);source=stream.read(stored)
                if hashlib.sha256(source).hexdigest()!=digest:
                    raise ValueError(f'Smash aspect ARC changed during preparation:{key}')
                raw=source if source[:4]==b'SARC' else codec.decompress(source,decoded)
                if len(raw)!=decoded:
                    raise ValueError(f'Smash aspect raw SARC size mismatch:{key}')
                transformed,receipt=transform_sarc(raw,key)
                if len(transformed)!=decoded:
                    raise ValueError(f'Smash aspect transformed SARC size changed:{key}')
                if source[:4]==b'SARC':
                    replacement=transformed
                    compression={'one_frame':False,'uncompressed':True,'span_bytes':stored}
                else:
                    replacement,compression=fixed_span_frame(codec,transformed,source)
                if len(replacement)!=stored:
                    raise ValueError(f'Smash aspect replacement changed index span:{key}')
                (spans/key).write_bytes(replacement)
                resources.append({'hash40':key,'offset':offset,'stored_bytes':stored,
                    'decoded_bytes':decoded,'original_stored_sha256':digest,
                    'prepared_stored_sha256':hashlib.sha256(replacement).hexdigest(),
                    'prepared_decoded_sha256':hashlib.sha256(transformed).hexdigest(),
                    'compression':compression,'ui':receipt})
        # Every asset transformation and compression succeeded before a cache
        # or large archive copy is materialized. The stage is private and is
        # removed on any failure; existing output/input paths stay unchanged.
        cache=stage/'rewritten'
        shutil.copytree(rewritten,cache,symlinks=True,copy_function=_clone_file)
        binary=cache/'main.patched.bin'
        if binary.is_symlink():
            binary.unlink();_clone_file(rewritten/'main.patched.bin',binary)
        binary.chmod(stat.S_IMODE(binary.stat().st_mode)|stat.S_IWUSR)
        with binary.open('r+b') as stream:
            for address,_,replacement,_ in CUTS:
                stream.seek(address);stream.write(struct.pack('<I',replacement))
            stream.flush();os.fsync(stream.fileno())
        cut_path=cache/'main.cuts.tsv'
        prior=cut_path.read_text()
        if cut_path.is_symlink():cut_path.unlink()
        cut_path.write_text(prior+''.join(f'{a:#x}\t{old}\t{new}\tSmash13.0.5 native4:3: {why}\n'
                                          for a,old,new,why in cuts))
        check_rewritten(cache)
        romfs=stage/'RomFS';romfs.mkdir();archive=romfs/'data.arc'
        _clone_file(data_arc,archive)
        archive.chmod(stat.S_IMODE(archive.stat().st_mode)|stat.S_IWUSR)
        with archive.open('r+b') as stream:
            for resource in resources:
                replacement=(spans/resource['hash40']).read_bytes()
                stream.seek(resource['offset']);stream.write(replacement)
            stream.flush();os.fsync(stream.fileno())
        # A second read of the emitted archive catches offset/write mistakes,
        # validates every full-span digest and round-trips the final frame.
        with archive.open('rb') as stream:
            for resource in resources:
                stream.seek(resource['offset']);data=stream.read(resource['stored_bytes'])
                if hashlib.sha256(data).hexdigest()!=resource['prepared_stored_sha256']:
                    raise ValueError('Smash aspect final stored resource validation failed')
                decoded=data if data[:4]==b'SARC' else codec.decompress(data,resource['decoded_bytes'])
                if hashlib.sha256(decoded).hexdigest()!=resource['prepared_decoded_sha256']:
                    raise ValueError('Smash aspect final decoded resource validation failed')
        current=data_arc.stat()
        if (source_stat.st_dev,source_stat.st_ino,source_stat.st_size,source_stat.st_mtime_ns)!=(
                current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns):
            raise ValueError('Smash aspect original ARC identity changed during staging')
        if hashlib.sha256((rewritten/'main.patched.bin').read_bytes()).hexdigest()!=binary_hash:
            raise ValueError('Smash aspect input rewrite changed during preparation')
        if any(hashlib.sha256(path.read_bytes()).hexdigest()!=source_hashes[name]
               for name,(path,_) in sources.items()):
            raise ValueError('Smash aspect preparation source changed during transformation')
        receipt={'schema':1,'title_id':'01006A800016E000','build_id':MAIN_BUILD,
            'preparation_sources_sha256':source_hashes,
            'original_main_sha256':MAIN_SHA256,'source_rewritten_main_sha256':binary_hash,
            'prepared_main_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'display_aspect':'4:3','logical_ui_canvas':[1920,1440],
            'physical_raster_changed':False,'simulation_changed':False,
            'source_arc_bytes':ARC_BYTES,'prepared_arc_bytes':archive.stat().st_size,
            'arc_index_and_all_span_offsets_lengths_unchanged':True,
            'original_inputs_untouched':True,'complete_arena_group_preserved':True,
            'required_observers':[list(x) for x in OBSERVERS],
            'cuts':[{'offset':a,'original':old,'prepared':new,'reason':why} for a,old,new,why in cuts],
            'resources':resources,
            'physical_device_verified':False}
        (stage/'aspect-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        shutil.rmtree(spans)
        if output.exists() or output.is_symlink():
            raise ValueError('Smash aspect output appeared during staging')
        os.rename(stage,output)
    return PreparedAspect(output/'rewritten',output/'RomFS',output/'aspect-receipt.json')

def check_assets(data_arc,receipt: Path,*,deep: bool=False) -> dict:
    """Verify an actual staged/packaged Path or caller-owned seekable stream.

    Fast mode hashes every prepared compressed span. Deep mode additionally
    undoes each declared float change, re-admits its original SARC identity and
    recomputes the canonical transformation, proving the complete field receipt.
    A passed stream remains open and its original position is restored.
    """
    import contextlib
    record=json.loads(Path(receipt).read_text())
    source_hashes=record.get('preparation_sources_sha256',{})
    for name in ('smash_aspect.py','smash_aspect_ui.py'):
        path=Path(__file__).with_name(name)
        if source_hashes.get(name)!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('Smash aspect asset receipt source hash mismatch')
    if (record.get('schema'),record.get('title_id'),record.get('build_id'),record.get('display_aspect'))!=(
            1,'01006A800016E000',MAIN_BUILD,'4:3'):
        raise ValueError('Smash aspect asset receipt/archive identity mismatch')
    resources=record.get('resources',[])
    keys=[x.get('hash40') for x in resources]
    if len(keys)!=len(set(keys)) or set(keys)!=set(ARCHIVE_SPANS):
        raise ValueError('Smash aspect incomplete or duplicate prepared asset catalog')
    codec=Zstd() if deep else None
    if deep:
        from smash_aspect_ui import _members,transform_sarc
    changed_fields=0
    owned=not(hasattr(data_arc,'read') and hasattr(data_arc,'seek'))
    @contextlib.contextmanager
    def reader():
        if owned:
            path=Path(data_arc)
            with path.open('rb') as stream:
                yield stream,path.stat().st_size
        else:
            try:
                position=data_arc.tell()
                size=data_arc.seek(0,os.SEEK_END)
                data_arc.seek(position)
            except Exception:
                raise ValueError('Smash aspect assets require a seekable binary stream') from None
            try:
                yield data_arc,size
            finally:
                data_arc.seek(position)
    with reader() as (stream,size):
        if size!=ARC_BYTES:
            raise ValueError('Smash aspect asset receipt/archive identity mismatch')
        for resource in resources:
            key=resource['hash40'];offset,stored,decoded,digest=ARCHIVE_SPANS[key]
            if (resource.get('offset'),resource.get('stored_bytes'),resource.get('decoded_bytes'),resource.get('original_stored_sha256'))!=(offset,stored,decoded,digest):
                raise ValueError(f'Smash aspect changed ARC index facts:{key}')
            stream.seek(offset);data=stream.read(stored)
            if len(data)!=stored or hashlib.sha256(data).hexdigest()!=resource.get('prepared_stored_sha256'):
                raise ValueError(f'Smash aspect staged prepared span mismatch:{key}')
            if not deep:
                continue
            raw=data if data[:4]==b'SARC' else codec.decompress(data,decoded)
            if len(raw)!=decoded or hashlib.sha256(raw).hexdigest()!=resource.get('prepared_decoded_sha256'):
                raise ValueError(f'Smash aspect staged decoded identity mismatch:{key}')
            members={x.name:x for x in _members(raw)};original=bytearray(raw);touched=set()
            for change in resource.get('ui',{}).get('changes',[]):
                member=members.get(change.get('member'));relative=change.get('offset')
                if member is None or not isinstance(relative,int) or not 0<=relative<=member.size-4:
                    raise ValueError(f'Smash aspect invalid field receipt:{key}')
                absolute=member.offset+relative
                before,after=bytes.fromhex(change['before']),bytes.fromhex(change['after'])
                if len(before)!=4 or len(after)!=4 or absolute in touched or raw[absolute:absolute+4]!=after:
                    raise ValueError(f'Smash aspect duplicate/mismatched field receipt:{key}')
                touched.add(absolute);original[absolute:absolute+4]=before
            canonical,canonical_receipt=transform_sarc(bytes(original),key)
            if canonical!=raw or canonical_receipt!=resource['ui']:
                raise ValueError(f'Smash aspect canonical transformation receipt mismatch:{key}')
            changed_fields+=len(touched)
    return {'archives':len(resources),'archive_bytes':ARC_BYTES,'deep':deep,
            'canonical_changed_fields':changed_fields if deep else None,'status':'PASS'}
