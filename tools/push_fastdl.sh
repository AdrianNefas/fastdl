#!/usr/bin/env bash
# Выложить дерево FastDL (out/fastdl) в ветку gh-pages своего репозитория
# GitHub и напечатать адрес для sv_downloadurl.
#
#   tools/push_fastdl.sh git@github.com:ЛОГИН/РЕПО.git [папка сборки]
#
# Ветка gh-pages перезаписывается ОДНИМ коммитом (--force): 400 МБ
# сжатых файлов на каждое обновление мода в истории раздули бы
# репозиторий до гигабайтов, а GitHub советует держать его до 1-5 ГБ.
# Ветку main (инструменты, опись) скрипт не трогает.
#
# GitHub Pages должен раздавать gh-pages: Settings → Pages → Deploy from a
# branch → gh-pages, / (root). Если стоит gh (GitHub CLI) — скрипт
# попробует включить это сам.
set -euo pipefail

remote="${1:?нужен адрес репозитория: git@github.com:ЛОГИН/РЕПО.git}"
out="${2:-$(dirname "$0")/../../nowp-out}"
src="$out/fastdl"
[ -d "$src" ] || { echo "нет $src — сначала tools/build.py"; exit 2; }

files=$(find "$src" -type f | wc -l)
size=$(du -sm "$src" | cut -f1)
echo "выкладываю $files файлов, ${size} МБ из $src"
if [ "$size" -gt 950 ]; then
    echo "больше 950 МБ: у GitHub Pages предел сайта 1 ГБ — убери часть "
    echo "предметов в exclude.txt и пересобери"; exit 3
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r "$src"/. "$tmp"/
cd "$tmp"
git init -q
git -c core.autocrlf=false add -A
git -c user.name="nowp-fastdl" -c user.email="nowp-fastdl@localhost" \
    commit -q -m "FastDL: New-Old Weapons Pack ($(date +%Y-%m-%d))"
git branch -M gh-pages
git -c http.postBuffer=524288000 push --force "$remote" gh-pages

# github.com:ЛОГИН/РЕПО(.git) → https://ЛОГИН.github.io/РЕПО/
slug=$(echo "$remote" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
owner=${slug%%/*}; repo=${slug#*/}
url="https://${owner}.github.io/${repo}/"
if command -v gh >/dev/null 2>&1; then
    gh api "repos/$slug/pages" -X POST -f "source[branch]=gh-pages" \
        -f "source[path]=/" >/dev/null 2>&1 \
        && echo "GitHub Pages включён на gh-pages" \
        || echo "Pages уже включён или gh не вошёл — проверь Settings → Pages"
fi
echo
echo "Готово. Через 1-2 минуты (сборка Pages) в cfg/nowp_fastdl.cfg:"
echo "    sv_downloadurl \"$url\""
echo "Проверка: curl -I ${url}CREDITS.md   — ждём 200"
