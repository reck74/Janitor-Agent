# Desinstalar el Janitor antiguo (instalado por terminal)

La app de escritorio de Janitor es un **punto cero**: no adopta ni actualiza una
instalación anterior hecha con `bootstrap.sh` / `janitor-install.sh`. Si la app
encuentra `~/.janitor/janitor-core`, se niega a instalar y no toca nada. Hay que
retirar lo antiguo primero y empezar limpio.

> Estos pasos salen de leer los instaladores antiguos. **No se han ensayado en una
> máquina real de punta a punta.** Ningún paso borra datos: lo antiguo se aparta con
> otro nombre y lo eliminas tú cuando compruebes que no lo necesitas.

## 1. Apaga lo que esté corriendo

El bot de mensajería (Telegram) corre como unidad de systemd de usuario. Su nombre
depende del home: con `~/.janitor` suele ser `hermes-gateway-<código>.service`, no
`hermes-gateway.service` a secas (ese es el de un Hermes en `~/.hermes`). No adivines:
lista las que tengas.

```bash
systemctl --user list-unit-files 'hermes-gateway*' 'janitor-*'
```

Para cada `hermes-gateway…` que aparezca, comprueba que es la de Janitor:

```bash
systemctl --user cat <unidad> | grep HERMES_HOME
```

Si dice `.janitor`, apágala y desactívala:

```bash
systemctl --user disable --now <unidad>
```

Una `hermes-gateway…` cuyo `HERMES_HOME` no sea `.janitor` es de otro Hermes: no
la toques. Si la lista sale vacía, no tenías bot. Cierra también cualquier
`janitor` abierto en un terminal.

## 2. Aplicativos con Docker (solo si los usabas)

Honcho, n8n, LightRAG, NocoDB, WAHA y Firecrawl guardan sus datos en volúmenes de
Docker, que **no** se borran con estos pasos.

```bash
docker ps -a --filter name=janitor-
```

Detén los que sean de Janitor. El filtro busca `janitor-` en cualquier parte del
nombre: si la lista anterior muestra algún contenedor que no instaló Janitor,
detén los de Janitor uno a uno (`docker stop <nombre>`) en lugar de usar este
comando. Sirve con cualquier versión antigua (el `janitor services` de las más
viejas puede no existir):

```bash
docker ps -q --filter name=janitor- | xargs -r docker stop
```

Si tenías Honcho como servicio de usuario de systemd, aparece en la lista del
paso 1 como `janitor-honcho.service`; desactívalo igual:

```bash
systemctl --user disable --now janitor-honcho.service
```

Los archivos de despliegue viven en `~/.janitor/docker`. Al apartar el home (paso 3)
los contenedores quedan sin ellos: después de instalar la app nueva se vuelven a
desplegar con `janitor services deploy <nombre>`. **Sin verificar:** que el despliegue
nuevo reencuentre los volúmenes antiguos depende de que coincidan sus nombres, y eso
no se ha comprobado servicio por servicio. Los volúmenes no se borran en ningún caso
(`docker volume ls --filter name=honcho`, por ejemplo, te dice si siguen ahí).

## 3. Aparta el home antiguo

```bash
mv ~/.janitor ~/.janitor.antiguo
```

Ahí quedan tu `.env` (claves), `SOUL.md`, `config.yaml`, memorias y sesiones. La app
nueva crea un `~/.janitor` limpio.

## 4. Quita el comando antiguo

```bash
rm ~/.local/bin/janitor
```

Era un enlace al motor antiguo; la app nueva crea el suyo.

## 5. Limpia el arranque de tu shell

El instalador antiguo añadió dos líneas a `~/.bashrc` y/o `~/.zshrc`. Bórralas a mano:

```bash
grep -n 'HERMES_HOME\|\.janitor' ~/.bashrc ~/.zshrc
```

La que importa es `export HERMES_HOME="$HOME/.janitor"`: la app nueva no la necesita.
Abre un terminal nuevo después de quitarla.

## 6. Instala la app nueva

Instala la app siguiendo [`instalar-app.md`](instalar-app.md) (Linux, Arch, Windows
o macOS), ábrela y elige proveedor. Las claves se vuelven a introducir en la app.

## Qué puedes rescatar de `~/.janitor.antiguo`

| Qué | Cómo |
|---|---|
| Claves de API | Míralas en `.env` e introdúcelas en la app nueva |
| `SOUL.md` editado por ti | Cópialo sobre `~/.janitor/SOUL.md` |
| Memoria (`memories/MEMORY.md`, `memories/USER.md`) | Se puede copiar a `~/.janitor/memories/`; **sin verificar** entre versiones |
| Sesiones antiguas (`state.db`) | No se trasladan. Quedan en el home apartado |

Cuando estés seguro de que no necesitas nada más, mándalo a la papelera:

```bash
gio trash ~/.janitor.antiguo
```

Si no tienes `gio`, `trash-put ~/.janitor.antiguo` hace lo mismo. Vaciar la papelera
después, o usar `rm -rf ~/.janitor.antiguo` en su lugar, sí es definitivo.
