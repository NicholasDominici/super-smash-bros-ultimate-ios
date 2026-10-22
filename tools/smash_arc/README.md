# Targeted Smash ARC inspection

This developer tool reads a player's own, already merged `data.arc`. It lists
and extracts selected extensions without expanding the entire archive. It does
not download game data, decrypt an NSP/XCI, run NROs, or translate shaders.

The ARC index stores hashes rather than complete path strings. File selection
uses each entry's extension hash. Optional `--labels /private/hashes.txt` adds
human-readable names to the manifest; labels never determine output paths.
Extracted files use `<40-bit-hash>.<extension>`. The generated manifest records
the region, archive offsets, lengths and each extracted file's SHA-256.

Build artifacts and extracted game material must be outside the source checkout.
Extraction requires a new output directory and refuses to overwrite files.
The defaults allow up to 256 MiB per selected file and 4 GiB across the selection;
override either limit explicitly when the input survey establishes a need.
Selection errors, truncated ranges and incorrect decompressed lengths fail the
command. A failed extraction may leave an incomplete private output directory;
its completed manifest is written only after all files succeed.

## Build and use

Requires a recent Rust toolchain and a C compiler for the zstd dependency.
From the repository root:

```sh
export CARGO_TARGET_DIR="$(cd .. && pwd)/toolchain/smash-arc-build"
cargo build --locked --release --manifest-path tools/smash_arc/Cargo.toml
cargo test --locked --manifest-path tools/smash_arc/Cargo.toml

"$CARGO_TARGET_DIR/release/smash-arc-tool" list \
  --arc /private/game/RomFS/data.arc --region us_en \
  --extensions nro,nushdb,nufxlb > /private/game/arc-selection.json

"$CARGO_TARGET_DIR/release/smash-arc-tool" extract \
  --arc /private/game/RomFS/data.arc --region us_en \
  --extensions nro --out /private/game/modules

"$CARGO_TARGET_DIR/release/smash-arc-tool" extract \
  --arc /private/game/RomFS/data.arc --region us_en \
  --extensions nushdb,nufxlb --out /private/game/shader-sources

"$CARGO_TARGET_DIR/release/smash-arc-tool" shader-archives \
  --arc /private/game/RomFS/data.arc --region us_en \
  --out /private/game/ui-shader-sources

"$CARGO_TARGET_DIR/release/smash-arc-tool" effect-shaders \
  --arc /private/game/RomFS/data.arc --region us_en \
  --out /private/game/effect-shader-sources
```

Use `--help` for all flags and accepted region names. `list` emits JSON to
standard output; keep redirected output outside the checkout. `extract` writes
a manifest into its new output directory. Neither command modifies `data.arc`.

`shader-archives` processes `.arc` resources as bounded SARC archives one at a
time. It validates each directory, name and member range, then retains only
members containing BNSH shaders. Identical member payloads share a SHA-256-named
`.bnsh` file; `manifest.json` preserves every archive hash, original member path,
size and digest. Textures and other UI assets are discarded from memory after
each archive. No whole SARC archive is written. Unknown nested archive formats
fail explicitly. The input SARC limit remains `--max-file-bytes`.

`effect-shaders` decodes `.eff` files one at a time. It validates the EFFN
wrapper, bounded names, EFT2/VFXB header and advancing section chain, then keeps
only the original GRSN graphics and GRSC compute shader carriers. External-model
wrappers with no embedded EFT2 payload are recorded without invented shaders.
Original BNSH/FSHA containers are SHA-256 named and deduplicated; the completed
manifest retains their effect hash and section identity. Textures, models and
emitter data are discarded after each resource.

All three shader collections are required. Pass `--smash-shaders /private/game/shader-sources`,
`--smash-ui-shaders /private/game/ui-shader-sources`, and
`--smash-effect-shaders /private/game/effect-shader-sources` to
`dm/gfx/tools/shader_split.py`. It verifies the completed extraction manifests and every
retained payload before scanning, preserves exact BNSH program stage pairs,
and uses the original SARC member identity in the shader map.

For shaders observed during a separately version-gated local Mac run,
`shader_split.py --nvn-shader-capture /private/game/capture` accepts the host's
actual `.ctl`/`.code` pairs. It bounds every input, validates stage/length/c1
metadata, and requires each filename to equal the hash of its original control
section plus complete code area. Static duplicates keep their static identity;
new captured shaders are labelled explicitly. Captures are private game bytes,
must have producer/build/run provenance in the human build workflow, and never
belong in this source repository. They do not establish coverage of unvisited
gameplay paths.

## Source and licensing

The wrapper is original project code under the repository's MIT license.
`smash-arc` is a Git dependency pinned to
[`944ac568689fe9c9ddeea93a776db42dc7d41790`](https://github.com/jam1garner/smash-arc/tree/944ac568689fe9c9ddeea93a776db42dc7d41790).
Its [package metadata](https://github.com/jam1garner/smash-arc/blob/944ac568689fe9c9ddeea93a776db42dc7d41790/Cargo.toml)
declares MIT. Its upstream tree does not provide a separate LICENSE file; no
upstream source is vendored here. Cargo retains package notices in its external
dependency cache. The dependency's `ArcFile::from_reader` and `ArcLookup` APIs
parse the index and perform bounded per-file reads/zstd decoding. `Cargo.lock`
pins transitive dependencies. No game archive, shader, executable or hash-label
database is included.


The EFFN/EFT2 layouts follow the MIT-licensed
[EffectLibrary at d5491138d645221ec92189eeff3ded8c43fd0a1a](https://github.com/KillzXGaming/EffectLibrary/tree/d5491138d645221ec92189eeff3ded8c43fd0a1a),
Copyright 2024 KillzXGaming. The primary layout files are
[EFFN/NamcoEffectFile.cs](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFFN/NamcoEffectFile.cs)
and [EFT2/Structs.cs](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFT2/Structs.cs),
[PtclFile.cs](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFT2/PtclFile.cs),
and [Shaders.cs](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFT2/Shaders.cs).
Its [LICENSE](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/LICENSE)
is MIT. This extractor is original code; no upstream binary libraries, game
fixtures, or upstream implementation are bundled.
