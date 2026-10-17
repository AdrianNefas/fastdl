"""Урезанная схема шапок TF2 под бюджет моделей движка.

17.10.2026 полная схема (886 шапок) положила сервер: движок грузит
модели ВСЕХ предметов схемы при загрузке карты, а у 886 шапок 2735
разных .mdl (225 шапок — по 9 моделей, на каждый класс):
«PrecacheModel ... overflow, too many models», segfault.

Лимит Classified — 4096 моделей (sv_precacheinfo, 17.10: ctf_2fort с
20 ботами без шапок занимает 1519). 2735 моделей шапок сверху дали
~4254 — переполнение. Сначала берём шапки с одной моделью (639), потом
с несколькими по числу моделей (9 на шапку у 225 штук — по модели на
класс), внутри — по возрастанию номера TF2, пока новые модели не
дойдут до бюджета. Запас под тяжёлые карты оставляет сам бюджет.

    python3 make_lite.py <полная custom_weapons_additions.txt>
        <полный tf2_hats.cfg> <бюджет моделей> <каталог вывода>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    full, cfg, budget, out = (Path(sys.argv[1]), Path(sys.argv[2]),
                              int(sys.argv[3]), Path(sys.argv[4]))
    text = full.read_text(encoding="utf-8")
    head, rest = text.split('\t"items"\n\t{\n', 1)
    items = re.findall(r'(\t\t"(\d+)"[^\n]*\n\t\t\{.*?\n\t\t\}\n)', rest,
                       re.S)
    picked, models = [], set()
    # Номер TF2 < 2000 в схеме сдвинут на 20000 (заняты Classified).
    def tf2(i: str) -> int:
        n = int(i)
        return n - 20000 if 20000 <= n < 22000 else n

    def cost(block: str) -> int:
        return len(set(re.findall(r'"([^"]+\.mdl)"', block)))

    for block, iid in sorted(items, key=lambda x: (cost(x[0]), tf2(x[1]))):
        mdl = set(re.findall(r'"([^"]+\.mdl)"', block))
        new = mdl - models
        if len(models) + len(new) > budget:
            continue
        models |= new
        picked.append((block, iid))
    ids = {iid for _, iid in picked}
    out.mkdir(parents=True, exist_ok=True)
    keep = sorted(picked, key=lambda x: int(x[1]))
    # newline="\n": на Windows write_text записал бы CRLF, и md5 не
    # сошёлся бы с проверкой на сервере.
    with open(out / "custom_weapons_additions.txt", "w", encoding="utf-8",
              newline="\n") as f:
        f.write(head + '\t"items"\n\t{\n' + "".join(b for b, _ in keep)
                + "\t}\n}\n")
    # tf2_hats.cfg: блок «"имя" { "id" "N" "classes" "..." }».
    ctext = cfg.read_text(encoding="utf-8")
    blocks = re.findall(r'(\t"[^"\n]+"\n\t\{\n\t\t"id"\t"(\d+)"\n.*?\n\t\}\n)',
                        ctext, re.S)
    kept = [b for b, i in blocks if i in ids]
    with open(out / "tf2_hats.cfg", "w", encoding="utf-8",
              newline="\n") as f:
        f.write('"tf2_hats"\n{\n' + "".join(kept) + "}\n")
    print(f"шапок {len(picked)} из {len(items)}, моделей {len(models)} "
          f"(бюджет {budget}), в меню {len(kept)}")
    return 0 if len(kept) == len(picked) else 1


if __name__ == "__main__":
    sys.exit(main())
