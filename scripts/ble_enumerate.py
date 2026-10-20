#!/usr/bin/env python3
"""
Read-only BLE discovery + GATT enumeration for a SINGLE known device address.

Scoped on purpose: we only look for our own already-known Amazfit Bip 6 MAC
(from an earlier bluetoothctl `devices` listing), never an open "find anything
nearby" scan. We only read services/characteristics, never write.

Usage:
    .venv/bin/python ble_enumerate.py <MAC> [--scan-timeout 15]
"""
import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner


async def find_device(address: str, scan_timeout: float):
    print(f"[*] Scanning up to {scan_timeout:.0f}s for {address} only ...")

    def _match(device, adv_data):
        return device.address.upper() == address.upper()

    device = await BleakScanner.find_device_by_filter(_match, timeout=scan_timeout)
    return device


async def dump_gatt(address: str, scan_timeout: float):
    device = await find_device(address, scan_timeout)
    if device is None:
        print(f"[!] Device {address} not found during scan window. "
              f"Make sure the watch is awake/nearby and not connected elsewhere.")
        return 1

    print(f"[+] Found: {device.name!r} ({device.address}), connecting (read-only)...")

    async with BleakClient(device, timeout=30.0) as client:
        print(f"[+] Connected: {client.is_connected}")
        svcs = client.services
        for service in svcs:
            print(f"\n[SERVICE] {service.uuid}  (handle {service.handle})  — {service.description}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    [CHAR] {char.uuid}  handle={char.handle}  props=[{props}]  — {char.description}")
                for desc in char.descriptors:
                    print(f"        [DESC] {desc.uuid} handle={desc.handle}")

        print("\n[*] Disconnecting (no reads/writes to characteristics performed).")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address", help="Target BLE MAC address")
    ap.add_argument("--scan-timeout", type=float, default=15.0)
    args = ap.parse_args()
    rc = asyncio.run(dump_gatt(args.address, args.scan_timeout))
    sys.exit(rc)


if __name__ == "__main__":
    main()
