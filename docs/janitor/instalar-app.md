# Instalar la app de Janitor

Janitor se instala como una app de escritorio. La app, al abrirla por primera
vez, instala el motor en tu carpeta personal (`~/.janitor`) y te deja elegir el
proveedor de IA. No hace falta Docker ni ninguna clave para la instalación base.

> **Pendiente de confirmar en la primera versión publicada.** A fecha de esta guía
> la última versión publicada solo trae el AppImage de Linux. Los nombres de los
> demás archivos (Windows, macOS, Arch, `PKGBUILD`, `SHA256SUMS`) salen del flujo
> de publicación (`.github/workflows/janitor-desktop-release.yml`) y todavía no se
> han visto en una versión publicada. Si no coinciden, manda lo que veas en la
> página de versiones.

¿Tienes un Janitor antiguo instalado por terminal (`~/.janitor/janitor-core`)? La
app no lo adopta y se niega a instalar encima. Desinstálalo primero con
[`desinstalar-instalacion-antigua.md`](desinstalar-instalacion-antigua.md).

## 1. Descargar

Todo está en la página de versiones del proyecto:
<https://github.com/reck74/Janitor-Agent/releases/latest>

| Sistema | Archivo |
|---|---|
| Linux (cualquier distribución, x86_64) | `Janitor-linux-x86_64.AppImage` |
| Arch Linux | `janitor-desktop-bin-<versión>-1-x86_64.pkg.tar.zst` (y su `PKGBUILD`) |
| Windows (x64) | `Janitor-win-x64.exe` |
| macOS (Apple Silicon) | `Janitor-mac-arm64.dmg` |
| macOS (Intel, experimental) | `Janitor-mac-x64.dmg`, solo si aparece en la versión |
| Todos | `SHA256SUMS` (sumas para verificar la descarga) |

En el paquete de Arch, `<versión>` es la etiqueta sin la `v` y con puntos en lugar
de guiones: la etiqueta `v0.21.5-janitor.1` da
`janitor-desktop-bin-0.21.5.janitor.1-1-x86_64.pkg.tar.zst`.

Verifica lo que bajaste antes de ejecutarlo (sección 9).

## 2. Linux (AppImage)

```bash
chmod +x Janitor-linux-x86_64.AppImage
./Janitor-linux-x86_64.AppImage
```

Es un único archivo: déjalo donde quieras (por ejemplo `~/Aplicaciones/`). Para
actualizar la app, reemplázalo por el nuevo.

## 3. Arch Linux (paquete)

```bash
sudo pacman -U ./janitor-desktop-bin-<versión>-1-x86_64.pkg.tar.zst
```

- Aparece en el lanzador de aplicaciones como **Janitor**.
- Desde terminal se abre con `janitor-desktop` (no confundir con `janitor`, que
  es el motor; ver sección 6).
- Opciones extra de Electron: una por línea en
  `~/.config/janitor-desktop-flags.conf` (o `$XDG_CONFIG_HOME/janitor-desktop-flags.conf`).
  Las líneas vacías y las que empiezan por `#` se ignoran. Por ejemplo, para
  Wayland nativo:

  ```text
  --ozone-platform=wayland
  ```

- Desinstalar: `sudo pacman -R janitor-desktop-bin`.

**Alternativa: construirlo tú con `makepkg`.** El `PKGBUILD` de la versión
descarga el AppImage publicado y lo reempaqueta, pero también necesita a su lado
tres archivos del repositorio **de la misma etiqueta** (sus sumas están fijadas en
el `PKGBUILD`), que la versión no adjunta:

```bash
tag=v0.21.5-janitor.1   # la etiqueta de la versión que instalas
mkdir janitor-desktop-bin && cd janitor-desktop-bin
# Copia aquí el PKGBUILD descargado de la versión y después:
base="https://raw.githubusercontent.com/reck74/Janitor-Agent/$tag"
curl -fLO "$base/apps/desktop-janitor/packaging/arch/janitor-desktop.sh"
curl -fLO "$base/apps/desktop-janitor/packaging/arch/Janitor.desktop"
curl -fLO "$base/LICENSE"
makepkg -si
```

> Pendiente de confirmar: en CI el paquete se construye con todos los archivos ya
> presentes; esta vía con la descarga del AppImage desde la versión no se ha
> ensayado.

## 4. Windows

Ejecuta `Janitor-win-x64.exe` y sigue los pasos. Instala para tu usuario: no hace
falta ser administrador. Crea el acceso **Janitor**.

**SmartScreen.** Windows puede detener el instalador con «Windows protegió su PC».
Pulsa **Más información** → **Ejecutar de todas formas**.

Por qué sale el aviso: el instalador **no está firmado**. Firmar en Windows exige
un certificado de pago y este proyecto no lo tiene. Si no te fías, verifica la suma
SHA-256 (sección 9) antes de ejecutarlo.

## 5. macOS

1. Abre `Janitor-mac-arm64.dmg` (Mac con Apple Silicon).
2. Arrastra **Janitor** a **Aplicaciones**.
3. Abre Janitor desde Aplicaciones.

**Gatekeeper.** La primera vez macOS la bloquea. Dos salidas:

- **Ajustes del Sistema → Privacidad y seguridad**, baja hasta el aviso sobre
  Janitor y pulsa **Abrir igualmente**.
- O desde terminal:

  ```bash
  xattr -dr com.apple.quarantine /Applications/Janitor.app
  ```

Por qué: la app lleva una **firma ad hoc** y **no está notarizada** por Apple (eso
exige una cuenta de desarrollador de pago). Gatekeeper bloquea por defecto todo lo
que no está notarizado.

Si el Mac no tiene Git, el instalador del motor puede abrir el diálogo de las
herramientas de línea de comandos de Xcode: acéptalo y, cuando termine, vuelve a
intentar la instalación desde la app.

## 6. Primer arranque

1. **La app instala el motor.** Verás las etapas de la instalación en pantalla.
   El motor queda en `~/.janitor` (en Windows, `%USERPROFILE%\.janitor`):
   configuración, sesiones, memoria y el código del motor en
   `~/.janitor/hermes-agent`.
2. **Eliges el proveedor de IA.** **MiniMax** es el recomendado y viene
   preconfigurado (modelo por defecto `MiniMax-M3`); necesitas tu propia clave
   API de MiniMax. Puedes elegir otro proveedor si lo prefieres.
3. **El navegador no se instala de entrada.** El navegador que usa el agente para
   navegar (Chromium) se descarga la primera vez que el agente lo necesita: esa
   primera navegación tarda bastante más que las siguientes.

Los aplicativos opcionales (Honcho, n8n, LightRAG, NocoDB, WAHA, Firecrawl, Open
Design) no se instalan con la base. Se añaden después, y solo entonces hace falta
Docker.

## 7. El comando `janitor`

La instalación deja también el comando `janitor`:

- Linux y macOS: `~/.local/bin/janitor`.
- Windows: `%USERPROFILE%\.janitor\bin`, añadido a tu `PATH` de usuario.

Abre una terminal **nueva** para que lo encuentre. Usa el mismo home (`~/.janitor`)
y las mismas sesiones que la app:

```bash
janitor                  # Janitor en el terminal
janitor --tui            # la interfaz de pantalla completa
janitor --version
janitor services list    # aplicativos opcionales (necesitan Docker)
```

## 8. Actualizar

- **Solo se publican versiones etiquetadas.** Ni la app ni `janitor update` siguen
  la rama de desarrollo: siguen el canal de versiones publicadas.
- **El motor:** la app comprueba si hay versión nueva y te avisa. Desde terminal:

  ```bash
  janitor update --check   # solo mira
  janitor update           # actualiza
  ```

  Si todavía no hay ninguna versión publicada, lo dice y no toca nada.
- **La app:** si el motor queda más nuevo que la app, la app te lo dice y te
  lleva a la página de versiones. Descarga la nueva y:
  - Linux: reemplaza el AppImage (Arch: `sudo pacman -U` con el paquete nuevo).
  - Windows: ejecuta el instalador nuevo; se instala encima del anterior.
  - macOS: arrastra la nueva Janitor a Aplicaciones y reemplaza la anterior.

  Tus chats y ajustes no se tocan.

## 9. Verificar la descarga

`SHA256SUMS` lleva la suma SHA-256 de cada archivo de la versión. Descárgalo junto
al archivo y compara.

Linux:

```bash
sha256sum -c SHA256SUMS --ignore-missing
```

macOS:

```bash
shasum -a 256 Janitor-mac-arm64.dmg
grep Janitor-mac-arm64.dmg SHA256SUMS
```

Windows (PowerShell):

```powershell
Get-FileHash .\Janitor-win-x64.exe -Algorithm SHA256
Select-String Janitor-win-x64.exe .\SHA256SUMS
```

Las dos sumas tienen que ser iguales (en Windows sale en mayúsculas; da igual). Si
no coinciden, borra la descarga y no la ejecutes.

## 10. Desinstalar

Primero la app:

| Sistema | Cómo |
|---|---|
| Linux (AppImage) | Borra el archivo `Janitor-linux-x86_64.AppImage`. |
| Arch Linux | `sudo pacman -R janitor-desktop-bin` |
| Windows | Configuración → Aplicaciones → Aplicaciones instaladas → **Janitor** → Desinstalar. |
| macOS | Arrastra `/Applications/Janitor.app` a la Papelera. |

Quitar la app **no** borra el motor ni tus datos. Si quieres borrarlo todo:

1. Si instalaste aplicativos opcionales con Docker, quítalos antes, uno por uno:
   `janitor services uninstall <nombre>` (`janitor services list` te dice cuáles
   tienes).
2. Mueve a la papelera la carpeta del motor. **Ahí están tus sesiones, tu memoria
   y tus claves API (`.env`)**: si quieres conservar algo, cópialo antes.
   - Linux y macOS: `~/.janitor` y el comando `~/.local/bin/janitor`.
   - Windows: `%USERPROFILE%\.janitor`, y quita `%USERPROFILE%\.janitor\bin` de tu
     `PATH` de usuario (Configuración → Sistema → Información → Configuración
     avanzada del sistema → Variables de entorno).
