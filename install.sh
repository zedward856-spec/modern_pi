#!/bin/bash

echo "🚀 Starting Modern Pi Desktop Restoration..."

# 1. Install dependencies
echo "📦 Installing required packages..."
sudo apt-get update
sudo apt-get install -y rofi papirus-icon-theme python3-gi gir1.2-gtk-3.0

# 2. Create target directories
echo "📁 Preparing directory structures..."
mkdir -p ~/.config/rofi
mkdir -p ~/.config/wf-panel-pi
mkdir -p ~/.config/openbox
mkdir -p ~/.local/bin
mkdir -p ~/.local/share/icons/Papirus
mkdir -p ~/.icons/Papirus

# 3. Copy files to their correct locations
echo "📥 Restoring configuration files and scripts..."
cp -r config/rofi/* ~/.config/rofi/ 2>/dev/null
cp -r config/wf-panel-pi/* ~/.config/wf-panel-pi/ 2>/dev/null
cp config/openbox/rc.xml ~/.config/openbox/rc.xml 2>/dev/null
cp -r local/share/icons/Papirus/* ~/.local/share/icons/Papirus/ 2>/dev/null
cp -r icons/Papirus/* ~/.icons/Papirus/ 2>/dev/null
cp -r bin/* ~/.local/bin/ 2>/dev/null

# 4. Make scripts executable
echo "⚙️  Setting permissions..."
chmod +x ~/.local/bin/*.py

# 5. Restart panel to apply changes
echo "🔄 Refreshing the desktop environment..."
pkill wf-panel-pi || true
openbox --reconfigure || true
# Wayfire configs usually apply immediately, but we restart the panel just to be safe.

echo "✅ Setup complete! Your Pi is now back to its custom modern state!"
