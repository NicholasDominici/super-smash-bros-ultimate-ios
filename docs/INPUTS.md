# Supported Smash inputs

The supported title is **Super Smash Bros. Ultimate**, base ID
`01006A800016E000`, update ID `01006A800016E800`, update **13.0.5 / v2031616**.
Supply your own base NSP or XCI, update NSP and console `prod.keys`. This tool
never downloads game files. It compiles the bundled LibHac extractor in an
external temporary directory and uses its normal NCA integrity checks. There
is no damaged-file override in the player command.

```sh
python tools/smash.py --base /private/Smash/Base.xci \
  --update /private/Smash/Update-13.0.5.nsp --keys /private/Keys/prod.keys \
  --bundle-id com.yourname.smash --work /private/Smash-build-01 \
  --app-only --allow-known-geometry-gap
```

Archives such as ZIP/7z/RAR are not input packages; unpack your own archives
before building. The explicit paths avoid guessing which package is the base
or update. Renaming files cannot bypass the original-module checks.

| Module | NSO build ID (first 16 bytes) | Original file SHA-256 |
| --- | --- | --- |
| main | `21450c647b8c5940ed5b68218ea128fd` | `eb79e639e47d9a0c79bcfe2ec50fc807afa9601800226627b58bd6a1a83dc52d` |
| subsdk0 | `60c6edbbfcebd4176cc301d5d9cb5a6f` | `2ac9587ec0d20a2bda42d7a8f04574f18af3e047d9864a599070d57666b1811e` |
| sdk | `5fd4f531c1195e9e5510c9e73f22cd39` | `8d20111b4f1dd9a301901ed9c2a0f31ce5678076f7b233bfb8bdbafe52f955f1` |

These are identity metadata, not copies of executable game code. Other builds
are rejected. Do not weaken the gate to accept another version.

The offline rewrite also adapts this exact main executable's sparse virtual
arena from 62 GiB to 30 GiB. It checks the original file hash, build ID and the
complete group of size, metadata and end-bound instructions before changing a
private decompressed copy. The 64 KiB allocation units and 14 MiB metadata
allowance stay intact. The source profile uses a 36 GiB host window containing
a 32 GiB alias region; physical application memory and heap capacity are
unchanged. This is automatic: supply the original files without prepatching
them. Reused rewritten modules from the old layout are rejected and must be
regenerated. Device probes and gameplay qualification are separate; see
[VALIDATION.md](VALIDATION.md).

## Already merged files

The same complete, integrity-checked merged extraction can be supplied as:

```text
/private/Smash-13.0.5/
  ExeFS/main
  ExeFS/subsdk0
  ExeFS/sdk
  RomFS/data.arc
  RomFS/.nrr/*.nrr
  control.nacp       optional app metadata
  icon.jpg           optional private app icon
```

```sh
python tools/smash.py --extracted-dir /private/Smash-13.0.5 \
  --bundle-id com.yourname.smash --work /private/Smash-build-02 \
  --app-only --allow-known-geometry-gap
```

The helper checks all three original modules, the ARC header and 14 NRR
registrations. It extracts and hashes the 98 native modules, 41 Nushdb/4 Nufx
databases and shader members from all 362 nested ARC resources. The latter
retains 247 member references as 124 deduplicated BNSH payloads, about 9.9 MB,
without retaining all 898 MB of decoded UI archives. It rewrites the static and dynamic modules and prepares shaders
without modifying the extraction. With already extracted files, the caller is
responsible for supplying a complete integrity-checked merged RomFS; the three
NSO hashes alone do not prove every asset in that RomFS is intact.

Effect extraction additionally walks all **329 `.eff` resources** through
EFFN → VFXB/EFT2 → GRSN/GRSC → BNSH. It decodes them one at a time (1,523,130,680
bytes cumulatively; maximum 34,419,200 per resource), retaining 654 shader-member
references as 386 deduplicated payloads totaling 290,926,184 bytes. The helper
checks that full census, manifests, membership, lengths and hashes before
passing `--smash-effect-shaders` to the splitter. Only retained shader carriers
are kept; complete decoded effects are not staged.

The resulting static corpus has **35,012 keys**, including all 8,028 keys from
the recorded registration run, the 116 older battle misses and the 18 earlier
menu captures. Those matches require no capture inputs or aliases. They prove
coverage of those observed keys, not that every stage has been drawn or every
fighter/effect rendered correctly. Current compilation and device-test limits
are in VALIDATION.md. Private receipts bind each extraction manifest, and
full builds preserve those manifests while releasing preparation scratch.

## Optional bounded native shader capture

Earlier SSBH/UI-only sources omitted effect carriers. The completed static
extraction covers all keys observed by the existing menu, registration and
battle runs. Capture is optional verification or investigation for future
unresolved keys; a menu-only run still cannot establish match coverage.

Use `--capture-runtime` with a new private Mac host and disposable save/temp
folders. Its default `--capture-route match` repeats confirm inputs through
44 seconds, attempts fighter selection and match start at 50–62 seconds, then
attempts movement, attacks, shielding and a jump from 70 seconds onward.
This longer schedule adapts the earlier successful navigation to registration
capture; its actual battle state still requires visual verification.
Those additional scripted actions are input attempts, not proof of fighter or
effect coverage. It performs the static shader build first, freezes a separate
producer profile, runs only its own new
process group, then resplits and rebuilds a new corpus if captures are present.
No device or real progress is used. `--capture-seconds` controls the timeout
(1–600 seconds, default match 105, menus 32); there is no claimed frame cap.
Starting from the static profile allows the same run to retain missing menu inputs as well as
later match inputs. For the shorter historical menu route, use
`--capture-route menus --capture-seconds 32`.

Owned captures enable boot instrumentation, so `logs/runtime-capture.log`
records the first-present timing and later frame evidence. Add
`--capture-screenshots` for four private PNGs at frames 1200, 2400, 3600 and
4800 under `capture-frames/`, separate from the shader payload directory.
Screenshots are produced only if those frames are reached. Inspect them to
check the actual route; timed button attempts alone do not prove a match.
These images contain game content and must stay outside the public repository.

Every helper-owned fresh run sets `DM_NVN_SHDUMP_REGISTER=1` to request original
inputs at program registration, alongside draw-time capture. A boot was observed
registering 7,846 programs, which is broader than the programs drawn by two
fighters. Registration capture is intended to retain those original registered
programs even when the bounded route does not draw them. Programs that are
deferred or never registered during the run remain outside that census.
The private summary records `registration_census_requested` separately from
payload validation; enabling the switch alone is not a completeness result.
For a requested census, the helper also requires `registration-census.jsonl`:
complete ordered rows, every declared registration stage reconciled, zero
invalid/error or unresolved deferred stages, and captured keys matching the
actual original pair files. The ledger's digest, size and validated counters
are bound into the producer receipt and rechecked on reuse. A missing or
incomplete ledger stops packaging.

Before and after execution the helper fingerprints the exact original modules,
NRRs, host binary, runtime/graphics/rewriter sources, rewritten modules and frozen
profile/header. Every captured control/code pair must match its original-byte
key. A crash, forced SIGKILL, changed producer or incomplete corpus stops the
build. The local receipt is audit evidence, not an authenticity signature.
Neither route establishes coverage of every gameplay shader, fighter or stage.

## Advanced reuse

A repeated build can reuse private outputs from the same supported game and
source/tool chain. `--rewritten` is independent; `--shaders` and
`--shader-manifest` must be supplied together:

```sh
python tools/smash.py --extracted-dir /private/Smash-13.0.5 \
  --rewritten /private/previous-build/rewritten \
  --shaders /private/previous-build/shader/initial/ios \
  --shader-manifest /private/previous-build/shader/initial/mac/b-CHAIN/_b_build.json \
  --bundle-id com.yourname.smash --work /private/Smash-build-03 \
  --app-only --allow-known-geometry-gap
```

Replace `b-CHAIN` with the actual generated directory. The helper creates a new
private profile and resplits the original shaders. Reused rewrites must contain
the correct static build IDs, current guard observation sites and the full
98-module catalog matching the original NRO/NRR identities. Reused shaders must
match the newly computed chain, full manifest, stage/reflection identities and
both Mac/iOS library sets. A cache from an older source chain is rejected.
The Mac reflection/MSL files beside the manifest are required to generate the
constant-buffer guard tables. Reuse your own trusted build output.

`--nvn-shader-capture` requires `capture-provenance.json` and every unchanged
producer/input file named by that receipt. Rebuilding or moving that producer
invalidates reuse; create a fresh capture instead. Captured shader caches must
be used with the same validated capture. For static-only caches, omit the
capture option and use the `shader/initial/{mac,ios}` directories. The helper
never adds keys by relabeling an unrelated shader.

`--prepare-only` performs preparation and validation without compiling/staging
an app. It still runs a disposable Mac host if `--capture-runtime` was requested.
`--work` is always fresh; partial/old directories are not silently
replaced. Receipts, tool logs, package files, modules, shader caches, signing
material and apps stay outside the source checkout.

A finished private app/IPA includes the game and rewritten code. A generic shell
app cannot import that executable code later; each build must be signed with
its game code embedded. Source checks in CI do not require those inputs.
