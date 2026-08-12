# Publicering med GitHub Actions

Detta projekt har GitHub Actions-stöd för validering, preview-bygge och release-bygge.

## Struktur

`.github/` ligger i repositoryts rot, på samma nivå som `README.md`.

```text
.github/workflows/01-validate.yml
.github/workflows/02-build-preview.yml
.github/workflows/03-release.yml
scripts/validate_project.py
scripts/build_book.py
publishing/metadata.yaml
publishing/epub.css
publishing/fix-epub-after-pandoc.py
publishing/pdf-template.tex
publishing/pdf-filter.lua
```

## Workflows

- **Validate** körs vid pull request och push till `main`.
- **Build Preview** körs manuellt via `workflow_dispatch` och laddar upp ett gemensamt artifact med EPUB och PDF.
- **Release** körs när en tagg som börjar med `v` pushas, till exempel `v1.0.0`, och publicerar EPUB/PDF som separata release assets.

## Byggprincip

- Källan är `kapitel/kapitel-01.md` till `kapitel/kapitel-32.md`.
- Kapitelnoteringar efter kapitlets avskiljare exporteras inte.
- EPUB byggs med omslag och utan inledande synlig innehållsförteckning i bokflödet.
- PDF byggs med omslag, titelsida och klickbar innehållsförteckning.
- Pandoc är låst till version `3.1.11.1`.
- PDF byggs med XeLaTeX och TeX Gyre Pagella.
