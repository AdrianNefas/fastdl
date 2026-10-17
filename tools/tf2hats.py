"""Шапки оригинальной TF2 для сервера TF2 Classified.

    python tools/tf2hats.py <items_game.txt TF2> <модели TF2> <схема NOWP> <выход>
        [--tf2c <items_game.txt Classified>]

<модели TF2> — *_dir.vpk игры TF2 (через запятую) или текстовый список
путей .mdl, по одному в строке. Classified монтирует VPK TF2
(gameinfo_base.txt), так что модели шапок у игрока уже есть: качать
нечего, нужна только запись предмета в схеме.

На выходе:
  <выход>/server/custom/tf2hats/scripts/items/custom_weapons_additions.txt
      — предметы; этот файл схема NOWP уже подключает (#base в
      custom_items_game.txt), отдельная папка — чтобы обновление мода её
      не затёрло;
  <выход>/server/addons/sourcemod/configs/tf2_hats.cfg — меню nowp_hats;
  <выход>/tf2_hats.tsv — номер, имя, классы: список для режиссёра бота.

Номера: у TF2 и Classified они пересекаются (в Classified 52 — лук, в TF2
это шапка), поэтому старые номера TF2 (< 2000) уходят в 20000 + номер.
Номера TF2 от 30000 остаются как есть. Пересечение с Classified всё равно
проверяет --tf2c (на машине сборки или на сервере: tools/tf2hats_check.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import kv  # noqa: E402
import vpk  # noqa: E402

TAB, NL = chr(9), chr(10)
# Имя уходит в кавычки KeyValues, в код VScript и в консоль сервера.
BAD_NAME_CHARS = (chr(34), ";", chr(92), "\n", "\r")
# Ключ класса в схеме TF2 → ключ в used_by_classes Classified и в меню
# nowp_hats (там тяжёлый — heavyweapons, как m_iClass в SourceMod).
CLASSES = {"scout": ("Scout", "scout"), "sniper": ("Sniper", "sniper"),
           "soldier": ("Soldier", "soldier"),
           "demoman": ("Demoman", "demoman"), "medic": ("Medic", "medic"),
           "heavy": ("Heavy", "heavyweapons"), "pyro": ("Pyro", "pyro"),
           "spy": ("Spy", "spy"), "engineer": ("Engineer", "engineer")}
# Что подставляет TF2 в «basename» вместо %s: короткие имена, у подрывника
# demo (модели *_demo.mdl). Подставляем сами и пишем модель на каждый
# класс явно: так не зависим от того, как это делает движок Classified.
SHORT = {"demoman": "demo"}
OLD_ID_SHIFT = 20000


def todict(node) -> dict:
    """Пары kv → dict (ключи в нижнем регистре); повторный блок
    сливается с первым."""
    out: dict = {}
    for k, v, _ in node:
        k = k.lower()
        if isinstance(v, list):
            v = todict(v)
            if isinstance(out.get(k), dict):
                v = {**out[k], **v}
        out[k] = v
    return out


def merge(base: dict, over: dict) -> dict:
    r = dict(base)
    for k, v in over.items():
        r[k] = merge(r[k], v) if isinstance(v, dict) \
            and isinstance(r.get(k), dict) else v
    return r


def resolve(item: dict, prefabs: dict, depth: int = 0) -> dict:
    r: dict = {}
    for p in str(item.get("prefab", "")).split():
        pf = prefabs.get(p.lower())
        if isinstance(pf, dict) and depth < 10:
            r = merge(r, resolve(pf, prefabs, depth + 1))
    return merge(r, item)


def load_kv(path: str) -> dict:
    text = Path(path).read_text("utf-8", errors="replace")
    return todict(kv.parse(text))


def schema_root(d: dict) -> dict:
    """Корень схемы: items_game у игр, new_old_weapons_pack у NOWP."""
    for v in d.values():
        if isinstance(v, dict) and ("items" in v or "prefabs" in v):
            return v
    return d


def model_set(spec: str) -> set[str]:
    out: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        if part.lower().endswith(".vpk"):
            out |= {e["path"].lower() for e in vpk.entries(part)
                    if e["path"].lower().endswith(".mdl")}
        elif part:
            for line in Path(part).read_text("utf-8", "replace").splitlines():
                line = line.strip().replace(chr(92), "/").lower()
                if line.endswith(".mdl"):
                    out.add(line.split()[0])
    return out


def taken(schema: dict) -> tuple[set[int], set[str], set[str]]:
    """Номера, имена (в нижнем регистре) и модели предметов схемы."""
    ids, names, models = set(), set(), set()
    for k, v in (schema.get("items") or {}).items():
        if not k.isdigit() or not isinstance(v, dict):
            continue
        ids.add(int(k))
        if v.get("name"):
            names.add(str(v["name"]).lower())
        if v.get("model_player"):
            models.add(str(v["model_player"]).lower())
    return ids, names, models


def collect(tf2: dict, models: set[str], nowp: dict,
            tf2c: dict | None) -> tuple[list[dict], dict]:
    prefabs = tf2.get("prefabs") or {}
    n_ids, n_names, n_models = taken(nowp)
    c_ids, c_names, _ = taken(tf2c) if tf2c else (set(), set(), set())
    why: dict[str, int] = {}
    seen_models: set[tuple] = set()
    hats: list[dict] = []

    def skip(reason: str) -> None:
        why[reason] = why.get(reason, 0) + 1

    items = tf2.get("items") or {}
    for iid in sorted((k for k in items if k.isdigit()), key=int):
        it = items[iid]
        if not isinstance(it, dict):
            continue
        r = resolve(it, prefabs)
        if str(r.get("item_slot", "")).lower() != "head":
            continue
        name = str(r.get("name", "")).strip()
        if not name or any(ch in name for ch in BAD_NAME_CHARS):
            skip("имя не годится")
            continue
        ubc = [c.lower() for c, v in (r.get("used_by_classes") or {}).items()
               if str(v) != "0" and c.lower() in CLASSES]
        if not ubc:
            ubc = list(CLASSES)
        mp = str(r.get("model_player", "")).strip()
        per: dict[str, str] = {}
        pc = r.get("model_player_per_class")
        if not mp and isinstance(pc, dict):
            base = str(pc.get("basename", ""))
            for c in ubc:
                m = pc.get(c) or (base.replace("%s", SHORT.get(c, c))
                                  if base else "")
                if m and str(m).lower() in models:
                    per[c] = str(m)
            ubc = [c for c in ubc if c in per]
        elif mp and mp.lower() not in models:
            mp = ""
        if not mp and not per:
            skip("модели нет в TF2")
            continue
        key = (mp.lower(),) if mp else tuple(sorted(
            (c, m.lower()) for c, m in per.items()))
        if key in seen_models:
            skip("та же модель у предмета с меньшим номером")
            continue
        if name.lower() in n_names or (mp and mp.lower() in n_models):
            skip("уже есть в New-Old Weapons Pack")
            continue
        new_id = int(iid) + OLD_ID_SHIFT if int(iid) < 2000 else int(iid)
        if not (OLD_ID_SHIFT <= new_id < OLD_ID_SHIFT + 2000
                or 30000 <= new_id < 32768):
            skip("номер вне диапазона")
            continue
        if new_id in n_ids or new_id in c_ids or name.lower() in c_names:
            skip("номер или имя заняты в Classified/NOWP")
            continue
        seen_models.add(key)
        vis = r.get("visuals") or {}
        hats.append({
            "id": new_id, "tf2_id": int(iid), "name": name,
            "classes": ubc, "model": mp, "per_class": per,
            "image": str(r.get("image_inventory", "")),
            "bodygroups": {k: v for k, v in
                           (vis.get("player_bodygroups") or {}).items()
                           if isinstance(v, str)},
        })
    return hats, why


def q(s: str) -> str:
    return '"' + s + '"'


def schema_text(hats: list[dict]) -> str:
    t = TAB
    lines = [
        "// Шапки оригинальной TF2 для сервера TF2 Classified.",
        "// Сделано tools/tf2hats.py (AdrianNefas/fastdl) из items_game.txt",
        "// TF2; модели — из VPK TF2, которые Classified монтирует сам.",
        "// Номер TF2 < 2000 сдвинут на 20000: в Classified эти номера",
        "// заняты своими предметами.",
        q("tf2_hats"), "{", t + q("items"), t + "{"]
    for h in hats:
        p = t * 2
        lines += [p + q(str(h["id"])) + t + "// TF2 " + str(h["tf2_id"]),
                  p + "{",
                  p + t + q("name") + t + q(h["name"]),
                  p + t + q("prefab") + t + q("wearable_passive"),
                  p + t + q("propername") + t + q("1"),
                  p + t + q("item_name") + t + q(h["name"]),
                  p + t + q("item_type_name") + t + q("#TF_Wearable_Hat"),
                  p + t + q("item_quality") + t + q("unique")]
        if h["image"]:
            lines.append(p + t + q("image_inventory") + t + q(h["image"]))
        if h["model"]:
            lines.append(p + t + q("model_player") + t + q(h["model"]))
        else:
            lines += [p + t + q("model_player_per_class"), p + t + "{"]
            lines += [p + t * 2 + q(c) + t + q(m)
                      for c, m in h["per_class"].items()]
            lines.append(p + t + "}")
        lines += [p + t + q("used_by_classes"), p + t + "{"]
        lines += [p + t * 2 + q(CLASSES[c][0]) + t + q("1")
                  for c in h["classes"]]
        lines.append(p + t + "}")
        if h["bodygroups"]:
            lines += [p + t + q("visuals"), p + t + "{",
                      p + t * 2 + q("player_bodygroups"), p + t * 2 + "{"]
            lines += [p + t * 3 + q(k) + t + q(v)
                      for k, v in h["bodygroups"].items()]
            lines += [p + t * 2 + "}", p + t + "}"]
        lines.append(p + "}")
    lines += [t + "}", "}"]
    return NL.join(lines) + NL


def cfg_text(hats: list[dict]) -> str:
    lines = ['"tf2_hats"', "{"]
    for h in sorted(hats, key=lambda h: h["name"].lower()):
        cl = " ".join(CLASSES[c][1] for c in h["classes"])
        lines += [TAB + q(h["name"]), TAB + "{",
                  TAB * 2 + q("id") + TAB + q(str(h["id"])),
                  TAB * 2 + q("classes") + TAB + q(cl), TAB + "}"]
    lines.append("}")
    return NL.join(lines) + NL


def tsv_text(hats: list[dict]) -> str:
    lines = ["# id\tname\tclasses — шапки TF2 (tools/tf2hats.py)"]
    for h in sorted(hats, key=lambda h: h["id"]):
        cl = " ".join(CLASSES[c][1] for c in h["classes"])
        lines.append(f"{h['id']}\t{h['name']}\t{cl}")
    return NL.join(lines) + NL


def main() -> None:
    args = sys.argv[1:]
    tf2c_path = None
    if "--tf2c" in args:
        i = args.index("--tf2c")
        tf2c_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 4:
        sys.exit(__doc__)
    tf2 = schema_root(load_kv(args[0]))
    models = model_set(args[1])
    nowp = schema_root(load_kv(args[2]))
    tf2c = schema_root(load_kv(tf2c_path)) if tf2c_path else None
    out = Path(args[3])
    hats, why = collect(tf2, models, nowp, tf2c)
    srv = out / "server"
    sch = srv / "custom/tf2hats/scripts/items/custom_weapons_additions.txt"
    cfg = srv / "addons/sourcemod/configs/tf2_hats.cfg"
    for p in (sch, cfg):
        p.parent.mkdir(parents=True, exist_ok=True)
    sch.write_text(schema_text(hats), "utf-8")
    cfg.write_text(cfg_text(hats), "utf-8")
    (out / "tf2_hats.tsv").write_text(tsv_text(hats), "utf-8")
    per_cls = {c: sum(c in h["classes"] for h in hats) for c in CLASSES}
    print(f"моделей TF2: {len(models)}; шапок: {len(hats)}")
    print("по классам:", ", ".join(f"{c} {n}" for c, n in per_cls.items()))
    for reason, n in sorted(why.items(), key=lambda x: -x[1]):
        print(f"  пропущено ({reason}): {n}")
    if not tf2c_path:
        print("  номера Classified НЕ сверены: нужен --tf2c "
              "или tools/tf2hats_check.py на сервере")


if __name__ == "__main__":
    main()
