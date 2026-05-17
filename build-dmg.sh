#!/bin/bash
# CTM Companion DMG Builder
# Usage: cd /Users/jasonsmith/ctm-companion && bash build-dmg.sh

set -e

echo "🔨 Building CTM Companion DMG..."
echo ""

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXECUTABLE=".build/release/CTMCompanion"
APP_BUNDLE="CTMCompanion.app"
APP_DIR="$APP_BUNDLE/Contents/MacOS"
DMG_NAME="CTMCompanion-1.0.dmg"
FINAL_DMG="/Users/jasonsmith/$DMG_NAME"

# Step 1: Build release version
echo "📦 Step 1: Building release version..."
swift build -c release 2>&1 | tail -3

# Step 2: Create app bundle
echo ""
echo "📦 Step 2: Creating app bundle..."
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_DIR"
mkdir -p "$APP_BUNDLE/Contents/Resources"
cp "$EXECUTABLE" "$APP_DIR/CTMCompanion"
chmod +x "$APP_DIR/CTMCompanion"

# Copy resource bundle with scripts
RESOURCE_BUNDLE=".build/release/CTMCompanion_CTMCompanion.bundle"
if [ -d "$RESOURCE_BUNDLE" ]; then
    cp -R "$RESOURCE_BUNDLE" "$APP_BUNDLE/Contents/Resources/"
    echo "✅ Resource bundle copied"
fi

# Copy app icon
if [ -f "Sources/CTMCompanion/Resources/AppIcon.png" ]; then
    cp "Sources/CTMCompanion/Resources/AppIcon.png" "$APP_BUNDLE/Contents/Resources/"
    echo "✅ App icon copied"
fi

# Code sign the app (required for macOS Gatekeeper)
echo "📦 Step 2b: Code signing app..."
codesign -s - "$APP_BUNDLE" -f 2>&1 | grep -E "replacing|error" || echo "✅ App signed"

# Create Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key>
	<string>en</string>
	<key>CFBundleExecutable</key>
	<string>CTMCompanion</string>
	<key>CFBundleIdentifier</key>
	<string>com.ctm.companion</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>CTM Companion</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon.png</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>LSMinimumSystemVersion</key>
	<string>14.0</string>
	<key>NSHumanReadableCopyright</key>
	<string>CTM Companion - Professional macOS companion app for CTM users</string>
	<key>NSPrincipalClass</key>
	<string>NSApplication</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSSupportsAutomaticGraphicsSwitching</key>
	<true/>
</dict>
</plist>
EOF

echo "✅ App bundle created"

# Step 3: Create DMG
echo ""
echo "📦 Step 3: Creating DMG..."
DMG_DIR="/tmp/ctm-dmg-build"
rm -rf "$DMG_DIR" "$FINAL_DMG"
mkdir -p "$DMG_DIR"

cp -R "$APP_BUNDLE" "$DMG_DIR/"
ln -s /Applications "$DMG_DIR/Applications"

hdiutil create \
  -volname "CTM Companion" \
  -srcfolder "$DMG_DIR" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  "$FINAL_DMG" 2>&1 | grep -E "created:|failed:" || echo "✅ DMG created"

# Verify
echo ""
echo "✅ Verification:"
ls -lh "$FINAL_DMG"

# Final summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 DMG Build Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "File:    $FINAL_DMG"
echo "Size:    $(du -h "$FINAL_DMG" | cut -f1)"
echo "Ready for distribution: ✅"
echo ""
echo "To distribute:"
echo "  1. Share: $FINAL_DMG"
echo "  2. Share: /Users/jasonsmith/DISTRIBUTION.md"
echo "  3. Users: Double-click → Drag to Applications → Run"
echo ""
