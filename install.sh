#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ $# -lt 1 ]; then
  echo "Uso: $0 <nombre-de-app>"
  echo "Apps disponibles:"
  ls -1 "$ROOT/apps"
  exit 1
fi
APP="$1"
if [ ! -d "$ROOT/apps/$APP" ]; then
  echo "App no encontrada: $APP" >&2
  exit 1
fi
exec "$ROOT/apps/$APP/install.sh"