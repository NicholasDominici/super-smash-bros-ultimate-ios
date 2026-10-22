# Validation and current limits

This is **Smash Ultimate bring-up**, not a verified finished iPad release.
Do not carry Odyssey or Tears of the Kingdom gameplay claims into this port.

## What has evidence

- The supported base plus cumulative update 13.0.5 were merged with LibHac's
  integrity checks. All three original NSO identities are recorded in INPUTS.md.
- Targeted ARC extraction identified 98 native NRO modules and 14 NRR
  registrations; module identities are validated before offline rewrite/embed.
- The native Mac host reaches the opening movie, menus and battles. An
  85-second Kirby/Mario test demonstrates player movement, jumping and attacks,
  CPU movement/combat, damage, a knockout and respawn. The run exited normally;
  exact inputs, rewritten modules, sources, profile and host identities were
  unchanged. There were no missing shader keys or unresolved native factories.
  Its two pipeline-link errors led to the renderer lifetime fix below. A fresh
  post-fix 85-second Kirby/Donkey Kong run shows active combat, damage, moving
  fighters and item effects, with no rendering errors, pipeline-link errors,
  missing keys, unresolved factories or descriptor-pool overflows. It exited
  normally and its recorded inputs/source/profile/host identities stayed
  unchanged. A later 85-second Final Destination combat run uses the new
  30 GiB game arena and 36 GiB host window, reaches damage and knockouts,
  and exits normally with unchanged identities. It has no pipeline-link errors,
  missing keys, unresolved calls or pool overflows, but reports one cube-versus-2D
  texture mismatch; the renderer substitutes its zero cube. That run is not a
  clean rendering acceptance result. The same fallback was observed before
  the arena change; the affected shader/binding and visual effect remain unresolved.
  These are scripted Mac results, not physical iPad or two-human-controller results.
- Fighter script imports are now bound to catalog-verified native providers
  when their NROs finish loading. Before this fix, matches could render while
  both fighters remained frozen at startup placeholders. Strong unresolved
  function imports now fail closed until the exact provider commits; unload
  withdraws them before finalization. Constructor visibility, failed-load
  rollback, provider identity, concurrent publication and repeated unload/reload
  have dedicated game-free coverage. Previously rewritten format-1 catalogs
  must be regenerated.
- Pipeline lookahead previously recycled a 64-entry composite-program ring
  while saved render states still referenced its entries. A private trace
  directly observed saved program serials and shaders changing during
  prediction. Composite records now remain immutable and retain their resolved
  programs for the renderer session. A 16,384-combination regression retains
  256 saved identities through hash growth, stage changes and serial reuse;
  ordinary and ASan/UBSan runs pass. The shader payloads and translation chain
  are unchanged. Storage grows with distinct stage-serial combinations for
  the session; extended device memory/thermal qualification remains pending.
- Static extraction includes 362 nested ARC resources and all 329 EFFN/EFT2
  effect resources. The latter retain 654 shader-member references as 386
  deduplicated carriers, without keeping complete decoded effects. Alongside
  UI, SSBH and embedded sources, the new static census is **35,012 keys**
  (22,197 VS, 12,761 PS, 53 CS and the one known GS), with 28,607 pairs.
  Exact original identities cover all 8,028 keys from the registration run,
  all 116 earlier battle misses and all 18 earlier menu captures, with zero
  capture inputs or aliases. **35,011 stages compile on both Mac and iOS**,
  with **10,211 framebuffer-fetch variants per platform**, on chain
  `0e445495ca2e`. The only compile failure is the documented geometry shader.
  Every expected key, reflection and library set was reconciled, and the
  constant-buffer guard tables were regenerated from the compiled MSL. This
  establishes static build coverage, not execution or visual correctness.
- A fresh, owned 32-second native Mac menu run produced **18 additional original
  control/code pairs**. Its exact modules, NRRs, host, 269 source files, 707
  rewritten files and 11 frozen profile/header files were recorded before and
  after and rehashed by the consumer. Intrinsic keys match the original bytes.
  That earlier, effect-incomplete private corpus had **8,611 keys**:
  **8,610 compiled** on both Mac and iOS, with **3,540 framebuffer-fetch
  variants** on each platform.
  `CharacterDamageModel2GS` is the only declared-corpus compile failure. This
  bounded menu route does not prove shader coverage across gameplay, fighters,
  stages or modes.
- The subsequent Mac battle encountered **116 additional unmapped shader keys**.
  That older picture was incomplete despite the verified menu-corpus manifests.
  The full static corpus now covers those identities; no complete
  gameplay-shader-coverage claim follows from the 8,611-key corpus.
- An earlier 85-second Mac run used the full 35,012-key static corpus. Private
  screenshots show a Kirby/Link match on an Animal Crossing
  stage. Its log reported no missing shader keys, descriptor-pool errors or
  crashes. Original inputs, rewritten modules, host sources, frozen private
  profile and host binary were unchanged across the run. This establishes a
  bounded rendering result: the later input test found frozen fighters and led
  to the import fix above. It did not establish gameplay, two physical players, all
  fighters/stages or iPad performance.
- A real register-all capture reconciled **8,395 observed programs**, **8,984
  stages** and **8,028 unique original pairs**, with zero unresolved deferred
  stages or capture errors. It includes programs not drawn by the short route.
  The run ended in menus and captured only 27 of the preceding battle's 116
  missing keys; it is not a new battle-coverage result. The subsequent
  control-prefix merge issue was corrected using explicit original-byte
  provenance. The fuller effect-based static corpus supersedes that workaround;
  deferred/unregistered programs and visual/runtime behavior still require
  separate evidence.
- Portable controller tests cover independent SDK state/latches, native authored
  output, motion, assignment swaps, hotplug and stale callback rejection.
  Eight logical slots/16 actuators are exercised synthetically; the product
  target remains two mixed physical controllers.
- Exact-build guard observers, remapped Guard bindings, repeated block entries,
  expiry/lifecycle cancellation and concurrent producers/polling pass synthetic
  tests, including ThreadSanitizer stress. Controller Objective-C code compiles
  against the real iOS SDK. These checks do not establish physical haptic feel.
- Existing Odyssey observer/transport regressions remain passing independently
  of the new Smash profile. Save archive/coordinator checks use controlled
  transport and synthetic fixtures, not a real Smash iCloud handoff.
- The player helper completed a fresh private work directory from
  the verified merged extraction, reused exact rewritten modules and the full
  static shader cache. Its unsigned iOS app passes resource/product validation
  with background CloudKit enabled. The current runtime build includes the
  deferred-import and composite-lifetime fixes and regenerated format-2 catalog.
  The rebuilt 36 GiB-host package also passes signing with an exact-app
  Extended Virtual Addressing, Increased Memory Limit and CloudKit profile.
  That signature does not establish installation or gameplay; those physical
  checks remain pending.
- A real disposable Mac match created a five-file save; production save-archive
  capture, encode, decode and restore preserved its exact digest in a new
  private directory. This validates that actual file set and codec, not iCloud
  upload or a two-device handoff.

## What remains unverified

Physical iPad gameplay, a complete two-controller match, per-player feedback
feel, long sessions, thermal/memory behavior, all fighters/stages/modes and
end-to-end Smash save synchronization remain unverified. Cloud snapshot capture
must be checked against actual Smash commits and both handoff directions.

The current composition is 16:9. Corrected native iPad/iPhone camera/HUD layouts
are not implemented; borders are expected on other screen shapes. Frame
interpolation is optional and off by default. It adds displayed frames while
retaining 60 Hz simulation; it is not native 120 FPS rendering. Its artifacts,
latency and performance require their own device tests.

The large sparse address reservation requires Extended Virtual Addressing in
addition to Increased Memory Limit. It is not a physical RAM allocation or a
guarantee that every iOS 26+ device can run the game.

A signed startup probe on the M5 iPad Pro accepts individual reservations up
to 64 GiB but rejects the original 68 GiB request with `ENOMEM`. Holding a
64 GiB alias reservation also prevents the separate 3.5 GiB heap reservation.
Both memory entitlements are present in the signature and provisioning profile;
available disk storage is a separate issue. A 36 GiB reservation succeeds on
that device. The profile now uses that smaller host window with a 32 GiB alias
region; the exact-build rewrite must adapt the game's corresponding arena and
all its bookkeeping together. That exact-build rewrite now passes original
identity and instruction gates, atomic rejection tests, independent disassembly
review and the bounded Mac combat run described above. The physical application pool and host heap
capacity remain unchanged. A successful address-space probe does not establish
gameplay or device memory/performance behavior.

## Build acceptance

`tools/smash.py` does not interpret a shader command's zero exit status as
success. It requires one manifest row for every freshly split shader-map key,
no duplicate/extra/missing keys, complete Mac/iOS library and reflection sets,
matching identity/stage/chain/platform metadata, valid library headers/lengths,
usable binding/driver metadata and matching framebuffer-fetch variants.
It regenerates constant-buffer guard tables from the validated Mac MSL.

The only explicit exception is `--allow-known-geometry-gap`, restricted to
key `ef507c559969bc0a`, stage GS and source `CharacterDamageModel2GS`. Any other
failure stops packaging. Accepting that exception is not a claim that the
game's geometry effects or every runtime shader are correct.

A fresh build creates private receipts and logs outside the checkout. Reused
caches must match the new chain. A completed manifest establishes static build
coverage of the supplied corpus, not actual runtime-key coverage, visual
correctness, installation or performance.

Static SSBH/UI/effect extraction covers the currently observed keys without a
native capture run. Optional `--capture-runtime` builds its Mac producer outside
the checkout and uses fresh disposable save/temp directories. It kills only its owned process
group on timeout and rejects crashes or SIGKILL. Capture reuse rehashes the
actual producer, original inputs, source, rewritten modules, frozen profile and
payload files; the receipt alone cannot admit arbitrary data. The frozen
producer profile remains separate from the final mutable build profile.
The default route now attempts a match for up to 105 seconds, repeating confirm
inputs through 44 seconds, attempting selection/start at 50–62 seconds, then
adding later action inputs from 70 seconds onward. The older register-all run's
log did not contain an exact first-present timestamp; its earliest timed frame
was frame 3 at 3.31 seconds. A delayed first present is not an established cause
of the missed route. Fresh runs enable boot timing, with optional private frame
screenshots, so the actual route can be checked. Capture starts
from static shader tables so menu misses can be captured too. The older menu
route remains available explicitly. Individual scripted actions and all
fighters/stages still require runtime verification.
Registration capture is requested explicitly with `DM_NVN_SHDUMP_REGISTER=1`;
receipts distinguish that request from old draw-only runs. The switch and a
successful process exit cannot establish complete program coverage by themselves.
The helper requires a bound `registration-census.jsonl`, with every declared
registration stage reconciled, no invalid/error or unresolved deferred stages,
and a captured-key set matching the original payloads. Synthetic tests exercise
that gate and receipt tamper rejection, and the first real register-all capture
passed the ledger gate. Deferred/unregistered and unvisited gameplay limits
remain, and the delayed route still needs its own visual match result.

Capture admission permits at most 65,536 unique pairs, matching the native
writer, while retaining the independent 16 MiB provenance-receipt and 1 GiB
payload bounds. A larger run stops rather than silently dropping records.

## Game-free checks

```sh
python3 tools/check.py
python3 tools/audit_repo.py
```

The source suite covers configuration/signing policy, synthetic ARC/SSBH parsing,
NRO catalog/loader policy, input/feedback isolation and lifecycle, verified
observation guards, inherited presentation checks, save-archive integrity and
CloudKit coordination. The current run passes 113 Python tests plus native,
sanitizer, archive and 17 cloud-coordinator scenarios (153 checks). It uses no
game files, accounts or devices. The audit
checks staged Git blobs for excluded game/signing/private artifacts and pinned
redistributable tool identities. It is not a live-device test.

For a local preparation check, use the commands in INPUTS.md with
`--prepare-only`, a new private `--work` directory and your own files. No app is
compiled, signed or installed by that option. With `--capture-runtime`, the
bounded disposable Mac producer is launched. Full input-to-app/IPA
validation and physical gameplay results should be recorded separately.

Before a requested live update, save/close the game, byte-verify a stable backup,
preserve bundle/team identity, install and compare save files before launch.
Test picture, menus, audio, both players, custom Guard mappings, repeated blocks,
disconnect/reconnect and foreground/background. Check actual cloud digests and
progress in each direction separately; distinguish observed commands from
hardware feedback and acknowledged saves from queued work.
