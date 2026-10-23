# Frame rate and the FPS corner

Smash 13.0.5 retains its original 60 Hz game pacing. No independently verified
variable-step patch for its combat, animation, hit-stop and timers is present.
Changing a display-link rate or present interval alone does not establish safe
native 120 FPS gameplay. The engine-cap patches in `dm/host/hle_fpslock.c` apply
to other exact game builds, not Smash.

Add `--frame-generation on` to the normal `tools/smash.py` command to generate
a private `frame_generation 2x` profile. The public default remains off.
VideoToolbox can add one image between game frames while simulation remains
60 Hz. The worker checks display refresh (at least 100 Hz), hardware/API
support, pixel formats, even dimensions and platform dimension/pixel limits.
It interpolates the cropped source raster (currently 1920 × 1080), independently
of the iPad's larger drawable and its 4:3 presentation transform.

Capture/output queues are bounded. Unsupported, loading, overloaded and
suspended paths retain original-frame fallback. `DM_FRAMEGEN=0` in
`Documents/env.txt` disables interpolation without rebuilding. Preserve other
entries when editing that file. An enabled flag does not prove generated frames
were displayed; check active matches for pacing, artifacts, latency and heat.

The FPS counter sits at safe-area top-left, normally 80 × 22 points, with an
11-point monospaced readout. A tap hides only its text; tapping the same clear
corner reveals it. Visibility persists locally, the target remains available
with controllers, and no settings row is added. Outside touches pass through;
other held fingers continue controlling the game. Very short landscape windows
narrow the target to preserve the normal L3 center. Explicit corner ownership
takes priority over the small overlapping part of the expanded ZL hit rim;
all control geometry and normal ZL/L3 centers remain intact.

The number counts actual displayed frames. `FG` appears only when generated
frames were displayed during the sample interval. It does not describe a
120 Hz simulation or native 120 FPS rendering. Delayed/background samples show
`-- fps` until the next valid sample.
