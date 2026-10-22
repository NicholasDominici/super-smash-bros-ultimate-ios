#!/usr/bin/env python3
"""Sign a locally built private IPA and optionally install it on a registered device."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import ctypes
import errno
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from odyssey_assets import outside_repo

REPO = Path(__file__).resolve().parents[1]
MEMORY = 'com.apple.developer.kernel.increased-memory-limit'
EXTENDED_VA = 'com.apple.developer.kernel.extended-virtual-addressing'
CLOUD_IDS = 'com.apple.developer.icloud-container-identifiers'
CLOUD_ENV = 'com.apple.developer.icloud-container-environment'


def validate_profile(profile: dict, bundle: str, device: str | None, cloud: str, extended_va: bool = False) -> dict:
    """Require an unexpired exact-app development profile and required capabilities."""
    expiration = profile['ExpirationDate'].replace(tzinfo=datetime.timezone.utc)
    if expiration <= datetime.datetime.now(datetime.timezone.utc):
        raise ValueError('Provisioning profile has expired')
    allowed = profile['Entitlements']
    team = profile['TeamIdentifier'][0]
    if allowed.get('application-identifier') != team + '.' + bundle:
        raise ValueError('Provisioning profile must match this exact bundle ID')
    if not allowed.get('get-task-allow'):
        raise ValueError('This helper supports development signing. See docs/INSTALL.md for distribution differences.')
    if device and device not in profile.get('ProvisionedDevices', []):
        raise ValueError('This device is not registered in the provisioning profile')
    if allowed.get(MEMORY) is not True:
        raise ValueError('Profile lacks Increased Memory Limit; enable that capability in your developer account.')
    entitlements = {'application-identifier': team + '.' + bundle, 'get-task-allow': True,
                    'com.apple.developer.team-identifier': team, MEMORY: True}
    if extended_va:
        if allowed.get(EXTENDED_VA) is not True:
            raise ValueError('Profile lacks Extended Virtual Addressing; enable that capability for this app.')
        entitlements[EXTENDED_VA] = True
    if cloud:
        environment = allowed.get(CLOUD_ENV, [])
        services = allowed.get('com.apple.developer.icloud-services', [])
        if cloud not in allowed.get(CLOUD_IDS, []) or 'Development' not in environment or ('CloudKit' not in services and services != '*'):
            raise ValueError('Profile does not allow this CloudKit container in Development')
        entitlements.update({CLOUD_IDS: [cloud], CLOUD_ENV: 'Development', 'com.apple.developer.icloud-services': ['CloudKit']})
    return entitlements


def provision(work: Path, team: str, bundle: str, device: str | None, cloud: str, extended_va: bool = False) -> Path:
    """Let Xcode obtain a development profile using the builder's signed-in account."""
    if not re.fullmatch(r'[A-Z0-9]{10}', team):
        raise ValueError('--team must be your 10-character Apple developer Team ID')
    project = work / 'provision'
    project.mkdir()
    (project / 'main.m').write_text('#import <UIKit/UIKit.h>\nint main(int argc,char **argv){ @autoreleasepool{return UIApplicationMain(argc,argv,nil,nil);} }\n')
    entitlements = {MEMORY: True}
    if extended_va: entitlements[EXTENDED_VA] = True
    if cloud:
        entitlements.update({CLOUD_IDS: [cloud], CLOUD_ENV: 'Development', 'com.apple.developer.icloud-services': ['CloudKit']})
    (project / 'App.entitlements').write_bytes(plistlib.dumps(entitlements))
    # JSON is a valid YAML document, avoiding shell/YAML interpolation of user input.
    spec = {'name': 'NativeSigning', 'targets': {'NativeSigning': {
        'type': 'application', 'platform': 'iOS', 'deploymentTarget': '26.0', 'sources': ['main.m'],
        'settings': {'PRODUCT_BUNDLE_IDENTIFIER': bundle, 'DEVELOPMENT_TEAM': team, 'CODE_SIGN_STYLE': 'Automatic',
                     'CODE_SIGN_ENTITLEMENTS': 'App.entitlements', 'GENERATE_INFOPLIST_FILE': 'YES',
                     'TARGETED_DEVICE_FAMILY': '1,2', 'INFOPLIST_KEY_UILaunchScreen_Generation': 'YES'}}}}
    (project / 'project.yml').write_text(json.dumps(spec, indent=2))
    subprocess.run(['xcodegen', 'generate', '--quiet'], cwd=project, check=True)
    command = ['xcodebuild', '-project', 'NativeSigning.xcodeproj', '-scheme', 'NativeSigning',
               '-configuration', 'Release', '-destination', 'id=' + device if device else 'generic/platform=iOS',
               '-derivedDataPath', str(project / 'Derived'), '-allowProvisioningUpdates']
    if device:
        command.append('-allowProvisioningDeviceRegistration')
    command.append('build')
    log = project / 'provision.log'
    with log.open('w') as handle:
        result = subprocess.run(command, cwd=project, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f'Xcode could not provision the app. Sign in in Xcode Settings > Apple Accounts and check {log}. See docs/INSTALL.md.')
    return project / 'Derived/Build/Products/Release-iphoneos/NativeSigning.app/embedded.mobileprovision'


def check_ipa(path: Path) -> None:
    """Accept only a single regular local app tree, with no unsafe archive entries."""
    with zipfile.ZipFile(path) as archive:
        names = set()
        for entry in archive.infolist():
            parts = Path(entry.filename).parts
            if entry.filename in names or not parts or parts[0] != 'Payload' or '..' in parts or Path(entry.filename).is_absolute():
                raise ValueError('Invalid or duplicate IPA path')
            names.add(entry.filename)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError('IPA contains a symlink; only this builder\'s regular app bundles are supported')
        roots = {Path(name).parts[1] for name in names if len(Path(name).parts) > 1}
        if roots != {'DmIOS.app'}:
            raise ValueError('Expected one Payload/DmIOS.app from tools/odyssey.py')


def resolve_device(identifier: str, work: Path) -> str:
    """Resolve either a CoreDevice identifier or UDID to the hardware UDID."""
    if re.fullmatch(r'[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}|[0-9A-Fa-f]{40}', identifier):
        return identifier.upper()
    result = work / 'device-details.json'
    subprocess.run(['xcrun', 'devicectl', 'device', 'info', 'details', '--device', identifier,
                    '--json-output', str(result), '--timeout', '45'], check=True, stdout=subprocess.DEVNULL)
    data = json.loads(result.read_text())
    udid = data.get('result', {}).get('hardwareProperties', {}).get('udid')
    if not udid:
        raise ValueError('Device details did not contain a hardware UDID. Unlock/trust the device and retry.')
    return udid


def check_app(path: Path) -> None:
    """Require a regular app tree and an executable contained in its root."""
    if path.is_symlink() or not path.is_dir() or path.suffix != '.app':
        raise ValueError('Choose a regular .app directory')
    for current, directories, files in os.walk(path, followlinks=False):
        for name in directories + files:
            item = Path(current) / name
            mode = item.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError('App contains a symlink or special file: ' + str(item))
    info = plistlib.loads((path / 'Info.plist').read_bytes())
    executable = info.get('CFBundleExecutable', '')
    if not isinstance(executable, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', executable) or executable in ('.', '..'):
        raise ValueError('App executable must be a regular filename within the bundle')
    if not (path / executable).is_file():
        raise ValueError('App executable is missing')


def clone_app(source: Path, destination: Path) -> None:
    """Stage a private app with APFS file clones when the volume supports them."""
    clonefile = ctypes.CDLL(None, use_errno=True).clonefile
    def copy(source_file, destination_file):
        if clonefile(os.fsencode(source_file), os.fsencode(destination_file), 0):
            code = ctypes.get_errno()
            if code not in (errno.EXDEV, errno.ENOTSUP, errno.EINVAL):
                raise OSError(code, os.strerror(code), destination_file)
            return shutil.copy2(source_file, destination_file)
        shutil.copystat(source_file, destination_file)
        return destination_file
    shutil.copytree(source, destination, copy_function=copy)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--ipa', type=Path, help='unsigned IPA produced locally by this project')
    source.add_argument('--app', type=Path, help='unsigned app directory; avoids making and extracting a large IPA')
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('--team', help='your Apple developer Team ID; Xcode obtains a development profile')
    identity.add_argument('--profile', type=Path, help='existing exact-bundle development mobileprovision')
    parser.add_argument('--device', help='UDID from xcrun devicectl list devices; required for --install')
    parser.add_argument('--install', action='store_true', help='install the signed app on --device; does not launch or delete it')
    parser.add_argument('--output', type=Path, help='signed private IPA output')
    args = parser.parse_args(argv)
    if args.install and not args.device:
        raise ValueError('--install requires --device')
    input_path = outside_repo(args.app or args.ipa, REPO)
    suffix = '-signed.app' if args.app else '-signed.ipa'
    output = outside_repo(args.output or input_path.with_name(input_path.stem.replace('-unsigned', '') + suffix), REPO)
    if output == input_path or output.is_relative_to(input_path) or output.exists():
        raise ValueError('Choose a new signed output path; inputs and existing files are never replaced')
    if args.app: check_app(input_path)
    else: check_ipa(input_path)
    work = Path(tempfile.mkdtemp(prefix='native-signing-', dir=input_path.parent))
    print(f'Private signing work: {work}')
    device = resolve_device(args.device, work) if args.device else None
    app = work / 'Payload/DmIOS.app'
    if args.app:
        app.parent.mkdir()
        clone_app(input_path, app)
    else:
        subprocess.run(['ditto', '-x', '-k', str(input_path), str(work)], check=True)
    check_app(app)
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    bundle = info['CFBundleIdentifier']
    metadata = app / 'NativeBuild.plist'
    if not metadata.is_file(): metadata = app / 'OdysseyBuild.plist'  # inherited builder compatibility
    settings = plistlib.loads(metadata.read_bytes())
    if settings['BundleIdentifier'] != bundle:
        raise ValueError('Build metadata and app bundle ID disagree')
    cloud = settings.get('CloudContainer', '')
    extended_va = settings.get('RequiresExtendedVirtualAddressing', False)
    if not isinstance(extended_va, bool): raise ValueError('Invalid extended-addressing build metadata')
    profile_path = outside_repo(args.profile, REPO) if args.profile else provision(work, args.team, bundle, device, cloud, extended_va)
    profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(profile_path)], stderr=subprocess.DEVNULL))
    entitlements = validate_profile(profile, bundle, device, cloud, extended_va)
    identities = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
    certificate = next((hashlib.sha1(cert).hexdigest().upper() for cert in profile['DeveloperCertificates']
                        if hashlib.sha1(cert).hexdigest().upper() in identities), None)
    if not certificate:
        raise ValueError('No matching signing certificate with private key is available in this Mac\'s Keychain')
    shutil.copy2(profile_path, app / 'embedded.mobileprovision')
    entitlement_path = work / 'signing.entitlements'
    entitlement_path.write_bytes(plistlib.dumps(entitlements))
    executable = app / info['CFBundleExecutable']
    executable.chmod(executable.stat().st_mode | 0o111)
    subprocess.run(['codesign', '--force', '--sign', certificate, '--timestamp=none', '--generate-entitlement-der',
                    '--entitlements', str(entitlement_path), str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    actual = plistlib.loads(subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(app)], stderr=subprocess.DEVNULL))
    if actual != entitlements:
        raise ValueError('Signed entitlements do not match the requested capabilities')
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.app:
        shutil.move(str(app), str(output))
        app = output
    else:
        subprocess.run([sys.executable, str(REPO / 'dm/ios/tools/pack_ipa.py'), str(output), '--store',
                        '.arc:.aras:.bfsar:.bfstm:.mp4:.szs:.metallib', 'Payload/DmIOS.app=' + str(app)], check=True)
    receipt = {'bundle_id': bundle, 'cloud_container': cloud, 'cloud_environment': 'Development' if cloud else None,
               'signed_app' if args.app else 'signed_ipa': str(output), 'expiration': profile['ExpirationDate'].isoformat(),
               'signature_verified': True, 'installed': False}
    if args.install:
        subprocess.run(['xcrun', 'devicectl', 'device', 'install', 'app', '--device', device, str(app), '--timeout', '1800'], check=True)
        receipt['installed'] = True
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Signed {"app" if args.app else "IPA"}: {output}\nSigning receipt: {work / "receipt.json"}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'Signing stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
