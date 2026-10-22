# Native iPad aspect

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
main is regenerated with the two exact-build UI gates. Original inputs and
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
The new layout is undergoing physical validation; keep US-English selected.

Primary camera research: [Fl4sh9174's aspect-ratio research](https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods).
The implementation independently gates the supplied 13.0.5 build and does not
include that mod's executable patches or game content. Compression follows the
[Zstandard frame format](https://github.com/facebook/zstd/blob/v1.5.7/doc/zstd_compression_format.md).
