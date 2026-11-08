#!/usr/bin/env python3
"""Scaffolder: crea una nueva app en apps/<nombre>/ a partir de templates/gtk4-app/."""

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'templates' / 'gtk4-app'
APPS = ROOT / 'apps'


def slugify(name):
    return re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-')


def camel(name):
    return ''.join(part.capitalize() for part in re.split(r'[-_]+', name) if part)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', help='nombre (slug) de la app, ej. mi-app')
    parser.add_argument('--display', help='nombre visible')
    parser.add_argument('--id', help='application id (reverse DNS)')
    args = parser.parse_args()

    name = slugify(args.name)
    display = args.display or name.replace('-', ' ').title()
    app_id = args.id or f'io.github.radi.{camel(name)}'
    destination = APPS / name
    if destination.exists():
        raise SystemExit(f'Ya existe {destination}')
    if not TEMPLATE.is_dir():
        raise SystemExit(f'No existe la plantilla {TEMPLATE}')

    shutil.copytree(TEMPLATE, destination)

    # Sustituir placeholders en todos los ficheros de texto.
    replacements = {
        '__APP_NAME__': name,
        '__APP_DISPLAY__': display,
        '__APP_ID__': app_id,
    }
    for path in destination.rglob('*'):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for old, value in replacements.items():
            new = new.replace(old, value)
        if new != text:
            path.write_text(new, encoding='utf-8')

    # Renombrar ficheros principales.
    renames = {
        'app.py': f'{name}.py',
        'app.desktop': f'{name}.desktop',
        'icon.svg': f'{name}.svg',
    }
    for old, new in renames.items():
        src = destination / old
        if src.exists():
            src.rename(destination / new)

    install = destination / 'install.sh'
    if install.exists():
        install.chmod(0o755)
    print(f'Creada app "{name}" en {destination}')
    print(f'  Display: {display}')
    print(f'  ID:      {app_id}')
    print(f'Instala con: ./install.sh {name}')


if __name__ == '__main__':
    main()