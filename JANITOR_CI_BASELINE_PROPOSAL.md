# Propuesta pendiente: comparación de CI durante la sincronización

No aplicada. El control automático rechazó modificar estos gates sin aprobación explícita del alcance. Los workflows actuales permanecen intactos.

## Evidencia

- La comparación contra el fork de agosto produce 6.447 hallazgos de salud sobre 11.998 archivos, incluyendo el motor importado.
- Comparar las diferencias con Hermes estable d923a5eb487a17c0a68801bba9ef0f56c81040a8 produce 40 bloqueos sobre 117 archivos. Esos 40 se repararon; el diagnóstico final registra cero bloqueos y un advisory. No se propone omitirlos.
- Los tres blobs señalados contra el fork son idénticos por SHA de objeto Git a los de Hermes estable: nous-dmg-2b.tiff, gateway-contract.openrpc.json y test_tui_gateway_server.py.
- Los cuatro blobs inicialmente señalados al comparar con Hermes eran idénticos a los del fork anterior: infographic.png, telegram_welcome.jpg, janitor-logo-banner.png y filler-bg0.jpg. La infografía obsoleta se retiró siguiendo el guard existente; quedan los tres assets activos.

## Cambio exacto propuesto

Añadir un módulo aislado `janitor_ext/ci_baseline.py`, con el SHA estable anterior como constante aprobada, usado únicamente por los dos controles incrementales:

1. Verificar con Git que tanto la base del PR como ese motor exacto son ancestros de HEAD. Si falta historia o no coincide la ascendencia, fallar.
2. Salud: si la base del PR ya incluye el motor, seguir comparando contra la base del PR. Durante esta sincronización, comparar contra el motor exacto, de forma que todas las diferencias Janitor sigan sujetas a los límites actuales.
3. Blobs: mantener la detección contra la base del PR y excluir únicamente un resultado cuyo SHA de contenido completo ya exista en el árbol del motor aprobado. No eximir por nombre, tamaño, carpeta ni semejanza. Un solo byte nuevo vuelve a evaluarse normalmente.
4. Mantener todos los guards de árbol completo: Ruff, portabilidad, escritura de configuración, límites de AGENTS, interfaces de workflows, seguridad y pruebas. No cambiar sus límites ni sus listas de excepciones.
5. Añadir pruebas con repositorios Git temporales: merge válido; motor no ancestro; historia incompleta; base posterior al sync; blob idéntico heredado; mismo nombre con contenido distinto; archivo nuevo grande. El manifiesto canónico incluirá estas pruebas.

Workflows afectados:

```diff
--- .github/workflows/lint.yml
+++ .github/workflows/lint.yml
@@ code-health
-          fetch-depth: 2
+          fetch-depth: 0
-        run: python scripts/check --only health --base HEAD^1
+        run: python -m janitor_ext.ci_baseline health --base HEAD^1
--- .github/workflows/blob-size-check.yml
+++ .github/workflows/blob-size-check.yml
@@ check-blob-size
-          fetch-depth: 2
+          fetch-depth: 0
-        run: python3 scripts/ci/check_blob_size.py --base HEAD^1
+        run: python3 -m janitor_ext.ci_baseline blob-size --base HEAD^1
```

## Alcance y riesgo

El cambio acepta como deuda heredada la salud del motor estable elegido, en lugar de tratar toda su evolución desde agosto como código nuevo de Janitor. No demuestra que ese motor carezca de problemas. Durante esta sincronización también puede perder un límite más estricto alcanzado previamente por el fork: un método con complejidad 30 en Hermes, 25 en el fork anterior y 28 en el candidato pasaría contra Hermes y fallaría contra el fork. Una revisión independiente reprodujo este caso con el comparador real. Autorizar esta propuesta implica aceptar explícitamente ese cambio temporal de referencia y revisar esas unidades; no significa que todas las mejoras previas del fork queden protegidas automáticamente. Se añadirá el caso a las pruebas y al informe. La suite completa upstream y las pruebas del fork siguen siendo obligatorias. Después de integrar la sincronización en main, el control vuelve automáticamente a la base normal del PR y conserva las mejoras desde ese momento.

Alternativa más estricta, si no se acepta ese cambio de referencia: conservar por unidad los límites previos del fork y reconocer únicamente unidades idénticas al motor aprobado, en lugar de cambiar todo el baseline. Requiere implementar y probar ese comparador de dos padres; no está aplicado ni se da por autorizado.

Sin esta aprobación, los gates originales se conservan y el PR no puede declararse listo para publicación. El resto de reparaciones y validaciones puede continuar.
