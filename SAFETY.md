# Safety rules for this investigation

This is owner-authorized security research on a personally owned Amazfit
Bip 6 (A2435 / "Pamir"). Goal: understand how far the device can be
customized via official APIs, and only then evaluate deeper jailbreak
options — never destructive-first.

## Hard rules (do not violate without explicit, per-action approval)

1. Do **not** flash, erase, overwrite, downgrade, or modify firmware,
   bootloader, recovery, partitions, or persistent storage without first:
   - identifying the exact format/target,
   - confirming a known-good recovery/rollback path exists,
   - understanding how firmware validation works,
   - having an original stock image preserved,
   - getting explicit, per-action approval from the owner.
2. Do **not** inject voltage into unknown PCB test pads, assume a pad's
   voltage, or attach a programmer before measuring logic levels.
3. Do **not** disable signature verification "just to experiment."
4. Do **not** run broad/unscoped BLE scans that passively collect data on
   third-party devices (neighbors' phones, earbuds, etc.) — BLE investigation
   stays scoped to the owner's own known device (`<REDACTED_MAC>`,
   "Amazfit Bip 6") wherever possible.
5. Never commit auth keys, tokens, or other credentials to git. See
   `.gitignore` in this directory.
6. Never redistribute proprietary firmware or leaked credentials.
7. Prefer official/public channels (Zepp Developer Mode, Zeus CLI, Developer
   Bridge, Gadgetbridge's open-source protocol implementation) over guessing.
8. Classify every conclusion in notes as CONFIRMED / STRONG EVIDENCE /
   INFERENCE / UNKNOWN. Never state an inference as fact.
9. Opening the case (hardware phase) requires explicit approval and a
   warning that it will likely void water resistance.

## Current approval state

- ✅ Non-destructive software/BLE investigation: approved (standing).
- ❌ Any firmware flashing/patching: NOT approved yet — needs a specific,
  later go-ahead once Phase 7–9 (firmware acquisition + validation model) are
  understood.
- ❌ Opening the case / hardware probing: NOT approved yet.
