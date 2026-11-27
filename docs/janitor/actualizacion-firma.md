# Firma de las actualizaciones: lo que hace el dueño a mano

Complementa [`plans/actualizacion-automatica.md`](plans/actualizacion-automatica.md)
(Fase 9, decisión 7.2). Desde la primera versión con actualizador, la app y el paquete de
Arch solo instalan lo que describe un manifiesto firmado con Ed25519. Esa firma depende
de un par de claves que **solo crea y custodia el dueño del proyecto**: ningún agente crea,
ve ni escribe la clave privada.

Mientras no exista la clave pública en el repositorio, todo sigue como hasta la
`v0.21.5-janitor.3`: se publica sin manifiesto, la app se compila sin clave y no se
actualiza sola (avisa y hay que reinstalar a mano).

## 1. Crear el par de claves (una vez, en tu equipo)

```bash
openssl genpkey -algorithm ed25519 -out janitor-update.private.pem
```

```bash
openssl pkey -in janitor-update.private.pem -pubout -out update-key.pem
```

- `janitor-update.private.pem` es la clave **privada**. No se sube al repositorio ni se
  pega en ningún chat. Guarda una copia fuera de GitHub (gestor de contraseñas o un
  soporte desconectado): si se pierde, hay que publicar una app con clave nueva e
  instalarla a mano en cada equipo.
- `update-key.pem` es la clave **pública**. Empieza por `-----BEGIN PUBLIC KEY-----`.

## 2. Guardar la privada como secreto de un entorno protegido

En GitHub, repositorio `reck74/Janitor-Agent`:

1. **Settings → Environments → New environment**, nombre exacto: `janitor-release`.
2. En ese entorno, **Deployment branches and tags → Selected branches and tags** y añade
   la regla de etiquetas `v*`. Así solo una publicación por etiqueta puede leer el
   secreto. Opcional y recomendable: **Required reviewers** contigo mismo, para aprobar
   cada publicación.
3. En el mismo entorno, **Add environment secret**: nombre `JANITOR_UPDATE_SIGNING_KEY`,
   valor el contenido completo de `janitor-update.private.pem` (con las líneas
   `BEGIN`/`END`).

Con la CLI, desde la carpeta donde está la clave (el valor no pasa por ningún agente):

```bash
gh secret set JANITOR_UPDATE_SIGNING_KEY --env janitor-release --repo reck74/Janitor-Agent < janitor-update.private.pem
```

## 3. Subir la clave pública al repositorio

Copia `update-key.pem` a `apps/desktop-janitor/brand/update-key.pem` y súbela por un PR
normal. Desde ese commit:

- la app compilada lleva esa clave dentro (`brand/app-update-patches.mjs`, parche P22);
- el paquete de Arch la instala en `/usr/lib/janitor-desktop/update-key.pem`;
- el flujo de publicación **exige** el secreto: genera `janitor-update.json`, lo firma,
  comprueba la firma con la clave pública del repositorio y cada archivo contra el
  manifiesto, y solo entonces publica. Si el secreto no es la pareja de la clave pública,
  la publicación falla antes de publicar nada.

Las pruebas rechazan un archivo que no sea una clave pública Ed25519, y comprueban que no
haya ninguna clave privada dentro de `apps/desktop-janitor/`.

## 4. Publicar la primera versión con actualizador y la última instalación manual

1. Sube la versión (`pyproject.toml` y `hermes_cli/__init__.py`), fusiona a `main` y crea
   la etiqueta `v…` (solo tú). El flujo adjunta los archivos y el manifiesto firmado, los
   verifica y **al final** mueve `stable`.
2. En tu equipo (Arch), instala esa versión **a mano por última vez**: descarga el
   paquete de la página de la versión y `sudo pacman -U ./janitor-desktop-bin-…pkg.tar.zst`.
   Las instalaciones hasta la `.3` no traen el actualizador ni la clave. Con AppImage:
   descarga el archivo nuevo y reemplaza el anterior.
3. Abre la app y actualiza el motor desde ella. **Esa vez todavía verás el aviso
   antiguo** («el paquete de la app sigue siendo el viejo…») y tendrás que reabrir
   Janitor a mano: el guion de relevo que corre es el del motor que ya tenías (el de la
   `.3`), no el nuevo. Es la última vez; el motor actualizado ya trae el relevo nuevo.
4. Desde la versión siguiente: al abrir aparece «Hay una versión nueva de Janitor» con
   **Actualizar ahora** y **Más tarde**; en Arch el sistema pide tu contraseña con su
   propio diálogo (polkit). En Ajustes → Acerca de está «Actualizar siempre sin
   preguntar».

## 5. Si la clave privada se filtra o se pierde

Crea un par nuevo (paso 1), cambia el secreto (paso 2) y la clave pública (paso 3), y
publica una versión. Las apps con la clave antigua no aceptarán manifiestos firmados con
la nueva: esa versión hay que instalarla a mano en cada equipo. No hay todavía una
segunda clave fuera de línea que autorice el cambio (propuesta de Codex, decisión 7.2
pendiente).

## Qué no hace nunca el actualizador

- No cambia el origen: solo `https://github.com/reck74/Janitor-Agent`. Ninguna variable
  de entorno ni ajuste cambia el origen ni la clave.
- No pide ni guarda tu contraseña, y nunca ejecuta `sudo`: en Arch la pide el sistema.
- No baja de versión, y no toca el motor si la app nueva no se pudo instalar.
