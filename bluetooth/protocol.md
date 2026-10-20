# Bluetooth protocol notes — Amazfit Bip 6 (<REDACTED_MAC>)

Source: `adb bugreport` → `FS/data/log/bt/btsnoop_hci.log`, captured right
after the owner re-paired the watch with the Zepp app
(`com.huami.watch.hmwatchmanager`) on their Samsung Galaxy S24, Android 16.
Parsed with our own minimal parser (`scripts/btsnoop_parse.py`) — no
tshark/wireshark available/installed. Passive analysis only, no injection,
no decryption attempted.

## Transport — CONFIRMED

- The real companion-app connection is **Bluetooth Classic (BR/EDR)**, over
  a single ACL connection handle (`handle=2`), **not BLE/GATT**. The device
  is dual-mode and does advertise BLE (see `notes/RESEARCH.md`), but the
  official Zepp app bond/session happens over classic BT.
- `dumpsys bluetooth_manager` shows `[ DUAL ] [ACL BR/EDR:Y LE:N]
  [Encryption status(BR/EDR): EncryptionStatus{keySize=16, algorithm=2}]` —
  so the ACL link is encrypted (standard BT encryption), on top of which the
  Huami/Zepp application protocol presumably layers its own
  authentication/encryption (consistent with Gadgetbridge's documented
  "auth key" concept for this device family) — **not directly observed in
  this capture**, since the actual link-key/auth exchange happened before
  this capture window started.
- Traffic rides on what looks like RFCOMM/L2CAP channels (classic SDP
  negotiation visible early in the capture, encoding the same vendor UUIDs
  seen earlier over BLE advertising/SDP).

## Custom UUID family — CONFIRMED (seen in plaintext on the wire)

Base: `0000XXXX-0000-3512-2118-0009af100700`. Short IDs observed in this
capture:

```
00000001-0000-3512-2118-0009af100700
00000002-0000-3512-2118-0009af100700
00000004-0000-3512-2118-0009af100700
00000005-0000-3512-2118-0009af100700
00000016-0000-3512-2118-0009af100700
00000017-0000-3512-2118-0009af100700
00000022-0000-3512-2118-0009af100700   (also seen in BLE SDP, see RESEARCH.md)
00000023-0000-3512-2118-0009af100700
00000024-0000-3512-2118-0009af100700
00001531-0000-3512-2118-0009af100700
00001532-0000-3512-2118-0009af100700
```

**INFERENCE**: this reads like a private service/characteristic table (one
short ID per logical channel/feature), analogous to how a BLE GATT profile
assigns 16-bit IDs within a custom 128-bit base — just reused here over
classic RFCOMM multiplexing. Which ID maps to which feature is **UNKNOWN**
without further correlation work (e.g. matching timing of specific app
actions in the Zepp app to specific IDs appearing on the wire).

The second vendor UUID seen earlier over BLE
(`6a24eeab-4b65-4693-986b-3c26c352264f`) did **not** reappear in this
specific capture window — **UNKNOWN** whether it's BLE-only or just wasn't
exercised during this session.

## Firmware / module version manifest — CONFIRMED (plaintext on the wire)

A semicolon-separated module/version manifest was observed in cleartext:

```
FFD39-1.1.3;F653B-1.0.1.21;FFD3C-1.0.16;100446-1.0.18;106C54-2.1.1;10A78D-1.1.0;
```

This is almost certainly the per-component firmware version table Zepp OS
reports for this device (main firmware, BT/radio module, sensor hub,
bootloader, etc. — **INFERENCE** on which component is which; the IDs
themselves are opaque hex-ish codes, not self-describing).

Other bare version-looking strings seen nearby in the same traffic, not yet
correlated to a specific field: `0.135.23.0`, `4.0.17`, `4.6.0.3`, `1.0.2`.

This single capture already satisfies a good chunk of **Phase 1** (firmware
version fingerprint) without needing the watch's own Settings screen or a
Zeus CLI session.

## Feature/module name strings — CONFIRMED (plaintext on the wire)

```
agps  music  notification  sticky_notification  screenshot  voicememo
sport  httpproxy  jsapp  terminal  BT_PORT
```

Read as internal module/service identifiers used by the Huami/Zepp
protocol stack. Notable ones for our actual goals:

- `jsapp` — **STRONG EVIDENCE** this is the internal name for the Zepp OS
  Mini Program (JS) runtime — i.e. the same surface Zeus CLI/Developer
  Bridge targets. Useful confirmation that "custom Mini Program" is indeed
  the right official lever to pull for custom UI/companion features.
- `httpproxy` — **INFERENCE**: suggests the watch can route HTTP requests
  through the phone's connection. Potentially very relevant later for a
  Roadstr-style integration (watch asks phone to fetch something over
  HTTP) — worth a dedicated look once we're inside Zeus CLI/Mini Program
  development, rather than guessing from this string alone.
- `sticky_notification` — **INFERENCE**: persistent/ongoing notification
  concept (e.g. an active call or turn-by-turn instruction), relevant to
  the "Roadstr on the wrist" idea from the original brief.
- `screenshot`, `voicememo`, `music`, `sport`, `agps`, `terminal` — standard
  system app/service hooks, lower priority for our goals.

## Potentially identifying strings — NOT further shared

Two long numeric strings (serial-number/session-ID shaped) were observed in
the capture. Treated as semi-sensitive device identifiers: recorded only in
the raw capture file on disk (owner's own machine), not reproduced in this
document and not to be pasted into any issue/forum/public write-up.

## What we did NOT get

- The actual Huami/Zepp application-layer auth key/link key — the exchange
  predates this capture window. Classic BT "Link Key Notification"
  (HCI event 0x18) was not present in this capture either.
- Any BLE/GATT-side traffic — this capture only covers the classic BR/EDR
  session (handle 2).
- Decoded structure of the custom RFCOMM framing (looks like a `0x55`-led
  packet header repeated across many frames — **INFERENCE**, not yet
  confirmed as a real sync byte vs. coincidence) — would need more capture
  samples correlated with specific known UI actions to confirm.

## Reproducibility check (second capture)

Forced a controlled disconnect/reconnect via `adb shell svc bluetooth
disable`/`enable` (no app interaction) and pulled a second bugreport
(`capture2_full.txt`). Result: the opening SDP/L2CAP setup sequence, the
full UUID family, the firmware/module manifest, and all the feature-name
strings (`jsapp`, `httpproxy`, `sticky_notification`, etc.) **reappeared
essentially unchanged** — **CONFIRMED**: this is a stable
capability/status-negotiation exchange that happens automatically on every
(re)connection, not something tied to a specific user action in the Zepp
app. L2CAP channel IDs did shift between captures (e.g. `0x47/0x48` →
`0x49/0x4a`) — **CONFIRMED** these are per-session dynamic, not fixed
protocol identifiers.

Practical implication: a plain BT toggle cannot be used to isolate "which
short ID means notifications vs. weather vs. sport" — that needs a real,
specific app-level action (e.g. send one test notification) captured
against this now-known baseline, so only the *new* traffic is attributed
to that action.

## Encryption boundary (third capture — correlated notification test)

Enabled Notification Access for the Zepp app
(`com.huami.watch.hmwatchmanager/com.xiaomi.hm.health.ui.smartplay.NotificationAccessService`,
granted by the owner via Settings; confirmed present in
`secure/enabled_notification_listeners`). Posted one test notification via
`adb shell cmd notification post -S bigtext -t "Test RE" "amazfit-re-test"
"Messaggio di test..."`, then immediately pulled a third bugreport/btsnoop
capture.

Result: the literal notification text/tag/title **never appears anywhere**
in the capture (checked across all distinct printable strings, not just
near the end) — **CONFIRMED**. The connection-setup/capability-negotiation
phase stays in plaintext (same UUID family, firmware manifest, feature
names as before), but actual application payloads (e.g. the notification
being pushed to the watch) are opaque/high-entropy — **CONFIRMED**
application-layer encryption on top of the already-encrypted BT Classic
link, exactly matching Gadgetbridge's documented Huami "auth key" model:
the key encrypts/authenticates payloads but is itself never transmitted
over the air.

Practical conclusion for the jailbreak-feasibility question: passively
sniffing BT traffic will **not** by itself let us read or inject
notification-level data without the per-device Huami auth key. Getting that
key still requires either (a) extracting it from the phone-side app/account
(needs root or a cloud-account-based method we're deliberately not doing
with pasted credentials), or (b) finding an implementation weakness in the
key-exchange/derivation itself (not attempted — would require a capture of
the original bonding/key-exchange moment, which we don't have, plus active
protocol fuzzing, which is a bigger, riskier undertaking than passive
sniffing).

## Huami auth key — obtained (Zepp cloud, owner's account, owner's choice to share in-session)

Retrieved via the official Gadgetbridge-documented **browser-console method**
(no third-party script run, no password handled by us): owner signed into
`watchface.zepp.com` with their own Zepp account, ran the console snippet
from
[gadgetbridge.org's Huami/Xiaomi server pairing page](https://gadgetbridge.org/basics/pairing/huami-xiaomi-server/),
which read the session's own login cookie and queried
`https://api-mifit-us3.zepp.com/users/{userId}/devices` — returning this
device's record. Saved verbatim to `bluetooth/auth_key_device_info.json`
(gitignored via the `auth*` pattern).

This **resolves two of the previously-"uncorrelated" loose version strings**
from the BT captures:

| Cloud field | Value | Previously seen on the wire as |
|---|---|---|
| `firmwareVersion` | `4.6.0.3` | loose string `4.6.0.3` in both BT captures — **CONFIRMED** = watch firmware version |
| `additionalInfo.hardwareVersion` | `0.135.23.0` | loose string `0.135.23.0` in both BT captures — **CONFIRMED** = hardware version |
| `sn` | `<REDACTED_SERIAL>` | fragment `c<REDACTED_SERIAL>` in capture1 strings — **CONFIRMED** = device serial number (the extra leading `c` is a field-prefix byte, not part of the serial) |
| `deviceId` | `<REDACTED_DEVICE_ID>` | — | **CONFIRMED**: standard 48-bit MAC → 64-bit EUI-64 conversion of `<REDACTED_MAC>` (insert `FFFE` in the middle) |

Still **UNKNOWN**: what `1.0.2` and `4.0.17` (also seen loose in the
captures) correspond to — not present in this cloud record; likely a Zepp
app-side or sub-component version not exposed by this endpoint.

Other fields of note: `productId=155`, `productVersion=257` (opaque
model/variant identifiers, not yet decoded), `lastBindingPlatform=
android_phone`, `auth_key` is 32 hex chars = 16 bytes, consistent with an
AES-128 key — matches Gadgetbridge's documented Huami auth-key size/format.

**Caveat (per Gadgetbridge docs)**: unpairing from the Zepp app or a hard
reset on the watch invalidates this key (and changes the BT MAC on hard
reset). As long as we don't do either, this key stays valid.

## Auth handshake script — written, and the wall it hit (CONFIRMED)

Wrote `scripts/huami_auth.py`: a from-scratch implementation of the legacy
Huami auth handshake documented by Gadgetbridge for this device family
(`SEND_KEY` → `REQUEST_RANDOM` → AES-128-ECB-encrypt the 16-byte challenge
with our `auth_key` → `SEND_ENCRYPTED_RANDOM`), using Python's native Linux
`AF_BLUETOOTH`/`BTPROTO_RFCOMM` sockets (no pybluez/sdptool needed) and
pycryptodome for AES.

**Result: every one of RFCOMM channels 1–30 timed out on `connect()`** —
not an explicit rejection, a plain timeout. Suspected this was a
single-connection-slot conflict with the phone's already-active classic
bond, so retested:

- `bluetoothctl pair <REDACTED_MAC>` **with the phone's Bluetooth
  connected**: device info shows `Connected: no` / not even visible as
  `[NEW]` during a fresh scan (it may simply stop advertising while busy
  with the phone).
- `bluetoothctl pair <REDACTED_MAC>` **with the phone's Bluetooth
  switched off** (slot free, confirmed via `adb shell svc bluetooth
  disable`): device **is** discovered fresh, but pairing still fails with
  **`org.bluez.Error.AuthenticationRejected`** — identical to our very
  first attempt back when we didn't have the auth key yet.

**CONFIRMED**: this is not a connection-slot contention issue. The watch
actively refuses to bond with this Linux host regardless of transport or
whether the phone is connected. Having the correct `auth_key` did not change
this outcome, because the key is used *after* a bond/connection exists, and
we cannot get that far — **the gate is at the pairing/bonding step itself**,
before the auth_key would ever come into play.

**INFERENCE**: the watch's Bluetooth stack likely performs some
vendor-specific check during/before the standard pairing procedure that
only the official Zepp app satisfies (e.g. a specific probe/command sent
before initiating SSP, or an IO-capability/allowlist check) — we have not
identified what that is. Confirming it would need a capture of the
*official app's own* fresh pairing sequence from byte zero (we only ever
captured *reconnects* to an already-bonded phone, not the original bonding
handshake itself), which would mean deliberately unpairing again (and
re-fetching a new `auth_key` afterward, since unpairing invalidates it).

**Practical conclusion**: the auth key is confirmed real/correctly-shaped,
but exercising it against the watch from an arbitrary Linux host is blocked
upstream, at the OS-level Bluetooth bonding step. The only currently-working
path to actually *use* this key is from a host the watch already accepts —
i.e. the phone, where the classic bond already exists (would need either
Gadgetbridge or a custom Android app, not a plain Linux script).

## GROUND TRUTH — real auth protocol, from Gadgetbridge's own source code

Read directly from `ZeppOsAuthenticationService.java` (git sparse-clone of
Codeberg, not web-scraped — see `firmware/package_format.md` for why).
**This supersedes our earlier `huami_auth.py` guess** (legacy Mi Band 2/3
scheme) — Zepp OS 2021+ devices, including ours (confirmed: this class is
explicitly written to also support "btrfcomm devices", i.e. our exact BT
Classic/RFCOMM transport), use a completely different, much stronger
handshake:

**Real protocol (ENDPOINT 0x0082, commands CMD_PUB_KEY=0x04, CMD_SESSION_KEY=0x05):**

1. Phone generates an ephemeral EC keypair on a custom **163-bit binary
   curve** (`ECDH_B163` — GB's own reimplementation; private key 24 bytes,
   public key 48 bytes — not a standard JDK curve, Huami-specific).
2. Phone → watch: `0x04 0x02 0x00 0x02 || <48-byte public key>`.
3. Watch → phone: `<status> 0x04 <status2> || <16-byte random> || <48-byte watch public key>`.
4. Phone computes ECDH shared secret from its private key + the watch's
   public key.
5. `encryptedSequenceNumber` = first 4 bytes of the shared secret as uint32.
6. **Session key derivation**: `sessionAES[i] = sharedSecret[i+8] XOR authKey[i]`
   for i in 0..15 — i.e. the long-term `authKey` (ours:
   `<REDACTED_AUTH_KEY>`) is XORed byte-wise into bytes 8–23
   of the ECDH output to produce the actual 16-byte AES session key. Simple
   XOR whitening, not a real KDF (HKDF/etc.), but it does mean the session
   key depends on *both* the long-term secret *and* a fresh ECDH exchange
   each connection (forward-secrecy-ish, limits replay).
7. Phone sends back `0x05 || AES-ECB(authKey, watchRandom) || AES-ECB(sessionAES, watchRandom)`
   (33 bytes: 1 cmd + 16 + 16) — proves knowledge of *both* the raw
   authKey *and* the correctly-derived session key in one shot.
8. Watch validates and responds via CMD_SESSION_KEY: payload byte 2 ==
   `0x25` means **"wrong auth key"** (explicit, named failure code);
   anything else non-success is a generic failure; success → authenticated,
   all further traffic encrypted with `sessionAES`.

**`getSecretKey()` confirms the exact authKey format** Gadgetbridge expects
in its own prefs (key name `"authkey"`): either `0x` + 32 hex chars (34
chars total) or bare 32 hex chars — **exactly matches the format of our
cloud-obtained key** and how we entered it (`0x<REDACTED_AUTH_KEY>`).
There's a hardcoded dummy fallback key (ASCII `"0123456789@ABCDE"`) used
only if no real key is configured — just a placeholder, not a backdoor.

**Why our `huami_auth.py` was never going to work**: it implemented the
*old* (pre-2021) Huami scheme (plain `SEND_KEY`/`REQUEST_RANDOM`/
`SEND_ENCRYPTED_RANDOM` with a single AES-ECB step, no ECDH at all). Even
if the Linux bonding wall hadn't stopped us, the watch would never have
recognized that handshake. This is now a **closed, understood question**
rather than an open one — no need to keep guessing at the legacy scheme
for this device generation.

## Next step for this angle

Capture a **fresh, full HCI snoop** (if "full" mode can be made to stick —
UI toggle is currently reverting to `empty` for the global setting, under
investigation) while performing one specific, known Zepp-app action at a
time (e.g. "send a test notification", "open weather", "start workout") so
each short ID / `0x55`-framed message can be correlated to a concrete
action instead of being reverse-guessed from a mixed capture.
