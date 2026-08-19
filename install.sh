#!/bin/bash
set -e

INSTALL_DIR="/opt/ddwriter"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing DDWriter..."

# Create install directory
sudo mkdir -p "$INSTALL_DIR"

# Copy files
sudo cp "$SCRIPT_DIR/ddwriter.py" "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR/ddwriter.png" "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/ddwriter.py"

# Update .desktop file with install path
sed "s|Exec=.*|Exec=python3 $INSTALL_DIR/ddwriter.py|" "$SCRIPT_DIR/ddwriter.desktop" > /tmp/ddwriter.desktop

# Install desktop file
mkdir -p ~/.local/share/applications
cp /tmp/ddwriter.desktop ~/.local/share/applications/
rm /tmp/ddwriter.desktop

# Install icon
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
cp "$SCRIPT_DIR/ddwriter.png" ~/.local/share/icons/hicolor/256x256/apps/

# Update icon cache
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true

echo "Installed to $INSTALL_DIR"
echo "DDWriter is now available in your application menu."
