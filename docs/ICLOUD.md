# Optional iCloud saves

Cloud sync is **off by default**. The inherited coordinator uploads whole,
verified completed save snapshots quietly and imports remote progress only
before game boot. Local saves remain available without CloudKit setup.
**A real Smash save upload and two-device handoff have not yet been verified.**
Do not infer them from the Odyssey port's earlier tests or from successful signing.

## Your own container

1. Use a bundle ID you control, such as `com.yourname.smash`, under your own
   developer team. Keep that bundle/team identity across devices and updates.
2. In your Apple Developer account, enable iCloud → CloudKit on that explicit
   App ID and associate your own container, such as `iCloud.com.yourname.smash`.
   Keep both required memory/addressing capabilities enabled too.
3. Add the same container option when building each device's app:

   ```sh
   python tools/smash.py --base /private/Smash/Base.xci \
     --update /private/Smash/Update-13.0.5.nsp --keys /private/Keys/prod.keys \
     --bundle-id com.yourname.smash --cloud-container iCloud.com.yourname.smash \
     --work /private/Smash-cloud-build-01 --app-only \
     --allow-known-geometry-gap
   ```

   The container is written only to the private generated profile. The public
   source profile stays cloud-disabled.
4. Sign with `tools/sign_install.py`. Its exact-app development profile must
   permit that container, CloudKit, the **Development** environment, both required
   capabilities and the device. Use `--profile` if automatic provisioning fails.
5. Sign both devices into the same iCloud account. Back up their local save
   folders before testing. Start the device with current progress, save in-game
   and leave it running with a connection until `Documents/iCloudSync/status.json`
   acknowledges the local digest. Then fully close it before opening the other.
6. Verify the second device imports the same digest before boot and loads the
   expected progress. Test the return direction separately. A queued upload or
   an installed CloudKit entitlement does not establish delivery.

The private database uses record type **GameSave**, record name
`01006A800016E000-save-format-1`, and fields `payload` (Asset), `digest` (String),
`device` (String), and `updated` (Date/Time). Development CloudKit can create the
schema during testing. Use [CloudKit Console](https://icloud.developer.apple.com/)
to inspect your own private development database; public sharing is not required.

## Consistency and conflicts

The source preserves complete-commit capture, SHA-256 integrity verification,
account pinning, compare-and-swap cloud writes, conflict backups and explicit
conflict choices. A cloud restore never overwrites a mounted live save.
The Smash profile requires `save_data/system_data.bin` before publishing a
progress snapshot; the path comes from the original executable. A disposable
Mac match produced the real five-file save set, which the production archive
codec captured and restored with an identical digest. Completed-save upload,
account/network behavior and physical-device handoffs remain unverified.

Play on one device at a time. Save, wait for acknowledgement, close it, then
switch. iOS controls background execution and networking; an immediate force-close
can interrupt an outstanding upload. Different iCloud accounts have separate
private saves. Account changes do not silently publish old-account progress to
another account. Divergent changes require an explicit conflict choice, with
alternatives backed up. Offline local play does not require cloud delivery.

The signing helper uses Development. Production is separate and requires a
matching distribution flow and [deployed schema](https://developer.apple.com/documentation/cloudkit/deploying-an-icloud-container-s-schema).
Changing an entitlement does not move existing cloud records between environments.
Cloud unit/transport tests do not replace provisioning, account, network,
background/retry, real save capture and bidirectional physical-device tests.
