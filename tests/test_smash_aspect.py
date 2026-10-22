"""Game-free exact-build, atomic admission and fixed-span Zstd coverage."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dm/tools'))
import smash_aspect as aspect

class AspectTests(unittest.TestCase):
    def fixture(self):
        size=max(max(a for a,*_ in aspect.CUTS),max(a for a,_ in aspect.CONSTITUENTS))+4
        image=bytearray(size)
        for address,old,*_ in aspect.CUTS:
            struct.pack_into('<I',image,address,old)
        for address,word in aspect.CONSTITUENTS:
            struct.pack_into('<I',image,address,word)
        return b'NSO0'+bytes(0x3c)+bytes.fromhex(aspect.MAIN_BUILD),image
    def digest(self):
        return mock.patch.object(aspect.hashlib,'sha256',return_value=SimpleNamespace(hexdigest=lambda:aspect.MAIN_SHA256))
    def observers(self,path):
        facts=aspect.OBSERVERS+aspect.HAPTIC_OBSERVERS
        (path/'main.obs.tsv').write_text(''.join(f'{off:#x}\t{number}\t{word:08x}\texact synthetic\n' for off,number,word in facts))
        (path/'main.gates.tsv').write_text(''.join(f'{0x900000+number*64:#x}\tobs\t{number}\t{off:#x}\n' for off,number,_ in facts))
    def test_atomic_complete_default_group_and_input_bounds_preserved(self):
        nso,image=self.fixture()
        preserved=image[0x3743e60:0x3743e68]
        with self.digest():
            cuts=aspect.apply_image(nso,image)
        self.assertEqual(len(cuts),34)
        for off,_,new,_ in aspect.CUTS:
            self.assertEqual(struct.unpack_from('<I',image,off)[0],new)
        self.assertEqual(image[0x3743e60:0x3743e68],preserved)
        self.assertNotIn(0x3743e60,{x[0] for x in aspect.CUTS})
        self.assertEqual(struct.unpack_from('<f',image,0x4472c5c)[0],struct.unpack('<f',bytes.fromhex('abaaaa3f'))[0])
    def test_wrong_identity_and_each_late_gate_fail_before_first_write(self):
        nso,image=self.fixture()
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            aspect.apply_image(nso,image)
        digest=hashlib.sha256
        for off in [x[0] for x in aspect.CUTS]+[x[0] for x in aspect.CONSTITUENTS]:
            image[off]^=1;before=digest(image).digest()
            with self.digest(),self.assertRaises(ValueError):
                aspect.apply_image(nso,image)
            self.assertEqual(digest(image).digest(),before)
            image[off]^=1
        with self.assertRaisesRegex(ValueError,'build ID'):
            aspect.apply_image(bytes(80),image)
    def test_camera_encoding_changes_only_imm16_and_keeps_packed_fields(self):
        camera=aspect.CUTS[:30]
        self.assertEqual(len(camera),30)
        for off,old,new,_ in camera:
            self.assertEqual(old&~(0xffff<<5),new&~(0xffff<<5),hex(off))
        packed=[x for x in camera if x[0] in (0x14e6014,0x14e6018)]
        self.assertEqual([(x[2]>>5)&0xffff for x in packed],[0xaaab,0x3faa])
        self.assertEqual([((x[2]>>21)&3)*16 for x in packed],[32,48])
    def test_observer_sites_require_unique_gate_registration_and_haptics(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);self.observers(path);aspect.verify_observers(path)
            for name in ['main.obs.tsv','main.gates.tsv']:
                original=(path/name).read_text()
                (path/name).write_text('\n'.join(original.splitlines()[:-1])+'\n')
                with self.assertRaisesRegex(ValueError,'observer'):
                    aspect.verify_observers(path)
                (path/name).write_text(original)
            (path/'main.obs.tsv').write_text((path/'main.obs.tsv').read_text().splitlines()[0]+'\n'+(path/'main.obs.tsv').read_text())
            with self.assertRaisesRegex(ValueError,'duplicate'):
                aspect.verify_observers(path)
    def test_fixed_span_single_frame_empty_blocks_and_checksum(self):
        codec=aspect.Zstd();raw=b'Original game-free synthetic UI fixture\0'*63
        for checksum in [False,True]:
            frame=codec.compress(raw,3,10,checksum)
            for extra in range(40):
                if extra in (1,2,5):
                    with self.assertRaises(ValueError):aspect.pad_frame(frame,len(frame)+extra)
                else:
                    padded=aspect.pad_frame(frame,len(frame)+extra)
                    self.assertEqual(len(padded),len(frame)+extra)
                    self.assertEqual(codec.decompress(padded,len(raw)),raw)
                    self.assertEqual(aspect.frame_window(padded),aspect.frame_window(frame))
            for invalid in [b'not a frame',frame[:-1],frame+b'garbage',frame+frame]:
                with self.assertRaises(ValueError):aspect.pad_frame(invalid,len(invalid)+8)
    def test_fixed_span_compression_preserves_decoder_window_and_exact_size(self):
        codec=aspect.Zstd();raw=b'fixture'*3000
        original=codec.compress(raw,1,10,True)
        original=aspect.pad_frame(original,len(original)+200)
        modified=raw[:-1]+b'!'
        frame,receipt=aspect.fixed_span_frame(codec,modified,original)
        self.assertEqual(len(frame),len(original));self.assertEqual(codec.decompress(frame,len(raw)),modified)
        self.assertLessEqual(aspect.frame_window(frame),aspect.frame_window(original))
        self.assertTrue(receipt['one_frame'])
    def test_span_catalog_is_bounded_disjoint_and_payload_free_metadata(self):
        rows=sorted(aspect.ARCHIVE_SPANS.values())
        self.assertEqual(len(rows),362);end=0
        for offset,stored,decoded,digest in rows:
            self.assertGreaterEqual(offset,end);end=offset+stored
            self.assertLessEqual(end,aspect.ARC_BYTES);self.assertLessEqual(decoded,256*1024*1024)
            self.assertEqual(len(digest),64);int(digest,16)
    def test_packaged_span_verification_catches_same_size_wrong_assets(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);arc=root/'data.arc';receipt=root/'receipt.json'
            payload=b'opaque-headerDATAopaque-tail';arc.write_bytes(payload)
            catalog={'0000000001':(13,4,4,'a'*64)}
            record={'schema':1,'title_id':'01006A800016E000','build_id':aspect.MAIN_BUILD,
                'display_aspect':'4:3','preparation_sources_sha256':{name:hashlib.sha256((ROOT/'dm/tools'/name).read_bytes()).hexdigest() for name in ['smash_aspect.py','smash_aspect_ui.py']},'resources':[{'hash40':'0000000001','offset':13,
                'stored_bytes':4,'decoded_bytes':4,'original_stored_sha256':'a'*64,
                'prepared_stored_sha256':hashlib.sha256(b'DATA').hexdigest()}]}
            receipt.write_text(json.dumps(record))
            with mock.patch.object(aspect,'ARC_BYTES',len(payload)),mock.patch.object(aspect,'ARCHIVE_SPANS',catalog):
                self.assertEqual(aspect.check_assets(arc,receipt)['archives'],1)
                import io
                stream=io.BytesIO(payload);stream.seek(5)
                self.assertEqual(aspect.check_assets(stream,receipt)['archives'],1)
                self.assertEqual(stream.tell(),5);self.assertFalse(stream.closed)
                arc.write_bytes(payload.replace(b'DATA',b'OLD!'))
                with self.assertRaisesRegex(ValueError,'prepared span'):
                    aspect.check_assets(arc,receipt)
                arc.write_bytes(payload);record['resources'].append(record['resources'][0]);receipt.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'duplicate'):
                    aspect.check_assets(arc,receipt)

    def test_output_guards_do_not_touch_existing_or_source_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);source=base/'cache';source.mkdir();arc=base/'data.arc';arc.write_bytes(b'synthetic')
            for output in [source,source/'child',arc]:
                with self.assertRaises(ValueError):aspect._private_output(output,source,arc)
            aspect._private_output(base/'new',source,arc)

if __name__=='__main__':unittest.main()
