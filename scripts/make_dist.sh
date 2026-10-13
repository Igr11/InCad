#!/bin/zsh
# Builds the macOS (Apple Silicon) test build: Distrib/InCad-<version>-<date>-<commit>-macOS-arm64/
# with the InCad module, README.txt, CHANGES.txt, the presentation and the user manual (English and Russian files),
# and the .zip of that folder next to it.
# Only the module goes in: no tests, docs, caches or macOS metadata files.
set -e
REPO="${0:A:h:h}"
cd "$REPO"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' InCad/incad/__init__.py)
NAME="InCad-${VER}-$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)-macOS-arm64"
for f in scripts/dist/CHANGES.txt scripts/dist/CHANGES_ru.txt; do  # every build says what changed
  grep -qx "$VER" "$f" || { echo "ERROR: $f has no section for $VER: add its improvements and bug fixes first"; exit 1; }
done
[[ -n "$(git status --porcelain -- InCad)" ]] && echo "NOTE: InCad/ has uncommitted changes; they go into the build"
OUT="$REPO/Distrib"
STAGE="$(mktemp -d)"  # built on the system disk: an external (exFAT) disk adds ._ files to every copy
trap 'rm -rf "$STAGE"' EXIT
export COPYFILE_DISABLE=1
mkdir -p "$STAGE/$NAME"
rsync -a --exclude "__pycache__" --exclude "._*" --exclude ".DS_Store" --exclude "*.pyc" InCad/ "$STAGE/$NAME/InCad/"
sed "s/VERSION/$NAME/g" scripts/dist/README.txt > "$STAGE/$NAME/README.txt"
sed "s/VERSION/$NAME/g" scripts/dist/README_ru.txt > "$STAGE/$NAME/README_ru.txt"
sed "s/VERSION/$NAME/g" scripts/dist/CHANGES.txt > "$STAGE/$NAME/CHANGES.txt"
sed "s/VERSION/$NAME/g" scripts/dist/CHANGES_ru.txt > "$STAGE/$NAME/CHANGES_ru.txt"
for f in InCad-presentation.pdf InCad-presentation_ru.pdf InCad-manual.pdf InCad-manual_ru.pdf; do  # one language each
  [[ -f scripts/dist/$f ]] || { echo "ERROR: scripts/dist/$f is missing (scripts/make_presentation.sh, scripts/print_manual.sh)"; exit 1; }
  cp scripts/dist/$f "$STAGE/$NAME/"
done
xattr -cr "$STAGE/$NAME"
(cd "$STAGE" && zip -qrX "$NAME.zip" "$NAME" -x "*/._*" "*/.DS_Store")
mkdir -p "$OUT"
rm -rf "$OUT/$NAME" "$OUT/$NAME.zip"
cp "$STAGE/$NAME.zip" "$OUT/"
(cd "$OUT" && unzip -q "$NAME.zip" && find "$NAME" -name "._*" -delete)
echo "$OUT/$NAME.zip"
unzip -l "$OUT/$NAME.zip" | tail -1
