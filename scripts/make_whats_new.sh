#!/bin/zsh
# Renders the What's New slides (docs/whats_new: make_slides.py RU, make_slides_en.py EN; pictures in img/, shot in the
# app) with the presentation's WebKit tools into scripts/dist/InCad-whats-new_ru.pdf and _en.pdf.
set -e
REPO="${0:A:h:h}"
P="$REPO/docs/whats_new"
T="$REPO/docs/presentation/tools"
W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
for lang in ru en; do
  gen="$P/make_slides.py"; [[ $lang == en ]] && gen="$P/make_slides_en.py"
  python3 -B "$gen" "$W/$lang" >/dev/null
  cp "$P/img"/*.jpg "$W/$lang/"
  swift "$T/render.swift" "$W/$lang" "$W/$lang.pdf" | tail -1
  title="InnCad — what's new"; [[ $lang == ru ]] && title="InnCad — что нового"
  PDF_TITLE="$title" swift "$T/merge.swift" "$REPO/scripts/dist/InCad-whats-new_$lang.pdf" "$W/$lang.pdf" >/dev/null
  echo "$REPO/scripts/dist/InCad-whats-new_$lang.pdf"
done
