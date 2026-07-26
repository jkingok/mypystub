#!/bin/bash
# 1. Quit Xcode safely if it's running 
osascript -e 'quit app "Xcode"'
# 2. Wipe the local provisioning profile caches
echo "Clearing provisioning profile cache..."
rm -rf ~/Library/Developer/Xcode/UserData/Provisioning\ Profiles/*
rm -rf ~/Library/MobileDevice/Provisioning\ Profiles/*
