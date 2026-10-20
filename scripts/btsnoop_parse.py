#!/usr/bin/env python3
"""
Minimal read-only BTSnoop (v1, H4-framed) parser.

Goal: find HCI events/ACL data related to a specific BT address (our own
Amazfit Bip 6) inside an adb-bugreport-extracted btsnoop_hci.log, without
needing tshark/wireshark. Read-only, no packet injection, no decryption
attempted — this is passive analysis of our own capture file.

Usage:
    python3 btsnoop_parse.py <btsnoop_hci.log> <TARGET_BDADDR like AA:BB:CC:DD:EE:FF>
"""
import struct
import sys

H4_CMD, H4_ACL, H4_SCO, H4_EVT = 1, 2, 3, 4

EVT_NAMES = {
    0x03: "Connection Complete",
    0x05: "Disconnection Complete",
    0x08: "Encryption Change",
    0x0B: "Read Remote Supported Features Complete",
    0x0C: "Read Remote Version Information Complete",
    0x16: "PIN Code Request",
    0x18: "Link Key Notification",
    0x3E: "LE Meta Event",
}


def parse_btaddr(b: bytes) -> str:
    # BD_ADDR is little-endian over the air (reverse order)
    return ":".join(f"{x:02X}" for x in reversed(b))


def read_records(path):
    with open(path, "rb") as f:
        magic = f.read(8)
        assert magic == b"btsnoop\x00", f"bad magic: {magic!r}"
        version, datalink = struct.unpack(">II", f.read(8))
        print(f"[*] btsnoop version={version} datalink_type={datalink}")
        while True:
            hdr = f.read(24)
            if len(hdr) < 24:
                break
            orig_len, incl_len, flags, drops, ts = struct.unpack(">IIIIq", hdr)
            data = f.read(incl_len)
            yield orig_len, incl_len, flags, drops, ts, data


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path, target = sys.argv[1], sys.argv[2].upper()

    handles_of_interest = set()
    n_total = 0
    n_relevant = 0

    for orig_len, incl_len, flags, drops, ts, data in read_records(path):
        n_total += 1
        if not data:
            continue
        pkt_type = data[0]
        body = data[1:]

        if pkt_type == H4_EVT and len(body) >= 2:
            code = body[0]
            plen = body[1]
            params = body[2:2 + plen]
            name = EVT_NAMES.get(code, f"0x{code:02X}")

            if code == 0x03 and len(params) >= 10:  # Connection Complete
                status = params[0]
                handle = struct.unpack("<H", params[1:3])[0]
                addr = parse_btaddr(params[3:9])
                if addr == target:
                    handles_of_interest.add(handle)
                    n_relevant += 1
                    print(f"[EVT] {name}: status={status} handle={handle} addr={addr} <== TARGET")
                elif status == 0:
                    print(f"[evt] {name}: handle={handle} addr={addr}")

            elif code == 0x05 and len(params) >= 3:  # Disconnection complete
                handle = struct.unpack("<H", params[1:3])[0]
                if handle in handles_of_interest:
                    n_relevant += 1
                    print(f"[EVT] {name}: handle={handle} reason=0x{params[3] if len(params)>3 else -1:02x} <== TARGET")

            elif code == 0x08 and len(params) >= 4:  # Encryption change
                handle = struct.unpack("<H", params[1:3])[0]
                if handle in handles_of_interest:
                    n_relevant += 1
                    print(f"[EVT] {name}: handle={handle} enabled={params[3]} <== TARGET")

            elif code == 0x16 and len(params) >= 6:  # PIN code request
                addr = parse_btaddr(params[0:6])
                if addr == target:
                    n_relevant += 1
                    print(f"[EVT] {name}: addr={addr} <== TARGET")

            elif code == 0x18 and len(params) >= 23:  # Link key notification
                addr = parse_btaddr(params[0:6])
                if addr == target:
                    n_relevant += 1
                    key_type = params[22]
                    print(f"[EVT] {name}: addr={addr} key_type={key_type} "
                          f"(link key bytes withheld from stdout; see --show-key) <== TARGET")

            elif code == 0x3E and len(params) >= 2:
                subcode = params[0]
                if subcode in (0x01,):  # LE Connection Complete
                    if len(params) >= 19:
                        handle = struct.unpack("<H", params[2:4])[0]
                        addr = parse_btaddr(params[5:11])
                        if addr == target:
                            handles_of_interest.add(handle)
                            n_relevant += 1
                            print(f"[EVT] LE Connection Complete: handle={handle} addr={addr} <== TARGET")

        elif pkt_type == H4_ACL and len(body) >= 4:
            handle_flags = struct.unpack("<H", body[0:2])[0]
            handle = handle_flags & 0x0FFF
            if handle in handles_of_interest:
                n_relevant += 1
                payload = body[4:]
                printable = "".join(chr(b) if 32 <= b < 127 else "." for b in payload)
                print(f"[ACL] handle={handle} len={len(payload)} hex={payload[:48].hex()} ascii={printable[:48]!r}")

    print(f"\n[*] Total records: {n_total}, relevant to {target}: {n_relevant}")
    print(f"[*] Connection handles seen for target: {sorted(handles_of_interest)}")


if __name__ == "__main__":
    main()
