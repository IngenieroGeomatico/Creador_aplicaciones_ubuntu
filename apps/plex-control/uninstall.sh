#!/usr/bin/env bash
set -euo pipefail
APP=plex-control
rm -f ~/.local/bin/$APP \
  ~/.local/share/applications/$APP.desktop \
  ~/.local/share/icons/hicolor/scalable/apps/$APP.svg \
  ~/.local/share/icons/hicolor/256x256/apps/$APP.png
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "$APP desinstalado."