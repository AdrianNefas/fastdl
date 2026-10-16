"""Опись New-Old Weapons Pack: каждый предмет, его файлы и их вес.

Граф зависимостей: предмет → модели (.mdl), иконка (materials/backpack),
звуки (имена из soundscript → .wav), частицы; модель → её материалы и
вложенные модели (заголовок studiohdr) и имена звуков из событий
анимаций; материал (.vmt) → текстуры (.vtf) и вложенные материалы.

Файл, который подменяет файл самой игры по тому же пути, у клиента через
FastDL НЕ сработает: скачанное ищется последним (gameinfo.txt,
«game+download ... searched LAST»). Такие файлы помечены «override».

    python tools/inventory.py <распакованный мод> <распакованный VPK> <выход>
                              [vpk игры ...]
"""
from __future__ import annotations

import csv
import json
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kv  # noqa: E402
import vpk  # noqa: E402

ASSET_EXT = (".mdl", ".vmt", ".vtf", ".wav", ".mp3", ".pcf", ".vcd",
             ".vvd", ".vtx", ".phy", ".ani")
MODEL_SIDE = (".vvd", ".dx80.vtx", ".dx90.vtx", ".sw.vtx", ".phy", ".ani",
              ".vtx")
# Варианты материала для четырёх команд TF2C подставляет игра по суффиксу:
# модель знает только c_leechgun, а c_leechgun_grn/_ylw берутся сами.
TEAM_SUFFIX = ("red", "blu", "blue", "grn", "green", "ylw", "yellow",
               "purple")
# «basename» с %s — модель на класс: игра подставляет имя класса игрока.
# Варианты для классов, которым предмет не выдан, не загружаются никогда.
CLASS_TOKEN = {"scout": ["scout"], "soldier": ["soldier"], "pyro": ["pyro"],
               "demoman": ["demo", "demoman"], "heavy": ["heavy"],
               "engineer": ["engineer"], "medic": ["medic"],
               "sniper": ["sniper"], "spy": ["spy"], "civilian": ["civilian"]}
HEADER = re.compile(r"^//\s*\(ID ([^)]*)\)\s*\|\s*(.*?)\s*\|\s*Tags:\s*(.*?)\s*"
                    r"(?:\|\s*Extra:\s*(.*))?$")


def norm(p: str) -> str:
    return p.replace("\\", "/").strip().lstrip("/").lower()


class Pack:
    def __init__(self, loose: Path):
        self.root = loose
        self.files: dict[str, int] = {}
        for f in loose.rglob("*"):
            if f.is_file():
                self.files[norm(str(f.relative_to(loose)))] = f.stat().st_size

    def has(self, p: str) -> bool:
        return norm(p) in self.files

    def read(self, p: str) -> bytes:
        return (self.root / norm(p)).read_bytes()


def cstr(b: bytes, off: int) -> str:
    end = b.find(b"\0", off)
    return b[off:end if end >= 0 else None].decode("latin-1")


def mdl_refs(data: bytes) -> tuple[set[str], set[str], list[str]]:
    """(материалы-кандидаты .vmt, вложенные модели, строки для звуков)."""
    mats, models = set(), set()
    try:
        tex_n, tex_i = struct.unpack_from("<ii", data, 204)
        cd_n, cd_i = struct.unpack_from("<ii", data, 212)
        cds = [cstr(data, struct.unpack_from("<i", data, cd_i + 4 * k)[0])
               for k in range(cd_n)]
        for t in range(tex_n):
            base = tex_i + 64 * t
            name = cstr(data, base + struct.unpack_from("<i", data, base)[0])
            for cd in cds or [""]:
                mats.add(norm(f"materials/{cd}{name}.vmt"))
        inc_n, inc_i = struct.unpack_from("<ii", data, 336)
        for k in range(inc_n):
            base = inc_i + 8 * k
            models.add(norm(cstr(data, base +
                                 struct.unpack_from("<i", data, base + 4)[0])))
    except (struct.error, IndexError):
        pass
    strings = [m.decode("latin-1") for m in
               re.findall(rb"[\x20-\x7e]{4,}", data)]
    return mats, models, strings


def vmt_refs(text: str) -> set[str]:
    out = set()
    for _path, v in kv.walk_strings(kv.parse(text)):
        v = norm(v)
        if not v or v.isdigit():
            continue
        v = v[len("materials/"):] if v.startswith("materials/") else v
        for cand in (f"materials/{v}", f"materials/{v}.vtf",
                     f"materials/{v}.vmt"):
            out.add(cand)
    return out


def load_sounds(paths: list[Path]) -> dict[str, set[str]]:
    """Имя звука из soundscript → набор wav-файлов (sound/...)."""
    out: dict[str, set[str]] = defaultdict(set)
    for p in paths:
        root = kv.parse(p.read_text("utf-8", errors="replace"))
        for name, body, _ in root:
            if isinstance(body, str):
                continue
            for keys, v in kv.walk_strings(body):
                if keys and keys[-1].lower() == "wave":
                    w = norm(re.sub(r"^[*#@<>^)(}$!?&~`+%]+", "", v))
                    out[name.lower()].add(f"sound/{w}")
    return out


class Base:
    """Файлы самой игры по их VPK: нужны, чтобы разобрать модель игры,
    чьи материалы подменяет мод (Blutsauger: модель игры, текстура мода)."""

    def __init__(self, dir_vpks: list[str]):
        self.idx: dict[str, tuple[str, dict]] = {}
        for v in dir_vpks:
            for e in vpk.entries(v):
                self.idx.setdefault(norm(e["path"]), (v, e))

    def __contains__(self, p: str) -> bool:
        return norm(p) in self.idx

    def read(self, p: str) -> bytes:
        v, e = self.idx[norm(p)]
        if e["arc"] == 0x7FFF:
            path, off = v, e["base"] + e["off"]
        else:
            path = v.replace("_dir.vpk", f"_{e['arc']:03d}.vpk")
            off = e["off"]
        with open(path, "rb") as f:
            f.seek(off)
            return e["preload"] + f.read(e["len"])


class Graph:
    def __init__(self, pack: Pack, sounds: dict[str, set[str]],
                 base: "Base | None" = None):
        self.pack, self.sounds, self.base = pack, sounds, base
        self.memo: dict[str, set[str]] = {}

    def _readable(self, p: str) -> bytes | None:
        if self.pack.has(p):
            return self.pack.read(p)
        if self.base is not None and p in self.base:
            try:
                return self.base.read(p)
            except OSError:
                return None
        return None

    def from_value(self, v: str) -> set[str]:
        """Строковое значение из схемы → файлы пака."""
        out: set[str] = set()
        low = v.lower().strip()
        if low in self.sounds:
            for w in self.sounds[low]:
                out |= self.file(w)
        p = norm(re.sub(r"^[*#@<>^)(}$!?&~`+%]+", "", v))
        for cand in (p, f"materials/{p}.vmt", f"materials/{p}",
                     f"sound/{p}", f"{p}.vmt",
                     # большая иконка рюкзака: image_inventory + "_large"
                     f"materials/{p}_large.vmt"):
            out |= self.file(cand)
        return out

    def file(self, p: str) -> set[str]:
        p = norm(p)
        if p in self.memo:
            return self.memo[p]
        self.memo[p] = out = {p} if self.pack.has(p) else set()
        data = self._readable(p) if p.endswith((".mdl", ".vmt")) else None
        if not out and data is None:
            return out
        if p.endswith(".vmt"):
            stem = p[:-4]
            for suf in TEAM_SUFFIX:
                out |= self.file(f"{stem}_{suf}.vmt")
        if p.endswith(".mdl"):
            stem = p[:-4]
            for ext in MODEL_SIDE:
                if self.pack.has(stem + ext):
                    out.add(stem + ext)
            mats, models, strs = mdl_refs(data)
            for m in mats:
                out |= self.file(m)
            for m in models:
                out |= self.file(m)
            for s in strs:
                if s.lower() in self.sounds:
                    for w in self.sounds[s.lower()]:
                        out |= self.file(w)
        elif p.endswith(".vmt"):
            text = data.decode("utf-8", errors="replace")
            for c in vmt_refs(text):
                if c != p:
                    out |= self.file(c)
                    if c.endswith(".vtf"):
                        st = c[:-4]
                        for suf in TEAM_SUFFIX:
                            out |= self.file(f"{st}_{suf}.vtf")
        elif p.endswith(".pcf"):
            for s in re.findall(rb"[\x20-\x7e]{4,}", self.pack.read(p)):
                s = s.decode("latin-1")
                if s.lower().endswith(".vmt"):
                    out |= self.file(f"materials/{s}")
        return out


def headers(text: str) -> list[tuple[int, dict]]:
    """Заголовки разделов «// (ID ...) | Название | Tags: ...» по строкам."""
    out = []
    lines = text.splitlines()
    for i, ln in enumerate(lines, 1):
        m = HEADER.match(ln.strip())
        if not m:
            continue
        info = {"ids": m.group(1), "title": m.group(2).strip(),
                "tags": re.findall(r"\(([^)]*)\)", m.group(3)),
                "extra": re.findall(r"\(([^)]*)\)", m.group(4) or ""),
                "overview": "", "authors": ""}
        for nxt in lines[i:i + 8]:
            s = nxt.strip()
            if s.startswith("// [Overview:"):
                info["overview"] = s[len("// [Overview:"):].rstrip("]").strip()
            elif s.startswith("// [Authors:"):
                info["authors"] = s[len("// [Authors:"):].rstrip("]").strip()
        out.append((i, info))
    return out


def status_of(item: list, tags: list[str]) -> str:
    t = {x.lower() for x in tags}
    if "debug" in t or "unused" in t:
        return "debug"
    if "supersecret" in t:
        return "supersecret"
    if "secret" in t:
        return "secret"
    if kv.find(item, "show_in_armory") == "0" or kv.find(item, "hidden") == "1":
        return "hidden"
    return "normal"


def main() -> None:
    mod_dir, loose_dir, out_dir = map(Path, sys.argv[1:4])
    game_vpks = sys.argv[4:]
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = Pack(loose_dir)
    custom = mod_dir / "tf2classified" / "custom"
    items_file = custom / "newoldweaponspack/scripts/items/nowp/newoldweaponspack.txt"
    text = items_file.read_text("utf-8", errors="replace")
    root = kv.parse(text)[0][1]
    snd_files = [custom / "newoldweaponspack/scripts/items/custom_level_sounds.txt"]
    sounds = load_sounds(snd_files)
    game = Base(game_vpks)
    g = Graph(pack, sounds, game)
    base = set(game.idx)

    prefabs = {k.lower(): body for k, body, _ in kv.find(root, "prefabs") or []
               if not isinstance(body, str)}

    def closure(node: list, seen_pref: set[str],
                classes: list[str]) -> set[str]:
        out: set[str] = set()
        for keys, v in kv.walk_strings(node):
            if keys and keys[-1].lower() == "prefab":
                for pf in v.lower().split():
                    if pf in prefabs and pf not in seen_pref:
                        seen_pref.add(pf)
                        out |= closure(prefabs[pf], seen_pref, classes)
                continue
            if "%s" in v:
                for c in classes or list(CLASS_TOKEN):
                    for tok in CLASS_TOKEN.get(c.lower(), [c.lower()]):
                        out |= g.from_value(v.replace("%s", tok))
                continue
            out |= g.from_value(v)
        return out

    hdrs = headers(text)
    items = []
    sources = [(kv.find(root, "items"), hdrs)]
    for extra in sorted(custom.glob("*/scripts/items/nowp/*/*.txt")):
        t2 = extra.read_text("utf-8", errors="replace")
        r2 = kv.parse(t2)
        if r2 and not isinstance(r2[0][1], str):
            sources.append((kv.find(r2[0][1], "items") or [], headers(t2)))
    for key, body, line, hdrs in [(k, b, ln, h) for its, h in sources
                                  for k, b, ln in its]:
        if isinstance(body, str):
            continue
        hdr = next((h for ln, h in reversed(hdrs) if ln <= line),
                   {"title": "", "tags": [], "extra": [], "overview": "",
                    "authors": "", "ids": ""})
        classes = [k for k, v, _ in (kv.find(body, "used_by_classes") or [])
                   if v == "1"]
        items.append({
            "id": key, "name": kv.find(body, "name") or "",
            "group": hdr["title"], "tags": hdr["tags"],
            "overview": hdr["overview"], "authors": hdr["authors"],
            "slot": kv.find(body, "item_slot") or "",
            "class_": kv.find(body, "item_class") or "",
            "classes": classes, "status": status_of(body, hdr["tags"]),
            "files": closure(body, set(), classes), "line": line,
        })

    # Кто на какой файл ссылается
    users: dict[str, set[str]] = defaultdict(set)
    for it in items:
        for f in it["files"]:
            users[f].add(it["id"])
    by_id = {it["id"]: it for it in items}

    def size(fs) -> int:
        return sum(pack.files.get(f, 0) for f in fs)

    override = {f for f in pack.files if f in base}
    for it in items:
        it["exclusive"] = {f for f in it["files"] if users[f] == {it["id"]}}
        it["excl_mb"] = size(it["exclusive"]) / 2**20
        it["all_mb"] = size(it["files"]) / 2**20
    used_normal = {f for f, u in users.items()
                   if any(by_id[i]["status"] in ("normal", "hidden") for i in u)}
    only_hidden = {f for f, u in users.items() if f not in used_normal}
    orphan = set(pack.files) - set(users)
    # Звуки озвучки, сцены и частицы ссылаются на себя сами (talker,
    # атрибуты по имени системы) — считаем их общими, а не сиротами.
    shared_kinds = ("scenes/", "sound/vo/", "particles/")
    orphan_shared = {f for f in orphan if f.startswith(shared_kinds)}
    orphan -= orphan_shared

    summary = {
        "files": len(pack.files), "mb": size(pack.files) / 2**20,
        "items": len(items),
        "override_files": len(override), "override_mb": size(override) / 2**20,
        "used_by_normal_mb": size(used_normal) / 2**20,
        "only_secret_debug_mb": size(only_hidden) / 2**20,
        "orphan_files": len(orphan), "orphan_mb": size(orphan) / 2**20,
        "shared_by_name_mb": size(orphan_shared) / 2**20,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), "utf-8")
    with (out_dir / "items.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "group", "status", "slot", "classes", "tags",
                    "exclusive_mb", "all_mb", "overview"])
        for it in sorted(items, key=lambda x: -x["excl_mb"]):
            w.writerow([it["id"], it["name"], it["group"], it["status"],
                        it["slot"], " ".join(it["classes"]),
                        " ".join(it["tags"]), f"{it['excl_mb']:.2f}",
                        f"{it['all_mb']:.2f}", it["overview"]])
    for name, fs in (("orphan.txt", orphan), ("override.txt", override),
                     ("only_secret_debug.txt", only_hidden)):
        (out_dir / name).write_text(
            "\n".join(f"{pack.files[f]}\t{f}" for f in
                      sorted(fs, key=lambda x: -pack.files[x])), "utf-8")
    (out_dir / "items.json").write_text(json.dumps(
        [{k: (sorted(v) if isinstance(v, set) else v) for k, v in it.items()}
         for it in items], ensure_ascii=False), "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
