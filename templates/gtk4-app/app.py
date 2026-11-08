#!/usr/bin/python3
"""__APP_DISPLAY__: esqueleto mínimo GTK4/libadwaita."""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk
import urllib.request

APP_NAME = '__APP_NAME__'
APP_DISPLAY = '__APP_DISPLAY__'
APP_ID = '__APP_ID__'


class Window(Adw.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title=APP_DISPLAY,
                         default_width=480, default_height=320)
        self.set_icon_name(APP_NAME)

        self.status = Gtk.Label(label='Comprobando la conexión…')
        self.status.set_margin_top(24)
        self.set_content(self.status)
        GLib.idle_add(self._check_network)

    def _check_network(self):
        try:
            urllib.request.urlopen('https://www.google.com/generate_204', timeout=5)
            self.status.set_text('En línea. ' + APP_DISPLAY + ' listo.')
        except Exception as exc:  # noqa: BLE001
            self.status.set_text(f'Sin conexión: {exc}')
        return False


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        if not self.get_active_window():
            Window(self).present()


if __name__ == '__main__':
    Application().run()