#!/bin/zsh
# Builds the real-input tools (CGEvent mouse/keyboard) into tests/real/bin (git-ignored).
HERE="${0:A:h}"
mkdir -p "$HERE/bin"
for t in click move keys; do
  swiftc -O "$HERE/tools/$t.swift" -o "$HERE/bin/$t" || exit 1
done
echo "built: $HERE/bin/{click,move,keys}"
