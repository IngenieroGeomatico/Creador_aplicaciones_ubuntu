# Cómo añadir una aplicación

1. Genera el esqueleto desde la plantilla:

   ```bash
   python3 tools/new_app.py mi-app --display "Mi App"
   ```

   Esto crea `apps/mi-app/` con `mi-app.py`, `mi-app.desktop`, `mi-app.svg` e `install.sh`.

2. Edita `apps/mi-app/mi-app.py` para implementar la funcionalidad.

3. (Opcional) Sustituye `mi-app.svg` por tu icono. Si tienes un PNG, añádelo como `mi-app.png`.

4. Instala y prueba:

   ```bash
   ./install.sh mi-app
   ```

5. Desinstala con:

   ```bash
   apps/mi-app/uninstall.sh
   ```

6. Añade la app al CI: el workflow ya ejecuta `python3 -m compileall` sobre `apps/`, `templates/` y `tools/`, y shellcheck sobre `apps/*/install.sh` y `apps/*/uninstall.sh`. Si tu app añade scripts nuevos, actualiza `.github/workflows/ci.yml`.

## Convenciones

- El nombre (slug) debe ser minúsculas con guiones: `mi-app`.
- Los ficheros se llaman igual que el slug.
- Usa placeholders `__HOME__` en el `.desktop` para la ruta del usuario; el instalador los sustituye.
- No subas binarios grandes ni datos con licencias restrictivas.