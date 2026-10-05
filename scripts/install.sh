#!/bin/zsh
# Links the InCad module into FreeCAD 1.1's user Mod folder (once). FreeCAD picks up code changes on restart.
set -e
REPO="${0:A:h:h}"
MOD="$HOME/Library/Application Support/FreeCAD/v1-1/Mod"
LINK="$MOD/InCad"
mkdir -p "$MOD"
if [[ -L "$LINK" ]]; then
  [[ "$(readlink "$LINK")" == "$REPO/InCad" ]] && { echo "Already installed: $LINK"; exit 0; }
  echo "❌ $LINK points elsewhere: $(readlink "$LINK")"; exit 1
elif [[ -e "$LINK" ]]; then
  echo "❌ $LINK exists and is not a link; not touching it."; exit 1
fi
ln -s "$REPO/InCad" "$LINK"
echo "Installed: $LINK -> $REPO/InCad"
