# Extracción de Documentación Oficial de n8n

n8n publica un índice completo de su documentación optimizado para consumo
por LLMs. Usar esto como fuente de verdad en lugar del knowledge interno
del modelo (que se desactualiza con cada release).

## Endpoint llms.txt

```
https://docs.n8n.io/llms.txt
```

- ~280KB de texto limpio (Julio 2026), 1,345 líneas
- Contiene TODOS los links de docs.n8n.io con descripción breve
- Organizado por secciones: Get started, Deploy, Build, Nodes, Integrate, Administer, etc.
- Ideal para reconocimiento antes de extraer contenido específico

### Técnica de extracción

1. `web_extract` el `llms.txt` completo (char_limit=25000 head+tail, o paginar
   el contenido si la respuesta se trunca)
2. Identificar las URLs `.md` relevantes al dominio de trabajo
3. `web_extract` cada URL `.md` (char_limit=10000-15000 por URL, batch de 4-5)
4. Escribir archivos `.md` estructurados citando la URL fuente

### Patrón de URL

Toda página de docs.n8n.io está disponible en markdown añadiendo `.md`:

| URL web | URL markdown |
|---------|-------------|
| `docs.n8n.io/build/flow-logic` | `docs.n8n.io/build/flow-logic.md` |
| `docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook` | `.../n8n-nodes-base.webhook.md` |

El markdown es contenido limpio sin chrome de UI, ideal para pipelines de
extracción automatizada.

## Estructura de la Documentación (secciones principales)

| Sección | Cobertura |
|---------|-----------|
| **Deploy** | Docker, npm, cloud providers, env vars, scaling, security, DB |
| **Build** | Workflows, nodes, data, expressions, code, flow logic, AI |
| **Nodes** | Core nodes (40+), app nodes (400+), trigger nodes, credentials |
| **Integrate** | MCP server, community nodes, custom API actions |
| **Administer** | Users, RBAC, SSO (SAML/OIDC), source control, credentials sharing |
| **API** | REST API reference (/api/v1), CLI commands |

## Proyecto de Documentación Local

Existe un proyecto local (ruta genérica `<your-docs-project>/`, p. ej.
`~/Projects/n8n_docs/`) con documentación operacional estructurada para
entrenamiento de agentes. 8 directorios:

```
01-core-concepts/  02-nodes/   03-workflows/    04-credentials/
05-self-hosting/   06-api/     07-integrations/ 08-troubleshooting/
```

Cada archivo `.md` cita la URL fuente de docs.n8n.io y la versión de
referencia (v2.31.6).

## Técnica de Paralelización

Para construir bases de documentación: desplegar 3 subagentes (delegate_task)
en paralelo, cada uno con:
- Un dominio de directorios asignado
- La lista exacta de URLs `.md` a extraer
- El formato obligatorio (metadata block, tablas, ejemplos, enlaces)
- Regla dura: web_extract antes de escribir, cero invención

El orquestador maneja los directorios que no requieren extracción masiva
(credentials, integrations) mientras los workers procesan los dominios pesados.
