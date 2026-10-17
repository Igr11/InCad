#!/bin/zsh
# Prints the user manual (docs/manual/en.html, ru.html; images in docs/manual/img) to A4 PDFs with WebKit:
# scripts/dist/InCad-manual.pdf and InCad-manual_ru.pdf, plus contact sheets docs/manual/out/{en,ru}.png
# (6 pages per row) for checking the layout. The Windows edition from the same sources (docs/manual/tools/windows.py:
# the Mac parts out, the Windows parts in): scripts/dist/InCad-manual-windows.pdf and InCad-manual-windows_ru.pdf.
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
for lang in en ru; do
  [[ -f "$M/$lang.html" ]] || continue
  suffix=""; [[ $lang == ru ]] && suffix="_ru"
  win="$M/${lang}_windows.html"  # next to the source: the images are found where they are
  python3 -B "$M/tools/windows.py" "$M/$lang.html" "$win"
  out="$REPO/scripts/dist/InCad-manual-windows$suffix.pdf"
  swift "$M/tools/print.swift" "$win" "$out" 2>/dev/null | tail -1
  rm -f "$win"
done
