# Controllers and local multiplayer

The Smash profile targets **two local players on one iPad**, each with an
independent extended gamepad. The adapter supports mixed models; features depend
on the actual controller. Pair controllers in Settings → Bluetooth before
opening the game. A physical two-controller Smash match is not yet verified.

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
