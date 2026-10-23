#!/usr/bin/env python3
"""Run game-free source checks; never access a device or real cloud account."""
from pathlib import Path
import os
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True, **kwargs)


def main():
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Native source checks require an Apple Silicon Mac; Python checks passed.')
    run(['make', '-C', 'dm/host', 'GAME=0100000000010000', 'game_profile'])
    with tempfile.TemporaryDirectory(prefix='odyssey-source-checks-') as temp:
        build = Path(temp)
        common = ['xcrun', 'clang', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-I', ROOT / 'dm/host',
                  '-I', ROOT / 'dm/host/gen/0100000000010000', '-I', ROOT / 'dm/games/0100000000010000']
        for name, sources in [
            ('feedback', ['dm/host/tests/t_feedback.c', 'dm/host/hle_feedback.c']),
            ('feedback-players', ['dm/host/tests/t_feedback_players.c', 'dm/host/hle_feedback.c']),
            ('smash-feedback', ['dm/host/tests/t_smash_feedback.c', 'dm/host/hle_feedback.c']),
            ('smash-aspect', ['dm/host/tests/t_smash_aspect.c']),
            ('smash-ui-scope', ['dm/host/tests/t_smash_ui_scope.c', 'dm/host/hle_smash_ui.c']),
            ('smash-display', ['dm/host/tests/t_smash_display.c', 'dm/host/hle_smash_display.c']),
            ('smash-camera-owner', ['dm/host/tests/t_smash_camera_owner.c']),
            ('smash-shipping-display', ['dm/host/tests/t_smash_shipping_display.c']),
            ('guest-read', ['dm/host/tests/t_guest_read.c']),
            ('nvn-command-pools', ['dm/host/tests/t_nvn_cb_pool.c']),
            ('nvn-program-cache', ['dm/host/tests/t_nvn_program_cache.c']),
            ('nvn-present-slots', ['dm/host/tests/t_nvn_present_slots.c']),
            ('movie-packets', ['dm/host/tests/t_movie_packets.c']),
            ('movie-audio-output', ['dm/host/tests/t_movie_audio_output.c']),
            ('policy', ['dm/host/tests/t_feedback_policy.c']),
            ('takeoffs', ['dm/host/tests/t_odyssey_feedback.c']),
            ('aspect', ['dm/host/tests/t_present_aspect.c']),
            ('touch-controls', ['dm/host/tests/t_touch_controls.c']),
            ('display-geometry', ['dm/host/tests/t_display_geometry.c']),
        ]:
            binary = build / name
            run(common + sources + ['-o', binary])
            run([binary])
        for name, flags in [('hid-players', []), ('hid-legacy', ['-DDM_TEST_SINGLE_PLAYER'])]:
            binary = build / name
            run(common + ['-Wno-unused-function', *flags, 'dm/host/tests/t_hid_players.c',
                          'dm/host/hle_feedback.c', '-o', binary])
            run([binary])
        binary = build / 'feedback-players-threads'
        run(common + ['-fsanitize=thread', 'dm/host/tests/t_feedback_players_threads.c',
                      'dm/host/hle_feedback.c', '-o', binary])
        run([binary])
        for sanitizer in ['address,undefined','thread']:
            binary=build/('smash-ui-scope-'+sanitizer.replace(',','-'))
            run(common+['-fsanitize='+sanitizer,'dm/host/tests/t_smash_ui_scope.c','dm/host/hle_smash_ui.c','-o',binary])
            run([binary])
        binary=build/'smash-production-gate'
        run(common+['dm/host/tests/t_smash_native_matrix.c','dm/host/tests/t_smash_gate_state.S','dm/host/entry.S','dm/host/hle_smash_ui.c','-o',binary])
        run([binary,'--gate-only'])
        binary = build / 'nvn-program-cache-address'
        run(common + ['-fsanitize=address,undefined', 'dm/host/tests/t_nvn_program_cache.c', '-o', binary])
        run([binary])
        binary = build / 'movie-packets-address'
        run(common + ['-fsanitize=address,undefined', 'dm/host/tests/t_movie_packets.c', '-o', binary])
        run([binary])
        binary = build / 'smash-aspect-address'
        audio_binary = build / 'movie-audio-output-address'
        run(common + ['-fsanitize=address,undefined', 'dm/host/tests/t_movie_audio_output.c', '-o', audio_binary])
        run([audio_binary])
        run(common + ['-fsanitize=address,undefined', 'dm/host/tests/t_smash_aspect.c', '-o', binary])
        run([binary])
        binary = build / 'nvn-command-pools-threads'
        run(common + ['-fsanitize=thread', 'dm/host/tests/t_nvn_cb_pool.c', '-o', binary])
        run([binary])
        binary = build / 'nvn-present-slots-threads'
        run(common + ['-fsanitize=thread', 'dm/host/tests/t_nvn_present_slots.c', '-o', binary])
        run([binary])
        for name, source, flags in [
            ('smash-feedback-threads', 'dm/host/tests/t_smash_feedback.c', ['-DDM_SMASH_STRESS']),
            ('hid-players-threads', 'dm/host/tests/t_hid_players.c', ['-DDM_HID_STRESS', '-Wno-unused-function']),
        ]:
            binary = build / name
            run(common + ['-fsanitize=thread', *flags, source, 'dm/host/hle_feedback.c', '-o', binary])
            run([binary])
        for name, flags in [('save-commit', ['-DDM_TEST_SAVE_COMMIT']), ('save-commit-mac', [])]:
            binary = build / name
            run(['xcrun', 'clang', '-O1', '-Wno-unused-function', '-Wno-incompatible-pointer-types-discards-qualifiers',
                 '-I', ROOT / 'dm/host', '-I', ROOT / 'dm/host/gen/0100000000010000',
                 '-I', ROOT / 'dm/games/0100000000010000', *flags, 'dm/host/tests/t_fs_save_committed.c',
                 'dm/host/tests/t_fs_save_committed_stub.c', 'dm/host/tests/t_fs_stub.c', 'dm/host/hle_bigstack.c', '-o', binary])
            run([binary])
        archive = build / 'archive'
        run(['xcrun', 'clang', '-fobjc-arc', '-fblocks', '-O1', '-g', '-I', ROOT / 'dm/ios/tests/cloud_coordinator',
             '-framework', 'Foundation', 'dm/ios/tests/t_save_archive.m', '-o', archive])
        env = dict(os.environ)
        env.pop('DM_TEST_SAVE_DIR', None)  # CI checks use only synthetic fixtures.
        run([archive], env=env)
    run(['sh', 'dm/ios/tests/cloud_coordinator/run.sh'])
    run([sys.executable, 'tools/audit_repo.py'])
    run(['git', 'diff', '--check'])
    print('PASS: game-free checks complete')


if __name__ == '__main__':
    main()
