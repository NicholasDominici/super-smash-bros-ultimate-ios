# Claude project guide

Read [AGENTS.md](AGENTS.md) first. This is the experimental Smash Ultimate iOS
port, targeting title `01006A800016E000`, update 13.0.5. Installation must remain
usable by humans without an AI assistant.

Start with README.md and docs/{INPUTS,INSTALL,CONTROLLERS,ICLOUD,VALIDATION,PROVENANCE}.md.
The player command is `tools/smash.py`; signing uses `tools/sign_install.py`.
The profile is `dm/games/01006A800016E000/`. Shared runtime/rewriting lives in
`dm/`; inherited Odyssey helpers and exact-build gates remain for regression
coverage, not as Smash gameplay semantics.

The human builder extracts SSBH databases, nested UI shader archives and
EFFN/EFT2 effect-shader carriers. All three static source classes are required;
runtime capture is optional verification, not a substitute for missing effects.
Keep extraction census/hash checks, manifest receipts and full platform shader
validation intact. Registration does not establish drawn/executed coverage.

Keep game inputs, generated game code/shaders, build/signing output, keys,
profiles, saves and private logs outside the checkout and Git history. The
builder creates a fresh external mutable profile. Cloud stays off by default
and uses the builder's own container. Preserve both required memory/addressing
capabilities, all exact-build/expected-word guards, per-player lifecycle leases,
save integrity and preboot-only restore rules.

The optional native shader capture must use a fresh external producer and
disposable save/temp paths, an owned bounded process group, exact-build inputs
and before/after byte fingerprints. Preserve its frozen producer profile and
header separately from final shader tables. Rehash actual inputs and intrinsic
control/code keys when reusing a receipt; never certify old captures using a
later rebuilt host. Capture receipts are local audit evidence, not signatures.
Fresh captures request program-registration input capture as well as draw-time
capture. Distinguish that requested census from validated dump completeness,
and keep deferred/unregistered program coverage explicit. Registration-mode
receipts must bind the complete reconciled registration-census.jsonl; do not
accept a missing ledger, unresolved stages or altered ledger bytes.

Run `python3 tools/check.py` and `python3 tools/audit_repo.py`. A zero shader-tool
exit status is insufficient: validate complete manifests and per-key platform
artifacts. Only the exact documented geometry failure has an explicit opt-in
exception. Never hide other missing shaders. Record unresolved runtime keys
and physical-device gaps separately from static build coverage.

Keep numbered human installation instructions at the very bottom of README.md.
Verify every documented flag against the actual helper. Do not claim a compile,
unit test, telemetry command or CI pass proves picture, multiplayer, controller
feel, sustained performance or real Smash cloud-save delivery.
