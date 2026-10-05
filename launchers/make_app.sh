#!/bin/zsh
# Builds "InCad.app" on the Desktop: double-click -> Terminal opens with the project's
# Claude Code session (resumes the latest conversation). Rebuild after editing the .command or icon.
set -e
HERE="${0:A:h}"
APP="$HOME/Desktop/InCad.app"
[[ -f "$HERE/icon/InCad.icns" ]] || /Applications/FreeCAD.app/Contents/Resources/bin/python "$HERE/icon/make_icon.py"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/icon/InCad.icns" "$APP/Contents/Resources/"
cp "$HERE/InCad.command" "$APP/Contents/Resources/incad.command"
chmod +x "$APP/Contents/Resources/incad.command"
cat > "$APP/Contents/MacOS/InCad" <<'SH'
#!/bin/sh
# Hand the .command to Terminal through LaunchServices: no Apple Events, so no permission prompts.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/open -a Terminal "$HERE/../Resources/incad.command"
SH
chmod +x "$APP/Contents/MacOS/InCad"
cat > "$APP/Contents/Info.plist" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key><string>InCad</string>
	<key>CFBundleExecutable</key><string>InCad</string>
	<key>CFBundleIconFile</key><string>InCad</string>
	<key>CFBundleIdentifier</key><string>local.incad.launcher</string>
	<key>CFBundleName</key><string>InCad</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>1.0</string>
	<key>CFBundleVersion</key><string>1</string>
	<key>LSMinimumSystemVersion</key><string>12.0</string>
	<key>LSUIElement</key><true/>
	<key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PL
printf 'APPL????' > "$APP/Contents/PkgInfo"
codesign --force --deep -s - "$APP"
touch "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
echo "OK: $APP"
