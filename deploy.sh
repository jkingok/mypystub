#!/bin/bash
set -e

export SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

source "${SCRIPT_DIR}/env"

# Configuration Definitions
TARGET_UDID="0FD48B24-D64E-5EBD-8F16-58A7D14A4CFD"
BUNDLE_ID="au.id.jking.mypystub"
PROJECT_ROOT="/Users/joshua/beeware-tutorial/mypystub"

cd "$PROJECT_ROOT"

echo "🔄 Syncing current Python code variations..."
briefcase update ios

echo "🏗 Moving to Xcode Workspace..."
cd build/mypystub/ios/xcode/

echo "🔨 Executing native xcodebuild compilation for physical hardware..."
xcodebuild -project "MyPyStub.xcodeproj" \
           -scheme "MyPyStub" \
           -configuration Debug \
           -destination "generic/platform=iOS" \
           -sdk iphoneos \
           ONLY_ACTIVE_ARCH=NO \
           SYMROOT="$PWD/build" \
           clean build

echo "📲 Moving binary over local network..."
xcrun devicectl device install app --device "$TARGET_UDID" "build/Debug-iphoneos/MyPyStub.app"

echo "🚀 Triggering application launch loop..."
xcrun devicectl device process launch --device "$TARGET_UDID" "$BUNDLE_ID"

echo "✔ Application updated and running smoothly!"
