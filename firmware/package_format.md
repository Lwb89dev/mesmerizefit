# Zepp OS / Huami firmware & app package format — from Gadgetbridge source

Source: `ZeppOsFwHelper.java` and `HuamiFirmwareType.java`, read directly
from Gadgetbridge's own Codeberg repo (sparse git clone, not web-scraped —
Codeberg serves deliberately garbled HTML to scrapers/AI agents, but the
git wire protocol itself is unaffected). Local copy:
`scripts/tools/gb-src/app/src/main/java/nodomain/freeyourgadget/gadgetbridge/devices/huami/zeppos/ZeppOsFwHelper.java`
and `.../service/devices/huami/HuamiFirmwareType.java`.

This is **CONFIRMED** (read straight from a maintained, tested open-source
implementation), not inferred from captures.

## Confirmed: our device in GB's own source

`AmazfitBip6Coordinator.java` (`devices/huami/zeppos/watches/`) lists
`getDeviceSources()` = `{9765120, 9765121, 10158337}` — **10158337 is
exactly our device's `deviceSource`**, confirmed independently via the
Zepp cloud API response earlier. It extends `ZeppOsCoordinator` — i.e. our
watch uses the **generic, shared Zepp OS protocol**, not anything
Bip6-specific. `supportsGpxUploads=true`, `supportsControlCenter=true`,
`supportsToDoList=true`, `supportsBluetoothPhoneCalls=true` are declared
directly in this class, matching what we found live via GB's device
capability screen.

## Package container formats Gadgetbridge recognizes

A file handed to the installer is detected by **magic header bytes**,
then parsed as one of:

### 1. Plain ZIP (`PK\x03\x04`) — most common, three sub-cases tried in order:

**a) Firmware** — ZIP containing one of (tried in order):
   - `META/firmware.bin`
   - `META/firmware_sign.bin`
   - `firmware.bin` (root)
   
   Plus optionally `META/fw_info` — a JSON file:
   ```json
   { "fw_info": [ { "name": "firmware", "version": "4.6.0.3", ... }, ... ] }
   ```
   If `fw_info` is absent, the version is instead read **directly from the
   firmware.bin binary itself**: a version string starting at **byte
   offset 10**, ASCII digits and dots only, terminated by a null byte or
   any non-digit/non-dot character (so firmware.bin has *some* kind of
   fixed-offset header in its first ~10 bytes, then a plaintext version
   string — matches what we found in the BT capture: `4.6.0.3` appeared
   as a bare ASCII string in cleartext traffic).

   **Validation performed by the app (not the watch!):**
   `isCompatibleFirmwareBin()` just searches the firmware.bin byte stream
   for the device's Bluetooth name (e.g. `"Amazfit Bip 6\0"`, null
   terminated) anywhere in the file. **That's it — no signature or hash
   check at the app layer.** Any real cryptographic signature
   verification, if it exists, must happen on the watch's own side
   (bootloader/recovery), which we have not observed — **UNKNOWN** whether
   it exists or how strict it is. This is the single most important open
   question for jailbreak feasibility.

**b) Watchface / App** — ZIP containing `app.json`:
   ```json
   { "app": { "appId": <int>, "appName": "...", "version": {"name": "..."},
              "appType": "watchface" | "app", "vender": "...", "icon": "assets/..." } }
   ```
   `appType` determines `HuamiFirmwareType.WATCHFACE` or `.APP`. Icon can
   be PNG or **TGA** format (`BitmapUtil.decodeTga`). This is the format
   our own custom Mini Programs (via Zeus CLI) would ultimately produce —
   confirms Zeus-built apps and this installer target the *same* package
   shape.

**c) ZAB bundle** — ZIP containing `manifest.json`:
   ```json
   { "zpks": [ { "name": "...", "platforms": [ {"deviceSource": 10158337, ...}, ... ] }, ... ] }
   ```
   A single `.zab` can bundle variants for multiple device models; GB
   picks the first `zpk` entry whose `platforms[].deviceSource` matches
   the connected device (confirmed: matches on our exact `10158337`).
   Each matched `zpk` is itself a zip containing `device.zip`, which is
   then recursively parsed as a firmware/watchface/app zip again.

### 2. UIHH container (own 4-byte magic, `UIHHContainer.UIHH_HEADER`)

Used mainly for **AGPS** updates and some firmware bundles. Contains
typed file entries:
- `FIRMWARE_ZIP` + `FIRMWARE_CHANGELOG` together → treated as
  `FIRMWARE_UIHH_2021_ZIP_WITH_CHANGELOG` (older MB7-style firmware
  packaging — the firmware.bin inside is extracted from
  `META/firmware.bin` inside the embedded zip, same compatibility check
  as above).
- `AGPS_EPO_GR_3`, `AGPS_EPO_GAL_7`, `AGPS_EPO_BDS_3` (GLONASS/Galileo/
  BeiDou ephemeris data) — all three present together → `AGPS_UIHH`.

## On-wire "file type" byte codes (`HuamiFirmwareType`)

Single-byte codes sent in the install protocol to tell the watch what
kind of payload follows: `FIRMWARE=0`, `FONT=1`, `RES=2`,
`RES_COMPRESSED=130(0x82)`, `GPS=3`, `GPS_CEP=4`, `GPS_ALMANAC=5`,
`WATCHFACE=8`, `APP=8` (same byte as watchface — disambiguated elsewhere),
`FONT_LATIN=11`, `ZEPPOS_UNKNOWN_0x13=0x13`, `ZEPPOS_APP=0xa0`,
`AGPS_UIHH=0xfc`(-4), `FIRMWARE_UIHH_2021_ZIP_WITH_CHANGELOG=0xfd`(-3).
Worth cross-referencing against the raw bytes in our earlier BT captures
later.

## What this does NOT tell us

- Whether the **watch itself** cryptographically verifies firmware
  signatures before accepting/booting a new image (the app-side check is
  trivially weak — just a substring search for the device name). This is
  the real crux of jailbreak feasibility and isn't visible from app code;
  it lives in the watch's own bootloader/recovery firmware, which we don't
  have yet.
- The internal structure of `firmware.bin` itself beyond "ASCII version
  string at offset 10" (compression? per-component sub-images? the
  `FFD39-1.1.3;F653B-...` module manifest we found on the wire suggests
  *multiple* named sub-components, possibly packed together or OTA'd
  separately).
