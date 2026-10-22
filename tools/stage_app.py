#!/usr/bin/env python3
"""Stage a private unsigned app with APFS clones instead of a large IPA round trip."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

from odyssey_assets import outside_repo
from sign_install import REPO, check_app, clone_app


def stage_app(app: Path, output: Path, shaders: Path, romfs: Path, aoc: Path | None = None) -> None:
    """Combine regular private resource trees without modifying the build products."""
    for path in (app, output, shaders, romfs, *([aoc] if aoc else [])):
        outside_repo(path, REPO)
    check_app(app)
    inputs = (app, shaders, romfs, *([aoc] if aoc else []))
    if output.exists() or any(output.is_relative_to(source) for source in inputs) or output.suffix != '.app':
        raise ValueError('Choose a new .app output outside the input app')
    for source in (shaders, romfs, *([aoc] if aoc else [])):
        if source.is_symlink() or not source.is_dir():
            raise ValueError('Resources must be regular directories: ' + str(source))
        # Reject links and special files before creating a partial app. Reuse the
        # signer validation policy for the completed tree below as a second check.
        for item in source.rglob('*'):
            if item.is_symlink() or not (item.is_file() or item.is_dir()):
                raise ValueError('Unsupported resource entry: ' + str(item))
    output.parent.mkdir(parents=True, exist_ok=True)
    clone_app(app, output)
    for name in ('_CodeSignature', 'embedded.mobileprovision', 'msl', 'romfs', 'aoc'):
        stale = output / name
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    (output / 'msl').mkdir()
    clone_app(shaders, output / 'msl' / shaders.name)
    clone_app(romfs, output / 'romfs')
    if aoc:
        clone_app(aoc, output / 'aoc')
    check_app(output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shaders', type=Path, required=True, help='one shader chain directory, such as b-0123456789ab')
    parser.add_argument('--romfs', type=Path, required=True)
    parser.add_argument('--aoc', type=Path)
    args = parser.parse_args(argv)
    stage_app(*(outside_repo(path, REPO) for path in (args.app, args.output, args.shaders, args.romfs)),
              outside_repo(args.aoc, REPO) if args.aoc else None)
    print('Unsigned app: ' + str(args.output.resolve()))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print('Staging stopped: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
