# Native iPad aspect

## Live scene and folded-window resizing

The frontend now fits the admitted game aspect to the current window bounds and
uses that window's screen scale. It responds to live bounds, display-scale and
safe-area changes, including folded/unfolded and narrow intermediate scenes.
Empty, nonfinite or oversized transitional geometry retains the last valid
drawable. No model name or fixed folded/unfolded aspect selects a layout.

The `--display-aspect 4:3` build enables the paired live camera, projection and
HUD adapter without a development environment variable. It generates private
layout rules from your admitted prepared archive and requires all five exact
receiving observer gates. Full-screen narrow landscape targets span 4:3 through
3:2; geometry always comes from the active scene. The default 16:9 preparation
keeps its existing wide-phone path and does not enable this adapter.

A fresh current world-camera owner, admitted layout and projection must agree
on the completed interval. Unknown owners (including results cinematics),
unadmitted layouts and aspects outside that range select a coherent proportional
4:3 fallback for the next interval. Five healthy baseline intervals precede
recovery. The failed completed source is reported honestly; it is never relabeled
with a newer aspect. Fallback can introduce bars; it preserves proportions.
Camera/HUD changes keep the physical raster and 60 Hz game clock unchanged.

A continuous actual Mac gameplay preview passed Open/Closed/Open folds, movement
on both sides and matching camera/HUD/projection generations and safe-area timer
anchors. This was real Mac rendering driven by Duo scene geometry, not game
execution on the simulator. Physical Duo gameplay, every menu/mode/camera and
opposite-landscape coverage remain deferred. See [receiving details](LIVE_ASPECT_RESEARCH.md).

Drawable changes invalidate interpolation captures, queued outputs and the
latest cached frame. The serial processing worker resets its history for the
new epoch. Main-thread notification does not wait for GPU/ML work or retire
in-use native swapchain tickets. Touch/gear ownership is cancelled separately
from lifecycle suspension, preserving paired controller slots and feedback focus.
Invalid touch geometry explicitly publishes zero contacts, releasing any prior
guest touchscreen contact even while the scene is temporarily empty or detached.
Controls and the FPS reveal target use the same safe-width scale cap in narrow
scenes, and labels use their window's display scale.

Receiving tests execute the actual frontend/adapter methods against synthetic
scene peers, including repeated geometry changes, invalid intermediates and a
scale-only transition. The real interpolation invalidator is stressed with
concurrent notifications while native ownership remains outstanding. These are
host checks; they do not prove physical folding, GPU timing or Smash gameplay in
the Duo simulator. Device testing remains deferred.

A separate receiving UIKit host fixture imported the actual Smash frontend,
touch adapter and FPS source on the iPhone Duo 27.1 simulator. Closed → Open →
Closed changed the scene from 678 × 466 to 951 × 669 points and back at scale 3;
the fitted drawables changed from 1864 × 1398 to 2676 × 2007 pixels and back.
The process/session stayed the same and the stub guest started once. FPS
hide/unfold/reveal and a fixture settings sheet survived these transitions;
two synthetic controller slot/epoch/focus invariants also passed. Guest code,
cloud, motion and feedback were stubbed. This qualifies UIKit delivery to these
frontend components, not Smash gameplay, physical folding, opposite-landscape
orientation or haptic feel.

## Exact-build 4:3 preparation

Add `--display-aspect 4:3` to `tools/smash.py` for the supported US-English
13.0.5 build. The default remains 16:9. This prepares a camera and UI correction;
changing only the frontend aspect would distort an uncorrected game.

The game keeps its current physical rendering budget and 60 Hz simulation.
The UI uses a 1920 × 1440 logical canvas. Camera defaults, camera fitting,
orthographic and perspective UI projections, nested clipping, edge anchors and
their animation keys are corrected together. Custom square cameras retain
their authored aspects. Text and circular UI elements keep their proportions.
Background and fade geometry expands independently from text and icons.

Preparation requires the exact original main module and original compressed
resource hashes. It preserves the complete 30 GiB arena patch, all 98 native
modules, their catalog and shader tables. A reused rewrite is cloned before
main is regenerated with the original UI gates and all five live receiving gates. Original inputs and
previous build caches are never edited.

The asset writer changes only admitted fields in 362 primary UI archives. It
recompresses each resource into one standard Zstandard frame, using valid empty
blocks to retain the original compressed span size. The ARC index and offsets
stay unchanged. All changed spans are decoded and verified before atomic
promotion. Product validation hashes the actual packaged spans, so a same-size
uncorrected archive cannot pass. Helper source hashes bind the preparation
receipt to the reviewed implementation.

Game-free tests cover atomic rejection, instruction encodings, projection
math, original caller/stack admission, all seven pass rectangles, animation
values and slopes, single-frame compression, packaged-stream checks and clone
preservation. Private canonical validation reverses every declared asset edit
to its original archive identity and recomputes the transform. These checks do
not establish physical appearance across all stages, modes or languages.
The signed build has been installed on an M5 iPad Pro. Its normal renderer logs
a full 2752 × 2064 viewport, a 1920 × 1080 raster and the corrected 4:3 logical
aspect. Physical captures show the Smash menu and a Kirby/Donkey Kong match on
Skyworld filling the display with natural proportions. The battle timer and
damage panels use the adjusted HUD placement. This clean launch used scripted
UI input, with no debugger, graphics validation or internal screenshot readbacks.
The generic touch overlay can overlap parts of the timer and left damage portrait.
Its 3,067 learned pipeline recipes and all five save files were verified
byte-for-byte across the update. These bounded checks do not qualify other
stages, modes or every camera state. Keep US-English selected.

Primary camera research: [Fl4sh9174's aspect-ratio research](https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods).
The implementation independently gates the supplied 13.0.5 build and does not
include that mod's executable patches or game content. Compression follows the
[Zstandard frame format](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md).
