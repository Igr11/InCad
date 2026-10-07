#!/bin/zsh
# Exit 0 when the macOS screen is locked (real mouse/keyboard input and keyboard-focus tests fail then — black
# screenshots, focus None — the user's Mac locks when they leave). Usage: tests/screen_locked.sh && echo locked
ioreg -n Root -d1 -a 2>/dev/null | grep -A1 CGSSessionScreenIsLocked | grep -q '<true/>'
