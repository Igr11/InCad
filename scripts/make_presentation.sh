#!/bin/zsh
# Renders docs/presentation (1920x1080 slides, images from img/) with WebKit (tools/render.swift), one PDF per
# language: en/*.html -> scripts/dist/InCad-presentation.pdf, ru/*.html -> scripts/dist/InCad-presentation_ru.pdf.
# With an argument, contact sheets of all pages (PNG, 4 per row) for checking the layout:
# scripts/make_presentation.sh /path/sheet.png  -> /path/sheet_en.png, /path/sheet_ru.png
set -e
REPO="${0:A:h:h}"
P="$REPO/docs/presentation"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
for lang in en ru; do
  mkdir -p "$W/$lang"
  cp "$P/$lang"/*.html "$W/$lang/"
  cp "$P/img"/*.jpg "$W/$lang/"
  suffix=""; [[ $lang == ru ]] && suffix="_ru"
  out="$REPO/scripts/dist/InCad-presentation$suffix.pdf"
  swift "$P/tools/render.swift" "$W/$lang" "$W/$lang.pdf" | tail -1
  title="InCad — presentation"; [[ $lang == ru ]] && title="InCad — презентация"
  PDF_TITLE="$title" swift "$P/tools/merge.swift" "$out" "$W/$lang.pdf" >/dev/null
  if [[ -n "$1" ]]; then swift "$P/tools/sheet.swift" "$out" "${1:r}_$lang.png" >/dev/null; fi
  echo "$out"
  mkdir -p "$W/win_$lang"  # the Windows edition: the same slides through docs/manual/tools/windows.py
  for f in "$P/$lang"/*.html; do python3 -B "$REPO/docs/manual/tools/windows.py" "$f" "$W/win_$lang/${f:t}"; done
  cp "$P/img"/*.jpg "$W/win_$lang/"
  out="$REPO/scripts/dist/InCad-presentation-windows$suffix.pdf"
  swift "$P/tools/render.swift" "$W/win_$lang" "$W/win_$lang.pdf" | tail -1
  PDF_TITLE="$title" swift "$P/tools/merge.swift" "$out" "$W/win_$lang.pdf" >/dev/null
  echo "$out"
done
