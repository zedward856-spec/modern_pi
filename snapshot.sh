#!/bin/bash

echo "📸 Taking a snapshot of current configurations..."

# Create target directories just in case
mkdir -p ~/pi-backup/config/{rofi,wf-panel-pi,openbox,pcmanfm,labwc,gtk-3.0,xsettingsd}
mkdir -p ~/pi-backup/local/share/icons/Papirus
mkdir -p ~/pi-backup/icons/Papirus
mkdir -p ~/pi-backup/bin
mkdir -p ~/pi-backup/Pictures

# Copy current system configurations to the backup repo
echo "📥 Copying files from system to pi-backup..."
cp -r ~/.config/rofi/* ~/pi-backup/config/rofi/ 2>/dev/null
cp -r ~/.config/wf-panel-pi/* ~/pi-backup/config/wf-panel-pi/ 2>/dev/null
cp ~/.config/openbox/rc.xml ~/pi-backup/config/openbox/rc.xml 2>/dev/null
cp -r ~/.config/pcmanfm/* ~/pi-backup/config/pcmanfm/ 2>/dev/null
cp -r ~/.config/labwc/* ~/pi-backup/config/labwc/ 2>/dev/null
cp -r ~/.config/gtk-3.0/* ~/pi-backup/config/gtk-3.0/ 2>/dev/null
cp -r ~/.config/xsettingsd/* ~/pi-backup/config/xsettingsd/ 2>/dev/null
cp -r ~/.local/share/icons/Papirus/* ~/pi-backup/local/share/icons/Papirus/ 2>/dev/null
cp -r ~/.icons/Papirus/* ~/pi-backup/icons/Papirus/ 2>/dev/null
cp -r ~/.local/bin/* ~/pi-backup/bin/ 2>/dev/null
cp -r ~/Pictures/* ~/pi-backup/Pictures/ 2>/dev/null

echo "✅ Snapshot complete! Files have been updated in ~/pi-backup."
echo "If you want to push these changes to GitHub, run:"
echo "cd ~/pi-backup && git add . && git commit -m 'System snapshot' && git push"
