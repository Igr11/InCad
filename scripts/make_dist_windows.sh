#!/bin/zsh
# Builds the Windows test build: Distrib/InCad-<version>-<date>-<commit>-Windows-x64-UNTESTED/ with the InCad module,
# install.bat / uninstall.bat (+ their .ps1 and the FreeCAD probe), the Windows README, CHANGES and the manuals,
# and the .zip of that folder next to it. UNTESTED until it has been run on a real Windows computer.
# Text files for Windows get CRLF line ends (cmd.exe needs them in .bat files).
set -e
REPO="${0:A:h:h}"
cd "$REPO"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' InCad/incad/__init__.py)
NAME="InCad-${VER}-$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)-Windows-x64-UNTESTED"
for f in scripts/dist/CHANGES.txt scripts/dist/CHANGES_ru.txt; do  # every build says what changed
  grep -qx "$VER" "$f" || { echo "ERROR: $f has no section for $VER: add its improvements and bug fixes first"; exit 1; }
done
# the Addon Manager reads package.xml: its version follows the module's
grep -q "<version>$VER</version>" package.xml || { echo "ERROR: package.xml says another version than $VER"; exit 1; }
[[ -n "$(git status --porcelain -- InCad scripts/windows)" ]] && echo "NOTE: uncommitted changes go into the build"
OUT="$REPO/Distrib"
STAGE="$(mktemp -d)"  # built on the system disk: an external (exFAT) disk adds ._ files to every copy
trap 'rm -rf "$STAGE"' EXIT
export COPYFILE_DISABLE=1
D="$STAGE/$NAME"
mkdir -p "$D"
rsync -a --exclude "__pycache__" --exclude "._*" --exclude ".DS_Store" --exclude "*.pyc" InCad/ "$D/InCad/"
for f in install.bat install.ps1 uninstall.bat uninstall.ps1 freecad_probe.py; do cp scripts/windows/$f "$D/"; done
sed "s/VERSION/$NAME/g" scripts/dist/README_windows.txt > "$D/README.txt"
sed "s/VERSION/$NAME/g" scripts/dist/README_windows_ru.txt > "$D/README_ru.txt"
sed "s/VERSION/$NAME/g" scripts/dist/CHANGES.txt > "$D/CHANGES.txt"
sed "s/VERSION/$NAME/g" scripts/dist/CHANGES_ru.txt > "$D/CHANGES_ru.txt"
cp LICENSE "$D/LICENSE.txt"
for f in manual presentation; do  # the Windows editions (Ctrl, install.bat, %LOCALAPPDATA%), under the usual names
  for suffix in "" _ru; do
    src=scripts/dist/InCad-$f-windows$suffix.pdf
    [[ -f $src ]] || { echo "ERROR: $src is missing (scripts/print_manual.sh, scripts/make_presentation.sh)"; exit 1; }
    cp $src "$D/InCad-$f$suffix.pdf"
  done
done
for f in "$D"/*.bat "$D"/*.ps1 "$D"/*.txt; do perl -pi -e 's/\r?\n/\r\n/' "$f"; done
perl -ne 'if (/[^\x00-\x7F]/) { print "$ARGV:$.: not ASCII\n"; $bad = 1 } END { exit $bad }' "$D"/*.bat "$D"/*.ps1 \
  || { echo "ERROR: .bat/.ps1 must be ASCII (Windows PowerShell reads them as ANSI)"; exit 1; }
xattr -cr "$D"
(cd "$STAGE" && zip -qrX "$NAME.zip" "$NAME" -x "*/._*" "*/.DS_Store")
mkdir -p "$OUT"
rm -rf "$OUT/$NAME" "$OUT/$NAME.zip"
cp "$STAGE/$NAME.zip" "$OUT/"
(cd "$OUT" && unzip -q "$NAME.zip" && find "$NAME" -name "._*" -delete)
echo "$OUT/$NAME.zip"
unzip -l "$OUT/$NAME.zip" | tail -1
