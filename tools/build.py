"""Сборка New-Old Weapons Pack для сервера и FastDL.

    python tools/build.py <архив мода .zip> <выход> [exclude.txt]

На выходе:
  <выход>/server/tf2classified/custom/newoldweaponspack/  — схема и файлы
      (без неиспользуемого; предметы из exclude.txt вырезаны из схемы)
  <выход>/server/tf2classified/addons/sourcemod/configs/nowp_downloads.txt
      — что клиент должен скачать (читает плагин nowp_downloads)
  <выход>/fastdl/  — те же клиентские файлы, сжатые bz2, в путях игры
  <выход>/report.json — что вошло и сколько весит

Подмены файлов самой игры идут на сервер, но не в FastDL: у клиента
скачанное ищется последним (gameinfo.txt), и подмена не сработает.

exclude.txt — по строке на правило, # — комментарий:
  3300                  предмет по ID
  group:Crowbar         все предметы раздела схемы с таким названием
  status:supersecret    все предметы со статусом (normal, hidden, secret,
                        supersecret, debug)
"""
from __future__ import annotations

import bz2
import json
import re
import shutil
import sys
import tempfile
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import inventory as inv  # noqa: E402
import kv  # noqa: E402
import vpk  # noqa: E402

GAME_VPKS = HERE / "game_vpks.txt"
# Звуки озвучки, сцены и частицы находит игра по имени, а не по ссылке из
# предмета, — берём целиком (вместе 6.5 МБ).
SHARED = ("scenes/", "sound/vo/", "particles/")
# «Precacher» помечен автором как Debug/Unused, но рабочий: он загружает
# модели, которые атрибуты берут по имени (магазины, снаряды, реквизит
# насмешек). Без него эти модели не появятся — не вырезать.
NEVER_EXCLUDE_GROUPS = {"precacher"}
TAB, NL = chr(9), chr(10)
# Имя шапки уходит в кавычки KeyValues и в код VScript.
BAD_NAME_CHARS = (chr(34), ";", chr(92))


def read_rules(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    out = []
    for ln in path.read_text("utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln:
            out.append(ln)
    return out


def excluded(it: dict, rules: list[str]) -> bool:
    if it["group"].lower() in NEVER_EXCLUDE_GROUPS:
        return False
    for r in rules:
        if r == it["id"]:
            return True
        if r.lower().startswith("group:") and \
                r[6:].strip().lower() == it["group"].lower():
            return True
        if r.lower().startswith("status:") and \
                r[7:].strip().lower() == it["status"]:
            return True
    return False


def cut_items(text: str, ids: set[str]) -> tuple[str, list[str]]:
    """Вырезать из схемы блоки предметов по ID: от строки ключа до
    парной скобки. Комментарии перед блоком остаются — они ни на что не
    влияют."""
    lines = text.split("\n")
    root = kv.parse(text)[0][1]
    spans = []
    for key, body, line in kv.find(root, "items"):
        if key in ids and not isinstance(body, str):
            depth, started = 0, False
            for j in range(line - 1, len(lines)):
                code = re.sub(r'"(?:[^"\\]|\\.)*"', '""',
                              lines[j].split("//", 1)[0])
                for ch in code:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth == 0:
                    spans.append((line - 1, j))
                    break
    cut = []
    for a, b in sorted(spans, reverse=True):
        cut.append(lines[a].strip())
        del lines[a:b + 1]
    return "\n".join(lines), cut


def compress(job: tuple[str, str]) -> int:
    src, dst = job
    data = Path(src).read_bytes()
    out = bz2.compress(data, 9)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_bytes(out)
    return len(out)


def main() -> None:
    mod_zip, out = Path(sys.argv[1]), Path(sys.argv[2])
    rules = read_rules(Path(sys.argv[3]) if len(sys.argv) > 3 else
                       HERE.parent / "exclude.txt")
    work = Path(tempfile.mkdtemp(prefix="nowp-build-"))
    print("распаковка", mod_zip)
    with zipfile.ZipFile(mod_zip) as z:
        for i in z.infolist():
            if i.filename.startswith("/") or ".." in Path(i.filename).parts:
                raise SystemExit(f"подозрительный путь в архиве: {i.filename}")
        z.extractall(work / "mod")
    custom = work / "mod" / "tf2classified" / "custom"
    loose = work / "loose"
    print("распаковка VPK:", vpk.extract(
        str(custom / "newoldweaponspack_assets.vpk"), str(loose)), "файлов")

    # Опись — тем же кодом, что inventory.py
    game = [ln.strip() for ln in GAME_VPKS.read_text("utf-8").splitlines()
            if ln.strip()]
    inv_out = out / "inventory"
    sys.argv = ["inventory.py", str(work / "mod"), str(loose), str(inv_out),
                *game]
    inv.main()
    items = json.loads((inv_out / "items.json").read_text("utf-8"))
    override = {ln.split("\t")[1] for ln in
                (inv_out / "override.txt").read_text("utf-8").splitlines()
                if "\t" in ln}

    drop = {it["id"] for it in items if excluded(it, rules)}
    keep_items = [it for it in items if it["id"] not in drop]
    pack = inv.Pack(loose)
    keep = {f for it in keep_items for f in it["files"]}
    keep |= {f for f in pack.files if f.startswith(SHARED)}
    client = sorted(keep - override)
    server = sorted(keep)

    srv = out / "server" / "tf2classified"
    if (out / "server").exists():
        shutil.rmtree(out / "server")
    if (out / "fastdl").exists():
        shutil.rmtree(out / "fastdl")
    mod_srv = srv / "custom" / "newoldweaponspack"
    shutil.copytree(custom / "newoldweaponspack" / "scripts",
                    mod_srv / "scripts")
    items_txt = mod_srv / "scripts/items/nowp/newoldweaponspack.txt"
    text, cut = cut_items(items_txt.read_text("utf-8", errors="replace"),
                          drop)
    items_txt.write_text(text, "utf-8")
    for f in server:
        dst = mod_srv / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(loose / f, dst)
    cfg = srv / "addons/sourcemod/configs/nowp_downloads.txt"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("// New-Old Weapons Pack — файлы для клиентов (FastDL)\n"
                   + "\n".join(client) + "\n", "utf-8")

    # Шапки для плагина nowp_hats: носимое из раздела «Misc» (супер-
    # секретные шапки автора), кроме вырезанного правилами.
    cls_key = {"scout": "scout", "soldier": "soldier", "pyro": "pyro",
               "demoman": "demoman", "heavy": "heavyweapons",
               "engineer": "engineer", "medic": "medic", "sniper": "sniper",
               "spy": "spy", "civilian": "civilian"}
    hats = [it for it in keep_items
            if "Wearable" in it["tags"] and "Misc" in it["tags"]]
    kvtxt = ['"nowp_hats"', "{"]
    for h in hats:
        if any(ch in h["name"] for ch in BAD_NAME_CHARS):
            continue
        cl = " ".join(cls_key.get(c.lower(), c.lower()) for c in h["classes"])
        kvtxt += [TAB + '"' + h["name"] + '"', TAB + "{",
                  TAB * 2 + '"id"' + TAB + '"' + h["id"] + '"',
                  TAB * 2 + '"classes"' + TAB + '"' + cl + '"', TAB + "}"]
    kvtxt.append("}")
    (srv / "addons/sourcemod/configs/nowp_hats.cfg").write_text(
        NL.join(kvtxt) + NL, "utf-8")
    # Плагины, скрипт и конфиг FastDL из репозитория — в тот же комплект.
    shutil.copytree(HERE.parent / "server", srv, dirs_exist_ok=True)

    print("сжатие bz2:", len(client), "файлов")
    jobs = [(str(loose / f), str(out / "fastdl" / (f + ".bz2")))
            for f in client]
    with ProcessPoolExecutor() as ex:
        sizes = list(ex.map(compress, jobs, chunksize=16))
    (out / "fastdl" / ".nojekyll").write_text("", "utf-8")
    shutil.copyfile(HERE.parent / "CREDITS.md", out / "fastdl" / "CREDITS.md")

    report = {
        "excluded_items": sorted(drop, key=lambda x: int(x) if x.isdigit()
                                 else 0),
        "cut_from_schema": len(cut),
        "server_files": len(server),
        "server_mb": round(sum(pack.files[f] for f in server) / 2**20, 1),
        "client_files": len(client),
        "client_mb": round(sum(pack.files[f] for f in client) / 2**20, 1),
        "fastdl_bz2_mb": round(sum(sizes) / 2**20, 1),
        "largest_bz2_mb": round(max(sizes) / 2**20, 2) if sizes else 0,
        "hats_in_menu": len(hats),
        "dropped_unused_mb": round(sum(
            s for f, s in pack.files.items() if f not in keep) / 2**20, 1),
    }
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
