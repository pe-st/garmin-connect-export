#!/bin/sh -e
plist_path="garmin-connect-export.cron.plist"
plist_filename=$(basename "$plist_path")
install_path="/Library/LaunchDaemons/$plist_filename"

echo "installing launchctl plist: $plist_path --> $install_path"
sudo cp -f "$plist_path" "$install_path"
sudo chown root "$install_path"
sudo chmod 644 "$install_path"

sudo launchctl unload "$install_path"
sudo launchctl load "$install_path"

echo "to check if it's running, run this command: sudo launchctl list | grep garmin"
echo "to uninstall, run this command: sudo launchctl unload \"$install_path\""

echo "setting execution permission to garmin-connect-export.sh"
sudo chmod +x /Users/cralvarez/Documents/CartoGPS/Data/garmin-connect-export.sh