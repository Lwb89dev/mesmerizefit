# Amazfit Bip 6 (A2435 / Pamir) — Research Log

Owner-authorized security research / jailbreak feasibility investigation on a
personally owned device. Non-destructive, reversible investigation only.
See `SAFETY.md` for the ground rules before any flashing/patching work.

## Gadgetbridge notification/navigation configuration (owner's goal: strip the
watch down to a minimal companion)

Configured on the Samsung S24 bridge phone (persists in Gadgetbridge's own
settings, survives this session ending):

- **Notification whitelist mode**: switched from blacklist to
  **"Permetti le notifiche dalle applicazioni selezionate"** (allow-list).
- **Apps enabled for watch notifications**: Telegram
  (`org.telegram.messenger`), Google Messages
  (`com.google.android.apps.messaging`), Samsung Messages
  (`com.samsung.android.messaging`), Roadstr production
  (`app.roadstr` — NOT `app.roadstr.roadtest`, left unchecked).
- **Media controls**: "Lista app ignorate per notifiche media" enabled, so
  media controls work for any media app without needing to whitelist each
  one individually.
- **Navigation bridge**: Gadgetbridge has a *native* "send navigation to
  watch" feature (`Impostazioni → Integrazioni Esterne → App di
  navigazione`), already enabled, but its supported-app list is hardcoded
  to **OsmAnd(+), Google Maps, CoMaps only** — Roadstr is not in it.
  **CONFIRMED**: Roadstr turn-by-turn will reach the watch only via the
  regular notification whitelist (already enabled above), as a normal
  notification, not the compact distance/turn display OsmAnd gets. True
  native integration would need either Roadstr mimicking OsmAnd's public
  broadcast API, or a custom Gadgetbridge build — neither attempted.
- **WhatsApp / Signal**: **not installed** on this bridge phone (by
  design — it's a dedicated bridge device, not the owner's daily phone).
  Not configured. Owner's own call to make how these reach the bridge
  phone (e.g. installing + linking as companion devices) — out of scope
  for this session per the owner's explicit boundary (Pixel 10 kept away
  from this agent on purpose).

## Zepp app full Java decompilation (jadx)

`zepp_base.apk` (184MB) fully decompiled with jadx 1.5.3 → **59,392 Java
files**, 364MB, 197 classes failed to decompile cleanly (normal for an app
this size/obfuscated — doesn't block searching the rest). Location:
`zepp-apps/decompiled/`. Not yet searched in depth beyond what the native
library pass covered — available for targeted `grep`/review in a future
session (e.g. OTA download endpoints, firmware signature logic if any
exists app-side, `HMCoreService`/`OtaService` implementation details).

## Native library analysis of the Zepp Android app (arm64 .so files)

Pulled both APKs (`base.apk` + `split_config.arm64_v8a.apk`) via adb,
treated as untrusted downloaded data (own directory, analysis tools kept
separate). No system binutils available (strings/objdump/nm/readelf all
missing) — installed `pyelftools` + `capstone` in the existing Python venv
instead (pure-Python ELF parsing/disassembly, no system packages needed).
Script: `scripts/analyze_so.py`.

Checked 4 native libraries initially guessed as protocol-relevant by name:

- **`libiwds.so` — REAL FIND.** This is Huami's "Uniconnect"/`IwdsRuntime`
  native connection layer (IWDS = likely "I Wear Device Service"). Exported
  symbols confirm: `handshake`/`nativeHandshake`, `bondAddress`/
  `unbondAddress` (→ `LinkManager::bond()`/`Link::bond()`),
  `createConnectionByUuid`/`createConnectionByPort`, `getMaxPayloadSize`,
  classes `Connection`/`ConnectionManager`/`Link`/`LinkManager`/`Package`.
  **Important: bonding is implemented via standard Android Bluetooth APIs**
  (`BluetoothDevice.createRfcommSocketToServiceRecord`,
  `BluetoothAdapter.listenUsingRfcommWithServiceRecord`, called via JNI
  reflection) — **no evidence of a custom pre-bonding "magic packet" or
  proprietary unlock step** on the app side. **INFERENCE**: our earlier
  `AuthenticationRejected` from the Linux host is more likely an SSP/IO-
  capability/agent configuration mismatch between BlueZ and whatever
  Android's stack does by default, than a deliberate host-allowlist in the
  watch's firmware — worth retrying from Linux later with a properly
  configured pairing agent, now deprioritized in favor of the firmware
  track.
- `libJhmSignal.so` — **not protocol-related**: Huami's ECG/heart-rate
  signal processing algorithm library (`com.huami.algo.jhmsignal.JhmSignal`,
  `AF_judge_ecg`, `getHRVRmssd`, etc.). Initial name-based guess was wrong.
- `libxmd.so` — **not protocol-related**: Xiaomi AI assistant channel
  (`com.xiaomi.ai.core.XMDChannel`, protobuf `AIPacket`/`BindRequest`/
  `BindResponse`) — XiaoAI voice assistant integration, unrelated to the
  watch link.
- `libuptsmaddon.so` — **not protocol-related** despite the "upt" in its
  name: generic TLS/X.509 certificate library (exported strings are
  standard LDAP/X.509 OID names like `id-it-caKeyUpdateInfo`,
  `pilotAttributeType`) — likely mbedTLS or similar, used for the app's
  HTTPS networking, nothing OTA-specific.

## MAJOR FINDING — Gadgetbridge declares `supportsFlashing = true` for this device

Via `Debug → Dispositivi → Amazfit Bip 6-F663` in Gadgetbridge, found its
full internal `DeviceCoordinator` capability model (hundreds of
`supportsXXX` booleans). GB's internal device type for this watch:
**`AMAZFITBIP6`** — the exact Java class name in GB's open-source codebase
that implements support for it. This is a high-value lead: GB's source
(freeyourgadget/Gadgetbridge on Codeberg/GitHub) is a maintained, tested
reference implementation — reading its `AmazfitBip6*`/`Huami*` support
classes tells us the *real* RFCOMM channel, auth handshake details, and
firmware update flow, instead of guessing from raw captures.

Key capabilities confirmed **ON** for this device:
- **`supportsFlashing = true`** — **CONFIRMED, highest priority lead**. GB
  has a built-in firmware/file flashing capability for this exact device.
  This is the natural entry point for Phase 7 (firmware acquisition) and
  beyond — corresponds to the "Installer file" option seen in the device
  card's long-press/overflow menu.
- `supportsDebugLogs`, `supportsFindDevice`, `supportsScreenshots` (can
  screenshot the watch's own screen — useful diagnostic tool),
  `supportsGpxUploads` (relevant to offline-route-on-watch idea),
  `supportsDataFetching`, `supportsNavigation` (already used),
  `supportsBluetoothPhoneCalls`, `supportsAppListFetching`.

Key capabilities confirmed **OFF** (reinforces earlier findings):
- `supportsAppsManagement`, `supportsAppReordering`,
  `supportsInstalledAppManagement`, `supportsCachedAppManagement`,
  `supportsWatchfaceManagement`, `supportsPowerOff` — GB cannot
  manage/remove/reorder on-watch apps or watchfaces for this device, and
  can't remote power-off either. Consistent with "no app-list feature"
  finding from the settings UI sweep.

**Checked "Installer file" (read-only — no file selected, nothing flashed).**
Gadgetbridge's own in-app text confirms:

- It's a generic multi-type installer: **firmware, watchface, app, GPS/GPX,
  resources, fonts**.
- Gadgetbridge does **not** bundle/distribute firmware files itself (legal
  reasons) — "dovrai procurarteli da solo" (source it yourself: APK
  extraction, forums, community watchface/firmware sites).
- In-app warning: flashing "può mandare in tilt il tuo dispositivo" (brick
  risk) but "non è mai successo a nessuno degli sviluppatori" (no known
  dev bricks) — reassuring, not a guarantee.
- Official docs (gadgetbridge.org/internals/features/installer/): generic
  across device types, no AmazfitBip6-specific documentation exists yet
  (newer device). For older Amazfit/Huami devices, custom watchfaces are
  uploaded the same way as firmware and **can't be deleted via GB, only
  overwritten** — stock watchfaces always remain. Not confirmed whether
  this applies identically to the Bip6.

**This is as far as Phase 7 preparation goes without an actual firmware
file in hand.** Getting one requires legitimate sourcing (official Zepp
OTA capture, APK extraction, or a reputable community archive — verify
SHA256, preserve original, never redistribute) — not completed this
session. Actually using the installer on anything (even a stock firmware
re-flash, let alone a modified one) needs the full `SAFETY.md` checklist
(format identified, recovery path, validation model understood, stock
image preserved, rollback documented) plus explicit per-action approval —
not something to rush through before a phone handoff.

## What was explicitly NOT done: on-device app removal

The owner's full goal is to **remove/strip fitness apps directly on the
watch itself** (not just hide them from a companion app) and fully cut the
watch off from Huami/Zepp's servers. Status:

- Communication with Huami/Zepp's servers: **already effectively cut**,
  since the Zepp app is disabled and Gadgetbridge (open-source, talks to
  no vendor cloud) is the only active companion.
- Actually removing/hiding fitness apps **from the watch's own launcher**:
  **not done, not currently possible with what we have**. Gadgetbridge
  exposes no app-list/launcher-customization feature for this device (its
  full device-specific settings list was enumerated — no such option
  exists). This would require genuine on-device/firmware-level access —
  the true jailbreak path (Phase 10/11 territory from the original brief),
  which has NOT been attempted this session: no firmware dump, no code
  execution on the watch's own SoC, no root of either phone. Real brick
  risk category, needs its own explicit go-ahead and safety process per
  `SAFETY.md`.

## Current status

Phase 1 (device identification) and Phase 2 (charging cradle) partially
started. Working purely from the Linux workstation's own Bluetooth adapter so
far — no phone (Pixel 10) connected to this machine yet, no Zeus CLI / Zepp
Developer Bridge session yet.

## Correction to initial brief

- The phone actually used for pairing is a **Samsung Galaxy S24 (SM-S921B)**,
  Android 16 (SDK 36), not the Pixel 10 assumed in the original brief —
  **CONFIRMED** via `adb shell getprop ro.product.model` after the owner
  connected and authorized it.
- The Bip 6 bonds over **Bluetooth Classic (BR/EDR)**, not BLE — **CONFIRMED**
  via `adb shell dumpsys bluetooth_manager` showing
  `[ DUAL ] [ACL BR/EDR:Y LE:N] [Encryption status(BR/EDR):
  EncryptionStatus{keySize=16, algorithm=2}]` for the bonded device. This
  explains why plain BLE SMP pairing attempts from the Linux host got
  `AuthenticationRejected` earlier: wrong transport entirely, not (only) a
  missing proprietary key. The device is dual-mode and advertises BLE, but
  the real companion-app bond is classic BT.
- Companion app package: **`com.huami.watch.hmwatchmanager`** — **CONFIRMED**
  (`adb shell pm list packages`).
- BR/EDR-side UUID set for the bonded device matches what we saw over BLE
  SDP: `00000022-0000-3512-2118-0009af100700`, `HSP`, `AudioSource`, `Avrcp`,
  `Handsfree`, `6a24eeab-4b65-4693-986b-3c26c352264f` — same vendor UUIDs,
  now confirmed present on the classic side too.

## Hardware facts

- **Model**: Amazfit Bip 6, model number A2435, codename "Pamir" (per user-supplied
  info / public teardown research referenced in the brief). — **UNKNOWN (not
  independently verified by us yet)**, carried over as given.
- **BLE identity observed from Linux host**:
  - Name: `Amazfit Bip 6`
  - MAC: `<REDACTED_MAC>` (public address)
  - RSSI at capture time: -54 dBm
  - Advertised UUID: `0000fee0-0000-1000-8000-00805f9b34fb` ("Anhui Huami
    Information Technology Co." base UUID — the standard Huami/Zepp
    proprietary service) — **CONFIRMED** (directly observed via `bluetoothctl`).
  - ManufacturerData.Key: `0x0157`
  - ManufacturerData.Value (hex): `02 ff ff ff ff ff ff ff ff ff ff ff ff ff
    ff ff ff 03 d8 80 3c cb f6 63` (trailing 6 bytes match the device MAC,
    consistent with Huami's advertising packet convention of embedding the
    MAC in manufacturer data) — **CONFIRMED** (observed), interpretation of
    the leading `ff` padding / `02`/`03` sub-fields — **UNKNOWN**.
  - Paired/Bonded/Trusted/Connected (from this Linux host): all `no`.
- USB: no new USB device enumerates on this workstation from the watch itself
  (expected — Bip 6 uses BLE only, no USB data per public docs). Charging
  cradle not yet physically tested against this workstation's USB ports —
  **Phase 2 not yet executed**, see "Next experiment".

## Software facts

- **Firmware/module version manifest — CONFIRMED**, recovered in plaintext
  from a live BT Classic capture (see `bluetooth/protocol.md` for full
  detail): `FFD39-1.1.3; F653B-1.0.1.21; FFD3C-1.0.16; 100446-1.0.18;
  106C54-2.1.1; 10A78D-1.1.0`. Component-to-ID mapping is **UNKNOWN**
  (opaque codes).
- Still not collected: Zepp OS version string / API_LEVEL as such, Zepp app
  version, installed Mini Programs list, free storage, region, OTA
  availability. These still require either the watch's own Settings > About
  screen, a Zepp app session, or Zeus CLI/Developer Bridge.

## Bluetooth Classic capture (adb bugreport → btsnoop)

See `bluetooth/protocol.md` for full detail. Headline findings:

- Real companion session is BT Classic (BR/EDR), handle 2, encrypted link.
- Custom UUID family `0000XXXX-0000-3512-2118-0009af100700` with 11 short
  IDs seen in plaintext (likely one per logical feature channel).
- Firmware/module version manifest recovered in plaintext (see above).
- Feature/module name strings recovered in plaintext, including `jsapp`
  (**STRONG EVIDENCE** = the Mini Program JS runtime, i.e. Zeus CLI's
  actual target) and `httpproxy` (**INFERENCE** — watch can proxy HTTP via
  phone; relevant to a future Roadstr-style integration).
- Did *not* capture the actual Huami app-layer auth key or the classic Link
  Key (exchange predates the capture window).

## BLE protocol

- Phone was disconnected (Bluetooth off) and the watch was unlinked from the
  Zepp account/app by the owner, to rule out a single-central-connection
  conflict as the cause of earlier connect failures.
- Plain `bluetoothctl connect` / `bleak` GATT connect still **times out**
  (tried with 10s and 30s connect timeouts) even with the phone fully out of
  the picture — **CONFIRMED**: this is not a "phone is holding the slot"
  issue. The device simply does not complete GATT service resolution for an
  unauthenticated link.
- Explicit `bluetoothctl pair <REDACTED_MAC>` (standard BLE SMP bonding)
  result: **`org.bluez.Error.AuthenticationRejected`** — **CONFIRMED**. The
  watch actively rejects generic/standard BLE bonding from a host it doesn't
  recognize. This is consistent with Huami/Zepp's documented proprietary
  auth scheme (an app-level auth key tied to the Zepp cloud account, not
  standard BT Secure Simple Pairing) gating the connection — **STRONG
  EVIDENCE** this is why plain connect/bonding stalls/fails, pending direct
  confirmation once we have a real auth key to test with.
- Full UUID list observed on this device (via SDP leak during the failed
  pair attempt — likely a window where the controller answers basic
  discovery/SDP before the proprietary auth gate kicks in):
  - `00001131` Headset HS, `00001108` Headset, `00001203` Generic Audio,
    `0000111e` Handsfree, `0000110c`/`0000110f`/`0000110e` AVRCP
    Target/Controller/base, `0000110a` Audio Source, `00001200` PnP Info,
    `00001000` SDP server — **CONFIRMED present in SDP response**, but
    **INFERENCE** that these are inert boilerplate from the chipset vendor's
    shared BT stack/SDK rather than features actually implemented by this
    watch (classic for budget wearables that reuse a common SoC BT
    profile table). Needs verification, not safety-relevant either way.
  - `00000022-0000-3512-2118-0009af100700` — vendor-specific 128-bit UUID,
    non-standard base. **UNKNOWN** which vendor/subsystem this belongs to;
    flagged for a web lookup, not guessed.
  - `6a24eeab-4b65-4693-986b-3c26c352264f` — vendor-specific 128-bit UUID,
    fully custom (not a Huami-base variant). **INFERENCE**: likely candidate
    for the actual Zepp OS GATT service (separate from the legacy
    `0000fee0` Mi Band/Huami service, which may be kept only for
    legacy identification/compatibility). Not yet verified.
  - `0000fee0-0000-1000-8000-00805f9b34fb` "Anhui Huami Information
    Technology Co." — **CONFIRMED**, the classic Huami/Zepp proprietary
    service, matches Gadgetbridge's documented identification method for
    this device family.
- No characteristic-level enumeration obtained yet — GATT service resolution
  never completes without the proprietary auth handshake.

## Developer mode findings

- User reports Developer Mode has been enabled on the watch (Zepp OS side)
  and the PC's own Bluetooth is on. Zeus CLI is not yet installed on this
  workstation. No Developer Bridge session established yet.

## Firmware format / Boot chain / Recovery / Security boundaries

- Not yet investigated. Needs either an official OTA capture or Zeus/Zepp
  app session first. **UNKNOWN.**

## Potential vulnerabilities

- None identified yet. Too early in the investigation (still in Phase 1/2).

## Huami auth key — obtained via Zepp cloud (owner's account)

Owner retrieved the device's auth key via the official Gadgetbridge-
documented browser-console method against `watchface.zepp.com` /
`api-mifit-us3.zepp.com` (no third-party script, no password handled by
us). Saved to `bluetooth/auth_key_device_info.json` (gitignored). This
resolved two previously-unidentified version strings from the BT captures
(`4.6.0.3` = firmware version, `0.135.23.0` = hardware version) — see
`bluetooth/protocol.md` for the full correlation table. 16-byte key,
AES-128-sized, matches Gadgetbridge's documented format.

Caveat: unpairing from Zepp app or a watch hard-reset invalidates this key.

## MILESTONE — Gadgetbridge connected successfully (owner-driven)

Owner installed Gadgetbridge, we disabled the Zepp app
(`pm disable-user com.huami.watch.hmwatchmanager` — reversible, not
uninstalled) to stop it racing Gadgetbridge for the classic BT connection
(it had auto-restarted after a plain force-stop and was winning the RFCOMM
connect race every time). Owner then entered our cloud-obtained `auth_key`
(`0x<REDACTED_AUTH_KEY>`) in Gadgetbridge's pairing flow.

**Result — CONFIRMED, cross-checked via screenshot + `dumpsys
bluetooth_manager`:** Gadgetbridge shows "Amazfit Bip 6-F663 — Connesso",
battery 79%, full control icon row (settings, sync, watchface, alarm,
signal, activity, find-watch, heart rate). `dumpsys bluetooth_manager`
confirms `[ACL BR/EDR:Y LE:Y]`, both transports encrypted
(`EncryptionStatus{keySize=16, algorithm=2}` on both). LE-side UUIDs only
now visible post-auth: standard `BATTERY` and `Hogp` (HID-over-GATT)
services.

**This is the practical payoff of the whole "risky path"**: we now have a
fully working, open-source, non-vendor control channel to the watch,
independent of the Zepp cloud/app, built entirely from owner-authorized,
mostly-reversible steps (cloud auth key via the owner's own account,
Gadgetbridge is a normal reversible app install, Zepp app is disabled not
removed). Directly serves the original goal: minimalist phone-companion
watch, no mandatory vendor app/cloud.

Note: earlier in this process we learned **toggling the phone's Bluetooth
off/on drops this device's bond entirely** (`BOND_BONDED → BOND_NONE`) —
avoid using that as a "nudge" for this specific device; let Gadgetbridge
manage reconnects itself instead.

## Auth handshake script hit a confirmed wall (see bluetooth/protocol.md)

Wrote and ran `scripts/huami_auth.py` (legacy Huami AES-ECB challenge-
response, native Linux RFCOMM sockets). All 30 tried RFCOMM channels
timed out. Retested `bluetoothctl pair` with the phone's BT both on and
off — **`AuthenticationRejected` in both cases**, ruling out a
connection-slot conflict. **CONFIRMED**: this Linux host cannot bond with
the watch at all, regardless of transport; the gate is at the
pairing/bonding step itself, before the auth_key would ever be used.
**INFERENCE**: some vendor-specific check during pairing that only the
official Zepp app satisfies — not identified. The only currently-viable
way to actually exercise the auth key is from a host the watch already
trusts (the phone), e.g. via Gadgetbridge — not from this Linux PC alone.

## Encryption boundary — CONFIRMED (third capture, correlated notification test)

Granted Notification Access to the Zepp app, posted one uniquely-worded test
notification via `adb shell cmd notification post`, captured immediately
after. The notification's literal text/title/tag **never appears anywhere**
in the capture. Connection-setup/capability-negotiation stays in plaintext
(same UUID family/firmware manifest/feature names as before); actual
application payloads are opaque — **CONFIRMED** app-layer encryption on top
of the BT Classic link encryption, matching Gadgetbridge's documented Huami
auth-key model (key used to encrypt/authenticate, never transmitted). See
`bluetooth/protocol.md` for full detail.

**This closes out the productive part of the passive-sniffing angle**:
further raw BLE/BT research would need either the auth key itself (phone
root / cloud account method — both bigger asks) or active protocol
fuzzing (bigger, riskier undertaking), not just more passive captures.

## Next experiment (safest next step)

1. **Phase 2 cradle test** — still not done; low priority now that BLE is
   the clearly richer channel.
2. **Fork in the road, resolved**: the raw-BLE path (Gadgetbridge-style) is
   now blocked on obtaining Huami's proprietary auth key, which legitimately
   only comes from an official Zepp-app pairing + extracting it from the
   phone side (app storage / account backend) — itself a bigger lift (needs
   phone ADB access, possibly app-data extraction).
   Recommendation: pivot to **Phase 3 — Zeus CLI / Developer Bridge**, since
   it directly serves the actual end goal (custom Mini Programs, custom
   watchface, notification bridge, GPS) without needing to defeat the BLE
   auth wall at all. Zeus CLI v1.9.3 is already installed
   (`~/.npm-global/bin`, added to PATH via `.bashrc`).
3. Zeus CLI / Developer Bridge needs: Zepp app re-paired with the watch,
   Developer Mode enabled in the Zepp app, phone and this workstation on the
   same network (Developer Bridge pairs via QR/local network, not raw BLE
   from this host).

## Risk level

**Zero/near-zero** for everything done so far (passive advertisement read,
one failed connection attempt, directory setup). No writes, no pairing
secrets stored, no firmware touched.

---

## WHAT WE LEARNED
- The watch is alive, advertising, and identifies itself with the expected
  Huami/Zepp service UUID, plus a second, fully custom 128-bit vendor UUID
  that is likely the real Zepp OS service.
- The watch actively rejects standard BLE bonding/pairing from a host it
  doesn't recognize, even with zero phone/app interference. This is a real
  security gate, not a side effect of our setup.

## WHAT IS CONFIRMED
- BLE advertising identity (name, MAC, service UUID, manufacturer data).
- `org.bluez.Error.AuthenticationRejected` on plain SMP pairing — the device
  itself refuses, independent of phone connection state.
- Full classic+vendor UUID list via SDP leak during the failed pair.

## WHAT IS STILL UNKNOWN
- Firmware version, Zepp OS version, API level, installed system apps
  (still needs a Zepp app session or watch Settings screen).
- What the two vendor-specific UUIDs (`00000022-...af100700` and
  `6a24eeab-...`) actually are/do.
- Whether the audio-profile UUIDs (Headset/AVRCP/etc.) are functional or
  inert chipset-vendor boilerplate.
- Cradle USB behavior with the real cradle hardware (Phase 2 not run yet).

## WHAT THE NEXT SAFEST EXPERIMENT IS
Pivot to Zeus CLI + Zepp Developer Bridge (official channel) rather than
continuing to fight the BLE auth wall — see "Next experiment" above.
(Superseded by the jailbreak deep-dive below — Gadgetbridge ended up
working, and the investigation moved to firmware/protocol RE.)

## Zepp firmware-update check — done safely, zero risk realized

With the owner's explicit go-ahead, re-enabled Zepp once more specifically
to check for a firmware update (separate from the earlier notification
test). Sequence:

1. Logcat watch set up for OTA/firmware/crash keywords before touching
   anything (first filter too broad/noisy — re-scoped mid-stream).
2. `pm enable com.huami.watch.hmwatchmanager` — Gadgetbridge's connection
   stayed up throughout this time (`ZeppOsConnectionService` ping/pong
   keepalive kept firing) — Zepp did **not** auto-grab the connection
   (unlike the earlier race in this session).
3. Opened the Zepp app UI, navigated Dispositivo → BIP 6 → GENERALI →
   **AGGIORNAMENTO DI SISTEMA**.
4. Result: **"La versione corrente è la più recente." Numero versione
   corrente: 4.6.0.3** — **CONFIRMED**, exactly as predicted from earlier
   web research. No download offered, nothing to intercept. EFEMERIDE
   (AGPS) also already "I più recenti".
5. Deliberately avoided the "DISATTIVA DISPOSITIVO" / "DISSOCIA" buttons
   on the same screen (would invalidate the auth key / break pairing).
6. Cleaned up immediately: force-stopped + `pm disable-user`'d Zepp again,
   verified Gadgetbridge's BT Classic+LE connection to the watch was still
   fully intact and encrypted afterward.

**Net result**: no firmware to capture right now (we're already on the
latest), experiment run and fully reverted with zero side effects. The
real OTA-capture opportunity remains Phase 6-style (HCI snoop active
*before* a genuinely new firmware version rolls out) — a waiting game for
a future session, not forceable today.

## Pixel 10 cache check — also closed out, cleanly

Owner mentioned they'd updated the watch to 4.6.0.3 earlier today via the
Zepp app on their main phone (Pixel 10, GrapheneOS), raising the
possibility of a still-cached OTA download there.

- Owner explicitly extended narrow, scoped access to the Pixel for this
  one check (connected via USB/adb, previously kept away from this
  session on purpose for privacy). Checked **only**
  `/sdcard/Android/data/com.huami.watch.hmwatchmanager/` (external storage,
  no root needed) — **CONFIRMED empty** (same as the Samsung bridge phone
  earlier). The temp download almost certainly lives in the app's
  *internal* cache (`/data/data/.../cache/`, matching the pattern
  Gadgetbridge's own `ZeppOsFwHelper` uses via `context.getCacheDir()`),
  which needs root to read.
- Considered temporary (non-persistent) root via `fastboot boot` of a
  Magisk-patched boot image — would **not** have touched the installed
  system, fully reversible by design. **Blocked twice over**:
  1. Claude Code's own safety classifier refused even the read-only
     `fastboot getvar unlocked` check (category: "Irreversible Local
     Destruction") — did not attempt to route around it.
  2. Owner checked the bootloader screen directly on-device (no computer
     involved): **`Device state: locked`** — GrapheneOS's recommended
     secure post-install configuration (bootloader re-locked with the
     user's own AVB key). Unlocking it again would **wipe the device**,
     which the owner explicitly ruled out.
- **Conclusion**: this path is closed, cleanly, with zero risk taken and
  zero changes made to either phone. No firmware recovered. The only
  remaining avenue for an actual firmware binary is still the Phase
  6-style live OTA capture, timed to a genuinely future new release.

## Zepp app reverse engineering — native libs + full decompile

- **Native libs (arm64 .so)** pulled from the installed APK, analyzed with
  `pyelftools`/`capstone` (installed in the project venv — no system
  binutils available). `libiwds.so` = Huami's "Uniconnect"/`IwdsRuntime`
  native connection layer: confirmed `handshake`, `bondAddress`/
  `unbondAddress`, `createConnectionByUuid`, `getMaxPayloadSize`. Bonding
  is implemented via **standard Android Bluetooth APIs**
  (`createRfcommSocketToServiceRecord`/`listenUsingRfcommWithServiceRecord`
  via JNI) — no evidence of a secret pre-bonding step. `libJhmSignal.so`
  (ECG/HR algorithms), `libxmd.so` (Xiaomi AI assistant channel), and
  `libuptsmaddon.so` (generic TLS/X.509 library) all turned out unrelated
  to the watch protocol despite name-based initial guesses.
- **Full Java decompile** of `zepp_base.apk` via jadx 1.5.3: 59,392 files,
  364MB, in `zepp-apps/decompiled/` — available for deeper targeted search
  in a future session, not yet exhaustively reviewed.
- **Gadgetbridge's own open-source code** (git sparse-clone of Codeberg —
  their web pages are deliberately garbled against scrapers, but the git
  protocol itself works fine) gave full ground truth on:
  - **Firmware/app/watchface package format** — see
    `firmware/package_format.md`. ZIP-based, `META/firmware.bin` +
    `META/fw_info` JSON, app-layer validation is just a device-name
    substring search (weak) — real signature verification, if any, is
    watch-side only and still unknown.
  - **Real auth protocol** — see the "GROUND TRUTH" section in
    `bluetooth/protocol.md`. ECDH on NIST B-163 (public, standard curve,
    not proprietary) + AES session key derivation, superseding our earlier
    legacy-protocol guess entirely.
