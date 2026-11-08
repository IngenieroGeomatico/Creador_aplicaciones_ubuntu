#!/usr/bin/env python3
"""Control de Plex Media Server: inicia y detiene el servicio snap."""

APP_NAME = 'plex-control'
APP_DISPLAY = 'Control Plex'

import os
import subprocess
import webbrowser
import tkinter as tk
from tkinter import messagebox

def get_status():
    """
    Devuelve True si Plex está activo, False si no.
    Funciona con Snap y detecta correctamente el estado del servicio.
    """
    try:
        output = subprocess.check_output(
            ["snap", "services", "plexmediaserver"], text=True
        )
        # revisamos cada línea para ver si plexmediaserver tiene 'active'
        for line in output.splitlines():
            if line.startswith("plexmediaserver") and ("active" in line or "activo" in line) and not("inactivo" in line or "inactive" in line):
                return True
        return False
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False

def update_status_label():
    if get_status():
        lbl_status.config(text="✅ Plex está ENCENDIDO", fg="green")
    else:
        lbl_status.config(text="🛑 Plex está APAGADO", fg="red")

def start_plex():
    code = os.system("pkexec sh -c 'snap enable plexmediaserver && snap start plexmediaserver'")
    if code == 0:
        messagebox.showinfo("Plex", "✅ Plex Media Server se ha iniciado")
    else:
        messagebox.showerror("Plex", "❌ Error al iniciar Plex o ya está iniciado")
    update_status_label()
    webbrowser.open("http://localhost:32400/web/")

def stop_plex():
    code = os.system("pkexec sh -c 'snap stop plexmediaserver && snap disable plexmediaserver'")
    if code == 0:
        messagebox.showinfo("Plex", "🛑 Plex Media Server detenido")
    else:
        messagebox.showerror("Plex", "❌ Error al detener Plex")
    update_status_label()

# Ventana principal
root = tk.Tk()
root.title(APP_DISPLAY)
root.geometry("350x200")

# (opcional) icono de Plex si lo tienes en /usr/share/icons
try:
    root.iconphoto(False, tk.PhotoImage(file="/usr/share/icons/hicolor/256x256/apps/plex.png"))
except:
    pass

lbl_status = tk.Label(root, text="Comprobando estado...", font=("Arial", 12))
lbl_status.pack(pady=10)

btn_start = tk.Button(root, text="Iniciar Plex", command=start_plex, bg="lightgreen", height=2, width=20)
btn_start.pack(pady=5)

btn_stop = tk.Button(root, text="Detener Plex", command=stop_plex, bg="lightcoral", height=2, width=20)
btn_stop.pack(pady=5)

update_status_label()  # muestra estado inicial

root.mainloop()
