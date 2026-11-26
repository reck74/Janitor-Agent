# Janitor dirige a Claude Code y a Codex («obreros»)

> **Estado: APROBADA por el dueño el 2026-11-25** («Sí, acéptalas»): las siete decisiones de
> la sección 7 quedan como estaban propuestas. Lo pidió el dueño ese mismo día. El tablero de
> la sección 6 dice qué está hecho.
> El plan general sigue siendo [`janitor-desktop-app.md`](janitor-desktop-app.md).

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
  (`skills/autonomous-ai-agents/`) ya están en `janitor/catalog.yaml` para la plantilla
  **Creador de proyectos**. Son recetas en prosa: el agente escribe a mano el comando
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
| F7-03 a F7-13 | sin empezar | — |

Observado en la prueba real: Codex no informa qué modelo contestó, y una consulta mínima
le cuesta unos 16.000 tokens de entrada (32.000 acumulados al reanudar); a Claude, unos
3.900 y 0,05 USD estimados. El tope de gasto tiene que contar con ese mínimo.

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

Queda abierto **cómo avisar a la conversación cuando un trabajo termina** (decisión 7.8).

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

8. **Aviso de fin de trabajo** (nueva, sin decidir). Dos caminos:
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
