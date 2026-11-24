# Desinstalar el Janitor antiguo (instalado por terminal)

La app de escritorio de Janitor es un **punto cero**: no adopta ni actualiza una
instalación anterior hecha con `bootstrap.sh` / `janitor-install.sh`. Si la app
encuentra `~/.janitor/janitor-core`, se niega a instalar y no toca nada. Hay que
retirar lo antiguo primero y empezar limpio.

> Estos pasos salen de leer los instaladores antiguos. **No se han ensayado en una
> máquina real de punta a punta.** Ningún paso borra datos: lo antiguo se aparta con
> otro nombre y lo eliminas tú cuando compruebes que no lo necesitas.

## 1. Apaga lo que esté corriendo

```bash
systemctl --user disable --now hermes-gateway.service
```

Es el bot (Telegram). Si el comando dice que la unidad no existe, no la tenías.
Cierra también cualquier `janitor` abierto en un terminal.

## 2. Aplicativos con Docker (solo si los usabas)

Honcho, n8n, LightRAG, NocoDB, WAHA y Firecrawl guardan sus datos en volúmenes de
Docker, que **no** se borran con estos pasos.

```bash
docker ps -a --filter name=janitor-
```

Para cada servicio que aparezca, detén sus contenedores:

```bash
janitor services stop honcho
```

Si tenías Honcho instalado como servicio del sistema:

```bash
systemctl --user disable --now janitor-honcho.service
```

Los archivos de despliegue viven en `~/.janitor/docker`. Al apartar el home (paso 3)
los contenedores quedan sin ellos: después de instalar la app nueva se vuelven a
desplegar con `janitor services deploy <nombre>`, y reencuentran sus volúmenes.

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

Descarga el AppImage desde los releases del repositorio, ábrelo y elige proveedor.
Las claves se vuelven a introducir en la app.

## Qué puedes rescatar de `~/.janitor.antiguo`

| Qué | Cómo |
|---|---|
| Claves de API | Míralas en `.env` e introdúcelas en la app nueva |
| `SOUL.md` editado por ti | Cópialo sobre `~/.janitor/SOUL.md` |
| Memoria (`memories/MEMORY.md`, `memories/USER.md`) | Se puede copiar a `~/.janitor/memories/`; **sin verificar** entre versiones |
| Sesiones antiguas (`state.db`) | No se trasladan. Quedan en el home apartado |

Cuando estés seguro de que no necesitas nada más:

```bash
rm -rf ~/.janitor.antiguo
```

Esto último sí es definitivo.
