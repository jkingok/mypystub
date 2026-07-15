#!/bin/bash -x
#set -e

export SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Configuration Definitions
PROJECT_NAME="$(sed -n -e 's/^formal_name = "\(.*\)"$/\1/p' ${SCRIPT_DIR}/pyproject.toml | sed -e 's/ //g')"
PROJECT_ROOT="${SCRIPT_DIR}"

cd "$PROJECT_ROOT"

echo "🔄 Syncing current Python code variations..."
briefcase update ios || exit 1

echo "🏗 Moving to Xcode Workspace..."
cd build/*/ios/xcode/

echo "🔨 Executing native xcodebuild compilation for physical hardware..."
xcodebuild -project "${PROJECT_NAME}.xcodeproj" \
           -scheme "${PROJECT_NAME}" \
           -configuration Debug \
           -destination "generic/platform=iOS" \
           -sdk iphoneos \
           -allowProvisioningUpdates \
           ONLY_ACTIVE_ARCH=NO \
           SYMROOT="$PWD/build" \
           clean build || exit 2

for DEVICE in $(xcrun devicectl list devices -j - | jq -r '.result.devices[] | .identifier'); do
	echo "📲 Moving binary over local network..."
	xcrun devicectl device install app --device "$DEVICE" "build/Debug-iphoneos/${PROJECT_NAME}.app"
done
