# Janitor dirige a Claude Code y a Codex («obreros»)

> **Estado: APROBADA por el dueño el 2026-11-25** («Sí, acéptalas»): las siete decisiones de
> la sección 7 quedan como estaban propuestas. Lo pidió el dueño ese mismo día. El tablero de
> la sección 6 dice qué está hecho.
> El plan general sigue siendo [`janitor-desktop-app.md`](janitor-desktop-app.md).

## 0. Estado y relevo (cierre de sesión, 2026-11-27)

Para quien retome la fase 7 en una sesión nueva. Esta sección manda sobre la tabla 6.1,
que se escribió antes de la auditoría de 6.6 y conserva frases ya superadas.

**Qué hay en `main`, publicado como `v0.21.5-janitor.3`** por orden del dueño el
2026-11-27 (corrida de publicación 46073205800 en verde en sus siete trabajos; `stable`
en `76cd7cc47b`, igual que `main`; instaladores de Linux, Windows, macOS y paquete de
Arch adjuntos). El dueño la va a probar en la app instalada en su equipo; **esa prueba
no está hecha**:

| PR | Contenido |
|---|---|
| #100, #101 | Supervisor de trabajos, comando `janitor obreros`, herramientas `obreros_enviar` / `obreros_ver`, aviso de fin, skill `janitor-obreros`, primer recorrido real |
| #102 | Codex contenido a la carpeta del proyecto (sin comandos en consulta; perfil de permisos en revisión), detección de sesión, robustez del comando, reintento del arranque vacío, auditoría independiente |
| #103 | Fuera del catálogo las skills de upstream `claude-code` y `codex` (decisión del dueño) |
| #105 | Fuera también `opencode`; versión `0.21.5+janitor.3` |

**Estado por tarea:**

| Id | Estado |
|---|---|
| F7-00 | hecho |
| F7-01, F7-02, F7-03, F7-13, F7-05, F7-08 | hecho y auditado por un revisor distinto, con reparos; los reparos corregidos o anotados en 6.6. Solo Linux |
| F7-06, F7-07 | hecho y auditado sin reparos |
| F7-10 | a medias: falta la semilla y el aviso de activación en la app |
| F7-11 | recorrido de solo lectura hecho en el terminal (6.5) y aprobación con usuario respondiendo (6.6); falta en la app y con construcción. **Sin auditar** |
| F7-04 (construcción en copias de trabajo) | sin empezar |
| F7-09 (pantalla en la app) | sin empezar |
| F7-12 (Windows y macOS con los programas reales) | sin empezar |

**Sin verificar, dicho sin rodeos:**

- El perfil de permisos de Codex (`janitor/obreros/codex.py`) solo se probó en Linux. En
  macOS y Windows no se sabe si contiene la lectura; si el perfil no sirve, el trabajo
  falla en vez de quedar abierto, pero eso tampoco se probó allí.
- Nada de obreros se ejecutó en Windows ni macOS con los programas reales: el CI de esos
  sistemas corre las pruebas con programas falsos.
- Nada se probó dentro de la app de escritorio.
- Las skills de upstream del catálogo no se leyeron una por una.

**Pendiente de decisión del dueño:**

- `opencode` también se retiró del catálogo (decisión del dueño, 2026-11-27). El dueño
  dijo que más adelante verá qué más quitar; tiene la lista de skills del catálogo.
- La versión `.3` salió a todos los que siguen `stable` con el perfil de Codex sin
  verificar en macOS y Windows: F7-12 pasa a ser lo primero.

**Siguiente paso recomendado, en orden:** F7-12 (cerrar la duda del perfil de Codex en
macOS y Windows, que es de seguridad), F7-09 con el resto de F7-10 (la pantalla resuelve
además el límite de «activación reciente» de 6.4), repetir F7-11 en la app, y F7-04.

**Límites conocidos que siguen abiertos** (detalle en 6.3, 6.4 y 6.6): el tope de tokens
cuenta solo trabajos terminados; las herramientas pueden no aparecer si la sesión se abre
justo después de activar; el aviso se pierde si el turno falla; el tope de rondas de
revisión es solo una instrucción de la skill; no hay tope en dinero; quitar las skills no
impide que el modelo lance `claude` o `codex` por la terminal. Fuera de esta fase: en el
terminal clásico la pregunta al usuario se titula «Hermes needs your input» y el banner
dice «Nous Research».

**Cómo repetir las pruebas reales en este equipo:**

- Instalación de prueba (no es la del dueño): `/var/tmp/janitor-a4/home`, con proveedor
  ya configurado y el perfil `obra` (Creador de proyectos). No se lee su `.env`.
- Guion: `/var/tmp/janitor-f7-11/j.sh <argumentos de janitor>` corre `janitor.cli` del
  checkout contra ese home usando la sesión real de Claude Code y Codex del dueño.
  Ejemplo: `j.sh -p obra chat -Q -q "…"`; para un usuario que responde, `--cli` en tmux.
  Las salidas del recorrido de 6.5 siguen en esa carpeta.
- `janitor obreros estado` ejecuta los programas reales (`--version` y estado de sesión).
- Pruebas: `scripts/run_tests.sh tests/janitor/` (886 pasan el 2026-11-27) y
  `node --test apps/desktop-janitor/scripts/build.test.mjs`. Esta última falla si se
  quita una skill de upstream del catálogo sin quitar su fila en
  `apps/desktop-janitor/brand/palette.mjs` y en el `plugin.js` del plugin de escritorio.

**Estado del repositorio al cerrar:** el checkout principal está en
`janitor-app/proyectos-1` con trabajo sin confirmar de la fase Proyectos (F8), que salió
de `main` antes del PR #103 y tendrá que traerlo. Su entorno `.venv` tiene instalado el
paquete como `.2`: tras traer `main`, la prueba `test_touchpoint_contract[version]`
falla hasta reinstalar (`uv sync` o `pip install -e .`). Ramas `janitor-app/*` ya fusionadas,
borradas. Los archivos `recomendaciones-codex-para-claude.md` y
`transicion-equipo-del-dueno.md` de esta carpeta no están en el repositorio a propósito.

## 1. Objetivo

Que Janitor pueda mandar sobre los dos programas de código que el usuario ya tiene
instalados y con sesión iniciada en su equipo, **Claude Code** (`claude`) y **Codex**
(`codex`), y usarlos para sacar adelante proyectos largos:

- Solo se enciende si el programa está instalado **y** con sesión iniciada. Con uno solo,
  funciona con ese; sin ninguno, la función no aparece.
- Los modelos más capaces (Fable en Claude, Astra en Codex) planifican.
- Janitor reparte trabajo a uno y a otro, y les hace revisarse mutuamente: «Claude, haz
  esto; Astra, haz esto otro; Claude, mira lo que hizo Astra; Astra, mira lo que hizo
  Claude; opinen».
- Sirve para procesos de larga duración con un objetivo: desarrollar, crear, estructurar.

## 2. Hechos verificados (2026-11-25)

Tres investigaciones de solo lectura. Lo marcado «doc» sale de la documentación oficial y
no se comprobó aquí; lo demás se comprobó en el equipo de desarrollo o en el código.

### 2.1 Qué hay ya en Janitor

- Las skills de upstream `claude-code`, `codex` y `opencode`
  (`skills/autonomous-ai-agents/`) estaban en `janitor/catalog.yaml` para la plantilla
  **Creador de proyectos** (las dos primeras se retiraron el 2026-11-27, sección 6.6). Son recetas en prosa: el agente escribe a mano el comando
  (`claude -p …`, `codex exec …`) en la terminal. La de Claude enseña a guardar el id de
  sesión y reanudar (`SKILL.md:224`), pero el estado queda en manos del modelo: no hay
  registro de trabajos.
- **Nada comprueba hoy que un programa exista.** El campo `prerequisites.commands` de
  las skills no se aplica (`tools/skills_tool.py` lo deja vacío). Lo que sí funciona:
  `check_fn` de una herramienta (`tools/registry.py`) y `requires_tools` en la skill
  (`agent/prompt_builder.py`).
- Para trabajo largo upstream ofrece: terminal en segundo plano con
  `notify_on_complete`, `watch_patterns` y `heartbeat`; `delegate_task` (hijos que son
  agentes Hermes, en segundo plano); cron; y **kanban**, cuyo trabajador tiene que ser
  un perfil (`hermes -p <perfil> chat -q`) con el lanzador por defecto; el lanzador
  (`spawn_fn(task, workspace, board)`, `hermes_cli/kanban_db_dispatch.py:1978`) se puede
  sustituir desde Python y registra el PID. El kanban ya está traducido en la app.
- `approvals.mode: manual` pide permiso solo para los comandos que el terminal reconoce
  como peligrosos. **Lanzar `claude` o `codex` no es uno de ellos** (`tools/approval*.py`
  no tiene regla para esos programas), y un subproceso lanzado por el plugin ni siquiera
  pasa por ese control. La autorización tiene que ponerla este diseño (4.5).
- El registro de procesos de upstream puede recuperar un proceso tras un reinicio, pero
  sin su historial de salida (`tools/process_registry.py`).
- `janitor/opencode/` (retirado en F2-04) era lo más parecido a esto: un cliente de
  `opencode serve` con un registro de sesiones y reintentos.
- El plan vigente (§2, líneas de «Especialista y subagente») dice que el principal no
  delega en perfiles especialistas y que no se crean sistemas de agentes paralelos
  (directiva #19).

### 2.2 El puente `claude_codex` (el que usan hoy Claude y Codex entre sí)

- Un solo script, `tools/bridge.py` (659 líneas, solo biblioteca estándar, v0.1.0, sin
  licencia, 51 pruebas con un CLI falso). Sirve en las dos direcciones.
- Lo aprovechable: el esquema del encargo (`objetivo`, `contexto`, `entregables`,
  `restricciones`), las líneas de comando endurecidas de cada programa, la lista blanca
  de variables de entorno, la carpeta de evidencia por corrida, los analizadores de la
  salida JSON y la detección de «pedí un modelo y contestó otro».
- Lo que le falta para este objetivo:
  - **No corre en Windows** (usa `fcntl`, `getuid`, `killpg`).
  - Cada llamada bloquea hasta terminar; no hay trabajos en segundo plano ni consulta
    de estado.
  - **No reanuda conversaciones** (lanza los dos programas en modo efímero).
  - **Codex solo lee**; solo Claude puede escribir.
  - No comprueba la sesión iniciada, solo `--version`.

### 2.3 Los dos programas

| | Claude Code 2.1.332 | Codex 0.172.0 |
|---|---|---|
| Sesión iniciada | `claude auth status` → JSON con `loggedIn`; salida 0/1 | `codex login status` → una línea de texto; salida 0 (la de «sin sesión» no está documentada) |
| Sin pantalla | `claude -p --output-format json\|stream-json` | `codex exec --json` |
| Reanudar | `--resume <id>`; se puede fijar con `--session-id` | `codex exec resume <thread_id>` |
| Escribir en el proyecto | `--permission-mode` + `--allowedTools` | `--sandbox workspace-write` |
| Coste | `total_cost_usd` estimado + tokens | solo tokens |
| Windows (doc) | nativo | nativo |

- Otras interfaces: el Agent SDK de Claude (envuelve el mismo binario), `codex
  app-server` (JSON-RPC, **marcado experimental**), y `codex mcp-server`, que **ya no
  existe**. Ninguno de los dos habla ACP de forma nativa.
- Los dos cambian deprisa (opciones ocultas, opciones retiradas). `claude --bare`, que
  la documentación anuncia como futuro valor por defecto de `-p`, **no usa la
  suscripción**.
- `claude -p` en una carpeta ejecuta los hooks y servidores MCP del proyecto sin
  preguntar (doc): no se lanza sobre carpetas que el usuario no haya elegido.

### 2.4 Condiciones de uso (leer antes de decidir)

- **Anthropic** (doc, <https://code.claude.com/docs/en/legal-and-compliance>): prohíbe a
  terceros ofrecer el inicio de sesión de Claude.ai en su aplicación o encaminar
  peticiones con credenciales de un plan en nombre de sus usuarios. La misma página dice
  que eso no impide que el usuario final use el binario **sin modificar** de Claude Code
  con su propia suscripción. Condiciones: binario sin modificar, el usuario se autentica
  y paga él, y **no usar «Claude Code» en el nombre del producto o de la función**. Los
  límites del plan suponen «uso individual ordinario».
- **OpenAI** (doc): `codex exec` reutiliza la sesión guardada; recomienda clave de API
  para automatización. No encontramos una frase que permita o prohíba que una
  herramienta local lance el `codex` del usuario.
- **Lectura nuestra, no asesoría legal:** lanzar el binario del usuario sin tocar sus
  archivos de credenciales parece permitido. Leer sus credenciales para usarlas como
  proveedor de IA de Janitor queda del lado prohibido en Anthropic. Un uso automático
  intenso puede salirse de «uso individual ordinario»: es una zona gris.

## 3. Opciones

| | Qué es | A favor | En contra |
|---|---|---|---|
| **A. Solo skills** | Mejorar las recetas actuales; el agente escribe los comandos | Casi sin código | Sin estado, sin reanudar, sin detección; el modelo debe recordar opciones que cambian; un permiso por comando; nada que mostrar en la app |
| **B. Motor propio + comando + skill** | Un módulo `janitor/` que lanza los dos programas, guarda cada trabajo y lo reanuda; se usa con `janitor obreros …`; una skill enseña el método | Estado y evidencia en disco; funciona en los tres sistemas; lo usan el agente, el terminal y la app; no añade peso a cada llamada al modelo; es el peldaño 2 de la «escalera» del proyecto | Hay que escribirlo y mantenerlo al ritmo de los dos programas |
| **C. Herramientas del plugin** | Igual que B, pero el agente lo llama como herramienta con `check_fn` | Parámetros estructurados; desaparece sola si no hay programas | Ocupa sitio en cada llamada al modelo; conviene solo como capa fina sobre B |
| **D. Kanban con perfiles** | El tablero de upstream reparte tareas a perfiles que llaman a los programas | Ya existe, con pantalla; pensado para trabajo largo | El trabajador es un perfil con su propio modelo: una capa más entre Janitor y el obrero; choca con «el principal no delega en especialistas» |
| **E. Usarlos como proveedor de IA** | Que el cerebro de Janitor sea Fable o Astra vía la suscripción | Janitor «piensa» con el mejor modelo | Con Claude queda del lado prohibido (2.4); con Codex depende de un modo experimental. Y no da obreros: da otro cerebro |

## 4. Recomendación

**B como base, con una capa fina de C, y D más adelante solo si hace falta. A se
descarta por frágil; E se descarta para Claude y se aparca para Codex.**

### 4.1 Quién hace qué

Janitor no planifica con su propio modelo (MiniMax-M3): **dirige**. Mantiene el objetivo,
habla con el usuario, reparte y decide cuándo algo está terminado.

| Papel | Quién | Permisos |
|---|---|---|
| Director | Janitor | habla con el usuario; lanza y lee trabajos |
| Planificadores | Fable (Claude) y Astra (Codex), los dos | solo lectura |
| Constructores | modelo intermedio de cada lado (Sonnet, Sol) | escriben, cada uno en su copia de trabajo |
| Revisores | el del lado contrario al que construyó | solo lectura |

Los modelos por papel son valores por defecto en `config.yaml`, no fijos en el código.

### 4.2 El ciclo de un objetivo

1. **Encargo.** Janitor convierte lo que pide el usuario en un encargo (objetivo,
   contexto, entregables, restricciones) y lo confirma con él.
2. **Dos planes.** Fable y Astra planifican por separado, sin verse.
3. **Crítica cruzada.** Cada uno lee el plan del otro y opina.
4. **Plan único.** Janitor lo consolida y **el usuario lo aprueba**. Sin aprobación no
   se escribe nada.
5. **Construcción.** Cada parte va a un obrero, en una copia de trabajo propia
   (`git worktree`), nunca dos escribiendo en la misma carpeta.
6. **Revisión cruzada.** El otro lado revisa el cambio; los hallazgos vuelven al
   constructor, con un tope de rondas.
7. **Entrega.** Janitor muestra el resultado y las pruebas; integrar o descartar lo
   decide el usuario.

Con un solo programa disponible, los pasos cruzados se hacen con dos modelos del mismo
lado, y Janitor avisa de que no hay segunda opinión independiente.

### 4.3 Piezas

- **Motor `janitor/obreros/`** (solo biblioteca estándar, tres sistemas):
  - detección: `shutil.which` + `--version` + estado de sesión, sin leer credenciales;
  - un adaptador por programa que construye la línea de comando y analiza la salida;
    las opciones se comprueban contra `--help` al arrancar, porque cambian;
  - registro de trabajos en el home efectivo del perfil (`obreros/`): por cada
    **intento**, el encargo, el id de sesión explícito (nunca «la última»), la carpeta,
    la política de permisos, el estado, la salida, los tokens y el coste;
  - trabajos en segundo plano que **no dependen del proceso de Janitor**: el obrero
    escribe su salida y su resultado en disco; al arrancar, Janitor reconcilia lo que
    quedó a medias sin repetir escrituras y entrega el aviso de «terminó» a la
    conversación que lo pidió, una sola vez;
  - reanudar es **otro turno** de la misma conversación, no recuperar un trabajo caído:
    son dos operaciones distintas, y al reanudar se vuelve a fijar la política de
    permisos (Codex no la acepta en `resume`; hay que comprobar cuál queda en efecto);
  - consulta, reanudación y cancelación siguen disponibles aunque la sesión haya
    caducado;
  - tres modos: consulta (sin herramientas), revisión (solo lectura) y construcción
    (escribe en su copia de trabajo);
  - topes: tiempo por trabajo, trabajos a la vez, rondas de revisión y gasto.
- **Comando `janitor obreros`**: `estado`, `enviar`, `ver`, `seguir`, `reanudar`,
  `cancelar`. Lo usan el agente, el usuario en el terminal y la app.
- **Herramienta fina del plugin Janitor** con `check_fn` (hay al menos un programa con
  sesión): solo «enviar» y «ver». Es lo que permite que la skill aparezca o no
  (`requires_tools`) sin tocar el core. `check_fn` va con caché y solo dice si la
  función está **disponible**; la **autorización** se comprueba en cada envío. Un cambio
  de disponibilidad se aplica en la sesión siguiente, para no romper la caché del
  prompt.
- **Skill `janitor-obreros`** (grupo `projects/`): el método de 4.2 y cuándo no usarlo.
- **Agentes.** Dos caminos, a decidir (7.3):
  - que **Creador de proyectos** use los obreros por defecto cuando estén disponibles;
  - una plantilla nueva de **director** para objetivos largos.
- **App**: en la pantalla del plugin de escritorio, el estado de cada programa
  (instalado, con sesión) y la lista de trabajos con su resultado. Sin esto, el usuario
  no ve qué está pasando en un proceso de horas.

### 4.4 Qué se reutiliza del puente

Del `bridge.py` se toman, reescritos dentro de `janitor/obreros/`, el esquema del
encargo, las opciones endurecidas, la lista blanca de variables, los analizadores y la
detección de modelo equivocado. No se toma como dependencia: no corre en Windows, no
tiene licencia y le faltan justo las tres cosas que este objetivo necesita (segundo
plano, reanudar, Codex escribiendo).

### 4.5 Reglas

- **Nunca se leen ni copian credenciales** de `~/.claude` ni `~/.codex`. Janitor solo
  ejecuta el binario del usuario, sin modificar.
- **Activación explícita.** Detectar los programas solo ofrece la función; el usuario la
  enciende, tras un aviso en español: su código sale hacia Anthropic u OpenAI y consume
  su plan o su saldo.
- **Solo en carpetas que el usuario eligió** como proyecto.
- **La autorización es propia, no la del terminal.** Aprobar el plan autoriza un
  proyecto, un commit base y un alcance concretos; cada envío se comprueba contra eso.
- **Permisos explícitos en cada lanzamiento**: aislamiento y política de aprobación
  fijados en la línea de comando, sin heredar los del usuario. Si el obrero necesita un
  permiso que no tiene, el trabajo queda **bloqueado** y vuelve al director; nadie
  aprueba por él.
- **Copias de trabajo**: commit base fijado, una rama por intento y un cerrojo por
  copia (las copias comparten objetos y referencias de Git). La revisión se hace sobre
  un diff identificado, y es ese diff el que se entrega.
- **Nada se integra solo.** Los obreros escriben en copias de trabajo; fusionar, subir o
  borrar lo confirma el usuario (regla de `SOUL.md`, directiva #19).
- **Sin recursión**: un obrero no puede llamar a Janitor ni a otro obrero.
- **Nombre**: la función no se llama «Claude Code» ni lleva marcas ajenas en el nombre.
- No se añade nada a `apps/desktop/` ni al core fuera de touchpoints declarados
  (directivas #1, #16).

## 5. Riesgos

- **Condiciones de uso** (2.4). El uso automático e intenso con la suscripción es zona
  gris; se mitiga con activación explícita, topes y la opción de clave de API, pero no
  se elimina. Es decisión del dueño (7.2).
- **Los programas cambian.** Una opción retirada rompe el adaptador. Mitigación:
  comprobación contra `--help`, pruebas con un programa falso y una prueba real manual
  por versión.
- **Gasto.** Planificar con dos modelos caros y revisar en cruz multiplica el consumo.
  Topes por defecto conservadores. Codex solo informa tokens, así que un tope en dinero
  no se puede garantizar de ese lado: allí el tope es de tokens y de tiempo.
- **«Sin herramientas» y «sin recursión» hay que demostrarlos**, no declararlos: hooks,
  servidores MCP y procesos hijos del obrero necesitan una prueba cada uno.
- **Directiva #19.** Esto introduce trabajadores que no son perfiles. Hay que
  registrarlo como excepción explícita, o como decisión nueva, antes de escribir código
  (7.4).
- **Seguridad.** Un obrero con permiso de escritura ejecuta lo que el proyecto le diga.
  En Windows, Claude no tiene aislamiento nativo (doc).
- **Sin verificar**: todo lo marcado «doc» en la sección 2; que la sesión de Codex sin
  iniciar devuelva salida distinta de 0; el comportamiento de los dos programas en
  Windows y macOS.

## 6. Tareas propuestas (Fase 7)

Primera entrega: solo consulta y revisión (decisión 7.5).

| Id | Tarea | Alcance | Verificación |
|---|---|---|---|
| F7-00 | Ensayo: cuánto resuelven el kanban (`spawn_fn` externo) y el registro de procesos de upstream antes de escribir un supervisor propio | solo lectura + prototipo desechable | informe con evidencia |
| F7-01 | Detección de los dos programas y de su sesión | `janitor/obreros/deteccion.py` | pruebas con binarios falsos; salida real en Linux |
| F7-02 | Adaptadores: línea de comando, análisis de salida, comprobación de opciones | `janitor/obreros/claude.py`, `codex.py` | pruebas con programa falso |
| F7-03 | Registro de trabajos, segundo plano, reanudar, cancelar, topes | `janitor/obreros/trabajos.py` | pruebas; un trabajo real de consulta por lado |
| F7-04 | Copias de trabajo por obrero y modo construcción | `janitor/obreros/copias.py` | prueba en un repositorio temporal |
| F7-05 | Comando `janitor obreros` | `janitor/plugin/` | pruebas del analizador de argumentos |
| F7-06 | Herramienta fina con `check_fn` | `janitor/plugin/` | la herramienta no existe sin programas |
| F7-07 | Skill `janitor-obreros` y entrada en el catálogo | `janitor/skills/projects/`, `janitor/catalog.yaml` | `python -m janitor.catalog check` |
| F7-08 | Agente: Creador de proyectos o plantilla nueva (según 7.3) | `janitor/templates/` | creación del perfil en un home temporal |
| F7-09 | Pantalla en la app: estado y trabajos | `janitor/desktop_plugin/` | captura con la app compilada |
| F7-10 | Aviso de activación y ajustes en `config.yaml` | semilla + plugin | prueba |
| F7-11 | Recorrido real: un objetivo pequeño de punta a punta con los dos programas | — | evidencia en la bitácora |
| F7-12 | Prueba en Windows y macOS: resolución del ejecutable y sus lanzadores, rutas con espacios, cancelación del árbol de procesos | CI + equipo real | — |
| F7-13 | Recuperación y aviso al director: caída antes y después de guardar el resultado, entrega duplicada, perfiles A→B→A | `janitor/obreros/trabajos.py` | pruebas en `tests/janitor/` |

Orden (ajustado tras la revisión de Codex): F7-00 y F7-10 primero; F7-01 y F7-02 con
F7-12 desde el principio, no al final; F7-03 con F7-13 y F7-05; después F7-06 a F7-08 y
un primer F7-11 en solo lectura. La construcción (F7-04) va en la segunda entrega, con
F7-11 repetido sobre un conflicto real, y la app (F7-09) cierra. Cada entrega lleva
pruebas en `tests/janitor/` y un revisor distinto (directiva #20).

### 6.1 Estado (2026-11-25)

| Id | Estado | Evidencia |
|---|---|---|
| F7-00 | hecho (ensayo de solo lectura, subagente Opus) | Ver 6.2 |
| F7-01 | hecho; **sin auditar por un revisor distinto**; sin probar en Windows ni macOS, ni con un programa sin sesión | `scripts/run_tests.sh tests/janitor/test_janitor_obreros_deteccion.py` → 20 pasan. En este equipo detecta los dos, con sesión, sin correo ni organización en el resultado |
| F7-02 | hecho; **sin auditar**; sin probar en Windows ni macOS; modo revisión sin probar contra un modelo | `scripts/run_tests.sh tests/janitor/test_janitor_obreros_adaptadores.py` → 60 pasan. Cada opción comprobada en `--help` de Claude Code 2.1.332 y Codex 0.172.0. **Prueba real** en una carpeta vacía (`/var/tmp/janitor-obreros-smoke/`): una consulta y una reanudación con cada programa; los dos contestaron, el analizador obtuvo respuesta, id de sesión y tokens (y coste en Claude), y al reanudar recordaron el turno anterior |
| F7-03, F7-13, F7-05 | hecho (2026-11-26); **revisado por Codex en lectura estática, sin auditar por un revisor que repita las pruebas**; sin probar en Windows ni macOS | Supervisor (`trabajos.py`, `ejecutor.py`, `procesos.py`, `registro.py`), ajustes y comando `janitor obreros` (`orden.py`). `scripts/run_tests.sh -j 4 tests/janitor/` → 830 pasan, 24 saltadas. **Prueba real** en un home temporal (`/var/tmp/janitor-obreros-smoke2/`): rechazo sin activar; consulta con cada programa; reanudación con Claude; revisión de una carpeta con los dos (ambos encontraron el defecto sembrado y no tocaron el archivo); rechazo de `~/.ssh`; cancelación, sin procesos colgados |
| F7-10 | a medias: aviso de activación y ajustes `janitor.obreros` en `config.yaml` hechos dentro del comando; falta la semilla y el aviso en la app | Misma evidencia |
| F7-06, F7-07, F7-08 | hecho (2026-11-26); **revisado por Codex en lectura estática, sin auditar por un revisor que repita las pruebas**; sin probar con un modelo conduciendo las herramientas | Herramientas `obreros_enviar` y `obreros_ver` con `check_fn` y aviso de fin por `pre_llm_call` (`janitor/plugin/obreros.py`); skill `janitor-obreros` en el catálogo (sin `requires_tools`, ver 6.4); Creador de proyectos la usa por defecto. Carpetas autorizadas por el usuario (`janitor obreros autorizar`). `scripts/run_tests.sh -j 4 tests/janitor/` → 880 pasan, 24 saltadas. **Prueba real** por el cargador de plugins en un home temporal: herramientas ocultas sin activar y visibles al activar; envío a los dos programas con una conversación como origen; el aviso llegó una vez y solo a esa conversación; revisión rechazada sin autorizar la carpeta y aceptada tras autorizarla |
| F7-11 | primer recorrido en solo lectura hecho (2026-11-27), ver 6.5; aprobación con un usuario respondiendo probada en el terminal (6.6); falta en la app y con el modo construcción | 6.5, 6.6 |
| F7-04, F7-09, F7-12 | sin empezar | — |

Observado en la prueba real: Codex no informa qué modelo contestó, y una consulta mínima
le cuesta unos 16.000 tokens de entrada (32.000 acumulados al reanudar); a Claude, unos
3.900 y 0,05 USD estimados. El tope de gasto tiene que contar con ese mínimo.

### 6.3 Revisión de Codex del supervisor (2026-11-26)

Ocho hallazgos, contrastados con el código. **Corregidos, con prueba salvo el primero**:

- Cancelar mientras el programa arrancaba podía dejarlo vivo: ahora se espera a que el
  ejecutor anote el PID o cierre el trabajo antes de matarlo. Sin prueba automática de
  esa ventana.
- Reconciliar podía pisar con `perdido` un resultado publicado mientras miraba: relee
  tras confirmar que el ejecutor murió.
- La carpeta protegida se comparaba por grafía: ahora también por identidad en disco
  (`.SSH` en un volumen que no distingue mayúsculas). Prueba solo en macOS.
- La activación y los topes se releen con el cerrojo de envío tomado.

**Aceptados como límite conocido, sin corregir**:

- El tope de tokens del día solo cuenta trabajos terminados con métricas: uno cancelado
  cuenta cero y dos a la vez pueden rebasarlo. Los programas no informan tokens hasta
  el final, así que no hay dato que sumar.
- El cerrojo de envío se da por abandonado a los 60 s; un equipo suspendido en mitad de
  un envío podría dejar pasar dos a la vez.
- Activar o desactivar reescribe `config.yaml` entero, como el resto de Janitor: una
  edición simultánea del usuario se pierde.
- Margen de 1 s al comparar la hora de arranque de un PID: exige que el PID se
  reutilice en el mismo segundo en que nació el original.
- Un enlace simbólico cambiado entre la comprobación de la carpeta y el lanzamiento.

Además: en modo consulta, el aislamiento de solo lectura de Codex no le impide leer el
resto del disco; la carpeta vacía no es una garantía de ese lado. **Esto estaba mal
clasificado como límite: era un agujero en los dos modos y se corrigió el 2026-11-27
(ver 6.6).**

### 6.4 Revisión de Codex de la herramienta, el aviso y la skill (2026-11-26)

Seis hallazgos. **Corregidos, con prueba**:

- El agente podía mandar a revisión cualquier carpeta no protegida: ahora solo las que
  el usuario autoriza (`janitor.obreros.carpetas`; `janitor obreros autorizar DIR`).
- El aviso metía la respuesta del obrero en el mensaje del usuario: ahora lleva solo
  id, programa, modo y estado; el contenido se lee con `obreros_ver`.
- `obreros_ver` leía con la función desactivada, y otra conversación podía consumir un
  aviso ajeno.
- Un envío sin conversación identificable prometía un aviso que no iba a llegar.

**Encontrado por el CI, no por la revisión**: el core difiere toda herramienta de plugin
tras `tool_search`/`tool_call`, así que nunca está en la lista directa del agente y una
skill con `requires_tools` sobre ellas no aparecería jamás. El entorno local no lo mostró
porque le faltaba una dependencia del buscador. La skill va sin esa condición: la ve
siempre el perfil que la tiene en su catálogo, y explica qué hacer si no hay obreros. El
propósito de 4.3 («que la skill aparezca o no») queda sin cumplir.

**Límites conocidos, sin corregir**:

- **Activación reciente.** El core guarda la lista de herramientas por firma de
  `config.yaml` sin caducidad, y el resultado de `check_fn` 30 s. Una sesión abierta en
  ese margen tras activar puede quedarse sin las herramientas hasta reiniciar Janitor.
  Verificado en `model_tools.py::get_tool_definitions`. Se resuelve cuando la app
  active desde dentro del proceso (F7-09) e invalide la caché.
- **Aviso perdido.** El aviso se reserva antes de la llamada al modelo: si ese turno
  falla, no se repite. Tampoco llega en el modo `codex_app_server` del core.
- **Subagentes, compresión y `/reset`.** El aviso va a la conversación que envió el
  trabajo; si cambia su identificador, el trabajo solo se ve con `obreros_ver`.
- `activar` y `autorizar` son órdenes de terminal: nada impide a un agente
  ejecutarlas salvo la instrucción de la skill, igual que el resto de órdenes.

### 6.5 Primer recorrido real, F7-11 en solo lectura (2026-11-27)

Perfil Creador de proyectos (MiniMax-M2.7) creado en el home de prueba
`/var/tmp/janitor-a4/home`, con el código de esta rama, por `janitor -p obra chat -q`
(cuatro turnos de la misma sesión). Proyecto de ejemplo: una CLI de notas en Python
(`/var/tmp/janitor-f7-11/proyecto`); objetivo: buscar por etiqueta y exportar a JSON.
Guiones y salidas en `/var/tmp/janitor-f7-11/`.

Qué pasó:

1. El agente cargó la skill y lanzó un plan a cada obrero en modo revisión, sin esperar.
2. En el mensaje siguiente recibió el aviso (dos mensajes de usuario lo llevan en
   `api_content` y ninguno en el texto visible), leyó los planes con `obreros_ver` y
   lanzó la crítica cruzada reanudando la conversación de cada obrero.
3. Presentó un plan único con las discrepancias y preguntó al usuario (`clarify`).
4. Aplicó los cambios él mismo y lanzó la revisión cruzada del código.
5. Contrastó los hallazgos ejecutando el código, corrigió y no hizo commit.

Seis trabajos, todos terminados; unos 291.000 tokens de obreros (0,07 USD estimados
por trabajo de Claude; Codex no informa coste). Comprobado aparte: las 67 pruebas del
proyecto pasan y los obreros no escribieron nada.

Observado:

- **La aprobación del usuario no quedó probada.** En el modo de una sola consulta el
  core contesta a `clarify` «no hay usuario, elige tú y sigue», y el agente aplicó el
  plan. Es un efecto del modo de prueba, pero la skill ahora dice que sin respuesta se
  detiene. Hay que repetirlo en la app o el TUI con un usuario respondiendo.
- El agente llegó a las herramientas directamente y una vez por `tool_call`; las dos
  vías conservaron la conversación de origen.
- El perfil lleva también las skills de upstream `claude-code` y `codex`, que enseñan
  a lanzar esos programas a mano; en este recorrido no las usó. Se retiraron después
  (sección 6.6).
- El agente amplió el alcance por su cuenta (deuda del proyecto, 67 pruebas para dos
  funciones). Es conducta del modelo director, no del motor.
- Texto del modelo con algunos caracteres en chino mezclados (MiniMax-M2.7).

### 6.6 Auditoría independiente y pruebas del 2026-11-27

**Auditoría (directiva #20).** Un revisor distinto (subagente Opus, solo lectura)
repitió `scripts/run_tests.sh -j 4 tests/janitor/` (880 pasan, 24 saltadas), el overlay
check y el catálogo, y comprobó que ocho pruebas clave fallan si se rompe la regla que
protegen. Veredicto: F7-06 y F7-07 **auditadas sin reparos**; F7-01, F7-02, F7-03/13,
F7-05 y F7-08 **auditadas con reparos**. Los reparos y qué se hizo:

- **Codex podía leer todo el disco** en los dos modos: su aislamiento `read-only` solo
  impide escribir. Confirmado con un archivo señuelo fuera de la carpeta (con el
  preámbulo de Janitor Codex se negó; con una instrucción directa lo leyó). **Corregido**:
  en consulta se le quita la herramienta de comandos; en revisión corre con un perfil de
  permisos que solo deja leer la carpeta del proyecto, lo mínimo del sistema y la
  instalación del propio Codex, sin escritura ni red. Repetida la prueba del señuelo en
  consulta, revisión y reanudación: bloqueado en las tres; `~/.ssh` y el home de Janitor
  no existen para el obrero. **Solo verificado en Linux** (el perfil usa bubblewrap; en
  macOS y Windows queda para F7-12, y si el perfil no sirve allí el trabajo falla, no
  queda abierto). Claude ya estaba contenido (`--restricted`): negó la lectura.
- La orden `janitor obreros` daba traza con un encargo enorme o muy anidado y con cifras
  no ASCII en el tope: **corregido**, con pruebas.
- La detección de Codex miraba solo la primera línea: **corregido**; una salida que no
  dice nada queda «desconocido».
- **El plan afirmaba cosas que el código no hace** (se corrige aquí): las opciones no se
  comprueban contra `--help` al arrancar (fue una comprobación manual por versión); el
  tope de rondas de revisión solo es una instrucción de la skill; no hay tope en dinero,
  solo en tokens al día.
- «Sin recursión» depende de una variable de entorno más el aislamiento: con Codex sin
  comandos (consulta) o sin red ni escritura (revisión), y Claude solo con lectura, un
  obrero no puede lanzar nada. Sin prueba automática de eso.
- El perfil Creador de proyectos llevaba las skills de upstream `claude-code` y
  `codex`, que enseñan a lanzar los programas a mano y se saltan activación, topes y
  carpetas. **Retiradas del catálogo por decisión del dueño (2026-11-27)**: un perfil
  ya creado las pierde la próxima vez que se aplica el catálogo. `opencode` se retiró
  el mismo día, por una segunda decisión. La terminal del agente sigue pudiendo lanzar esos programas
  si el modelo lo decide por su cuenta: quitar la receta no es un bloqueo.
- Sin corregir, menores: con Codex no existe el estado `bloqueado`; reanudar sin
  conversación dice que no habrá aviso y sí llega a la original; cancelar justo cuando
  el trabajo termina se queda sin aviso; el obrero recibe `DBUS_SESSION_BUS_ADDRESS`.

**Programas sin sesión** (carpetas de configuración vacías, sin tocar las reales): los
dos se detectan como «instalado, pero sin sesión», el envío se rechaza con el comando
para iniciarla y las herramientas del agente no aparecen.

**Aprobación del plan, con un usuario respondiendo.** Sesión interactiva del perfil
`obra` en el home de prueba, conducida por tmux sobre un clon limpio del proyecto de
ejemplo. El agente lanzó un plan a cada obrero, presentó el plan único y se detuvo en
la pregunta de aprobación con cero archivos cambiados; ante «No, quiero cambiar algo
antes» no aplicó nada y preguntó qué cambiar. Cero archivos cambiados al final.

**Visto de paso**:

- Una consulta de Claude falló una vez con salida vacía mientras «cargaba los ajustes
  de la organización». El ejecutor repite ahora una vez un arranque que sale sin
  escribir nada (con prueba).
- En el terminal clásico (`--cli`), la pregunta al usuario se titula «Hermes needs your
  input» y el banner dice «Nous Research»: marca e inglés a la vista (directiva #17).
  No es de esta fase; queda anotado.
- El agente, tras el recorrido, creó por su cuenta una skill propia
  (`extend-existing-project`) en el perfil: es la autoaprendizaje de upstream.

### 6.2 Resultado del ensayo F7-00

Ni el registro de procesos ni el kanban de upstream sirven de supervisor:

- **Registro de procesos**: la salida del hijo es una tubería hacia Janitor (si Janitor
  cae, el obrero muere al escribir); el punto de control no guarda salida; el aviso de
  fin vive en memoria y se pierde al reiniciar; la recuperación solo la llama la pasarela
  de mensajería, no la app ni el TUI.
- **Kanban**: el lanzador solo se cambia desde Python; la pasarela siempre usa el suyo.
  No hay ajuste ni hook para inyectar otro: usarlo exigiría tocar el core.
- **Delegación asíncrona**: es el único camino duradero de «turno nuevo al quedar libre»,
  pero no tiene interfaz pública.

**Conclusión: supervisor propio y pequeño** (F7-03): proceso desligado que escribe su
salida y su resultado en `obreros/<id>/` del home del perfil, PID más hora de arranque
contra la reutilización de PID, y reconciliación al cargar el plugin y en cada orden.

El aviso de fin de trabajo se decidió en 7.8: sin tarjetas.

## 7. Decisiones del dueño (tomadas el 2026-11-25: se acepta cada propuesta)

1. **Nombre** de la función y del comando. Propuesta: «obreros» (`janitor obreros`).
2. **Suscripción o clave de API.** Propuesta: permitir la sesión del usuario con
   activación explícita y aviso, y ofrecer clave de API como alternativa. La otra opción
   es exigir clave de API y renunciar a la suscripción.
3. **Agentes.** Propuesta: Creador de proyectos usa los obreros por defecto; la
   plantilla de director se deja para después del recorrido real (F7-11).
4. **Directiva #19.** Propuesta: añadir que los obreros son programas externos del
   usuario dirigidos por un perfil, no un sistema de agentes paralelo, y que no tienen
   memoria ni identidad propias.
5. **Escritura.** Propuesta: la primera entrega es solo consulta y revisión; construir
   llega en una segunda entrega.
6. **Topes por defecto**: trabajos a la vez, rondas de revisión, minutos por trabajo y
   gasto. Propuesta: 2 a la vez, 2 rondas, 30 minutos, y un tope de gasto que el usuario
   fija al activar.
7. **Prioridad** frente a lo pendiente: probar la `.2` en equipos reales, los defectos
   pequeños ya anotados y la sincronización con upstream (PR #90). El dueño no fijó un
   orden; el orquestador entiende que esta fase se empieza ya, porque el dueño la pidió
   como importante y lo demás depende de equipos que no están a mano. Si no es así,
   basta decirlo.

8. **Aviso de fin de trabajo.** **Decidido por el dueño el 2026-11-26: sin tarjetas.**
   El resultado se ve en `janitor obreros` y en la pantalla de obreros, y Janitor lo
   cuenta en el siguiente mensaje del usuario; no abre un turno por su cuenta. La
   tarjeta de kanban queda como mejora posible tras el recorrido real. Los dos caminos
   que se valoraron:
   - *Tarjeta en el tablero kanban*: cada trabajo crea una tarjeta y su suscripción de
     aviso; upstream entrega el aviso una sola vez y abre un turno aunque Janitor se haya
     reiniciado, en app, terminal y mensajería. Coste: los trabajos aparecen como
     tarjetas en el tablero.
   - *Sin tarjetas*: el resultado se entrega en el siguiente mensaje del usuario (no abre
     un turno solo) y se ve en la pantalla de obreros. Para que abra un turno haría falta
     un hook nuevo en upstream.

## 8. Revisión de Codex (2026-11-25)

Revisión de solo lectura con `gpt-6.2-astra` (modelo solicitado; el puente no verifica
cuál contestó). Veredicto: **de acuerdo con B como base y C como capa opcional**, con la
condición de ensayar antes el kanban y el registro de procesos (F7-00). Cinco hallazgos,
todos contrastados por el orquestador contra el código e incorporados arriba:

1. **Crítico.** El documento daba por hecho que el modo manual pediría permiso al lanzar
   los programas. Es falso (comprobado: no hay regla). Corregido en 2.1 y 4.5.
2. **Alto.** Se confundía reanudar una conversación con recuperar un trabajo caído.
   Corregido en 4.3; tarea nueva F7-13.
3. **Alto.** La concurrencia con copias de trabajo estaba sin definir. Corregido en 4.5.
4. **Alto.** Se mezclaban disponibilidad, autorización y perfil. Corregido en 4.3.
5. **Medio.** Garantías exageradas: la receta de Claude sí reanuda; el tope en dinero no
   es demostrable con Codex. Corregido en 2.1 y 5.

Codex no comprobó: Windows ni macOS, los estados con y sin sesión, el acceso a modelos,
las condiciones de uso ni el puente. Sobre `codex app-server`: lo considera útil si se
quieren aprobaciones interactivas y eventos estructurados, pero prefiere `exec` para el
primer obrero.
