#!/bin/zsh
# Prints the user manual (docs/manual/en.html, ru.html; images in docs/manual/img) to A4 PDFs with WebKit:
# scripts/dist/InCad-manual.pdf and InCad-manual_ru.pdf, plus contact sheets docs/manual/out/{en,ru}.png
# (6 pages per row) for checking the layout.
set -e
REPO="${0:A:h:h}"
M="$REPO/docs/manual"
mkdir -p "$M/out"
for lang in en ru; do
  [[ -f "$M/$lang.html" ]] || continue
  suffix=""; [[ $lang == ru ]] && suffix="_ru"
  out="$REPO/scripts/dist/InCad-manual$suffix.pdf"
  swift "$M/tools/print.swift" "$M/$lang.html" "$out" 2>/dev/null | tail -1
  echo "$lang: $(SHEET_W=420 SHEET_H=594 SHEET_COLS=6 swift "$M/tools/sheet.swift" "$out" "$M/out/$lang.png"), sheet $M/out/$lang.png"
done
