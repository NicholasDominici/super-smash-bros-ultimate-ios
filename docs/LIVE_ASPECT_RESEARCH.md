# Live camera and HUD adaptation research

The 4:3 player build now enables paired live camera, projection and pane
correction by default. The builder regenerates the exact main hooks, compiles
private rules from the admitted archive and rejects missing gates or rules.
The source repository contains the methods and synthetic fixtures only.

Continuous actual Mac gameplay passed stationary folds and actions in both Duo
postures, including immutable source/camera/HUD/projection generation binding
and safe-area timer anchors. Shipping uses a narrow 4:3-to-3:2 qualification and
coherent baseline fallback for wide scenes or unadmitted owners. Results and
stage-selection camera coverage, physical folding and all-content acceptance
remain separate. Existing signed/install evidence predating this source update
does not certify the new package.

## Receiving camera and layout findings

For original main build `21450c647b8c5940ed5b68218ea128fd`:

- Common camera update at `0x4ec800` takes a camera structure in X0. The surveyed
  default constructors and battle update paths call it. It reads vertical FOV at
  `+0x124` and aspect at `+0x128`, then derives horizontal/vertical tangents at
  `+0x134/+0x138` and inverse-projection values at `+0x13c/+0x140`. These are data
  hook candidates; static calls alone do not prove coverage of every camera.
- Existing observers24/25 remain unchanged. They admit UI projection/caller
  state and per-pass clipping for the prepared engine-primary layouts.
  The actual live probe found SetProjection runs at layout load and remains
  cached across thousands of draws. Dynamic correction therefore revalidates
  the current admitted DrawInfo matrix at each draw and sets its vertical
  coefficient absolutely from the horizontal coefficient and current aspect.
- The owning layout pointer is at `+0x458`, with derived vtable
  `main+0x523f6f0`. Animation walking is distinct from matrix calculation;
  active correction runs after derived panes have finished their own reflow.
- Layout root pane is at `+0x18`. Independent receiving-code reads establish
  runtime pane position `+0x30`, scale `+0x48`, size `+0x50` and name `+0xb0`.
  The public [nnsdk-rs UI bindings](https://github.com/ultimate-research/nnsdk-rs/blob/d23f131663ec72a87c84914e6e738999f3ab403d/src/nn/ui2d.rs)
  corroborate this structure. They are a research reference, not an admission
  substitute for the supplied game's bytes.
- The actual common Calculate function is `0x4b620`. It constructs a calculation
  context, records the current layout in DrawInfo at `+0xc0`, invokes root
  CalculateGlobalMatrix through virtual slot `+0x98` at `0x4b670`, then invokes
  the layout post-calculate callback at `0x4b684`. Observers bracket the root
  call at `0x4b654` and `0x4b674`, ending before that arbitrary callback. The separate Draw path uses
  root virtual slot `+0xa0`; it must not be mistaken for Calculate.

`smash_live_aspect.py` requires the exact original NSO identity, receiving
instruction facts and all five live observer stubs/return branches. The two
base-pane post sites are `0x587c0` (after native Local) and `0x588d4` (authored
matrix path), before child traversal. The latter internal site has an exact
build/site/neighbor allowlist and requires the production full-register gate.

The common world-camera update is cached too. The receiving game's consumers
resolve its current data root through `main+0x52b8f00` and a second pointer, with
the embedded primary camera at `+0xca0`; separate consumer paths use `+0xe30`
and `+0xfc0`. These are independently byte-gated receiving facts. After freezing
the completed source and latching the next interval, the adapter resolves the
current primary owner again. It validates its fields, runs the original native
camera update when its aspect changes, and checks all derived frustum caches.
No root/camera pointer survives that synchronous call. Current-owner applied
state updates remain separate from native observer callback counts.

## Exact resource reflow plans

The existing source-bound 4:3 receipt identifies every transformed field in362
primary archives: canvas/root dimensions, explicit edge groups, full-screen
fills, rotated fill origins and animation key values/slopes. The new planner
first reverses the receipt, admits the original archive identity, and reproduces
the canonical preparation. Modified, missing, overlapping or forged field
declarations fail before a target is returned.

The current policies are affine in the logical height expansion. Planning a
target aspect changes only these declared fields. Text, icon geometry, other
members and archive positions remain untouched. The 4:3 and authored16:9
endpoints are byte exact. Plans always start from the admitted baseline;
feeding a previously retargeted result back into the baseline receipt fails.

Run from the source checkout using the existing toolchain Python:

```sh
python3 dm/tools/smash_live_aspect.py \
  --main /private/inputs/ExeFS/main \
  --arc /private/cache/romfs/data.arc \
  --receipt /private/cache/aspect-receipt.json \
  --aspect 1.4549356223175967 --aspect 1.42152466367713 \
  --output /private/work/current-aspect-plans.json
```

The example ratios come from the measured Duo landscape scenes678×466 and
951×669points. Production geometry must use the current scene, not hard-code
these samples. Output contains hashes/counts, not transformed game payloads.
The `retarget` Python API also returns named field plans. `calculate_plan`
converts them into source-bound geometric rules for loaded-pane integration.
Fill growth is separate from content transforms: a non-leaf fill must preserve
descendant text/art even under rotated ancestors. No real pane size changes,
including RootPane, are allowed. Target root dimensions are used only in a
private parent copy when deriving the original local transform. A candidate
global correction uses `inverse(parent_growth) * local * own_growth`, derived
from the current native pose after any Text reflow. It writes the calculated
global matrix before children run. It leaves UserMatrix pointers, authored flags
and pane sizes owned by the game. Complete primary and relevant nested Parts
namespaces are admitted upfront; declined scopes never apply partial or outer
plans. A bounded method registry detects overlapping active calculations without
waiting across guest code. No pane pointer survives the method return.
Positions use additive offsets from current animated values. Nothing
is written into a runtime pane by this planner. This is resource math and
static-code evidence, not game execution.

Source-declared edge HUD groups also receive horizontal safe-area anchor
displacement. Their current positions are mapped into the safe horizontal span;
the attached text, icons and other geometry retain their scale. This is separate
from full-screen background growth and requires visual timer/edge validation.

## Remaining runtime qualification

1. Qualify additional camera owners, menus, dialogue and mode transitions;
   unknown owners currently select the coherent 4:3 fallback.
2. Verify this signed iOS implementation on physical hardware, including both
   landscape orientations, repeated folds, all safe-area edges and resumed play.
3. Measure sustained battle performance and interpolation artifacts/latency.
   Native CPU hooks and Mac visual proof do not establish these device results.

The current Metal4 backend cannot execute a full game on the tested Duo
Simulator runtime. A production UIKit host fixture proves layout delivery only.
Actual Mac game execution with a clearly identified geometry relay can provide
additional receiving visual evidence; it is not native Duo game execution or
physical-device acceptance.

The opt-in private CPU runner accepts `--input-manifest` and optionally
`--private-rewritten`. It first checks canonical input inventories, then verifies
the complete private observer group. Actual rewritten TSD gates call the
production UI core and `entry.S`; a deliberate callback clobbers caller registers,
SIMD, flags and FP control. The game-free `--gate-only` fixture checks that exact
assembly register frame without reading game files.
