# Release readiness

The accepted iPad baseline is suitable for continued private play and an
**experimental source release** with the limits below. It is not a general
production-quality compatibility claim for every iPhone, fighter, stage or mode.
No game-bearing app or IPA may be published with this source repository.

## Accepted scope

| Capability | Evidence and boundary |
| --- | --- |
| iPad picture and play | M5 iPad Pro player accepted full-screen 4:3 proportions and gameplay feel. Other device families and complete scene coverage remain unqualified. |
| Intro audio | Player confirmed clean audio after the PCM Base/range correction. Real logs show reused nonzero buffer offsets; matching clean short PCM fragments improve from 885/1600 to 1598/1600. Offline sample-alignment observations are not a reported remaining audible defect. |
| FPS corner | Player confirmed hide/reveal in all three related ports. The transparent target remains active when its text is hidden. |
| Generated presentation | 2399 displayed frames over 19.99235 seconds, about 119.996 FPS, in a controlled intro/menu run. These comprise 1199 native and 1200 generated presentations; game pacing remains 60 Hz. No numerical in-match 120 FPS claim. |
| Local progress | Whole-save commit/rollback/archive checks and protected-byte checks passed. Actual iPad committed-save uploads are acknowledged. |
| Names | Generated CFBundleDisplayName and CFBundleName are both exactly **Super Smash Bros. Ultimate**. The executable/product remains DmIOS. Directory/IPA filenames are independent of the visible app title. |

Controlled captures did not have a controller connected. Earlier controller
tuning is preserved, but this release does not inherit new physical DualSense
or mixed-controller acceptance from the intro/menu run. Phone installation and
phone-specific qualification were deferred.

## Remaining release gates

- **Duo/resizable scenes:** the 4:3 builder enables paired live camera/HUD
  correction with private generated rules and exact hooks. A continuous actual
  Mac gameplay Open/Closed/Open preview passed source-generation, safe-area,
  proportion and action checks. Shipping qualifies narrow 4:3-to-3:2 standard
  gameplay and uses a coherent 4:3 fallback for unknown owners or wide scenes.
  Physical execution, opposite landscape and all menus/modes remain deferred;
  the Duo simulator's UIKit fixture is separate from actual game execution.

- **Cloud durability receiving check:** the source now gates network work and
  acknowledgements on successful journal/state writes. Failed account pins do
  not advance; confirmed pending ancestry retries before newer commits. The
  production-coordinator harness passes real Foundation write-failure/recovery,
  restart and import cases. This fixes a demonstrated defect in the accepted
  baseline, where failed writes could still report `synced`. The updated binary
  requires its own signed-package verification and later install readback; prior server acknowledgements and
  gameplay acceptance do not establish that deployment.
- **Cloud handoff:** actual Smash download/preboot restore, return-device
  continuation, account/conflict/offline and background retry scenarios remain
  unverified on devices. Other titles' results do not certify Smash.
- **Content coverage:** the exact geometry-stage exception remains opt-in;
  historical texture-view and late tutorial-cleanup failures need targeted
  regression coverage. Accepted scenes do not clear those historical failures.
- **Local multiplayer and feedback:** test two independently paired mixed
  controllers through a complete match, per-player rumble, custom Guard mapping,
  repeated blocks and reconnect/background stops. Synthetic slot/actuator counts
  are not physical player qualification.
- **Performance/hardware:** measure matched active battles, long sessions,
  memory/thermal behavior and interpolation artifacts/latency. The 30/32/36 GiB
  arena/alias/window group and two required entitlements are title-specific;
  this is not a minimum-RAM guarantee or a qualified iPhone release.

These gates do not require changing the accepted gameplay/audio/haptic tuning
for a metadata-only name update. Keep the accepted executable and game resources
unchanged in that update; signing and installation require their own readback.

## Source-release checks

Before publishing a prospective source tree:

1. Run `python3 tools/check.py` and `cargo test --locked --manifest-path tools/smash_arc/Cargo.toml`
   with build output outside the checkout. Run `python3 tools/audit_repo.py`
   against the staged index and inspect every added/modified file. A clean index
   audit alone does not cover untracked working-tree additions.
2. Export only source, synthetic tests, pinned redistributable tool bytes and
   license/provenance notices into a fresh directory. Run the game-free checks
   there. Do not depend on another port's private game/generated files.
3. Follow the numbered README instructions with the builder's own exact base
   plus update 13.0.5, keys and signing account. The generated project, complete
   shader manifests, addressing group and packaged metadata must validate.
   No new clean-machine game-bearing build is implied by game-free checks.
4. Keep source, package, install, runtime and human acceptance tied to their
   actual revision/build. CI for an older published commit does not certify
   unpublished working-tree changes. Retain known failures and deferred tests.

The public build defaults remain 16:9, cloud off and frame generation off.
The accepted private iPad configuration uses matched 4:3 preparation, its existing
owned cloud identity and optional 2x generation. See [INSTALL.md](INSTALL.md),
[ICLOUD.md](ICLOUD.md), [FRAME_RATE.md](FRAME_RATE.md), [AUDIO.md](AUDIO.md) and
[PROVENANCE.md](PROVENANCE.md). Do not infer App Store/TestFlight or unrestricted
IPA distribution from the development-signing workflow.
