"""Чтение одиночного VPK (v1/v2, без _dir-частей): список и извлечение."""
import struct
import sys
from pathlib import Path


def read_cstr(f) -> str:
    out = bytearray()
    while True:
        c = f.read(1)
        if not c or c == b"\0":
            return out.decode("utf-8", "replace")
        out += c


def entries(path: str):
    with open(path, "rb") as f:
        sig, ver, tree = struct.unpack("<III", f.read(12))
        assert sig == 0x55AA1234, hex(sig)
        if ver == 2:
            f.read(16)
            header = 28
        else:
            header = 12
        data_base = header + tree
        while True:
            ext = read_cstr(f)
            if not ext:
                break
            while True:
                d = read_cstr(f)
                if not d:
                    break
                while True:
                    name = read_cstr(f)
                    if not name:
                        break
                    crc, pre, arc, off, ln, term = struct.unpack("<IHHIIH", f.read(18))
                    assert term == 0xFFFF
                    preload = f.read(pre)
                    full = (f"{d}/" if d.strip() not in ("", " ") else "") + f"{name}.{ext}"
                    yield {"path": full, "crc": crc, "preload": preload,
                           "arc": arc, "off": off, "len": ln, "base": data_base}


def extract(path: str, out_dir: str) -> int:
    n = 0
    with open(path, "rb") as f:
        for e in entries(path):
            assert e["arc"] == 0x7FFF, f"многочастный VPK: {e['path']}"
            f.seek(e["base"] + e["off"])
            data = e["preload"] + f.read(e["len"])
            dst = Path(out_dir) / e["path"]
            assert ".." not in Path(e["path"]).parts
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            n += 1
    return n


if __name__ == "__main__":
    if sys.argv[1] == "list":
        for e in entries(sys.argv[2]):
            print(len(e["preload"]) + e["len"], e["path"])
    elif sys.argv[1] == "extract":
        print(extract(sys.argv[2], sys.argv[3]), "файлов")
