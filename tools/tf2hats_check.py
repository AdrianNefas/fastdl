"""Проверка шапок TF2 против схемы Classified и NOWP — на сервере.

    python3 tf2hats_check.py <папка tf2classified> <custom_weapons_additions.txt>

Схема Classified (scripts/items/items_game.txt) лежит внутри
vpks/tf2c_assets_dir.vpk, на машине сборки её может не быть, поэтому
сверка — здесь, где стоит ровно та версия игры, что у игроков. Свой
файл без сторонних модулей: кладётся на сервер одним scp.

Код возврата 0 — номера и имена шапок свободны; 1 — есть пересечения
(печатает их): ставить файл нельзя, предмет Classified перезаписался бы
шапкой.
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(//[^\n]*)|([{}])|(\[[^\]\n]*\])'
                    r'|([^\s{}"]+)')


def parse(text: str) -> list:
    stack: list[list] = [[]]
    key = None
    for m in _TOKEN.finditer(text):
        quoted, comment, brace, cond, bare = m.groups()
        if comment is not None or cond is not None:
            continue
        if brace == "{":
            child: list = []
            stack[-1].append((key or "", child))
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            s = quoted if quoted is not None else bare
            if key is None:
                key = s
            else:
                stack[-1].append((key, s))
                key = None
    return stack[0]


def items(text: str) -> dict[int, str]:
    """Номер → имя для всех блоков items (на любом корне схемы)."""
    out: dict[int, str] = {}
    for _root, body in parse(text):
        if not isinstance(body, list):
            continue
        for sec, sub in body:
            if sec.lower() != "items" or not isinstance(sub, list):
                continue
            for k, v in sub:
                if k.isdigit() and isinstance(v, list):
                    name = next((x for kk, x in v if kk.lower() == "name"
                                 and isinstance(x, str)), "")
                    out[int(k)] = name
    return out


def _cstr(f) -> str:
    b = bytearray()
    while (c := f.read(1)) not in (b"", b"\0"):
        b += c
    return b.decode("utf-8", "replace")


def vpk_read(dir_vpk: Path, want: str) -> bytes | None:
    with open(dir_vpk, "rb") as f:
        sig, ver, tree = struct.unpack("<III", f.read(12))
        if sig != 0x55AA1234:
            return None
        if ver == 2:
            f.read(16)
        base = (28 if ver == 2 else 12) + tree
        while ext := _cstr(f):
            while d := _cstr(f):
                while name := _cstr(f):
                    _crc, pre, arc, off, ln, _t = struct.unpack(
                        "<IHHIIH", f.read(18))
                    preload = f.read(pre)
                    full = (f"{d}/" if d.strip() else "") + f"{name}.{ext}"
                    if full.lower() != want:
                        continue
                    if arc == 0x7FFF:
                        f.seek(base + off)
                        return preload + f.read(ln)
                    part = dir_vpk.with_name(
                        dir_vpk.name.replace("_dir.vpk", f"_{arc:03d}.vpk"))
                    with open(part, "rb") as p:
                        p.seek(off)
                        return preload + p.read(ln)
    return None


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    game, ours = Path(sys.argv[1]), Path(sys.argv[2])
    mine = items(ours.read_text("utf-8", "replace"))
    others: dict[int, tuple[str, str]] = {}
    sources = []
    want = "scripts/items/items_game.txt"
    loose = game / want
    if loose.is_file():
        sources.append((str(loose), loose.read_text("utf-8", "replace")))
    for v in sorted((game / "vpks").glob("*_dir.vpk")):
        data = vpk_read(v, want)
        if data:
            sources.append((v.name, data.decode("utf-8", "replace")))
    for f in sorted((game / "custom").glob("*/scripts/items/**/*.txt")):
        if f.resolve() != ours.resolve() and f.name != ours.name:
            sources.append((str(f.relative_to(game)),
                            f.read_text("utf-8", "replace")))
    if not any(s.endswith(".vpk") or s.endswith("items_game.txt")
               for s, _ in sources):
        sys.exit("схема Classified не найдена — проверять не с чем")
    for src, text in sources:
        for i, n in items(text).items():
            others.setdefault(i, (n, src))
    names = {n.lower(): (i, s) for i, (n, s) in others.items() if n}
    bad = 0
    for i, n in sorted(mine.items()):
        if i in others:
            print(f"номер {i} «{n}» занят: «{others[i][0]}» ({others[i][1]})")
            bad += 1
        elif n.lower() in names:
            j, s = names[n.lower()]
            print(f"имя «{n}» ({i}) занято предметом {j} ({s})")
            bad += 1
    print(f"шапок {len(mine)}, предметов в схемах сервера {len(others)} "
          f"({', '.join(s for s, _ in sources)}), пересечений {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
