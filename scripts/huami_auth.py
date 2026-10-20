#!/usr/bin/env python3
"""
Huami/Zepp classic-BT (RFCOMM) authentication handshake attempt, against our
own, owner-authorized Amazfit Bip 6 (Pamir), using the auth_key legitimately
retrieved from the owner's own Zepp cloud account (see
bluetooth/auth_key_device_info.json).

This replicates the LEGACY Huami auth handshake documented for older
Mi Band / Amazfit devices (Gadgetbridge's "request random auth number"
scheme, AES-128-ECB):

    phone -> watch : 0x01 || 16-byte auth_key               ("SEND_KEY")
    watch -> phone : ack
    phone -> watch : 0x02                                   ("REQUEST_RANDOM")
    watch -> phone : 0x10 || 0x02 || 0x01 || 16-byte random_number
    phone -> watch : 0x03 || AES-ECB-encrypt(auth_key, random_number)
                                                              ("SEND_ENCRYPTED_RANDOM")
    watch -> phone : 0x10 || 0x03 || 0x01   (success)  or  ...|| 0x04 (fail)

IMPORTANT: this is read-only/non-destructive with respect to the watch's
firmware/filesystem — worst case is a failed/rejected connection. We are NOT
flashing, erasing or downgrading anything. If this device's actual Zepp OS
generation uses a different/newer handshake, we expect a clean failure
(timeout / malformed response / explicit rejection), which is itself useful
data — this script is written to report exactly what happens at each step,
not to guess silently.

Usage:
    python3 huami_auth.py <MAC> <AUTH_KEY_HEX> [--channels 1-30]
"""
import argparse
import binascii
import socket
import struct
import sys
import time

try:
    from Crypto.Cipher import AES  # pycryptodome
except ImportError:
    AES = None


CMD_SEND_KEY = 0x01
CMD_REQUEST_RANDOM = 0x02
CMD_SEND_ENCRYPTED_RANDOM = 0x03

RESP_HEADER = 0x10


def aes_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    if AES is not None:
        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(data)
    # Minimal pure-python AES-ECB fallback (single block, 16 bytes) so this
    # script works even without pycryptodome installed.
    return _aes128_ecb_encrypt_block_pure(key, data)


# --- tiny pure-python AES-128 single-block ECB encryptor (fallback only) ---
# Standard FIPS-197 AES-128. Used only if pycryptodome isn't installed.
_SBOX = None


def _init_sbox():
    global _SBOX
    if _SBOX is not None:
        return
    p = q = 1
    sbox = [0] * 256
    for _ in range(255):
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        xf = q ^ ((q << 1 | q >> 7) & 0xFF) ^ ((q << 2 | q >> 6) & 0xFF) ^ \
            ((q << 3 | q >> 5) & 0xFF) ^ ((q << 4 | q >> 4) & 0xFF)
        sbox[p] = (xf ^ 0x63) & 0xFF
    sbox[0] = 0x63
    _SBOX = sbox


def _aes128_ecb_encrypt_block_pure(key: bytes, block: bytes) -> bytes:
    _init_sbox()
    sbox = _SBOX
    rcon = [0x01]
    for _ in range(10):
        rcon.append(((rcon[-1] << 1) ^ (0x11B if rcon[-1] & 0x80 else 0)) & 0xFF)

    def key_expansion(key):
        w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
        for i in range(4, 44):
            temp = list(w[i - 1])
            if i % 4 == 0:
                temp = temp[1:] + temp[:1]
                temp = [sbox[b] for b in temp]
                temp[0] ^= rcon[i // 4]
            w.append([a ^ b for a, b in zip(w[i - 4], temp)])
        return w

    def add_round_key(state, w, rnd):
        for c in range(4):
            for r in range(4):
                state[r][c] ^= w[rnd * 4 + c][r]

    def sub_bytes(state):
        for r in range(4):
            for c in range(4):
                state[r][c] = sbox[state[r][c]]

    def shift_rows(state):
        for r in range(1, 4):
            state[r] = state[r][r:] + state[r][:r]

    def xtime(a):
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        return a & 0xFF

    def mix_single_column(col):
        a = col[:]
        r = [0, 0, 0, 0]
        r[0] = xtime(a[0]) ^ (xtime(a[1]) ^ a[1]) ^ a[2] ^ a[3]
        r[1] = a[0] ^ xtime(a[1]) ^ (xtime(a[2]) ^ a[2]) ^ a[3]
        r[2] = a[0] ^ a[1] ^ xtime(a[2]) ^ (xtime(a[3]) ^ a[3])
        r[3] = (xtime(a[0]) ^ a[0]) ^ a[1] ^ a[2] ^ xtime(a[3])
        return r

    def mix_columns(state):
        for c in range(4):
            col = [state[r][c] for r in range(4)]
            col = mix_single_column(col)
            for r in range(4):
                state[r][c] = col[r]

    w = key_expansion(list(key))
    state = [[block[r + 4 * c] for c in range(4)] for r in range(4)]
    add_round_key(state, w, 0)
    for rnd in range(1, 10):
        sub_bytes(state)
        shift_rows(state)
        mix_columns(state)
        add_round_key(state, w, rnd)
    sub_bytes(state)
    shift_rows(state)
    add_round_key(state, w, 10)
    out = bytearray(16)
    for r in range(4):
        for c in range(4):
            out[r + 4 * c] = state[r][c]
    return bytes(out)


def try_channel(mac: str, channel: int, key: bytes, timeout: float = 5.0):
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.settimeout(timeout)
    try:
        print(f"[*] Trying RFCOMM channel {channel} ...")
        sock.connect((mac, channel))
    except OSError as e:
        print(f"    -> connect failed: {e}")
        sock.close()
        return False

    print(f"    -> connected on channel {channel}!")
    try:
        run_handshake(sock, key)
    finally:
        sock.close()
    return True


def run_handshake(sock: socket.socket, key: bytes):
    sock.settimeout(8.0)

    print("[*] Step 1: SEND_KEY")
    sock.send(bytes([CMD_SEND_KEY]) + key)
    try:
        resp = sock.recv(256)
        print(f"    <- {resp.hex()}")
    except socket.timeout:
        print("    <- (timeout, no response to SEND_KEY)")

    print("[*] Step 2: REQUEST_RANDOM")
    sock.send(bytes([CMD_REQUEST_RANDOM]))
    try:
        resp = sock.recv(256)
        print(f"    <- {resp.hex()}")
    except socket.timeout:
        print("    <- (timeout, no response to REQUEST_RANDOM)")
        return

    if len(resp) < 4 or resp[0] != RESP_HEADER:
        print(f"    !! unexpected response header, aborting handshake interpretation")
        return

    # Expected shape: 0x10 0x02 status(1) random(16)
    status = resp[2] if len(resp) > 2 else None
    random_number = resp[3:19] if len(resp) >= 19 else resp[3:]
    print(f"    status={status} random_number={random_number.hex()} (len={len(random_number)})")

    if len(random_number) != 16:
        print("    !! random number is not 16 bytes, cannot proceed with AES-ECB step as documented")
        return

    print("[*] Step 3: SEND_ENCRYPTED_RANDOM (AES-128-ECB of the random number with our key)")
    encrypted = aes_ecb_encrypt(key, random_number)
    print(f"    computed ciphertext: {encrypted.hex()}")
    sock.send(bytes([CMD_SEND_ENCRYPTED_RANDOM]) + encrypted)
    try:
        resp = sock.recv(256)
        print(f"    <- {resp.hex()}")
        if len(resp) >= 3 and resp[0] == RESP_HEADER and resp[1] == CMD_SEND_ENCRYPTED_RANDOM:
            if resp[2] == 0x01:
                print("    ==> AUTH SUCCESS (status 0x01)")
            else:
                print(f"    ==> AUTH FAILED (status 0x{resp[2]:02x})")
    except socket.timeout:
        print("    <- (timeout, no response to SEND_ENCRYPTED_RANDOM)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mac")
    ap.add_argument("auth_key_hex")
    ap.add_argument("--channels", default="1-30",
                     help="RFCOMM channel or range to try, e.g. 1-30 or 5")
    args = ap.parse_args()

    key = binascii.unhexlify(args.auth_key_hex)
    if len(key) != 16:
        print(f"!! auth key is {len(key)} bytes, expected 16", file=sys.stderr)
        sys.exit(1)

    if "-" in args.channels:
        lo, hi = (int(x) for x in args.channels.split("-", 1))
        channels = range(lo, hi + 1)
    else:
        channels = [int(args.channels)]

    print(f"[*] AES backend: {'pycryptodome' if AES is not None else 'pure-python fallback'}")

    any_connected = False
    for ch in channels:
        if try_channel(args.mac, ch, key):
            any_connected = True
        time.sleep(0.3)

    if not any_connected:
        print("\n[!] Could not open an RFCOMM connection on any tried channel.")
        print("    Possible causes: wrong channel range, device requires prior")
        print("    BR/EDR bonding we don't have from this host, or the service")
        print("    simply isn't reachable this way. This is useful negative data,")
        print("    not a dead end by itself.")


if __name__ == "__main__":
    main()
