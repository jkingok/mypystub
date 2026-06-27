#!/bin/bash
#set -e

export SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Configuration Definitions
BUNDLE_ID="au.id.jking.mypystub"
PROJECT_NAME="MyPyStub"
PROJECT_ROOT="$SCRIPT_DIR"

cd "$PROJECT_ROOT"

echo "🔄 Syncing current Python code variations..."
briefcase update ios || exit 1

echo "🏗 Moving to Xcode Workspace..."
cd build/mypystub/ios/xcode/

echo "🔨 Executing native xcodebuild compilation for physical hardware..."
xcodebuild -project "${PROJECT_NAME}.xcodeproj" \
           -scheme "${PROJECT_NAME}" \
           -configuration Debug \
           -destination "generic/platform=iOS" \
           -sdk iphoneos \
           ONLY_ACTIVE_ARCH=NO \
           SYMROOT="$PWD/build" \
           clean build || exit 2

for DEVICE in $(xcrun devicectl list devices -j - | jq -r '.result.devices[] | .identifier'); do
	echo "📲 Moving binary over local network..."
	xcrun devicectl device install app --device "$DEVICE" "build/Debug-iphoneos/MyPyStub.app"

	#echo "🚀 Triggering application launch loop..."
	#xcrun devicectl device process launch --device "$DEVICE" "$BUNDLE_ID"
done
