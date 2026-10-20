#!/usr/bin/env python3
"""
Lightweight ELF analysis for a native .so library: printable strings,
dynamic/exported symbol table, section list. No execution of the target
binary, purely static/passive parsing via pyelftools.

Usage: python3 analyze_so.py <path-to-.so> [out_prefix]
"""
import re
import sys
from elftools.elf.elffile import ELFFile


def extract_strings(data: bytes, min_len: int = 6):
    out = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        out.append(m.group().decode())
    return out


def main():
    path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else path

    with open(path, "rb") as f:
        data = f.read()

    print(f"[*] File: {path} ({len(data)} bytes)")

    with open(path, "rb") as f:
        elf = ELFFile(f)
        print(f"[*] Machine: {elf.get_machine_arch()}, Entry: {hex(elf['e_entry'])}")
        print(f"[*] Sections: {[s.name for s in elf.iter_sections()]}")

        print("\n[*] Dynamic symbols (exported/imported functions):")
        dynsym = elf.get_section_by_name('.dynsym')
        syms = []
        if dynsym is not None:
            for sym in dynsym.iter_symbols():
                if sym.name:
                    syms.append((sym.name, sym['st_info']['type'], sym['st_value']))
        for name, typ, val in sorted(syms):
            print(f"    {typ:12s} 0x{val:08x} {name}")
        print(f"    (total: {len(syms)})")

    strings = extract_strings(data, 6)
    with open(f"{prefix}.strings.txt", "w") as f:
        for s in strings:
            f.write(s + "\n")
    print(f"\n[*] {len(strings)} strings >= 6 chars written to {prefix}.strings.txt")


if __name__ == "__main__":
    main()
