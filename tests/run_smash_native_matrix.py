"""Explicit private CPU fixture; game-free CI never reads supplied game inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'dm/tools'))
import smash_aspect
import smash_live_aspect


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(manifest, private_rewritten=None):
    """Admit current module inventories and dispose native compiler products."""
    manifest = manifest.resolve(); work = manifest.parent.parent
    config = json.loads(manifest.read_text())
    assert config['title_id'] == '01006A800016E000'
    record = config['inventories']['rewritten']
    inventory_path = (work/record['path']).resolve()
    assert inventory_path.is_relative_to(work) and digest(inventory_path) == record['sha256']
    inventory = json.loads(inventory_path.read_text())
    rewritten = (work/config['paths']['rewritten']).resolve()
    assert rewritten.is_relative_to(work)
    for name in ('main.patched.bin', 'main.fixups.tsv', 'sdk.patched.bin'):
        assert digest(rewritten/name) == inventory[name], name
    original = (work/config['paths']['survey']/'ExeFS/main').read_bytes()
    smash_aspect._identity(original)
    smash_aspect.check_rewritten(rewritten)
    if private_rewritten:
        rewritten=private_rewritten.resolve()
        assert rewritten.is_relative_to(work) and rewritten!=work/config['paths']['rewritten']
        smash_live_aspect.verify_live_rewritten(rewritten)
    header = {}
    for line in (rewritten/'main.fixups.tsv').read_text().splitlines():
        if line.startswith('# '):
            key,value = line[2:].split('\t')
            if key in ('PATCH_OFF','IMAGE_SIZE','FILE_IMAGE_LEN'):
                header[key] = int(value,16)
    with tempfile.TemporaryDirectory(prefix='smash-native-matrix-') as temporary:
        binary = Path(temporary)/'fixture'
        profile=work/config['paths']['profile']
        env=dict(os.environ,DM_GAMES_DIR=str(profile.parent),DM_GAMES_FIRST='1',PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable,str(ROOT/'dm/games/game.py'),'header',config['title_id'],str(Path(temporary)/'game_profile.h')],env=env,check=True)
        subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        '-I'+str(ROOT/'dm/host'),'-I'+temporary,
                        str(ROOT/'dm/host/tests/t_smash_native_matrix.c'),str(ROOT/'dm/host/tests/t_smash_gate_state.S'),
                        str(ROOT/'dm/host/entry.S'),str(ROOT/'dm/host/hle_smash_ui.c'),
                        '-o',str(binary)],check=True)
        command=[str(binary),str(rewritten/'main.patched.bin'),str(rewritten/'sdk.patched.bin'),
                 str(header['IMAGE_SIZE']),str(header['FILE_IMAGE_LEN']),str(-header['PATCH_OFF'])]
        if private_rewritten:command.append(str(rewritten/'main.gates.tsv'))
        result = subprocess.run(command,
                                capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(f'Native CPU matrix fixture failed({result.returncode}): {result.stderr[-5000:]}')
        receipt=json.loads(result.stdout)
        receipt['inputs']={name:digest(rewritten/name) for name in ('main.patched.bin','main.gates.tsv','sdk.patched.bin')}
        receipt['source']={name:digest(ROOT/name) for name in (
            'dm/host/entry.S','dm/host/hle_smash_ui.c','dm/host/smash_ui_scope.h','dm/host/smash_ui_rules.h',
            'dm/host/smash_ui_matrix.h','dm/host/smash_ui_safe.h','dm/host/smash_camera_policy.h','dm/host/smash_camera_owner.h',
            'dm/host/tests/t_smash_native_matrix.c','dm/host/tests/t_smash_gate_state.S')}
        return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-manifest',type=Path,required=True)
    parser.add_argument('--private-rewritten',type=Path)
    args=parser.parse_args()
    print(json.dumps(run(args.input_manifest,args.private_rewritten),indent=2))
