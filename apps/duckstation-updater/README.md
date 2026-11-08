# DuckStation Updater

Comprueba e instala la última compilación oficial de DuckStation (AppImage).

## Uso

```bash
duckstation-updater              # abre la ventana
duckstation-updater --check      # 0 = al día, 10 = hay actualización, 2 = error
duckstation-updater --json       # como --check pero en JSON
duckstation-updater --update     # descarga e instala
duckstation-updater --integration # (re)crea lanzador, icono y acceso al menú
duckstation-updater --bios       # BIOS detectadas
duckstation-updater --import-bios FICHERO
duckstation-updater --disc FICHERO
```

## Variables de entorno

- `DUCKSTATION_APPIMAGE` (default `~/Applications/DuckStation.AppImage`)
- `DUCKSTATION_DATA` (default `~/.local/share/duckstation`)
- `XDG_CONFIG_HOME`, `XDG_DATA_HOME`