#!/usr/bin/python3
"""DuckStation Updater: comprueba e instala la última compilación oficial de DuckStation.

Interfaz gráfica GTK4/libadwaita y también modo consola:

  duckstation-updater              abre la ventana
  duckstation-updater --check      comprueba y sale (0 = al día, 10 = hay actualización, 2 = error)
  duckstation-updater --json       como --check pero en JSON
  duckstation-updater --update     descarga e instala la última versión
  duckstation-updater --integration  (re)crea lanzador, icono y acceso al menú
  duckstation-updater --bios       muestra las BIOS detectadas
  duckstation-updater --import-bios FICHERO   valida y copia una BIOS
  duckstation-updater --disc FICHERO          detecta la región de un disco

El AppImage oficial es la única distribución Linux que mantiene el proyecto
(no hay Flatpak ni snap oficial). La comprobación compara el SHA-256 local con
el que publica la API de GitHub para el asset correspondiente a esta CPU.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

APP_NAME = 'duckstation-updater'
APP_DISPLAY = 'DuckStation Updater'

API = 'https://api.github.com/repos/stenzek/duckstation/releases/latest'
USER_AGENT = 'duckstation-updater/1.0 (+https://www.duckstation.org/)'
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / APP_NAME
CONFIG_FILE = CONFIG_DIR / 'config.json'
DEFAULT_APPIMAGE = Path(os.environ.get('DUCKSTATION_APPIMAGE') or (Path.home() / 'Applications' / 'DuckStation.AppImage')).expanduser()
LAUNCHER = Path.home() / '.local' / 'bin' / 'duckstation'
ICON_URL = 'https://www.duckstation.org/assets/img/duck.svg'
ICON_DIR = Path.home() / '.local' / 'share' / 'icons' / 'hicolor' / 'scalable' / 'apps'
ICON_FILE = ICON_DIR / 'duckstation.svg'
APPS_DIR = Path.home() / '.local' / 'share' / 'applications'
DESKTOP_FILE = APPS_DIR / 'duckstation.desktop'

LAUNCHER_TEXT = '''#!/usr/bin/env bash
# Lanzador de DuckStation creado por DuckStation Updater.
# Sin FUSE 2 el AppImage se ejecuta extrayéndose automáticamente.
set -euo pipefail
APP="${DUCKSTATION_APPIMAGE:-__APPIMAGE__}"
if [ ! -x "$APP" ]; then
  echo "No se encuentra $APP. Instálalo con DuckStation Updater." >&2
  exit 1
fi
if ldconfig -p 2>/dev/null | grep -q 'libfuse\\.so\\.2'; then
  exec "$APP" "$@"
fi
exec "$APP" --appimage-extract-and-run "$@"
'''

DESKTOP_TEXT = '''[Desktop Entry]
Type=Application
Name=DuckStation
GenericName=PlayStation Emulator
Comment=Emulador de PlayStation 1
Exec=__LAUNCHER__ %f
Icon=duckstation
Terminal=false
Categories=Game;Emulator;
Keywords=ps1;playstation;emulator;duckstation;
StartupWMClass=duckstation-qt
'''

FALLBACK_ICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#1c1c1c"/>
<text x="32" y="43" font-size="24" text-anchor="middle" fill="#ffffff"
 font-family="sans-serif" font-weight="bold">PS</text></svg>
'''

# --------------------------------------------------------------------------- BIOS

_DATA_BASE = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
DATA_DIR = Path(os.environ.get('DUCKSTATION_DATA') or (_DATA_BASE / 'duckstation')).expanduser()
BIOS_DIR = DATA_DIR / 'bios'
BIOS_SIZES = {0x80000: 'PS1', 0x400000: 'PS2', 0x3E66F0: 'PS3'}
REGION_NAMES = {'US': 'USA (NTSC-U)', 'EU': 'Europa (PAL)', 'JP': 'Japón (NTSC-J)'}

# MD5 de las BIOS de PS1 reconocidas por DuckStation (src/core/bios.cpp).
# Se comparan los 512 KiB completos; el nombre del fichero es indiferente.
BIOS_TABLE = [
    ('SCPH-1000, DTL-H1000 (v1.0)', 'JP', '239665b1a3dade1b5a52c06338011044'),
    ('SCPH-1001, 5003, DTL-H1201, H3001 (v2.2)', 'US', '924e392ed05558ffdb115408c263dccf'),
    ('SCPH-1002, DTL-H1002 (v2.0)', 'EU', '54847e693405ffeb0359c6287434cbef'),
    ('SCPH-1002, DTL-H1102 (v2.1)', 'EU', '417b34706319da7cf001e76e40136c23'),
    ('SCPH-1002, DTL-H1202, H3002 (v2.2)', 'EU', 'e2110b8a2b97a8e0b857a45d32f7e187'),
    ('DTL-H1100 (v2.2)', 'JP', 'ca5cfc321f916756e3f0effbfaeba13b'),
    ('SCPH-3000, DTL-H1000H (v1.1)', 'JP', '849515939161e62f6b866f6853006780'),
    ('SCPH-1001, DTL-H1001 (v2.0)', 'US', 'dc2b9bf8da62ec93e868cfd29f0d067d'),
    ('SCPH-3500 (v2.1)', 'JP', 'cba733ceeff5aef5c32254f1d617fa62'),
    ('SCPH-1001, DTL-H1101 (v2.1)', 'US', 'da27e8b6dab242d8f91a9b25d80c63b8'),
    ('SCPH-5000, DTL-H1200, H3000 (v2.2)', 'JP', '57a06303dfa9cf9351222dfcbb4a29d9'),
    ('SCPH-5500 (v3.0)', 'JP', '8dd7d5296a650fac7319bce665a6a53c'),
    ('SCPH-5501, 5503, 7003 (v3.0)', 'US', '490f666e1afb15b7362b406ed1cea246'),
    ('SCPH-5502, 5552 (v3.0)', 'EU', '32736f17079d0b2b7024407c39bd3050'),
    ('SCPH-7000, 7500, 9000 (v4.0)', 'JP', '8e4c14f567745eff2f0408c8129f72a6'),
    ('SCPH-7000W (v4.1)', 'JP', 'b84be139db3ee6cbd075630aa20a6553'),
    ('SCPH-7001, 7501, 7503, 9001, 9003, 9903 (v4.1)', 'US', '1e68c231d0896b7eadcad1d7d8e76129'),
    ('SCPH-7002, 7502, 9002 (v4.1)', 'EU', 'b9d9a0286c33dc6b7237bb13cd46fdee'),
    ('SCPH-100 (v4.3)', 'JP', '8abc1b549a4a80954addc48ef02c4521'),
    ('SCPH-101 (v4.4)', 'US', '9a09ab7e49b422c007e6d54d7c49b965'),
    ('SCPH-101 (v4.5)', 'US', '6e3735ff4c7dc899ee98981385f6f3d0'),
    ('SCPH-102 (v4.4)', 'EU', 'b10f5e0e3d9eb60e5159690680b1e774'),
    ('SCPH-102 (v4.5)', 'EU', 'de93caec13d1a141a40a79f5c86168d6'),
    ('SCPH-1000R (v4.5)', 'JP', '476d68a94ccec3b9c8303bbd1daf2810'),
]
BIOS_BY_MD5 = {md5: (model, region) for model, region, md5 in BIOS_TABLE}

# Sitios donde suele haber una BIOS ya descargada o copiada de otro emulador.
COMMON_BIOS_DIRS = [
    Path.home() / 'Downloads',
    Path.home() / 'Descargas',
    Path.home() / 'Documents',
    Path.home() / 'Emulation' / 'bios',
    Path.home() / 'roms' / 'bios',
    Path.home() / '.config' / 'retroarch' / 'system',
    Path.home() / '.local' / 'share' / 'retroarch' / 'system',
    Path.home() / '.var' / 'app' / 'org.libretro.RetroArch' / 'config' / 'retroarch' / 'system',
]


def md5_file(path):
    digest = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_bios(path):
    """Valida un fichero de BIOS. Devuelve None si no tiene un tamaño válido."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size not in BIOS_SIZES:
        return None
    info = {
        'path': path,
        'name': path.name,
        'size': size,
        'kind': BIOS_SIZES[size],
        'md5': None,
        'model': None,
        'region': None,
        'known': False,
    }
    try:
        info['md5'] = md5_file(path)
        if info['kind'] == 'PS1':
            with open(path, 'rb') as f:
                header = f.read(0x80)
            if header[0x78:0x80] == b'OpenBIOS':
                info.update(model='OpenBIOS', region='US', known=True)
            elif info['md5'] in BIOS_BY_MD5:
                info['model'], info['region'] = BIOS_BY_MD5[info['md5']]
                info['known'] = True
    except OSError:
        return None
    return info


def scan_bios():
    """BIOS válidas presentes en la carpeta de DuckStation."""
    try:
        entries = sorted(BIOS_DIR.iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        if not entry.is_file():
            continue
        info = inspect_bios(entry)
        if info is not None:
            found.append(info)
    return found


def scan_common_bios():
    """Busca BIOS fuera de la carpeta de DuckStation (un nivel de profundidad)."""
    candidates = []
    for folder in COMMON_BIOS_DIRS:
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_file() or entry.name.startswith('.'):
                continue
            try:
                if entry.stat().st_size not in BIOS_SIZES:
                    continue
            except OSError:
                continue
            info = inspect_bios(entry)
            if info is not None:
                candidates.append(info)
    return candidates


def import_bios(source):
    """Copia una BIOS validada a la carpeta de DuckStation. Devuelve (info, destino)."""
    source = Path(source)
    info = inspect_bios(source)
    if info is None:
        raise ValueError('el fichero no tiene un tamaño de BIOS válido '
                         '(512 KiB para PS1, 4 MiB para PS2)')
    BIOS_DIR.mkdir(parents=True, exist_ok=True)
    destination = BIOS_DIR / source.name
    if destination.exists() and destination.resolve() != source.resolve():
        raise FileExistsError(destination)
    shutil.copy2(source, destination)
    return info, destination


def bios_summary(found):
    if not found:
        return 'No hay BIOS — DuckStation usaría su HLE (no recomendado)'
    if len(found) == 1:
        info = found[0]
        if info['known']:
            return f'{info["name"]} — {info["model"]} · {REGION_NAMES.get(info["region"], info["region"])}'
        return f'{info["name"]} — no reconocida (hash {info["md5"][:8]}…)'
    parts = []
    for info in found:
        region = REGION_NAMES.get(info['region'], info['region']) if info['known'] else 'desconocida'
        parts.append(f'{info["name"]} ({region})')
    return f'{len(found)} BIOS: ' + ', '.join(parts)


# --------------------------------------------------------------------------- disc

DISC_SERIAL = re.compile(rb'(SLUS|SLES|SLPS|SLPM|SCUS|SCES|SIPS|SCPS|SLED)[_-](\d{3})[.](\d{2})')
DISC_REGIONS = {'SLUS': 'US', 'SCUS': 'US', 'SLES': 'EU', 'SCES': 'EU',
                'SLPS': 'JP', 'SLPM': 'JP', 'SIPS': 'JP', 'SCPS': 'JP', 'SLED': 'JP'}


def disc_image(path):
    """Para un .cue devuelve el .bin al que apunta; para el resto, el propio fichero."""
    path = Path(path)
    if path.suffix.lower() == '.cue':
        try:
            text = path.read_text(errors='replace')
        except OSError:
            return path
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith('FILE '):
                name = stripped[5:].strip()
                if name.startswith('"') and '"' in name[1:]:
                    name = name[1:name.index('"', 1)]
                else:
                    name = name.split()[0]
                return path.parent / name
    return path


def disc_region(path):
    """Detecta la región del disco por el serial de SYSTEM.CNF. Devuelve None si no puede."""
    image = disc_image(path)
    try:
        with open(image, 'rb') as f:
            head = f.read(1 << 20)
    except OSError:
        return None
    match = DISC_SERIAL.search(head)
    if not match:
        return None
    serial = match.group(0).decode('ascii').replace('_', '-')
    prefix = match.group(1).decode('ascii')
    return {'serial': serial, 'region': DISC_REGIONS.get(prefix), 'prefix': prefix}


# --------------------------------------------------------------------------- config

def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=1) + '\n')


def appimage_path():
    override = load_config().get('appimage')
    return Path(override).expanduser() if override else DEFAULT_APPIMAGE


# --------------------------------------------------------------------------- helpers

def asset_name():
    machine = platform.machine().lower()
    if machine in ('aarch64', 'arm64'):
        return 'DuckStation-arm64.AppImage'
    if machine.startswith(('armv7', 'armv6', 'armhf')):
        return 'DuckStation-armhf.AppImage'
    try:
        cpuinfo = Path('/proc/cpuinfo').read_text()
    except OSError:
        cpuinfo = ''
    if 'avx2' in cpuinfo:
        return 'DuckStation-x64.AppImage'
    return 'DuckStation-x64-SSE2.AppImage'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            digest.update(chunk)
    return 'sha256:' + digest.hexdigest()


def human_size(n):
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or unit == 'GiB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024


def pretty_date(iso):
    """2026-11-07T03:09:45Z -> 2026-11-07 03:09 UTC"""
    if not iso:
        return 'desconocida'
    return iso.replace('T', ' ').replace('Z', ' UTC')


def fetch_release(timeout=30):
    req = urllib.request.Request(API, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/vnd.github+json',
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.load(response)
    wanted = asset_name()
    for asset in data.get('assets', []):
        if asset.get('name') == wanted:
            return {
                'name': asset['name'],
                'url': asset['browser_download_url'],
                'size': asset['size'],
                'updated': asset.get('updated_at'),
                'digest': asset.get('digest'),
                'published': data.get('published_at'),
            }
    raise RuntimeError(f'la release no incluye {wanted}')


def local_info(path):
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        'size': stat.st_size,
        'sha256': sha256_file(path),
        'mtime': stat.st_mtime,
    }


def compare(local, release):
    """Devuelve 'missing', 'current' o 'update'."""
    if local is None:
        return 'missing'
    if release.get('digest'):
        return 'current' if local['sha256'] == release['digest'] else 'update'
    return 'current' if local['size'] == release['size'] else 'update'


def download(url, destination, expected_digest=None, progress=None, timeout=60):
    """Descarga a `destination` verificando el SHA-256; devuelve el digest."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    digest = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=timeout) as response, open(destination, 'wb') as out:
        total = int(response.headers.get('Content-Length') or 0)
        while True:
            chunk = response.read(1 << 18)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if progress and total:
                progress(min(done / total, 1.0))
    result = 'sha256:' + digest.hexdigest()
    if expected_digest and result != expected_digest:
        raise RuntimeError('el SHA-256 descargado no coincide con el publicado')
    if progress:
        progress(1.0)
    return result


def install(release, path, progress=None):
    """Descarga y sustituye el AppImage de forma atómica."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.part', dir=path.parent)
    os.close(fd)
    try:
        download(release['url'], tmp, release.get('digest'), progress)
        os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_if_changed(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.read_text() == text:
            return False
    except OSError:
        pass
    path.write_text(text)
    path.chmod(mode)
    return True


def ensure_integration(path):
    """Crea lanzador, icono y entrada de menú para el AppImage. Devuelve lo creado."""
    created = []
    if _write_if_changed(LAUNCHER, LAUNCHER_TEXT.replace('__APPIMAGE__', str(path)), 0o755):
        created.append('lanzador')
    if not ICON_FILE.exists():
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(ICON_URL, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as response:
                ICON_FILE.write_bytes(response.read())
        except (OSError, urllib.error.URLError):
            ICON_FILE.write_text(FALLBACK_ICON)
        created.append('icono')
    if _write_if_changed(DESKTOP_FILE,
                         DESKTOP_TEXT.replace('__LAUNCHER__', str(LAUNCHER))):
        created.append('acceso al menú')
    if created:
        for tool in (['update-desktop-database', str(APPS_DIR)],
                     ['gtk-update-icon-cache', '-f', '-t', str(ICON_DIR.parents[1])]):
            try:
                subprocess.run(tool, capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                pass
    return created


def has_fuse2():
    try:
        out = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True).stdout
    except OSError:
        return False
    return 'libfuse.so.2' in out


def launch(path):
    if not path.exists():
        raise RuntimeError(f'no existe {path}')
    if has_fuse2():
        subprocess.Popen([str(path)], start_new_session=True)
    else:
        # Sin FUSE 2 el AppImage se puede ejecutar extrayéndolo.
        subprocess.Popen([str(path), '--appimage-extract-and-run'], start_new_session=True)


# --------------------------------------------------------------------------- CLI

def cli(args):
    path = Path(args.path).expanduser() if args.path else appimage_path()
    if args.bios:
        found = scan_bios()
        print(f'Carpeta: {BIOS_DIR}')
        print(bios_summary(found))
        for info in found:
            region = REGION_NAMES.get(info['region'], 'desconocida') if info['known'] else 'desconocida'
            print(f'  - {info["name"]}: {info["kind"]}, {region}, MD5 {info["md5"]}')
        if not found:
            candidates = scan_common_bios()
            for info in candidates:
                print(f'  candidata fuera de la carpeta: {info["path"]}')
        return 0
    if args.import_bios:
        try:
            info, destination = import_bios(args.import_bios)
        except FileExistsError as exc:
            print(f'error: ya existe {exc}; bórrala o renómbrala antes', file=sys.stderr)
            return 2
        except (OSError, ValueError) as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        print(f'Importada: {destination}')
        print(bios_summary([info]))
        return 0
    if args.disc:
        found = disc_region(args.disc)
        if found is None:
            print('No se pudo detectar la región del disco.', file=sys.stderr)
            return 2
        print(f'Disco: {args.disc}')
        print(f'Serial: {found["serial"]}')
        print(f'Región: {REGION_NAMES.get(found["region"], "desconocida")}')
        bios = [info for info in scan_bios() if info['known']]
        if bios:
            match = [info for info in bios if info['region'] == found['region']]
            print('BIOS compatible: ' + (match[0]['name'] if match else 'no hay una de la misma región'))
        return 0
    if args.integration:
        created = ensure_integration(path)
        print('Integración: ' + (', '.join(created) if created else 'ya estaba todo'))
        return 0
    try:
        release = fetch_release()
        local = local_info(path)
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    status = compare(local, release)
    if args.json:
        print(json.dumps({
            'path': str(path),
            'status': status,
            'installed': local,
            'latest': release,
        }, indent=1))
    else:
        print(f'AppImage:  {path}')
        print(f'Asset:     {release["name"]}')
        print(f'Última:    build del {pretty_date(release["updated"])} ({human_size(release["size"])})')
        if local:
            print(f'Instalado: {human_size(local["size"])} — {local["sha256"][:19]}…')
        else:
            print('Instalado: no encontrado')
        print({'current': 'Al día.', 'update': 'Hay una actualización disponible.',
               'missing': 'DuckStation no está instalado.'}[status])
    if args.update:
        if status == 'current':
            return 0
        last = [-1]
        def show(fraction):
            percent = int(fraction * 100)
            if percent != last[0]:
                last[0] = percent
                print(f'\rDescargando… {percent:3d}%', end='', flush=True)
        install(release, path, show)
        created = ensure_integration(path)
        print('\nInstalado correctamente.')
        if created:
            print('Integración creada: ' + ', '.join(created))
        return 0
    return {'current': 0, 'update': 10, 'missing': 10}[status]


# --------------------------------------------------------------------------- GUI

def gui():
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, GLib, Gtk

    CSS = b'''
    .status-title { font-size: 20px; font-weight: bold; }
    .status-ok { color: #2ec27e; }
    .status-update { color: #e5a50a; }
    .status-missing { color: #e01b24; }
    .mono { font-family: monospace; font-size: 11px; }
    '''

    class Window(Adw.ApplicationWindow):
        def __init__(self, application):
            super().__init__(application=application, title='DuckStation Updater',
                             default_width=620, default_height=680)
            self.set_icon_name(APP_NAME)
            self.path = appimage_path()
            self.release = None
            self.local = None
            self.busy = False
            self._build()

        # ---------------------------------------------------------------- UI

        def _build(self):
            provider = Gtk.CssProvider()
            provider.load_from_data(CSS)
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

            header = Adw.HeaderBar()
            header.set_decoration_layout('minimize,maximize,close')
            refresh = Gtk.Button(icon_name='view-refresh-symbolic', tooltip_text='Comprobar de nuevo')
            refresh.connect('clicked', lambda *_: self.refresh())
            header.pack_start(refresh)

            self.fullscreen_button = Gtk.Button(icon_name='view-fullscreen-symbolic',
                                                tooltip_text='Pantalla completa')
            self.fullscreen_button.connect('clicked', lambda *_: self._toggle_fullscreen())
            header.pack_start(self.fullscreen_button)

            about = Gtk.Button(icon_name='help-about-symbolic', tooltip_text='Acerca de')
            about.connect('clicked', lambda *_: self._about())
            header.pack_end(about)

            self.banner = Adw.Banner(revealed=False)
            self._banner_action = None
            self.banner.connect('button-clicked', self._on_banner_button)

            self.icon = Gtk.Image(icon_name='applications-games-symbolic', pixel_size=72)
            self.icon.set_margin_top(18)
            self.status = Gtk.Label(label='Comprobando…')
            self.status.add_css_class('status-title')
            self.detail = Gtk.Label(label='')
            self.detail.set_wrap(True)
            self.detail.set_justify(Gtk.Justification.CENTER)
            self.detail.add_css_class('dim-label')

            self.progress = Gtk.ProgressBar(show_text=True)
            self.progress.set_visible(False)
            self.progress.set_margin_top(8)

            group = Adw.PreferencesGroup(title='Detalles')
            self.row_path = Adw.ActionRow(title='Archivo')
            pick = Gtk.Button(label='Cambiar…', valign=Gtk.Align.CENTER)
            pick.connect('clicked', lambda *_: self._pick())
            self.row_path.add_suffix(pick)
            self.row_installed = Adw.ActionRow(title='Instalado')
            self.row_latest = Adw.ActionRow(title='Última versión')
            self.row_sha = Adw.ActionRow(title='SHA-256 instalado')
            self.row_sha.add_css_class('mono')
            for row in (self.row_path, self.row_installed, self.row_latest, self.row_sha):
                group.add(row)

            self.primary = Gtk.Button(label='Actualizar')
            self.primary.add_css_class('suggested-action')
            self.primary.add_css_class('pill')
            self.primary.connect('clicked', lambda *_: self.update())
            self.open_button = Gtk.Button(label='Abrir DuckStation')
            self.open_button.add_css_class('pill')
            self.open_button.connect('clicked', lambda *_: self._launch())
            folder = Gtk.Button(label='Abrir carpeta')
            folder.add_css_class('pill')
            folder.connect('clicked', lambda *_: self._open_folder())

            buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                              halign=Gtk.Align.CENTER)
            for button in (self.primary, self.open_button, folder):
                buttons.append(button)

            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            content.set_margin_top(12)
            content.set_margin_bottom(24)
            content.set_margin_start(24)
            content.set_margin_end(24)
            content.append(self.icon)
            content.append(self.status)
            content.append(self.detail)
            content.append(self.progress)
            content.append(group)

            bios_group = Adw.PreferencesGroup(title='BIOS de PlayStation')
            self.row_bios = Adw.ActionRow(title='BIOS detectada')
            import_bios_button = Gtk.Button(label='Importar…', valign=Gtk.Align.CENTER)
            import_bios_button.connect('clicked', lambda *_: self._import_bios_dialog())
            self.row_bios.add_suffix(import_bios_button)
            self.row_bios_folder = Adw.ActionRow(title='Carpeta de BIOS', subtitle=str(BIOS_DIR))
            open_bios_button = Gtk.Button(label='Abrir', valign=Gtk.Align.CENTER)
            open_bios_button.connect('clicked', lambda *_: self._open_bios_folder())
            self.row_bios_folder.add_suffix(open_bios_button)
            self.row_disc = Adw.ActionRow(title='Disco', subtitle='Sin comprobar')
            disc_button = Gtk.Button(label='Comprobar…', valign=Gtk.Align.CENTER)
            disc_button.connect('clicked', lambda *_: self._disc_dialog())
            self.row_disc.add_suffix(disc_button)
            for row in (self.row_bios, self.row_bios_folder, self.row_disc):
                bios_group.add(row)
            content.append(bios_group)

            content.append(buttons)

            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_propagate_natural_width(True)
            scrolled.set_propagate_natural_height(True)
            scrolled.set_child(content)

            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(header)
            toolbar.add_top_bar(self.banner)
            toolbar.set_content(scrolled)
            self.set_content(toolbar)

            self.set_resizable(True)
            self.set_size_request(420, 320)
            self.connect('notify::fullscreened', self._on_fullscreen_changed)

            self._render('checking')
            self._refresh_bios()
            self._scan_common_bios()
            GLib.idle_add(self.refresh)

        def _about(self):
            about = Adw.AboutWindow(
                transient_for=self,
                application_name=APP_DISPLAY,
                application_icon=APP_NAME,
                developer_name='Hecho para uso local',
                version='1.0',
                comments='Comprueba e instala la última compilación oficial de DuckStation.\n'
                         'DuckStation se distribuye en Linux únicamente como AppImage.',
                website='https://www.duckstation.org/',
                license_type=Gtk.License.MIT_X11,
            )
            about.present()

        def _error(self, message):
            self.banner.set_title(message)
            self.banner.set_revealed(True)

        # ------------------------------------------------------------ actions

        def _pick(self):
            dialog = Gtk.FileDialog(title='Elegir AppImage de DuckStation')
            dialog.open(self, None, self._picked)

        def _picked(self, dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            self.path = Path(file.get_path())
            config = load_config()
            config['appimage'] = str(self.path)
            save_config(config)
            self.refresh()

        def _open_folder(self):
            folder = self.path.parent if self.path.parent.exists() else Path.home()
            subprocess.Popen(['xdg-open', str(folder)], start_new_session=True)

        def _toggle_fullscreen(self):
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()

        def _on_fullscreen_changed(self, *_):
            if self.is_fullscreen():
                self.fullscreen_button.set_icon_name('view-restore-symbolic')
                self.fullscreen_button.set_tooltip_text('Salir de pantalla completa')
            else:
                self.fullscreen_button.set_icon_name('view-fullscreen-symbolic')
                self.fullscreen_button.set_tooltip_text('Pantalla completa')

        def _launch(self):
            try:
                launch(self.path)
            except (OSError, RuntimeError) as exc:
                self._error(str(exc))

        # -------------------------------------------------------------- BIOS

        def _refresh_bios(self):
            found = scan_bios()
            self._bios_found = found
            self.row_bios.set_subtitle(bios_summary(found))
            self.row_bios_folder.set_subtitle(str(BIOS_DIR))

        def _scan_common_bios(self):
            if scan_bios():
                return
            candidates = scan_common_bios()
            if not candidates:
                return
            first = candidates[0]
            self._bios_candidate = first
            self.banner.set_title(
                f'Se encontró una BIOS en {first["path"].parent}: {first["name"]}')
            self.banner.set_button_label('Importar')
            self._banner_action = lambda: self._do_import(first['path'])
            self.banner.set_revealed(True)

        def _on_banner_button(self, *_):
            action = self._banner_action
            self._banner_action = None
            self.banner.set_button_label(None)
            self.banner.set_revealed(False)
            if action is not None:
                action()

        def _error(self, message, button=None, action=None):
            self.banner.set_title(message)
            if button and action:
                self.banner.set_button_label(button)
                self._banner_action = action
            else:
                self.banner.set_button_label(None)
                self._banner_action = None
            self.banner.set_revealed(True)

        def _import_bios_dialog(self):
            dialog = Gtk.FileDialog(title='Importar BIOS de PlayStation')
            filter_all = Gtk.FileFilter()
            filter_all.set_name('BIOS (*.bin, *.rom)')
            filter_all.add_suffix('bin')
            filter_all.add_suffix('rom')
            filter_all.add_suffix('img')
            dialog.set_default_filter(filter_all)
            dialog.open(self, None, self._bios_picked)

        def _bios_picked(self, dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            self._do_import(Path(file.get_path()))

        def _do_import(self, source):
            try:
                info, destination = import_bios(source)
            except FileExistsError as exc:
                self._confirm_overwrite(Path(exc.args[0]), source)
                return
            except (OSError, ValueError) as exc:
                self._error(f'No se pudo importar la BIOS: {exc}')
                return
            self._refresh_bios()
            if info['known']:
                self.banner.set_title(
                    f'BIOS importada: {info["name"]} — {info["model"]} '
                    f'({REGION_NAMES.get(info["region"], info["region"])})')
            else:
                self.banner.set_title(
                    f'BIOS importada pero no reconocida (hash {info["md5"][:8]}…). '
                    'DuckStation la usará en slow boot.')
            self.banner.set_revealed(True)

        def _confirm_overwrite(self, destination, source):
            dialog = Adw.AlertDialog(
                heading='Sobrescribir BIOS',
                body=f'Ya existe {destination.name}. ¿Quieres reemplazarla?')
            dialog.add_response('cancel', 'Cancelar')
            dialog.add_response('overwrite', 'Sobrescribir')
            dialog.set_response_appearance('overwrite', Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.connect('response', lambda d, r: self._overwrite_response(r, destination, source))
            dialog.present(self)

        def _overwrite_response(self, response, destination, source):
            if response != 'overwrite':
                return
            try:
                destination.unlink()
                info, destination = import_bios(source)
            except (OSError, ValueError) as exc:
                self._error(f'No se pudo importar la BIOS: {exc}')
                return
            self._refresh_bios()
            self.banner.set_title(f'BIOS importada: {destination.name}')
            self.banner.set_revealed(True)

        def _open_bios_folder(self):
            BIOS_DIR.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(['xdg-open', str(BIOS_DIR)], start_new_session=True)

        def _disc_dialog(self):
            dialog = Gtk.FileDialog(title='Comprobar disco')
            dialog.open(self, None, self._disc_picked)

        def _disc_picked(self, dialog, result):
            try:
                file = dialog.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            self._check_disc(Path(file.get_path()))

        def _check_disc(self, path):
            info = disc_region(path)
            if info is None:
                self.row_disc.set_subtitle('No se pudo leer el serial del disco')
                return
            region = REGION_NAMES.get(info['region'], 'desconocida')
            found = [b for b in scan_bios() if b['known']]
            match = [b for b in found if b['region'] == info['region']]
            if match:
                subtitle = f'{info["serial"]} — {region}. BIOS compatible: {match[0]["name"]}'
            elif found:
                subtitle = (f'{info["serial"]} — {region}. '
                            f'No hay BIOS de esa región ({found[0]["name"]})')
            else:
                subtitle = f'{info["serial"]} — {region}. No hay BIOS; se usará HLE.'
            self.row_disc.set_subtitle(subtitle)

        # -------------------------------------------------------------- check

        def refresh(self):
            if self.busy:
                return False
            self.busy = True
            self.primary.set_sensitive(False)
            self._render('checking')
            threading.Thread(target=self._check_worker, daemon=True).start()
            return False

        def _check_worker(self):
            try:
                release = fetch_release()
                local = local_info(self.path)
                status = compare(local, release)
                GLib.idle_add(self._checked, release, local, status)
            except Exception as exc:  # noqa: BLE001 - se muestra al usuario
                GLib.idle_add(self._failed, str(exc))

        def _checked(self, release, local, status):
            self.busy = False
            self.release = release
            self.local = local
            self._render(status)
            return False

        def _failed(self, message):
            self.busy = False
            self._render('error')
            self._error(message)
            return False

        # ------------------------------------------------------------- update

        def update(self):
            if self.busy or self.release is None:
                return
            self.busy = True
            self.was_missing = self.local is None
            self.primary.set_sensitive(False)
            self.progress.set_visible(True)
            self.progress.set_fraction(0.0)
            self.progress.set_text('Descargando…')
            self.banner.set_revealed(False)
            threading.Thread(target=self._update_worker, daemon=True).start()

        def _update_worker(self):
            try:
                def progress(fraction):
                    GLib.idle_add(self._set_progress, fraction)
                install(self.release, self.path, progress)
                created = ensure_integration(self.path)
                GLib.idle_add(self._updated, created)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._update_failed, str(exc))

        def _set_progress(self, fraction):
            self.progress.set_fraction(fraction)
            self.progress.set_text(f'Descargando… {fraction * 100:.0f}%')
            return False

        def _updated(self, created):
            self.busy = False
            self.progress.set_visible(False)
            if getattr(self, 'was_missing', False):
                self.banner.set_title('DuckStation instalado. Ya aparece en el menú de aplicaciones.')
            else:
                self.banner.set_title('DuckStation se ha actualizado correctamente.')
            self.banner.set_revealed(True)
            self.refresh()
            return False

        def _update_failed(self, message):
            self.busy = False
            self.progress.set_visible(False)
            self._render('update')
            self._error(f'No se pudo actualizar: {message}')
            return False

        # ------------------------------------------------------------- render

        def _render(self, status):
            self.row_path.set_subtitle(str(self.path))
            if self.local:
                self.row_installed.set_subtitle(
                    f'{human_size(self.local["size"])} — {self.local["sha256"][:23]}…')
                self.row_sha.set_subtitle(self.local['sha256'])
            else:
                self.row_installed.set_subtitle('no encontrado')
                self.row_sha.set_subtitle('—')
            if self.release:
                self.row_latest.set_subtitle(
                    f'build del {pretty_date(self.release["updated"])} '
                    f'({human_size(self.release["size"])})')
            else:
                self.row_latest.set_subtitle('—')

            self.open_button.set_sensitive(self.local is not None)
            for label in ('status-ok', 'status-update', 'status-missing'):
                self.status.remove_css_class(label)
            self.status.remove_css_class('dim-label')
            self.icon.remove_css_class('status-ok')
            self.icon.remove_css_class('status-update')
            self.icon.remove_css_class('status-missing')

            if status == 'current':
                self.status.set_text('DuckStation está al día')
                self.detail.set_text('Tienes la última compilación publicada.')
                self.status.add_css_class('status-ok')
                self.icon.set_from_icon_name('emblem-ok-symbolic')
                self.primary.set_label('Al día')
                self.primary.set_sensitive(False)
            elif status == 'update':
                self.status.set_text('Hay una actualización disponible')
                self.detail.set_text('Pulsa «Actualizar» para descargar la última compilación.')
                self.status.add_css_class('status-update')
                self.icon.set_from_icon_name('software-update-available-symbolic')
                self.primary.set_label('Actualizar')
                self.primary.set_sensitive(True)
            elif status == 'missing':
                self.status.set_text('DuckStation no está instalado')
                self.detail.set_text('Pulsa «Instalar DuckStation»: se descarga el AppImage oficial '
                                     'y se crea el acceso en el menú de aplicaciones.')
                self.status.add_css_class('status-missing')
                self.icon.set_from_icon_name('dialog-question-symbolic')
                self.primary.set_label('Instalar DuckStation')
                self.primary.set_sensitive(self.release is not None)
            elif status == 'checking':
                self.status.set_text('Comprobando…')
                self.detail.set_text('Consultando la última versión publicada.')
                self.icon.set_from_icon_name('view-refresh-symbolic')
                self.primary.set_sensitive(False)
            else:  # error
                self.status.set_text('No se pudo comprobar')
                self.detail.set_text('Revisa tu conexión a internet e inténtalo de nuevo.')
                self.status.add_css_class('status-missing')
                self.icon.set_from_icon_name('dialog-warning-symbolic')
                self.primary.set_sensitive(False)

    class Application(Adw.Application):
        def __init__(self):
            super().__init__(application_id='io.github.radi.DuckStationUpdater')
            self.window = None

        def do_activate(self):
            if self.window is None:
                self.window = Window(self)
            self.window.present()

    return Application().run([])


# --------------------------------------------------------------------------- main

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='comprobar y salir')
    parser.add_argument('--json', action='store_true', help='salida JSON con --check')
    parser.add_argument('--update', action='store_true', help='descargar e instalar')
    parser.add_argument('--integration', action='store_true',
                        help='(re)crear lanzador, icono y acceso al menú')
    parser.add_argument('--bios', action='store_true', help='mostrar las BIOS detectadas')
    parser.add_argument('--import-bios', metavar='FICHERO',
                        help='validar y copiar una BIOS a la carpeta de DuckStation')
    parser.add_argument('--disc', metavar='FICHERO',
                        help='detectar la región de un disco (.cue/.bin)')
    parser.add_argument('--path', help='ruta del AppImage (por defecto la configurada)')
    args = parser.parse_args(argv)
    if (args.check or args.json or args.update or args.integration
            or args.bios or args.import_bios or args.disc):
        return cli(args)
    return gui()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
