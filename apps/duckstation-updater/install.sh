#!/usr/bin/env bash
set -euo pipefail
APP=duckstation-updater
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/bin ~/.local/share/applications \
  ~/.local/share/icons/hicolor/scalable/apps \
  ~/.local/share/icons/hicolor/256x256/apps
install -m 755 "$HERE/$APP.py" ~/.local/bin/$APP
install -m 644 "$HERE/$APP.svg" ~/.local/share/icons/hicolor/scalable/apps/$APP.svg
[ -f "$HERE/$APP.png" ] && install -m 644 "$HERE/$APP.png" ~/.local/share/icons/hicolor/256x256/apps/$APP.png
sed "s|__HOME__|$HOME|g" "$HERE/$APP.desktop" > ~/.local/share/applications/$APP.desktop
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "$APP instalado. Lánzalo desde el menú o con: $APP"