#!/bin/bash
set -e

echo "Uninstalling DDWriter..."

sudo rm -rf /opt/ddwriter
rm -f ~/.local/share/applications/ddwriter.desktop
rm -f ~/.local/share/icons/hicolor/256x256/apps/ddwriter.png

gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true

echo "DDWriter has been uninstalled."
