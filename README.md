# Creador de aplicaciones Ubuntu

Repositorio de aplicaciones de escritorio para Ubuntu, con instalador por app y CI.

## Requisitos

- `python3`
- `python3-gi`
- `gir1.2-gtk-4.0`
- `gir1.2-adw-1`

## Uso

Instalar una app concreta:

```bash
./install.sh duckstation-updater
```

Listar apps disponibles:

```bash
./install.sh
```

## Apps incluidas

- `duckstation-updater`: comprueba e instala la última compilación oficial de DuckStation.

## Añadir una app nueva

Ver `docs/how-to-add-an-app.md`. Se puede generar un esqueleto con:

```bash
python3 tools/new_app.py mi-app --display "Mi App"
```