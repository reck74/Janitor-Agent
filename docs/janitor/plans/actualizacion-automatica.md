# Actualización automática y completa de Janitor (motor y app)

> **Estado: APROBADA por el dueño el 2026-11-27** («Sí, apruébalo»), con las seis
> propuestas de la sección 7 tal como están. La pidió ese mismo día, tras actualizar la
> instalación de su equipo a `v0.21.5-janitor.3`: el motor se actualizó, la app (paquete
> de Arch) quedó en la `.2` y el aviso le pidió reinstalar a mano.
> **Primera entrega (Linux: AppImage y paquete de Arch) implementada el 2026-11-27**, sin
> auditar todavía por un revisor distinto y **sin probar en un equipo real**: tablero en
> la sección 6, detalle en la 9. Windows y macOS, sin empezar. Para el usuario nada
> cambia hasta que el dueño cree la clave de firma
> ([`../actualizacion-firma.md`](../actualizacion-firma.md)) y se publique una versión.
> El plan general sigue siendo [`janitor-desktop-app.md`](janitor-desktop-app.md).
> **Sustituye una decisión registrada**: ese plan decía (2026-11-22) «el AppImage nuevo
> llega por descarga guiada desde los releases del fork; no hay actualización
> automática». El cambio queda anotado allí y en
> [`actualizacion-diseno.md`](actualizacion-diseno.md) (tarea F9-00, hecha).

## 1. Qué pide el dueño

1. Al abrir la app, se comprueba sola si hay una versión nueva.
2. La actualización es completa: motor **y** app. Si hace falta contraseña, se le pide al
   usuario; lo demás ocurre solo.
3. Vale para Linux, macOS y Windows.

## 2. Hechos verificados (2026-11-27)

Leídos en el código por un subagente de solo lectura; las rutas son de `main`.

- **La comprobación al abrir ya existe, pero solo mira el motor.** `startUpdatePoller`
  (`apps/desktop/src/store/updates.ts`) comprueba al montar la app, cada 24 h y al
  recuperar el foco. Compara el commit del motor instalado con la punta de `stable`
  (`checkUpdates` en `apps/desktop/electron/main.ts`, rama cambiada por el parche P19).
  Nada compara la versión de la app con la publicada.
- **Nada descarga ni reemplaza la app.** El guion (`scripts/desktop-update/posix.sh`,
  `windows.ps1`) ejecuta `janitor update` y después:
  AppImage → reabre el mismo archivo viejo; paquete de Arch → resultado «skew», aviso de
  reinstalar y **no se reabre**; Windows → reabre el `.exe` viejo; macOS → reabre el
  `.app` viejo. Upstream sí reemplaza la app, pero compilándola en el equipo del usuario,
  cosa que Janitor no hace (`janitor/update_core.py` no compila la app).
- **Compatibilidad.** El parche P13 compara un número de contrato (`janitor/desktop-compat.json`,
  hoy `1`) y solo si el motor exige una app más nueva bloquea con un enlace de descarga.
- **Publicación.** Cada versión adjunta `Janitor-linux-x86_64.AppImage`,
  `Janitor-win-x64.exe`, `Janitor-mac-arm64.dmg`, `Janitor-mac-x64.dmg`, el paquete de
  Arch y un `SHA256SUMS`. Nombres estables, sin versión. No hay archivos de un
  actualizador estándar, ni `.zip` de macOS, ni firma de ningún tipo.
- **Sin certificados.** macOS va firmado ad hoc y Windows sin firmar.
- **Windows**: el instalador deja elegir «solo para mí» o «para todos»; la segunda opción
  obliga a pedir permiso de administrador en cada actualización.

Investigado en documentación y código fuente de terceros (segundo subagente; nada probado
en un equipo real):

- `electron-updater` **no sirve en macOS con firma ad hoc**: Apple y Electron exigen app
  firmada, y Squirrel.Mac compara la firma de la versión nueva con la de la que corre,
  que con ad hoc cambia en cada compilación.
- `electron-updater` **no reconoce nuestro paquete de Arch** (se arma extrayendo el
  AppImage, no con el empaquetador de pacman), y su actualizador de pacman reintenta con
  `pacman -Sy`, que Arch desaconseja.
- En Windows y AppImage sí funcionaría, pero la versión estable no verifica nada más que
  una suma publicada en el mismo sitio, y nuestras versiones con sufijo `-janitor.N`
  caen en un caso raro de su comparación de versiones.
- Una suma (`SHA256SUMS`) bajada del mismo sitio que el binario protege de errores de
  descarga, no de alguien que pueda escribir en las versiones del repositorio.

## 3. Opciones

| | A. `electron-updater` | B. Actualizador propio dentro del relevo que ya existe |
|---|---|---|
| Cubre | Windows y AppImage | Los cuatro tipos de instalación |
| macOS y Arch | Necesitan otro mecanismo de todos modos | El mismo mecanismo |
| Cambios en `apps/desktop` (upstream) | Dependencia nueva y `package-lock.json`: conflicto en cada sincronización | Solo parches de compilación y los guiones que ya son nuestros |
| Verificación | Suma del mismo sitio (firma propia solo en versión alfa) | Firma propia desde el primer día |
| Coste | Menos código propio en dos sistemas | Más código propio, pero uno solo |

## 4. Recomendación: opción B

Un solo mecanismo, montado sobre lo que ya hay: el guion de relevo que hoy corre cuando la
app se cierra para actualizar el motor.

### 4.1 Qué ve el usuario

1. Abre Janitor. En segundo plano se comprueba si `stable` tiene una versión más nueva
   que el motor **o que la app**.
2. Si la hay, aparece «Hay una versión nueva de Janitor» con **Actualizar ahora** y
   **Más tarde** (decisión 7.1: esto, o actualizar sin preguntar).
3. Al aceptar, la app descarga y verifica el instalador nuevo **antes de cerrar nada**.
   Si la descarga o la verificación fallan, no se toca nada y se dice por qué.
4. La app se cierra, **se instala primero la app nueva** (aquí se pide la contraseña si
   el sistema la exige), después se actualiza el motor al commit exacto de esa versión, y
   Janitor **se vuelve a abrir solo**, ya en la versión nueva.
5. Si el usuario cancela la contraseña o la instalación de la app falla, **no se toca el
   motor**: Janitor se reabre tal como estaba, con un aviso exacto de qué pasó. Si la app
   se instaló y falla el motor, se reabre la app nueva, que ya sabe ofrecer la
   actualización del motor. Nunca queda cerrado sin explicación. El paso en que iba
   queda anotado (`paso.json`) solo para diagnóstico: la misma entrega se termina al
   siguiente intento porque la app vuelve a comparar su versión y el commit del motor
   con el manifiesto firmado, no porque lea esa nota.

### 4.2 Piezas

- **Comprobación (proceso principal, parche de compilación).** Además del commit del
  motor, se lee la versión publicada en `stable` y se compara con la de la app en
  ejecución. Con eso se detecta también el caso «motor al día, app vieja», que es el del
  equipo del dueño hoy.
- **Manifiesto firmado por versión.** La publicación adjunta un archivo con la versión,
  el commit y, por cada instalador, nombre, tamaño y SHA-256; y su firma Ed25519 hecha en
  el flujo de publicación. La clave pública va dentro de la app. La app solo instala lo
  que ese manifiesto firmado describe. La clave privada vive como secreto del
  repositorio en un entorno protegido (decisión 7.2).
- **Tipo de instalación.** Una sola función decide: AppImage (variable `APPIMAGE` válida),
  paquete de sistema (el ejecutable pertenece a un paquete de pacman), Windows por
  usuario o por máquina, macOS (`.app`), o «desconocido» (compilación local, ruta rara).
  «Desconocido» no se actualiza solo: conserva el aviso de hoy.
- **Descarga y verificación (proceso principal).** Baja el manifiesto, comprueba la
  firma, baja el instalador que corresponde a una carpeta propia dentro de `~/.janitor`,
  comprueba tamaño y suma. Entrega al guion la ruta y la suma esperada.
- **Motor fijado a un commit.** Hoy el motor sigue la punta de la rama en el momento de
  actualizar; si `stable` avanza durante la descarga, motor y app serían de versiones
  distintas. `janitor update` gana un destino por commit (en `janitor/update_core.py`,
  directiva #13): el del manifiesto firmado, comprobado antes de activar el código.
- **Instalación (guion de relevo), antes de actualizar el motor:**

  | Instalación | Cómo se reemplaza | ¿Contraseña? |
  |---|---|---|
  | AppImage | Se sustituye el archivo por el nuevo (copia al lado y renombrado) y se abre | No, si la carpeta es del usuario; si no lo es, aviso con la ruta |
  | Paquete de Arch | Un auxiliar que instala el propio paquete, propiedad de root y con su permiso de polkit: copia el paquete a una carpeta privada de root, verifica ahí firma, versión, nombre y arquitectura con la clave pública del paquete, y ejecuta `pacman -U` sobre esa copia. La app solo le pasa la ruta | Sí, la del sistema |
  | Windows | Instalador en modo silencioso sobre la misma carpeta | No si es por usuario; aviso de permisos de Windows si se instaló «para todos» |
  | macOS | Se extrae el `.zip`, se comprueban arquitectura, identidad y firma del paquete y se intercambia el `.app`; la copia anterior se conserva hasta confirmar que la nueva arranca | No si la app es del usuario; la de administrador si no |

  Quien instala vuelve a verificar dentro de su propia frontera de permisos: no basta
  con que lo haya comprobado la app (ver 8, hallazgo 1).
- **Reapertura y resultado.** Se reabre siempre: la app nueva si se instaló, la anterior
  si no. El resultado («todo actualizado», «motor sí, app no: motivo») llega a la app por
  el archivo de resultado que ya existe, con textos nuevos en español.
- **Publicación.** Se añaden: `.zip` de macOS por arquitectura, el manifiesto y su firma.
  **Se invierte el orden del flujo**: hoy mueve `stable` y después adjunta los archivos;
  pasará a adjuntar y verificar todo primero y mover `stable` al final, para que nadie
  vea «hay versión nueva» antes de que exista completa. Windows nuevo se instala solo
  por usuario (decisión 7.3); las instalaciones «para todos» ya hechas conservan su
  alcance hasta probar la transición.
- **Qué versión corresponde a `stable`.** La app toma el commit de `stable`, deduce la
  etiqueta con la misma regla que el flujo de publicación y exige que el manifiesto
  firmado nombre ese commit. Si falta el instalador de su sistema (el de Mac Intel es
  opcional hoy), lo dice antes de tocar nada.
- **Contrato de compatibilidad.** Se mantiene como red de seguridad para quien tenga una
  app sin actualizador o cancele siempre.

### 4.3 Reglas

- Solo se instala desde `github.com/reck74/Janitor-Agent`, por HTTPS, con manifiesto
  firmado. Ninguna variable de entorno ni ajuste cambia el origen ni la clave.
- Nunca se pide ni se guarda la contraseña en Janitor: la pide el sistema (polkit, UAC,
  el diálogo de macOS). Nunca `sudo`.
- No se baja de versión: el manifiesto lleva un número de entrega creciente y la app
  recuerda el mayor aceptado. La misma entrega sí se puede repetir, para terminar una
  actualización a medias («motor al día, app vieja»).
- Descarga primero, cambios después. El motor no se toca si la app nueva no se pudo
  bajar y verificar.
- Todo el flujo del motor sigue en `janitor/update_core.py` (directiva #13); los cambios
  en archivos de upstream se declaran en `janitor/overlay.yaml` (#16); los de la app son
  parches de compilación en `apps/desktop-janitor/` (#17); todo texto en español (#18).

## 5. Riesgos y lo que no está confirmado

- **macOS con firma ad hoc.** Sin confirmar si macOS 13 o posterior deja que una app sin
  equipo de desarrollo reemplace su propio paquete («Gestión de apps»). Además, con ad hoc
  cada actualización hace que el sistema olvide los permisos concedidos (micrófono,
  captura de pantalla). Solo se resuelve con una cuenta de desarrollador de Apple. Hay
  que probarlo en un Mac real antes de darlo por hecho.
- **Windows sin firma.** El Control inteligente de aplicaciones de Windows 11 puede
  bloquear ejecutables sin firmar, también el instalador de la actualización. Sin
  confirmar cómo se comporta una instalación ya hecha «para todos» al pasar a instalador
  por usuario.
- **Arch sin agente de permisos gráfico.** `pkexec` falla en sesiones sin agente polkit.
  En ese caso queda el aviso con el comando exacto.
- **Arch y `pacman`.** Instalar con `pacman -U` desde la app es correcto para un paquete
  que no está en ningún repositorio, pero no es lo habitual en Arch; la alternativa
  (repositorio propio firmado) es más trabajo y queda fuera.
- **Primera versión con actualizador.** Las instalaciones actuales (hasta la `.3`) no lo
  llevan: necesitan **una última instalación manual**. A partir de ahí, sola.
- **Clave de firma.** Si se pierde o se filtra, hay que publicar una app con clave nueva
  e instalarla a mano. Quien pueda ejecutar el flujo de publicación puede firmar.
- **Interrumpir trabajo en curso.** Actualizar reinicia los gateways (Telegram, tareas
  programadas). De ahí la decisión 7.1.
- **Tamaño.** Cada actualización de la app baja entre 120 y 150 MB completos; no hay
  descarga diferencial.

## 6. Tareas propuestas (Fase 9)

| Id | Tarea | Dónde | Verificación |
|---|---|---|---|
| F9-00 | **Hecho (2026-11-27).** Registrar el cambio de decisión en el plan general y en `actualizacion-diseno.md` | `docs/janitor/plans/` | lectura |
| F9-01 | **Hecho en parte (2026-11-27), sin auditar.** Manifiesto y firma: `apps/desktop-janitor/scripts/update-manifest.mjs` (`build`, `sign` con la clave leída de una variable de entorno, `verify`) y los pasos «Signed update manifest», «Sign the manifest» y «Verify the signed manifest against the files» del flujo. Clave privada: secreto `JANITOR_UPDATE_SIGNING_KEY` del entorno `janitor-release`; pública: `apps/desktop-janitor/brand/update-key.pem` (las pone el dueño; sin la pública no se firma ni se actualiza sola). **Pendiente (segunda entrega):** `.zip` de macOS y Windows solo por usuario. | flujo de publicación, guion nuevo en `apps/desktop-janitor/scripts/` | `node --test apps/desktop-janitor/scripts/app-update.test.mjs` → 32 pruebas, 0 fallos. **No verificado:** el flujo con una etiqueta real y el secreto real (no hay clave todavía) |
| F9-02 | **Hecho (2026-11-27), sin auditar.** `apps/desktop-janitor/brand/app-update.mjs`: firma Ed25519 sobre los bytes exactos, esquema, suma, tamaño, origen fijo (`https://github.com/reck74/Janitor-Agent`, sin variable ni ajuste que lo cambie), número de entrega derivado de la versión (creciente; la misma entrega se repite), manifiesto atado al commit del canal | módulo nuevo en `apps/desktop-janitor/brand/` | misma corrida: manifiesto alterado, otra clave, firma truncada, clave RSA, contenido firmado pero inválido, versión más vieja, repetición de entrega, nombres con `../` |
| F9-03 | **Hecho (2026-11-27), sin auditar.** `detectInstallKind` en el mismo módulo: AppImage, paquete de pacman, desconocido; plataforma y hechos del disco como datos. Windows y macOS dan «desconocido» en esta entrega | mismo sitio | misma corrida: tres pruebas «install kind» |
| F9-04 | **Hecho (2026-11-27), sin auditar ni ver en pantalla.** Parche P22 (`brand/app-update-patches.mjs`): `checkUpdates` añade `janitorApp` y marca actualización también con «motor al día, app vieja»; la caché se ata a la versión de la app; aviso único «Hay una versión nueva de Janitor» con «Actualizar ahora» / «Más tarde»; «Actualizar siempre sin preguntar» en Ajustes → Acerca de (apagado por defecto, un arranque desatendido por sesión) | parche de compilación sobre `main.ts`, `updates.ts`, `about-settings.tsx`, `global.d.ts` | `node apps/desktop-janitor/scripts/build.mjs --check` → `280/280 patches resolve`; `node --test apps/desktop-janitor/scripts/app-update-patches.test.mjs` → 10 pruebas, 0 fallos. **No verificado:** la app compilada en pantalla (lo cubre la compilación de CI y F9-10) |
| F9-05 | **Hecho (2026-11-27), sin auditar.** `prepareUpdate` / `createDesktopUpdater`: baja y verifica manifiesto e instalador en `~/.janitor/desktop-update/<entrega>/` antes de cerrar; un rechazo vuelve antes de lanzar el relevo («No se cambió nada»); tipo desconocido, compilación sin clave o motor anterior al relevo nuevo → relevo de siempre, sin tocar la red | parche de compilación | pruebas con servidor local en `app-update.test.mjs`: N→N+1, repetición, solo motor, instalador sustituido, descarga corta o larga, `stable` que cambia durante la descarga, versión incompleta, repetición de una antigua |
| F9-06 | **Hecho para Linux (2026-11-27), sin auditar.** `scripts/desktop-update/janitor-app.sh` (propio del fork) enganchado en `posix.sh`: app primero, motor después con `--commit`; AppImage por copia verificada y renombrado; Arch por `pkexec` del auxiliar del paquete; reabre siempre; paso anotado en `~/.janitor/desktop-update/paso.json`. macOS, sin tocar | `scripts/desktop-update/posix.sh` (ya declarado en el inventario) y `janitor-app.sh` (declarado en `fork_paths`) | `scripts/run_tests.sh tests/janitor/test_janitor_desktop_update_app.py` → 20 pruebas, 0 fallos (N→N+1, archivo sustituido tras verificarlo, carpeta sin permiso, corte a mitad y reintento, contraseña cancelada, sin agente de polkit, rechazos del auxiliar). `pkexec` es un sustituto en esas pruebas |
| F9-07 | **Sin empezar (segunda entrega).** Guion de Windows: instalador silencioso, reabrir, resultados | `scripts/desktop-update/windows.ps1` | pruebas en el ejecutor de Windows |
| F9-08 | **Hecho para Linux (2026-11-27), sin auditar.** Textos nuevos en español; el aviso «AppImage/deb/rpm» ya no existe: para una instalación desconocida dice que esa copia no se actualiza sola y da el enlace a las versiones | `apps/desktop-janitor/brand/`, guiones | prueba «the relay no longer tells anyone to reinstall «AppImage/deb/rpm» by hand»; `test_janitor_overlay_contract.py::test_touchpoint_contract[desktop-update-posix]` |
| F9-09 | **Hecho en parte para Linux (2026-11-27).** Arch: paso «Updater end to end (N → N+1, throwaway keys)» del trabajo `arch-package` (instala el paquete N real, compila N+1, ejecuta el auxiliar real como root con claves de ensayo). AppImage: pruebas del relevo con ejecutables sustitutos y de la descarga con servidor local. **No cubierto en CI:** la app Electron real cerrándose y reabriendo la N+1, el diálogo de polkit y el camino `systemd-run` del auxiliar (el contenedor no tiene systemd) | flujo de publicación | ensayo local del paso de Arch en un contenedor `archlinux:base-devel` con un AppImage de mentira: `== Arch updater e2e: all checks passed (0.21.5.janitor.4-1 → 0.21.5.janitor.5-1)`. Corrida de CI: ver el PR |
| F9-10 | **Sin hacer.** Prueba real: equipo del dueño (Arch) y, si hay equipos, Windows y Mac. Necesita la clave del dueño y una versión publicada | — | evidencia anotada; lo no probado se anota como no probado |
| F9-11 | **Hecho para la entrega de Linux (2026-11-27).** Diseño del auxiliar revisado antes de escribirlo por un subagente distinto y por Codex (sección 9.2). Código final revisado por un subagente Opus distinto, que leyó el diff y volvió a correr las pruebas (sección 9.5): sin bloqueantes; 4 hallazgos importantes y 6 menores, corregidos o anotados. Pendiente: nada de Linux; la revisión se repite con Windows y macOS | sección 9.5 | directiva #20 |

| F9-12 | **Hecho (2026-11-27), sin auditar.** `janitor update --commit <sha>`: 40 hexadecimales; el commit debe estar contenido en `origin/<rama>` (se comprueba antes del stash, del cambio de rama y de activar código); nunca vuelve a un commit que HEAD ya superó; `merge --ff-only` y el mismo `reset --hard` de respaldo | `janitor/update_core.py` | `scripts/run_tests.sh tests/janitor/test_janitor_update_commit_pin.py` → 12 pruebas, 0 fallos, con git real |
| F9-13 | **Hecho (2026-11-27), sin auditar el código.** `janitor-update-helper` (root), acción `ai.janitor.desktop.update` (`auth_admin`, sin «keep»), clave pública y carpeta privada `/var/cache/janitor-desktop`, todo dentro del paquete. Diseño y revisiones en la sección 9 | `apps/desktop-janitor/packaging/arch/` | ensayo en contenedor de Arch (F9-09): 11 rechazos sin cambiar nada, N→N+1, repetición y paquete más viejo. **No verificado:** el diálogo de polkit en una sesión gráfica real, ni que polkit considere activa la sesión cuando el relevo corre bajo `user@.service` (Hyprland) |
| F9-14 | **Hecho (2026-11-27), sin ejecutar.** Orden nuevo del trabajo `release`: comprobar que el canal podrá avanzar (sin empujar nada) → descargar y comprobar archivos → manifiesto, firma y verificación → publicar (los archivos se suben con la versión en borrador) → verificar lo publicado → mover `stable` al final | flujo de publicación | lectura del YAML. **No verificado:** el trabajo `release` solo corre con una etiqueta `v…`, que solo ordena el dueño |

Orden (ajustado tras la revisión de Codex): F9-00; **ensayos tempranos en equipos
reales** de lo que puede tumbar el diseño (reemplazo del `.app` en macOS con firma ad
hoc, instalador silencioso en Windows 11, diálogo de polkit en Arch); F9-01, F9-02,
F9-03, F9-12 y F9-14; F9-05, F9-06, F9-07 y F9-13; F9-04 y F9-08 al final, cuando lo de
debajo funciona. La revisión de seguridad (F9-11) se hace dos veces: sobre el diseño de
permisos antes de escribirlo y sobre el código final. F9-09 y F9-10 van **antes** de
etiquetar, con dos compilaciones de prueba y claves de ensayo, e incluyen: N→N+1,
contraseña cancelada, corte a mitad, `stable` que cambia durante la descarga, archivo
sustituido tras verificarlo y repetición de la misma entrega. Dos entregas posibles:
primero Linux (AppImage y Arch), que se puede probar en el equipo del dueño; después
Windows y macOS.

Aparte, visto en los registros del 2026-11-27 y sin investigar: al reabrir la app tras
actualizar había un backend ya escuchando al que no se conectó, y arrancó otro.

## 7. Decisiones del dueño (tomadas el 2026-11-27: se acepta cada propuesta)

Quedan dos cosas que la aprobación no contesta: si un botón al abrir cumple «totalmente
automático» o debe arrancar sin preguntar (7.1 queda con el botón y la opción en
Ajustes), y si el dueño dispone de un Mac y un Windows 11 para los ensayos reales.

1. **¿Preguntar o actualizar sin preguntar?** Propuesta: preguntar al abrir («Actualizar
   ahora» / «Más tarde») y ofrecer en Ajustes «Actualizar siempre sin preguntar». El
   dueño dijo «totalmente automático»: falta que confirme si un botón al abrir lo
   cumple o si quiere que arranque sin preguntar.
2. **Clave de firma.** Propuesta: par Ed25519 creado por el dueño, privada como secreto
   del repositorio en un entorno protegido que solo usa el flujo de publicación. El
   agente no crea ni ve la clave privada. Codex recomienda además una segunda clave
   guardada fuera de GitHub que autorice y revoque la de publicación: protege si se
   filtra la primera, a cambio de que el dueño la custodie. Decidir si se hace desde el
   principio o después.
3. **Windows solo por usuario.** Propuesta: sí; quita la pregunta «para todos» del
   instalador y con ella el permiso de administrador en cada actualización.
4. **Arch.** Propuesta: auxiliar con permisos dentro del paquete (sección 4.2).
   Alternativa: repositorio propio.
5. **macOS.** Propuesta: implementarlo y probarlo en un Mac real antes de prometerlo; si
   macOS lo impide con firma ad hoc, queda la descarga guiada hasta tener certificado.
6. **Entregas.** Propuesta: Linux primero, Windows y macOS después.

## 8. Revisión de Codex (2026-11-27)

Consulta de solo lectura por el puente (modelo solicitado `gpt-6.2-astra`). Veredicto:
**la opción B es la arquitectura correcta**, pero el primer borrador no se podía aprobar
tal cual para los cuatro destinos. Seis hallazgos; los tres primeros hechos comprobados
por Claude en el código, y todos incorporados arriba salvo lo que se indica:

1. **Crítico — en Arch se podía cambiar el paquete después de verificarlo.** El archivo
   estaba en una carpeta del usuario y `pacman` lo abría como root tras el diálogo de
   contraseña: otro programa del usuario podía sustituirlo en ese intervalo y obtener
   root. Corregido en el diseño: verifica e instala un auxiliar de root sobre su propia
   copia (4.2, F9-13).
2. **Crítico — la firma no cubría el motor.** Comprobado: `update_core.py` hace
   `pull --ff-only` o `reset --hard origin/<rama>`, es decir, la punta de la rama, no un
   commit. Corregido: destino por commit del manifiesto (4.2, F9-12).
3. **Alta — «reabrir la anterior» no garantizaba una app que funcione** si el motor ya
   era nuevo y el contrato había subido. Corregido: app primero, motor después, y paso
   anotado (4.1). **No incorporado**: exigir una versión intermedia para saltos de
   contrato; se decide el día que el contrato suba por primera vez.
4. **Alta — `stable` se mueve antes de que la versión esté completa.** Comprobado en el
   flujo de publicación: el paso «Move the release channel to the tag» va antes de
   «Attach the files to the release». Ocurre ya hoy. Corregido en el plan (F9-14).
5. **Alta — faltaban frescura y recuperación de claves.** Incorporado el número de
   entrega y la repetición de la misma entrega (4.3). **Sin incorporar, a decisión del
   dueño**: segunda clave fuera de línea (7.2) y metadatos con caducidad para detectar
   que alguien congela las actualizaciones.
6. **Alta — macOS y Windows necesitan pruebas de admisión del sistema.** Comprobado: el
   intercambio actual hace dos movimientos seguidos y borra la marca de cuarentena.
   Incorporado: conservar la copia anterior hasta confirmar el arranque, no forzar el
   cambio de alcance en Windows, y los ensayos tempranos en equipos reales (6).

Límites que Codex declaró: revisión estática, sin equipos macOS ni Windows, sin sesión
gráfica de Arch, sin ejecutar CI. Siguen sin verificar la conservación de permisos en
macOS, el Control inteligente de aplicaciones y la transición de instalaciones «para
todos» en Windows.

## 9. Primera entrega: Linux (2026-11-27)

Hecha por Claude en la rama `janitor-app/actualizacion-automatica-linux`. Alcance:
AppImage y paquete de Arch. Fuera: Windows, macOS y cualquier cambio de comportamiento
para instalaciones «desconocidas» (solo cambió el texto de su aviso).

### 9.1 Cómo quedó

- **Manifiesto** `janitor-update.json` + `janitor-update.json.sig` por versión. El número
  de entrega se calcula de la versión (`0.21.5-janitor.4` → `21005004`): crece con cada
  versión y no necesita historial de git ni contador aparte. Regla que lo sostiene: nunca
  dos compilaciones con la misma versión (la etiqueta ya la impone `check_tag`).
- **La app** localiza la versión del canal leyendo `pyproject.toml` en el commit de
  `stable`, baja manifiesto y firma de esa versión y exige que nombren ese commit. Nada
  se cree hasta que la firma vale.
- **Relevo**: el guion que corre es el del motor instalado (el anterior a la
  actualización). Por eso la app comprueba que ese guion sabe instalar la app antes de
  pasarle nada; si no, hace el relevo de siempre. Consecuencia: la primera actualización
  del motor tras la última instalación manual todavía muestra el aviso antiguo una vez.
- **Sin clave no hay cambio**: sin `brand/update-key.pem` la app se compila con clave
  `null`, el paquete de Arch lleva la clave vacía y el auxiliar se niega, y el flujo de
  publicación avisa y publica sin manifiesto.

### 9.2 Auxiliar de Arch: diseño revisado antes de escribirlo (directiva #20)

Dos revisiones de solo lectura del diseño, las dos antes del código: un subagente Opus
distinto (con comprobaciones locales: `openssl pkeyutl` con Ed25519, `vercmp`, qué
conserva `pkexec`) y Codex por el puente (modelo solicitado `gpt-6.2-astra`). Ambas: el
diseño cierra el hallazgo 1 de la sección 8 y no hay camino a root ni a instalar algo
sin firma. Lo que encontraron y se adoptó:

| Hallazgo | Quién | Qué se hizo |
|---|---|---|
| El auxiliar hereda de quien lo llama el cgroup, los límites, las señales ignoradas y el terminal: un programa del usuario puede congelar o matar `pacman` a mitad | subagente | `pacman` corre como unidad transitoria del sistema (`systemd-run --wait --pipe --collect`); sin systemd, sesión nueva, entorno vacío, señales y límites restablecidos |
| El lector sin privilegios conserva descriptores heredados y se puede trazar | ambos | subproceso que cierra todo descriptor ≥ 3, entrada y errores a `/dev/null`, `setpriv --no-new-privs --inh-caps=-all --bounding-set=-all`, plazo con `KILL` también sobre el receptor de root |
| Se copiaba hasta 1 GiB antes de saber si el manifiesto valía; dos auxiliares a la vez podían bajar de versión | ambos | manifiesto y firma primero; el tope del paquete es el tamaño firmado; un solo auxiliar a la vez (`flock`); limpieza de restos y comprobación de espacio bajo el bloqueo |
| Buscar una línea del manifiesto aceptaría esa línea en cualquier sitio | Codex | tras verificar la firma se exige UNA sola entrada con el nombre del paquete y de ella salen tamaño y suma |
| Versión | ambos | se rechaza si el paquete no está instalado; se compara la versión completa (`pkgver-pkgrel`) |
| `pacman` reemplaza el guion mientras corre | subagente | todo el cuerpo dentro de `main` |

No adoptado: guardar en `/var/lib` el mayor número de entrega aceptado por root (lo cubre
la regla «una compilación por versión»). No cubierto: otro gestor de paquetes bajando la
versión a la vez que el auxiliar (no es el atacante del modelo).

Pasos del auxiliar, en orden: argumentos y `PKEXEC_UID`; bloqueo; copia del manifiesto y
la firma leídos con la identidad del usuario; firma Ed25519 con la clave que instaló el
paquete; entrada única del paquete en el manifiesto; copia del paquete con el tamaño
firmado como tope; tamaño y SHA-256 de la copia; solo entonces `.PKGINFO` (nombre,
versión, arquitectura); nunca más viejo que el instalado; `pacman -U --noconfirm
--noprogressbar -- <copia>`.

Corridas del 2026-11-27 en el equipo de desarrollo (worktree, con el entorno de Python
del checkout principal): `scripts/run_tests.sh tests/janitor/` → 51 archivos, 916
pruebas pasan, 2 fallan en `test_janitor_overlay_contract.py` (una, la del relevo, se
corrigió después y pasa a solas; la otra es la de la versión instalada, ver 9.3);
`node --test apps/desktop-janitor/scripts/*.test.mjs` → 404 pruebas, 0 fallos;
`node apps/desktop-janitor/scripts/build.mjs --check` → `280/280 patches resolve`;
`python -m janitor.overlay check` → `every divergence is fork-owned or a declared
touchpoint`; `python -m janitor.catalog check` → `40/40 catalog entries resolve`.

### 9.3 Lo que NO está verificado

- **El diálogo de polkit en una sesión gráfica real** (CI no tiene sesión ni agente), y
  que polkit considere «activa» la sesión cuando el relevo corre desacoplado bajo
  `user@.service` en Hyprland. Si no la considera activa, `pkexec` devuelve 127 y el
  usuario ve el aviso con el comando manual: no se rompe nada, pero no sería automático.
- El camino `systemd-run` del auxiliar (el contenedor de CI no tiene systemd; ahí corre el
  camino alternativo).
- La app Electron real: ver el aviso, descargar, cerrarse y reabrir la versión nueva.
  Las pruebas cubren la lógica y el relevo por separado, con sustitutos entre medias.
- El trabajo `release` con una etiqueta y con el secreto de firma reales.
- En el equipo de desarrollo, `test_touchpoint_contract[version]` falla porque el entorno
  de Python prestado del checkout principal tiene instalada la `.2`; no depende de este
  cambio (comprobar en CI).
- Las correcciones de la sección 9.5 las probó quien las escribió; el revisor no las ha
  vuelto a leer.
- Durante la ventana entre publicar la versión y mover `stable` (sección 9.5), que una
  instalación nueva desde el AppImage recién publicado consiga su commit pidiéndolo por
  SHA (`scripts/install.sh`, `git fetch origin <sha>`): GitHub lo permite para commits
  alcanzables, pero no se ha ejecutado.

### 9.4 Lo que tiene que hacer el dueño a mano

1. Crear el par de claves, guardar la privada como secreto `JANITOR_UPDATE_SIGNING_KEY`
   del entorno `janitor-release` y subir la pública a
   `apps/desktop-janitor/brand/update-key.pem`: pasos exactos en
   [`../actualizacion-firma.md`](../actualizacion-firma.md).
2. Ordenar la etiqueta de la primera versión con actualizador.
3. Instalar esa versión a mano por última vez en su equipo (`sudo pacman -U`) y
   actualizar el motor una vez (verá el aviso antiguo una última vez).
4. Con la versión siguiente, hacer la prueba real (F9-10): aviso al abrir, contraseña del
   sistema, reapertura sola; y probar a cancelar la contraseña.

### 9.5 Revisión del código por un revisor distinto (directiva #20, 2026-11-27)

Un subagente Opus sin el contexto del autor leyó el diff completo del PR 109 contra este
plan y volvió a correr las verificaciones. Veredicto: apto con correcciones menores; sin
bloqueantes y sin camino a root, a instalar algo sin firma, a bajar de versión ni a que
root lea archivos ajenos. Cada hallazgo se comprobó contra el código antes de aceptarlo.

| Hallazgo | Qué se hizo |
|---|---|
| Una app instalada a mano por delante del canal (o una instalación que sigue otra rama) dejaba al motor sin poder actualizarse desde la app: el manifiesto «más viejo» o inexistente lo bloqueaba todo | App por delante del canal → solo motor, fijado al commit del manifiesto (`decideUpdate`); sigue rechazándose una entrega más vieja que una ya aceptada. Instalación que sigue otra rama → relevo de siempre, sin pedir manifiesto (`releaseBranch`). Pruebas nuevas en `app-update.test.mjs` |
| `pacman` escribía en la tubería de quien llamó al auxiliar: un programa del usuario podía cortarlo o bloquearlo a mitad (reabría en parte el primer hallazgo de 9.2) | La salida de `pacman` va a un archivo en la carpeta privada de root y se copia a la salida de errores al terminar |
| La directiva #13 de `AGENTS.md` seguía diciendo que `stable` se mueve antes de adjuntar | Corregida: se mueve al final, tras publicar y verificar (F9-14) |
| La ventana entre publicar y mover `stable` no estaba analizada | Se mantiene el orden (canal al final, hallazgo 3 de la sección 8). En esa ventana la versión existe pero nadie la recibe; si el último `push` falla, se vuelve a lanzar el trabajo. Una instalación nueva desde ese AppImage clona `stable` y pide su commit por SHA: no verificado (9.3) |
| Sin plazo propio al pedir versión, manifiesto y firma | 30 s (`MANIFEST_TIMEOUT_MS`), con prueba |
| Dos pruebas leían código fuente | Sustituida una por una prueba de carga del módulo aislado; eliminada la otra (el relevo ya lo prueban `test_janitor_desktop_update*.py`). El resto de `app-update-patches.test.mjs` comprueba el texto ya parcheado, como las demás pruebas de parches del overlay: se deja |
| `paso.json` no lo lee nadie, y el plan decía que sí | Texto corregido (4.1 y `janitor-app.sh`): es solo diagnóstico |
| El aviso de la salida 13 del auxiliar solo describía uno de sus dos casos | Aviso que cubre los dos |
| Faltaba probar un manifiesto firmado sin la entrada del paquete, o con ella dos veces | Dos casos nuevos en `arch-update-e2e.sh` (salida 13) |
| Restos `.janitor-nuevo.*` de un corte junto al AppImage | Se borran al empezar la siguiente instalación |

Corridas tras las correcciones: `node --test apps/desktop-janitor/scripts/*.test.mjs` →
406 pruebas, 0 fallos; `node apps/desktop-janitor/scripts/build.mjs --check` → `280/280
patches resolve`; `scripts/run_tests.sh tests/janitor/` → 917 pasan, 1 falla (la de la
versión instalada del entorno prestado, 9.3; el revisor confirmó la causa);
`python -m janitor.overlay check` y `python -m janitor.catalog check` → correctos;
`arch-update-e2e.sh` en un contenedor `archlinux:base-devel` local → 13 rechazos, N→N+1,
repetición y paquete más viejo: `all checks passed (0.21.5.janitor.4-1 →
0.21.5.janitor.5-1)`. `shellcheck` no está instalado en el equipo: no se corrió.
