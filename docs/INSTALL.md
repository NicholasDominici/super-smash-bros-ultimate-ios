# Signing and installation

Start with the numbered instructions at the bottom of README.md. The builder
produces an unsigned private app or IPA; `tools/sign_install.py` signs a separate
copy and installs only when given `--install`. Neither helper deletes or
launches an installed app.

The visible app title is **Super Smash Bros. Ultimate**, including spaces.
Both CFBundleDisplayName and CFBundleName use that title; the internal executable
remains DmIOS. A private `.app` or `.ipa` filename is independent of that title.
Review [release readiness](RELEASE_READINESS.md) for accepted iPad behavior and
the remaining compatibility, cloud and multiplayer gates.

For a staged app:

```sh
python tools/sign_install.py --app /private/Smash-unsigned.app \
  --team YOUR_TEAM_ID --device YOUR_DEVICE_ID --install
```

For an IPA, use `--ipa /private/Smash-unsigned.ipa` instead. The development
profile must allow the exact bundle ID, the intended device and both capabilities:

- [Increased Memory Limit](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.increased-memory-limit)
- [Extended Virtual Addressing](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.developer.kernel.extended-virtual-addressing)

The currently checked shader toolchain uses **Xcode 27.1 (27A9275)** and
**spirv-cross 1.4.363.0**, with the bundled pinned translator. The lock checks
actual binary/compiler fingerprints. A different release may require a
contributor to rebuild and validate the shader chain; changing the lock alone
does not establish compatibility.

Smash reserves a large sparse virtual address range. Extended Virtual Addressing
permits that address layout; it does not allocate that much physical RAM or
make a low-memory device sufficient. Increased Debugging Memory Limit is a
separate entitlement and is not used by this project.

The helper reads the compiled app's `NativeBuild.plist`, validates its bundle,
CloudKit and addressing requirements against the profile, signs the executable,
checks the resulting signature and compares the actual entitlements. A successful
signature check is not a gameplay/memory-performance result.

## Profile setup

Automatic provisioning uses the Apple account already signed into Xcode.
If it fails:

1. In Xcode → Settings → Apple Accounts, select the intended developer team and
   ensure it has a development certificate with its private key on this Mac.
2. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list),
   create/select an explicit App ID matching the builder's `--bundle-id`.
3. Enable **Increased Memory Limit** and **Extended Virtual Addressing**. For
   optional cloud saves, also enable iCloud → CloudKit and associate your own
   container; see ICLOUD.md.
4. Register the device's **hardware UDID**. `xcrun devicectl list devices` can
   show a CoreDevice identifier; `xcrun devicectl device info details --device
   DEVICE_ID` or Xcode's device details shows the hardware UDID. The helper can
   resolve a reachable CoreDevice identifier for automatic provisioning.
5. Create an **iOS App Development** profile for that exact App ID, your
   certificate and the registered devices. Download it outside the checkout.
6. Sign with the profile:

   ```sh
   python tools/sign_install.py --app /private/Smash-unsigned.app \
     --profile /private/Smash.mobileprovision \
     --device YOUR_HARDWARE_UDID --install
   ```

Profiles with a wildcard bundle, missing capabilities, wrong device, expiry or
incompatible cloud environment are rejected. Keep provisioning files,
certificates, receipts and signed apps private.

## Updating and storage

Save in-game, fully close Smash and back up its `Documents/save` folder before
installing a replacement. Keep the same bundle ID and developer team. Deleting
the app removes its local save container. Do not uninstall it as an installation
troubleshooting shortcut.

Use USB for the large first transfer and keep the device unlocked. A staged
`--app-only` build uses APFS clones where supported and avoids an IPA pack/extract
round trip; another volume/filesystem may require full resource copies. The
signer also clones a separate app before signing. Its default output name ends
in `-signed.app` or `-signed.ipa`; an existing output is not overwritten.

## Common problems

| Problem | Action |
| --- | --- |
| Missing .NET 10 | Install the .NET 10 SDK/runtime; a newer runtime alone does not run the pinned translator. |
| Tool-chain fingerprint mismatch | Use the pinned Metal/spirv-cross/translator toolchain; do not update the lock merely to bypass a failed check. |
| Shader failure or incomplete manifest | Read the private shader log and `*-shader-completeness.json`; only the exact documented geometry exception can be allowed. |
| Capture receipt/fingerprint mismatch | Preserve the old evidence and make a new capture from unchanged inputs/source; do not edit a receipt to bypass the check. |
| Wrong module hash | Supply the unmodified base plus update 13.0.5, or a complete matching merged extraction. |
| Missing signing capability | Enable both memory/addressing capabilities on the explicit App ID and regenerate its profile. |
| Device not allowed or unreachable | Register the hardware UDID, trust the Mac, enable Developer Mode, unlock and keep it nearby. |
| Work/output already exists | Choose a new build/output path; preserve backups and existing builds. |
| Graphics missing or app exits | Check VALIDATION.md and private `log.txt`; this bring-up has unresolved graphics and live-test gaps. |

Apple documents [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)
and [registered-device installation](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices).

## A friend's iPhone

A development-signed IPA runs only on devices allowed by its profile. Register
the friend's device, obtain a matching development profile and sign again, or
let the friend build with their own game files and developer account. Sending
an IPA by AirDrop does not install it. Builds expire with their signing profile
and must be renewed. This helper does not implement ad hoc/App Store distribution;
do not publish game-bearing apps, IPAs or signing material.
