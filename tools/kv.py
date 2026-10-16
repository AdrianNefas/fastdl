"""Разбор KeyValues Valve (items_game, soundscripts, vmt) — терпимо к
комментариям, условиям [$WIN32] и строкам без кавычек.

Результат — список пар (ключ, значение, строка), где значение — строка
или вложенный такой же список. Повторяющиеся ключи сохраняются: в
items_game они законны.
"""
from __future__ import annotations

import re

_TOKEN = re.compile(
    r'"((?:[^"\\]|\\.)*)"'          # строка в кавычках
    r"|(//[^\n]*)"                  # комментарий
    r"|([{}])"                      # скобки
    r"|(\[[^\]\n]*\])"              # условие [$WIN32]
    r"|([^\s{}\"]+)"                # слово без кавычек
)


def tokens(text: str):
    line = 1
    pos = 0
    for m in _TOKEN.finditer(text):
        line += text.count("\n", pos, m.start())
        pos = m.start()
        quoted, comment, brace, cond, bare = m.groups()
        if comment is not None or cond is not None:
            continue
        if brace is not None:
            yield brace, line
        elif quoted is not None:
            yield ("s", quoted), line
        else:
            yield ("s", bare), line


def parse(text: str) -> list:
    stack: list[list] = [[]]
    key = None
    key_line = 0
    for tok, line in tokens(text):
        if tok == "{":
            child: list = []
            stack[-1].append((key if key is not None else "", child, key_line))
            stack.append(child)
            key = None
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        else:
            s = tok[1]
            if key is None:
                key, key_line = s, line
            else:
                stack[-1].append((key, s, key_line))
                key = None
    return stack[0]


def find(node: list, name: str):
    """Первый ребёнок с таким ключом (без учёта регистра)."""
    low = name.lower()
    for k, v, _ in node:
        if k.lower() == low:
            return v
    return None


def walk_strings(node, path=()):
    """Все строковые значения поддерева: (путь ключей, значение)."""
    if isinstance(node, str):
        yield path, node
        return
    for k, v, _ in node:
        yield from walk_strings(v, path + (k,))
