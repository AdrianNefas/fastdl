"""INVENTORY.md из inventory/items.json и списков: предметы по классам,
описание автора, вес, что убирается без вопросов."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

inv = Path(sys.argv[1] if len(sys.argv) > 1 else "inventory")
items = json.loads((inv / "items.json").read_text("utf-8"))
summary = json.loads((inv / "summary.json").read_text("utf-8"))

STATUS = {"normal": "в игре", "hidden": "скрыт (служебный вариант)",
          "secret": "секретный", "supersecret": "супер-секретный",
          "debug": "отладка"}
CLASS_RU = {"Scout": "Скаут", "Soldier": "Солдат", "Pyro": "Поджигатель",
            "Demoman": "Подрывник", "Heavy": "Пулемётчик",
            "Engineer": "Инженер", "Medic": "Медик", "Sniper": "Снайпер",
            "Spy": "Шпион", "Civilian": "Гражданский"}


def mb(x: float) -> str:
    return f"{x:.1f}" if x >= 0.05 else "—"


def lines_of(name: str) -> list[tuple[int, str]]:
    p = inv / name
    out = []
    for ln in p.read_text("utf-8").splitlines():
        if "\t" in ln:
            s, f = ln.split("\t", 1)
            out.append((int(s), f))
    return out


groups: dict[str, list[dict]] = defaultdict(list)
for it in items:
    cls = it["classes"]
    key = ("Все классы" if len(cls) >= 9 else
           ", ".join(CLASS_RU.get(c, c) for c in cls) if len(cls) > 1 else
           CLASS_RU.get(cls[0], cls[0]) if cls else "Без класса")
    if it["status"] in ("secret", "supersecret", "debug"):
        key = "Секретное и отладка"
    groups[key].append(it)

out = []
out.append("# New-Old Weapons Pack v4.3.0 — опись\n")
out.append("Автор мода — SilentFox3 (Kiri) и соавторы, см. CREDITS.md. "
           "Описания предметов — авторские, из заголовков схемы "
           "(newoldweaponspack.txt), на английском.\n")
out.append("«Своё, МБ» — файлы, которые нужны только этому предмету: столько "
           "уйдёт из FastDL, если предмет убрать. «Всего, МБ» — вместе с "
           "общими файлами.\n")
out.append("## Сводка\n")
out.append(f"* В VPK мода: {summary['files']} файлов, {summary['mb']:.0f} МБ.")
out.append(f"* Нужно предметам в игре: {summary['used_by_normal_mb']:.0f} МБ "
           "(после bz2 для FastDL ≈ 398 МБ, замер).")
out.append(f"* Только секретным и отладке: {summary['only_secret_debug_mb']:.0f}"
           " МБ (bz2 ≈ 15 МБ).")
out.append(f"* **Ни один предмет не использует: {summary['orphan_files']} файлов,"
           f" {summary['orphan_mb']:.0f} МБ** — остатки старых версий и "
           "вырезанное оружие (orphan.txt). Убираются сборкой.")
out.append(f"* **Подменяют файлы игры: {summary['override_files']} файлов, "
           f"{summary['override_mb']:.0f} МБ** (override.txt). Через FastDL у "
           "клиента не сработают: скачанное игра ищет последним. В FastDL не "
           "идут, на сервере остаются.")
out.append("* Вне VPK: исходники иконок убийств (kill-icons/[nowp_icon_"
           "creation_files], 43 МБ) — для художника, игре не нужны; папка "
           "mod-n-userscripts — по словам автора «только для личного "
           "использования, не для серверов». Обе в сборку не идут.\n")

orphan = lines_of("orphan.txt")
fam: dict[str, int] = defaultdict(int)
for s, f in orphan:
    stem = f.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    for suf in ("_large", "_red", "_blu", "_blue", "_grn", "_green", "_ylw",
                "_yellow", "_purple", "_exp", "_normal", "_phong"):
        stem = stem.replace(suf, "")
    fam[stem] += s
out.append("### Крупнейшее из неиспользуемого\n")
out.append("| что | МБ |\n|---|---|")
for k, v in sorted(fam.items(), key=lambda x: -x[1])[:25]:
    out.append(f"| {k} | {v / 2**20:.1f} |")
out.append("")

order = ["Все классы"] + [CLASS_RU[c] for c in CLASS_RU] + \
    sorted(k for k in groups if k not in CLASS_RU.values()
           and k not in ("Все классы", "Секретное и отладка")) + \
    ["Секретное и отладка"]
for key in order:
    if key not in groups:
        continue
    rows = sorted(groups[key], key=lambda x: (x["group"], int(x["id"])
                                              if x["id"].isdigit() else 0))
    tot = sum(r["excl_mb"] for r in rows)
    out.append(f"## {key} — {len(rows)} шт., своё {tot:.0f} МБ\n")
    out.append("| ID | предмет | слот | статус | своё, МБ | всего, МБ | "
               "описание автора |\n|---|---|---|---|---|---|---|")
    for r in rows:
        desc = (r["overview"] or "").replace("|", "/")
        tags = ", ".join(t for t in r["tags"] if t in ("New", "Old",
                                                       "Wearable", "Taunt",
                                                       "Community"))
        name = r["group"] or r["name"]
        if r["name"] and r["name"].lower() != name.lower():
            name += f" <br><sub>{r['name']}</sub>"
        out.append(f"| {r['id']} | {name} | {r['slot']} | "
                   f"{STATUS.get(r['status'], r['status'])}"
                   f"{' · ' + tags if tags else ''} | {mb(r['excl_mb'])} | "
                   f"{mb(r['all_mb'])} | {desc} |")
    out.append("")

(inv / "INVENTORY.md").write_text("\n".join(out), "utf-8")
print("строк", len(out))
