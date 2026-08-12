#!/usr/bin/env python3
"""Bygg EPUB och PDF från projektets kanoniska Markdown-kapitel.

Kapitelfilerna i kapitel/ är original. Detta script skapar tillfälliga,
exportnormaliserade Markdown-filer och ändrar inte romantexten.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

PANDOC_VERSION = "3.1.11.1"


def simple_metadata(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def pandoc_version() -> str:
    result = subprocess.run(["pandoc", "--version"], text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError("Pandoc finns inte i PATH.")
    first = result.stdout.splitlines()[0]
    match = re.search(r"pandoc\s+([0-9][^\s]*)", first)
    return match.group(1) if match else first


def strip_chapter_notes(text: str) -> str:
    patterns = [
        r"\n---\s*\n\s*Kort kapitelnotering:\s*\n",
        r"\n---\s*\n\s*##\s+Kapitelnotering\s*\n",
        r"\n---\s*\n\s*##\s+Efter kapitel\s*\n",
    ]
    cut = len(text)
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            cut = min(cut, match.start())
    return text[:cut].rstrip() + "\n"


def normalize_chapter_heading(text: str, fallback_number: int) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    m = re.match(r"^#\s+Kapitel\s+(\d+)\s+[–-]\s+(.+?)\s*$", lines[0].strip())
    if m:
        lines[0] = f"# {int(m.group(1))}. {m.group(2).strip()}"
    else:
        lines.insert(0, f"# {fallback_number}. Kapitel {fallback_number}")
    return "\n".join(lines).rstrip() + "\n"


def prepare_export_sources(root: Path, temp: Path, chapters: list[Path]) -> list[Path]:
    prepared: list[Path] = []
    for chapter in chapters:
        number = int(re.search(r"kapitel-(\d{2})\.md$", chapter.name).group(1))
        text = chapter.read_text(encoding="utf-8")
        text = strip_chapter_notes(text)
        text = normalize_chapter_heading(text, number)
        out = temp / f"{number:02d}.md"
        out.write_text(text, encoding="utf-8")
        prepared.append(out)
    return prepared


def find_texgyre_pagella() -> Path | None:
    required = {
        "regular": "texgyrepagella-regular.otf",
        "bold": "texgyrepagella-bold.otf",
        "italic": "texgyrepagella-italic.otf",
        "bolditalic": "texgyrepagella-bolditalic.otf",
    }
    search_roots = [
        Path("/usr/share/texmf/fonts/opentype/public/tex-gyre"),
        Path("/usr/share/fonts/opentype/texgyre"),
        Path("/usr/share/fonts/opentype/tex-gyre"),
    ]
    for candidate in search_roots:
        if all((candidate / filename).is_file() for filename in required.values()):
            return candidate
    for base in (Path("/usr/share/texmf"), Path("/usr/share/fonts")):
        if not base.exists():
            continue
        for regular in base.rglob(required["regular"]):
            candidate = regular.parent
            if all((candidate / filename).is_file() for filename in required.values()):
                return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--formats", default="epub,pdf", help="Kommaseparerade format: epub,pdf")
    parser.add_argument("--allow-pandoc-version-mismatch", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()

    validation = subprocess.run([sys.executable, "scripts/validate_project.py", "."], cwd=root)
    if validation.returncode != 0:
        return validation.returncode

    version = pandoc_version()
    if version != PANDOC_VERSION and not args.allow_pandoc_version_mismatch:
        print(
            f"ERROR: Pandoc {PANDOC_VERSION} krävs för reproducerbart bygge; hittade {version}.",
            file=sys.stderr,
        )
        return 2

    metadata_path = root / "publishing/metadata.yaml"
    metadata = simple_metadata(metadata_path)
    title = metadata["title"]
    subtitle = metadata.get("subtitle", "")
    author = metadata["author"]
    cover_rel = metadata["cover-image"]
    cover_path = (metadata_path.parent / cover_rel).resolve()

    base_name = args.name or slugify(f"{title}-{subtitle}" if subtitle else title)
    base_name = re.sub(r"\.(epub|pdf)$", "", base_name, flags=re.IGNORECASE)

    formats = [item.strip().lower() for item in args.formats.split(",") if item.strip()]
    invalid = sorted(set(formats) - {"epub", "pdf"})
    if invalid or not formats:
        print("ERROR: --formats måste innehålla epub och/eller pdf.", file=sys.stderr)
        return 2

    chapters = sorted((root / "kapitel").glob("kapitel-[0-9][0-9].md"))
    if not chapters:
        print("ERROR: Inga kapitelfiler hittades.", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="roman-export-") as tmpdir:
        temp = Path(tmpdir)
        prepared = prepare_export_sources(root, temp, chapters)

        title_page = temp / "00-title.md"
        title_page.write_text(
            '<section class="title-page">\n'
            f'<p class="book-title">{title}</p>\n'
            + (f'<p class="subtitle">{subtitle}</p>\n' if subtitle else "")
            + f'<p class="author">{author}</p>\n'
            '</section>\n',
            encoding="utf-8",
        )

        if "epub" in formats:
            output = output_dir / f"{base_name}.epub"
            command = [
                "pandoc",
                str(title_page),
                *[str(path) for path in prepared],
                "--from=markdown+raw_html",
                "--to=epub3",
                "--output", str(output),
                "--metadata-file", str(metadata_path),
                "--css", str(root / "publishing/epub.css"),
                "--epub-cover-image", str(cover_path),
                "--epub-title-page=false",
                "--toc",
                "--toc-depth=1",
                "--split-level=1",
            ]
            subprocess.run(command, cwd=root, check=True)
            subprocess.run(
                [sys.executable, str(root / "publishing/fix-epub-after-pandoc.py"), str(output)],
                cwd=root,
                check=True,
            )
            if not output.exists() or output.stat().st_size < 10_000:
                print("ERROR: EPUB-bygget gav ingen giltig EPUB-fil.", file=sys.stderr)
                return 2
            print(f"OK: EPUB skapad: {output}")

        if "pdf" in formats:
            pdf = output_dir / f"{base_name}.pdf"
            if shutil.which("xelatex") is None:
                print("ERROR: xelatex krävs för PDF-bygget.", file=sys.stderr)
                return 2

            font_dir = find_texgyre_pagella()
            pandoc_font_args: list[str] = []
            if font_dir is not None:
                pandoc_font_args = ["--variable", f"pdf-font-dir={font_dir.as_posix()}/"]
                print(f"OK: använder TeX Gyre Pagella OTF-filer från {font_dir}")
            else:
                print("VARNING: exakta TeX Gyre Pagella OTF-filer hittades inte; försöker med installerad fontfamilj.")

            command = [
                "pandoc",
                *[str(path) for path in prepared],
                "--from=markdown",
                "--to=pdf",
                "--pdf-engine=xelatex",
                "--output", str(pdf),
                "--metadata-file", str(metadata_path),
                "--template", str(root / "publishing/pdf-template.tex"),
                "--lua-filter", str(root / "publishing/pdf-filter.lua"),
                "--variable", f"cover-path={cover_path.as_posix()}",
                *pandoc_font_args,
                "--top-level-division=chapter",
            ]
            subprocess.run(command, cwd=root, check=True)
            if not pdf.exists() or pdf.stat().st_size < 10_000:
                print("ERROR: PDF-bygget gav ingen giltig PDF-fil.", file=sys.stderr)
                return 2
            print(f"OK: PDF skapad: {pdf}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
