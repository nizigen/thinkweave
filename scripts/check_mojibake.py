#!/usr/bin/env python3
"""Fail if likely mojibake artifacts are found in text source files."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDE_EXT = {".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".json"}
EXCLUDE_DIR_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
}

# Use escaped Unicode to keep this file ASCII-safe.
BAD_PATTERNS = [
    "\\u95c0\\u630e\\u6783",  # example mojibake fragment
    "\\u922b\\u20ac\\?",      # broken arrow fragment often seen as "鈫?"
    "`r`n",                       # accidental literal sequence
]


def should_scan(path: Path) -> bool:
    if path.name == "check_mojibake.py":
        return False
    if path.suffix.lower() not in INCLUDE_EXT:
        return False
    parts = set(path.parts)
    return not any(part in parts for part in EXCLUDE_DIR_PARTS)


def main() -> int:
    bad_re = re.compile("|".join(BAD_PATTERNS))
    failures: list[tuple[Path, int, str]] = []

    for path in ROOT.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append((path, 0, "non-utf8 file"))
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            if bad_re.search(line):
                failures.append((path, i, line.strip()[:120]))

    if not failures:
        print("OK: no mojibake patterns found")
        return 0

    print("Found potential mojibake artifacts:")
    for path, line_no, snippet in failures:
        rel = path.relative_to(ROOT)
        if line_no > 0:
            print(f"  - {rel}:{line_no}: {snippet}")
        else:
            print(f"  - {rel}: {snippet}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
