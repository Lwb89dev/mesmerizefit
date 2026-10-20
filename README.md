# mesmerizefit

Owner-authorized reverse-engineering research on a personally owned
**Amazfit Bip 6** (model A2435, codename *Pamir*, Zepp OS), aimed at
turning it into a minimal, privacy-respecting phone companion — no
mandatory vendor app, no vendor cloud — while documenting how far that
goes without needing a true firmware jailbreak.

This is a research log, not a finished tool. See [`SAFETY.md`](SAFETY.md)
for the ground rules this investigation follows (non-destructive first,
explicit approval before anything that could brick the device, no
credentials or proprietary binaries ever committed).

## What's actually in here

- **[`notes/RESEARCH.md`](notes/RESEARCH.md)** — the full investigation
  log, phase by phase: device identification, Bluetooth protocol mapping,
  Gadgetbridge integration, firmware/jailbreak feasibility findings.
- **[`bluetooth/protocol.md`](bluetooth/protocol.md)** — the Zepp OS
  Bluetooth protocol as actually observed and as implemented in
  Gadgetbridge's own open-source code: transport, custom GATT/RFCOMM
  service UUIDs, and the real authentication handshake (ECDH on the
  NIST B-163 curve + AES session key derivation).
- **[`firmware/package_format.md`](firmware/package_format.md)** — the
  firmware/watchface/app package format (ZIP-based, `META/firmware.bin`,
  `.zab`/`.zpk` bundling, UIHH/AGPS containers), read directly from
  Gadgetbridge's parser source.
- **[`scripts/`](scripts/)** — the small, original tools written for this
  research:
  - `btsnoop_parse.py` — minimal pure-Python BTSnoop (HCI capture) parser,
    no Wireshark/tshark required.
  - `ble_enumerate.py` — read-only BLE GATT service/characteristic
    enumeration via [bleak](https://github.com/hbldh/bleak).
  - `huami_auth.py` — from-scratch implementation of the legacy
    Huami AES-ECB challenge/response handshake, for reference (superseded
    by the real ECDH-based protocol documented in `protocol.md`).
  - `analyze_so.py` — lightweight ELF symbol/string extraction for native
    library analysis (via `pyelftools`, no system binutils needed).
- **[`zepp-apps/native-libs/analysis/`](zepp-apps/native-libs/analysis/)**
  — exported-symbol and string listings extracted from the official Zepp
  app's native libraries, used to identify which library actually
  implements the device connection layer.

## What's deliberately *not* in here

Per `SAFETY.md` and basic hygiene for a public repo:

- No auth keys, device MAC addresses, serial numbers, or other
  credentials — redacted from every committed file.
- No screenshots, bug reports, or raw Bluetooth captures (owner's own
  phone/device data).
- No proprietary Huami/Zepp APKs, decompiled app source, or extracted
  native binaries — only our own derived notes about them.
- No firmware images. None have been obtained yet; see `RESEARCH.md` for
  why, and what the plan is for getting one legitimately.

## Current state, short version

- A working, open-source companion setup exists today:
  [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge) talking
  directly to the watch, authenticated with a key obtained legitimately
  from the owner's own Zepp account, with the vendor app disabled (not
  talking to Huami's servers anymore).
- The real Bluetooth protocol (transport, custom service UUIDs,
  authentication handshake) is documented from verified source, not
  guesswork.
- A true on-device jailbreak (removing/hiding system apps from the
  watch's own firmware) has **not** been achieved — Gadgetbridge exposes
  no such capability for this device, and no firmware image has been
  obtained yet to study further. That remains the open frontier.

## License

Not yet decided — treat this as "all rights reserved, for now" unless a
`LICENSE` file says otherwise. The referenced third-party projects
(Gadgetbridge, bleak, pyelftools, capstone) keep their own licenses.
