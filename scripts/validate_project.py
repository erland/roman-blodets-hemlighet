#!/usr/bin/env python3
"""Snabb validering för Blodets hemlighet-projektet.

Avsedd att kunna köras både lokalt och i GitHub Actions.
Använder endast Python-standardbiblioteket.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

CHAPTER_RE = re.compile(r"kapitel-(\d{2})\.md$")
CHAPTER_H1_RE = re.compile(r"^#\s+Kapitel\s+(\d+)\s+[–-]\s+(.+?)\s*$")
MARKERS = ("TODO", "FIXME", "[PLACEHOLDER]", "XXX")

REQUIRED_PATHS = (
    "README.md",
    "roman-bibel.md",
    "synopsis.md",
    "kapitelplan.md",
    "projektstatus.md",
    "project-index.md",
    "stilguide.md",
    "tidslinje.md",
    "kontinuitetsanteckningar.md",
    "revisionsonskemal.md",
    "arbetslogg.md",
    "karaktarer/huvudperson.md",
    "karaktarer/antagonist.md",
    "karaktarer/bifigurer.md",
    "kapitel/kapitelmall.md",
    "omslag/blodets_hemlighet_den_forsta_gnistan.png",
    "publishing/metadata.yaml",
    "publishing/epub.css",
    "publishing/fix-epub-after-pandoc.py",
    "publishing/pdf-template.tex",
    "publishing/pdf-filter.lua",
    "scripts/build_book.py",
    "scripts/validate_project.py",
)

REQUIRED_METADATA_KEYS = (
    "title",
    "subtitle",
    "author",
    "language",
    "cover-image",
)

EXPECTED_TITLE = "Blodets hemlighet"
EXPECTED_SUBTITLE = "Den första gnistan"
EXPECTED_AUTHOR = "Erland Lindmark"
EXPECTED_CHAPTERS = 32


def error(errors: list[str], message: str) -> None:
    errors.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def parse_simple_yaml_scalars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def validate_markdown_links(root: Path, errors: list[str]) -> None:
    link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for md in sorted(root.rglob("*.md")):
        if ".git" in md.relative_to(root).parts:
            continue
        text = md.read_text(encoding="utf-8")
        for target in link_re.findall(text):
            target = target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            if " " in target and not target.startswith(("./", "../")):
                target = target.split(" ", 1)[0]
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            candidate = (md.parent / target).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if not candidate.exists():
                error(errors, f"Trasig intern Markdown-länk i {md.relative_to(root)}: {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []

    if not root.is_dir():
        error(errors, f"Projektkatalogen finns inte: {root}")
        return 1

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            error(errors, f"Obligatorisk projektsökväg saknas: {rel}")

    chapter_dir = root / "kapitel"
    chapters: dict[int, Path] = {}
    if chapter_dir.exists():
        for path in sorted(chapter_dir.iterdir()):
            if not path.is_file():
                continue
            match = CHAPTER_RE.fullmatch(path.name)
            if match:
                number = int(match.group(1))
                chapters[number] = path
            elif path.name.lower() != "kapitelmall.md" and re.search(r"kapitel.*\d", path.name, re.I):
                error(errors, f"Icke-kanonisk kapitelfil hittad: kapitel/{path.name}")
    else:
        error(errors, "Kapiteldir saknas: kapitel")

    numbers = sorted(chapters)
    expected_numbers = list(range(1, EXPECTED_CHAPTERS + 1))
    if numbers != expected_numbers:
        error(errors, f"Kapitelserien är inte komplett 1-{EXPECTED_CHAPTERS}: hittade {numbers}")

    for number, path in chapters.items():
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            error(errors, f"{path.relative_to(root)} är tom.")
            continue
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        match = CHAPTER_H1_RE.match(first_line)
        if not match:
            error(errors, f"{path.relative_to(root)} saknar H1 i formatet '# Kapitel X – Titel'.")
        elif int(match.group(1)) != number:
            error(errors, f"{path.relative_to(root)} har H1-kapitelnummer {match.group(1)} men filnummer {number}.")
        for marker in MARKERS:
            if marker in text:
                error(errors, f"{path.relative_to(root)} innehåller arbetsmarkör: {marker}")

    metadata_path = root / "publishing/metadata.yaml"
    if metadata_path.exists():
        metadata = parse_simple_yaml_scalars(metadata_path)
        for key in REQUIRED_METADATA_KEYS:
            if not metadata.get(key):
                error(errors, f"Metadata saknar värde för: {key}")
        if metadata.get("title") != EXPECTED_TITLE:
            error(errors, f"Metadata title är {metadata.get('title')!r}, väntat {EXPECTED_TITLE!r}.")
        if metadata.get("subtitle") != EXPECTED_SUBTITLE:
            error(errors, f"Metadata subtitle är {metadata.get('subtitle')!r}, väntat {EXPECTED_SUBTITLE!r}.")
        if metadata.get("author") != EXPECTED_AUTHOR:
            error(errors, f"Metadata author är {metadata.get('author')!r}, väntat {EXPECTED_AUTHOR!r}.")
        cover = metadata.get("cover-image", "")
        cover_path = (metadata_path.parent / cover).resolve() if cover else None
        if cover_path is None or not cover_path.exists():
            error(errors, f"Metadata cover-image pekar inte på en fil: {cover}")

    validate_markdown_links(root, errors)

    if errors:
        print(f"Validering misslyckades med {len(errors)} fel.", file=sys.stderr)
        return 1
    print(f"OK: projektet validerat ({EXPECTED_CHAPTERS} kapitel, metadata och omslag).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
