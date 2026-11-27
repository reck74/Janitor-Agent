## Qué cambia

<!-- El problema que resuelve y por qué este enfoque. Si es una tarea del plan, su id
(docs/janitor/plans/janitor-desktop-app.md). -->



## Cómo probarlo

<!-- Pasos para verificarlo. En un fallo: cómo se reproducía y la prueba de que ya no. -->

1. 

## Comprobaciones

- [ ] El PR solo contiene cambios de esta tarea, y los commits siguen Conventional Commits (`fix(janitor):`, `feat(janitor):`...)
- [ ] `scripts/run_tests.sh tests/janitor/` pasa, y añadí pruebas de comportamiento (no de instantánea) para el cambio
- [ ] `python -m janitor.overlay check` pasa: todo archivo de upstream editado está declarado como touchpoint en `janitor/overlay.yaml` (directiva #16)
- [ ] Ninguna búsqueda-y-reemplazo de `hermes` en el core (directiva #1)
- [ ] Si toqué el TUI: `npm run build` y `npm test` en `ui-tui/` (directiva #7)
- [ ] Si toqué una skill: `python -m janitor.catalog check` pasa (directiva #19)
- [ ] Texto visible en español y sin «Hermes» (directivas #17 y #18) — o N/A
- [ ] Actualicé el tablero del plan y la documentación afectada — o N/A

## Capturas o registros

<!-- Si aplica. -->
