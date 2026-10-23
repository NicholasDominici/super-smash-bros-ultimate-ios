# Controllers and local multiplayer

The Smash profile targets **two local players on one iPad**, each with an
independent extended gamepad. The adapter supports mixed models; features depend
on the actual controller. Pair controllers in Settings → Bluetooth before
opening the game. A physical two-controller Smash match is not yet verified.

## Touch controls

The overlay shares Odyssey's fixed left stick, Nintendo face diamond, inward
D-pad, invisible floating right stick and shoulder columns. Its lighter fills,
outlines and labels use opacity per shape, keeping the game view fully opaque.

Tap and release the top-centre gear to open Settings. A thumb may stay on
a gameplay control; opening Settings releases its input. A second gear finger
or movement over 12 points cancels the tap. Dragging outside the gear, including
coalesced out-and-back movement, or cancelling the touch also prevents opening.
Gear touches are consumed without pressing a game button. VoiceOver also provides
an explicit **Open settings** action. The gear stays visible with a controller
connected. The D-pad and invisible right stick are always enabled for touch
play. Obsolete compact-layout preferences remain stored but are ignored.
Plus/minus remain exposed game buttons. Closing settings,
rotating, backgrounding or reconnecting clears owned touch input.
Live bounds, scale and safe-area changes cancel touch/gear ownership too.
Geometry cancellation does not suspend or reassign paired controllers or stop
their feedback focus. The shared touch-v6 layout caps control scale by safe width
for narrow/tall scenes; ordinary landscape phone and iPad layouts are preserved.
Invalid/empty touch geometry publishes a zero-contact panel state so a previous
guest touchscreen contact cannot remain latched during the transition.

Settings contains **Gyro**, **Device haptics**, and **Also with controller**.
These switches are disabled because this Smash build has no device-gyro source
or built-in device-haptic backend. Supported controller haptics remain active
with their existing tuning; the disabled switches do not alter them.

This UI iteration needs physical interaction testing after installation.

## Button layout

The adapter preserves the Switch button positions rather than the printed Xbox
letters. Customize actions using Smash's own controller settings.

| Position | DualSense | Xbox | Switch prompt |
| --- | --- | --- | --- |
| Right face button | Circle | B | A |
| Bottom face button | Cross | A | B |
| Top face button | Triangle | Y | X |
| Left face button | Square | X | Y |
| Left/right bumper | L1 / R1 | LB / RB | L / R |
| Left/right trigger | L2 / R2 | LT / RT | ZL / ZR |

Each connected controller keeps its slot when another connects/disconnects or
the system's enumeration order changes. A new connection fills a vacant slot;
assignment is not a permanent pairing identity across app launches. Guest
controller-assignment swaps apply to input, vibration and motion together.
Touch controls feed player one only and release their state when hidden.
Single sideways Joy-Cons and micro-gamepad-only profiles are not implemented.

## Feedback

The game's native authored left/right vibration is the baseline. Supported
controller actuators receive independent output; a controller with one haptic
locality receives a mix. Controllers without haptics still provide input.

DualSense adds light trigger resistance only while the game confirms a shield
state and that player is holding a trigger actually assigned to **Guard**.
A committed shield-damage event adds a short trigger thump. Custom mappings and
the per-name rumble setting are respected; an unrelated trigger binding cannot
create shield feedback. CPU fighter slots do not target another player's pad.
These are verified 13.0.5 status/input hooks, not guesses from button presses.

Release, app suspension, controller replacement/disconnect, assignment changes
and stale game/input timestamps cancel effects. Short hardware-command leases
also bound output if the update queue stalls. Command counters are not proof
that hardware actuated, and synthetic tests do not establish the physical feel.
Smash trigger feel remains to be tested on the device.

Motion is transported separately for each controller that supplies rotation
sensors. This does not add Odyssey's shake-to-throw mechanic to Smash. Adaptive
trigger support requires DualSense hardware; Xbox/other controllers receive
only the features their GameController profile exposes.

## Testing a local match

Connect two different controllers and verify that each moves only its own cursor
and fighter. Test both players' attacks and shield feedback separately. Change
a Guard trigger to an unrelated action and confirm resistance disappears there.
Test repeated blocks, releasing mid-impact, disconnect/reconnect and
foreground/background transitions. Confirm the other player keeps working.

The app writes private `controller-feedback.json` and per-player diagnostic
files in Documents. Smash guard counters distinguish observed mappings/statuses
from trigger commands. Inspect them locally and redact device/account details
before sharing excerpts. No game or controller log belongs in the repository.

## FPS corner

Tap the small safe-area top-left counter to hide its text, then tap the same
transparent corner to reveal it. The target stays available with a controller
and preserves other held touches. See [frame-rate behavior](FRAME_RATE.md).
