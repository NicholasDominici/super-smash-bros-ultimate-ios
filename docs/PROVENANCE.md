# Source provenance and publication boundary

This Smash project starts from the source-only
[Super Mario Odyssey iOS port](https://github.com/NicholasDominici/super-mario-odyssey-ios)
snapshot `5abe9c27ec5467d486a9708f2317b503f15b6e2a`. That project snapshots
[seedds/nxnative](https://github.com/seedds/nxnative) at
`3de606fd11f5e39c6b148e22e06f392daaecd0c4`. Upstream MIT copyright/license and
bundled third-party notices remain intact. The Smash checkout is separate;
private game/build history is not imported.

Smash additions include its exact-build profile, native NRO catalog/loading,
bounded targeted ARC and SSBH shader preparation, two-player controller routing,
verified per-player shield observations, extended-addressing signing policy and
an external player build workflow. Native authored vibration remains the baseline.
An exact-build offline arena patch adapts the original virtual reservation and
its matching metadata/bounds to the iPad address-space budget. It operates only
on private rewritten output, with original identity and instruction gates; the
source contains compatibility metadata rather than rewritten game modules.
The shared cloud coordinator is inherited and configured with a separate game
record ID and an opt-in builder-owned container. Actual Smash cloud delivery
and physical gameplay still need verification; see VALIDATION.md.

Odyssey-specific source, exact-build gates and tests remain as regression
coverage. Its `tools/odyssey.py`, `prepare_odyssey_*.py` and the structural
SARC/FLYT/FLAN aspect implementation are not the Smash player workflow. The
inherited aspect strategy references
[SMO-AAR](https://github.com/fayaz12g/smo-aar/tree/e8fd670d1faeab3d8c4904177928bcfd14afb42c);
this does not imply a Smash camera/HUD correction.

The ARC wrapper uses the MIT-declared
[smash-arc](https://github.com/jam1garner/smash-arc/tree/944ac568689fe9c9ddeea93a776db42dc7d41790)
Git dependency pinned by Cargo.lock. Upstream does not provide a separate LICENSE
file in that tree; no upstream ARC source is vendored here. Cargo retains its
package metadata and dependency notices in an external cache.
The original SSBH parser follows primary format definitions from
[ssbh_lib](https://github.com/ultimate-research/ssbh_lib/tree/08f8bc4470a7d480dfc9b64d7e08e97f3820fed7)
at that pinned revision. No shader/game blobs or path-hash database are included.

The bounded EFFN/EFT2 effect-shader reader follows format layouts from
[KillzXGaming/EffectLibrary](https://github.com/KillzXGaming/EffectLibrary/tree/d5491138d645221ec92189eeff3ded8c43fd0a1a)
at `d5491138d645221ec92189eeff3ded8c43fd0a1a`, under its
[MIT license, copyright 2024 KillzXGaming](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/LICENSE).
Primary layout references include the pinned
[EFFN reader](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFFN/NamcoEffectFile.cs)
and [EFT2 shader structures](https://github.com/KillzXGaming/EffectLibrary/blob/d5491138d645221ec92189eeff3ded8c43fd0a1a/EffectLibrary/FileData/EFT2/Shaders.cs).
The port implements bounded traversal and retains only validated shader
carriers from the builder's own game archive; no effect or shader payloads are
distributed with source.

Verified controller/status research cross-checks local exact-build instructions
against primary public Smash modding APIs, including
[smash-rs](https://github.com/WuBoytH/smash-rs/tree/ddacc5e19ccf8616783b6ad29265a99afd59e83b),
[skyline-smash](https://github.com/ultimate-research/skyline-smash/tree/d2ca90d9ecffdf9bf58efe6bcf4dd49f62ea1435)
and the
[HDR controller definitions](https://github.com/HDR-Development/HewDraw-Remix/blob/a56075404c96853b260689a341d63fcb90a33f93/dynamic/src/ext.rs).
Source metadata and hashes are not copies of Nintendo executables. No broad
character-coverage or physical-controller claim follows from a symbol name alone.

Nested SARC/BNSH shader extraction preserves original member provenance. An
optional bounded native Mac capture adds original control/code pairs only when
their intrinsic content keys match. Its local receipt records unchanged exact
game modules, NRR registrations, producer binary/source, rewritten inputs,
frozen profile/header and every payload. The final shader corpus is built in a
separate mutable profile; capture evidence stays private. A receipt is not an
authenticity signature or proof that every game mode has been exercised.

`dm/gfx/tools/dmsh_xlate_bin` contains upstream redistributable translation
**tools**, not game shaders. Their exact bytes match `dmsh_chain.lock` and
[TOOLCHAIN-BINARIES.json](TOOLCHAIN-BINARIES.json). Rebuilding them changes shader
fingerprints. Corresponding source/project references and third-party notices
remain under `dm/gfx/tools/dmsh_xlate` and `dm/third_party`. The publication audit
rejects unlisted/changed binary tools and other forbidden binary files.

Public contents are source, scripts, synthetic-fixture tests, licenses and
reverse-engineered identity/format metadata. Excluded material includes NSP/XCI/NCA,
ExeFS/RomFS, original or rewritten modules, translated shaders, game-derived
icons/fonts/media, screenshots, saves, keys, account/device logs, credentials,
profiles/certificates, signed apps and IPAs. These stay outside the checkout.
Run `tools/audit_repo.py` against staged blobs before publication. CI must never
accept private game inputs or upload game-bearing artifacts.

MIT applies to this project's port code, not Nintendo's game/content/trademarks
or dependencies governed by their own licenses.
