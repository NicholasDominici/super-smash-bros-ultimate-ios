# Super Smash Bros. Ultimate for iPhone and iPad

An experimental native Apple Silicon port of **Super Smash Bros. Ultimate
13.0.5**, built on [nxnative](https://github.com/seedds/nxnative) and the
[Odyssey iOS port](https://github.com/NicholasDominici/super-mario-odyssey-ios).
The game code is rewritten on your Mac and signed into the app; there is no
runtime JIT or jailbreak requirement.

**This is an experimental port.** On an M5 iPad Pro, a player accepted full-screen
4:3 proportions, clean intro audio, the FPS hide/reveal corner and gameplay feel.
A controlled intro/menu run displayed about 120 FPS with generated frames while
preserving 60 Hz gameplay pacing; this is not a measured match-performance claim.
Actual completed saves have uploaded to iCloud.

First-use shader compilation can still pause unseen content. Historical scene
transition texture-view and late tutorial-cleanup failures have not been cleared
across all content, and one known geometry shader remains unsupported.
Two-controller matches, new controller-feel regression, sustained performance
and iCloud handoffs still need device tests. Read the
[release-readiness scope](docs/RELEASE_READINESS.md) and
[detailed validation](docs/VALIDATION.md) before spending time on a build.

You provide your own **base-game NSP or XCI, update 13.0.5 NSP, and console
keys**. This repository contains source, tools and metadata. It contains no
game, executable game modules, shaders, keys, saves or installable game IPA.

## Implemented in source

- A native iOS runtime and Metal shader build path, including Smash's dynamically
  loaded fighter modules and targeted SSBH, UI and effect-shader extraction from
  `data.arc`.
- An automatic, exact-version virtual-arena compatibility patch for the iPad
  address-space budget. Your original game files remain unchanged.
- Optional **4:3 iPad camera and UI preparation** for the supported US-English
  game resources, including animated HUD anchors and nested clipping.
- **Live paired camera/HUD adaptation** in the 4:3 build for narrow landscape
  scenes (4:3 through 3:2), with safe-area anchors, touch cancellation and
  interpolation reset. Standard-match fold/unfold passed an actual Mac gameplay
  preview; physical Duo execution remains deferred. Unqualified owners and wide
  scenes use a coherent 4:3 fit; see [display support](docs/NATIVE_ASPECT.md).
- **Two local players on one device**, using independent compatible extended
  gamepads. Mixed controller models are supported by the adapter.
- The game's authored left/right vibration, routed to the correct controller.
- **DualSense adaptive triggers**: light resistance during actual shielding and
  a short impact thump when a shield blocks a hit. Effects honor each player's
  custom Guard mapping and stop on release, expiry, disconnect or backgrounding.
- Per-controller motion transport where hardware and the game support it.
- Optional background **iCloud saves**, using your own developer container.
- An optional generated-frame presentation path; gameplay simulation stays at
  60 Hz. This is not native 120 FPS rendering and is off by default for Smash.
  See [frame-rate setup and the tap-to-hide FPS corner](docs/FRAME_RATE.md).

These are implementation features, not a claim that every path has passed
physical gameplay testing. [Controller details](docs/CONTROLLERS.md) and
[iCloud setup](docs/ICLOUD.md) describe the boundaries.

## Picture, saves and updates

The default build preserves the game's **16:9 composition**. Use
`--display-aspect 4:3` for iPad and narrow Duo scenes, including the paired live
camera/HUD adapter. Keep the default 16:9 build for wide phone composition.
It prepares private copies of the exact US-English resources and keeps the
current rendering pixel budget. An installed M5 iPad Pro build renders full-screen
4:3 menus and a Kirby/Donkey Kong match on Skyworld with normal proportions and
an adjusted HUD. Other stages and modes still need layout checks. This option
does not request full display-pixel rendering. See [NATIVE_ASPECT.md](docs/NATIVE_ASPECT.md).
Stable 60/120 FPS on a particular device is not guaranteed.

Local progress lives in the app's `Documents/save` folder, accessible through
Files or Finder file sharing. Save in-game, fully close the app and back up that
folder before an update. Keep the same bundle ID and signing team. Deleting the
app removes its local container. The build tool does not install anything; the
separate signing tool installs only when you pass `--install`.
Also preserve `Documents/pso_user.tsv`, the learned pipeline recipe list used
to prepare previously encountered shaders on later launches.

Cloud sync is **off by default** and experimental for Smash. It captures completed
save commits, publishes whole verified snapshots and imports only before game
boot. Use one device at a time, wait for an acknowledged upload, then close it
before switching. See [ICLOUD.md](docs/ICLOUD.md).

## Development and reporting

The player command is `tools/smash.py`; signing uses `tools/sign_install.py`.
The source profile is `dm/games/01006A800016E000/`. Build output and a mutable
profile are created in a new private directory outside the checkout. Advanced
users can reuse their own verified extraction, rewritten modules and shader
cache; see [INPUTS.md](docs/INPUTS.md).

Run game-free source checks with:

```sh
python3 tools/check.py
```

Read [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) and
[VALIDATION.md](docs/VALIDATION.md) before changing the runtime. Existing Odyssey
helpers and tests remain as inherited regression coverage; use `smash.py` for
this game.

[Report an issue](https://github.com/NicholasDominici/super-smash-bros-ultimate-ios/issues)
with the source commit, game version, device/OS, controller model and the action
that failed. Private receipts and diagnostics help with investigation. Remove
account/device details before sharing excerpts. Never attach game files, saves,
keys, provisioning material or a game-bearing app/IPA.

## Credits and license

- [seedds/nxnative](https://github.com/seedds/nxnative): native runtime, offline
  rewriting, graphics translation and original build tools.
- [ly05010419/MacNativeGames](https://github.com/ly05010419/MacNativeGames): work
  used by nxnative; retained license and notices.
- [Super Mario Odyssey iOS](https://github.com/NicholasDominici/super-mario-odyssey-ios):
  the inherited controller, presentation, cloud and human-installation foundation.
- [smash-arc](https://github.com/jam1garner/smash-arc) and
  [ssbh_lib](https://github.com/ultimate-research/ssbh_lib): ARC format APIs and
  primary SSBH format definitions used by the targeted extraction tools.
- [KillzXGaming/EffectLibrary](https://github.com/KillzXGaming/EffectLibrary/tree/d5491138d645221ec92189eeff3ded8c43fd0a1a):
  MIT-licensed EFFN/EFT2 format layouts used by the bounded effect-shader reader.
- [Ryujinx and other dependencies](dm/third_party/README.md): shader translation,
  codecs, headers and utilities under their own licenses.

Port source is MIT; see [LICENSE](LICENSE) and [PROVENANCE.md](docs/PROVENANCE.md).
This is an unofficial fan project. Nintendo's game, content and trademarks are
not covered by the source license.

## Install it yourself

No AI assistant is required. You need an **Apple Silicon Mac**, **Xcode 27 or
newer**, an iPhone/iPad on **iOS/iPadOS 26 or newer**, your own game files and keys,
and a developer team able to provision **Increased Memory Limit and Extended
Virtual Addressing**. The development-signing path uses a paid Apple Developer
team. Free-team signing and lower-memory devices are unverified. The game's
merged archive alone is about 17.6 GB; allow substantial additional space for
input packages, extraction, shader caches, app staging and device installation.

1. **Prepare Xcode and tools.** Open Xcode, accept its license, finish component
   installation and sign in under **Xcode → Settings → Apple Accounts**. Select
   it under **Settings → Locations → Command Line Tools**. With
   [Homebrew](https://brew.sh/) installed, run:

   ```sh
   xcodebuild -downloadComponent MetalToolchain
   brew install python rust xcodegen spirv-cross zstd
   brew install --cask dotnet-sdk
   ```

   Also install the [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)
   if your default SDK is newer. The pinned translator requires the .NET 10 runtime.
   The Metal compiler and `spirv-cross` must match `dmsh_chain.lock`; a mismatch
   stops the build instead of silently changing shader fingerprints. See the
   [pinned toolchain versions](docs/INSTALL.md).

2. **Get the source and Python dependencies.** In Terminal:

   ```sh
   git clone https://github.com/NicholasDominici/super-smash-bros-ultimate-ios.git
   cd super-smash-bros-ultimate-ios
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. **Prepare your files.** Put your unmodified base-game `.nsp` or `.xci`, update
   **13.0.5 (`v2031616`) `.nsp`**, and your `prod.keys` outside the source folder.
   Unpack your own ZIP/7z/RAR containers first. The actual module hashes are
   checked; renaming a different update will not work.

   <details>
   <summary>Optional: unpack .7z or multipart RAR files</summary>

   Replace these example paths, keeping the quotes:

   ```sh
   brew install sevenzip
   7zz x "/path/to/Base.7z" -o"/path/to/Unpacked"
   7zz x "/path/to/Update.part1.rar" -o"/path/to/Unpacked"
   ```

   Keep every RAR volume together with its original filename, and extract the
   first volume once. Depending on the naming scheme, it may end in
   `.part1.rar`, `.part01.rar`, or `.rar` followed by `.r00`, `.r01`, etc.
   Use the resulting NSP/XCI paths in step 4; the builder does not accept the
   compressed archives themselves.

   </details>

4. **Build an unsigned app.** Replace the example paths and choose a bundle ID
   you control. `--work` must name a **new** directory for each build:

   ```sh
   python tools/smash.py \
     --base "$HOME/Games/Smash/Base.xci" \
     --update "$HOME/Games/Smash/Update-13.0.5.nsp" \
     --keys "$HOME/Games/Keys/prod.keys" \
     --bundle-id com.yourname.smash \
     --work "$HOME/Games/Smash-build-01" \
     --app-only \
     --allow-known-geometry-gap
   ```

   Static extraction includes the game's UI and particle-effect shader carriers.
   For an iPad, add `--display-aspect 4:3` to prepare the matching camera and
   US-English UI. Leave the flag out for the original 16:9 view. Reused rewritten
   modules are cloned before the main module is refreshed; original inputs and
   caches remain unchanged. Optional shader capture currently uses 16:9.
   Optional bounded native capture is available for diagnostics; see
   [INPUTS.md](docs/INPUTS.md). It is not required for the known registered and
   battle shader keys covered by the current static sources.
   The last flag explicitly accepts the one documented unsupported geometry
   shader. Other failed or missing shaders still stop packaging. The first build
   extracts the game, rewrites its modules and compiles shaders; detailed logs
   stay in the private work directory. This project still has the graphics and
   live-test limitations described above. The final line prints the unsigned
   app path. It contains your game files and must stay private.

5. **Prepare the device and signing capabilities.** Connect by USB, unlock it,
   trust the Mac and enable **Settings → Privacy & Security → Developer Mode**.
   Run `xcrun devicectl list devices`. In your developer account, use an explicit
   App ID matching `com.yourname.smash` with **Increased Memory Limit** and
   **Extended Virtual Addressing** enabled. [INSTALL.md](docs/INSTALL.md) explains
   profile setup and how to obtain the hardware UDID.

6. **Sign and install.** Replace the team and device identifiers:

   ```sh
   python tools/sign_install.py \
     --app "$HOME/Games/Smash-build-01/SuperSmashBrosUltimate-unsigned.app" \
     --team YOUR_TEAM_ID \
     --device YOUR_DEVICE_ID \
     --install
   ```

   Xcode obtains a development profile. The helper validates both required
   capabilities, signs a separate copy, checks its entitlements and installs it.
   If automatic provisioning fails, use an exact-app profile with `--profile`;
   see [signing help](docs/INSTALL.md). It does not delete or launch an existing app.

7. **Open and test the game.** Pair your controllers in Settings → Bluetooth.
   Test picture, sound, movement and a local match before relying on this build.
   Save and back up progress before future updates. Reuse the same bundle ID
   and signing team. Optional cloud setup is in [ICLOUD.md](docs/ICLOUD.md).

8. **Use an IPA when needed.** Omit `--app-only` in step 4 to produce a private
   unsigned IPA, then pass it to the signer with `--ipa` instead of `--app`.
   Sending an IPA by AirDrop does not install it: a development-signed build runs
   only on devices in its provisioning profile. A friend can build independently
   with their own files/account, or you can register their device and sign with
   a suitable profile. Never publish the resulting game-bearing IPA.
