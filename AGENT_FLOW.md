# brain_ds — Flujo Agéntico (doc viva)

> Documento de referencia del flujo agéntico end-to-end. Se edita en cada cambio
> que toque agentes, prompts, skills o el harness MCP. Última revisión: 2026-06-12.

## Mapa de piezas

| Pieza | Claude Code | OpenCode | Fuente de verdad |
|---|---|---|---|
| Orquestador | `.claude/agents/brainds-orchestrator.md` | agente global `brain-ds-orchestrator` (prompt `prompts/brain-ds-orchestrator.md`) | repo |
| Sub-agente: explorador de fuentes | `.claude/agents/brainds-source-explorer.md` | `brainds-source-explorer` (prompt `prompts/brainds-source-explorer.md`) | repo |
| Sub-agente: mapeador/pusheador al grafo | `.claude/agents/brainds-graph-mapper.md` | `brainds-graph-mapper` | repo |
| Sub-agente: mapeador de conexiones | `.claude/agents/brainds-connection-mapper.md` | `brainds-connection-mapper` | repo |
| Sub-agente: escritor de BRD | `.claude/agents/brainds-brd-writer.md` | `brainds-brd-writer` | repo |
| Sub-agente: verificador semántico | `.claude/agents/brainds-semantic-verifier.md` | `brainds-semantic-verifier` | repo |
| Sub-agente: elicitor de currency | `.claude/agents/brainds-currency-elicitor.md` | `brainds-currency-elicitor` (prompt `prompts/brainds-currency-elicitor.md`) | repo |
| Sub-agente: compositor de KPI | `.claude/agents/brainds-kpi-composer.md` | `brainds-kpi-composer` (prompt `prompts/brainds-kpi-composer.md`) | repo |
| Sub-agente: consultor del grafo | `.claude/agents/brainds-query-consultant.md` | — (pendiente) | repo |
| Skills de dominio | `skills/*/SKILL.md` | `.opencode/skills/*/SKILL.md` (espejo byte-idéntico) | `skills/` |
| Comandos slash | — | `~/.config/opencode/commands/*.md` (desplegados por installer) | `commands/` |
| Harness MCP (cross-client) | `brain_ds/mcp/grounding.py` — `run_elicit`, `map_connections`, `generate_brd` | ídem | `grounding.py` |

El **harness MCP es la fuente de verdad cross-client**: los prompts de OpenCode son
delgados a propósito y le ordenan al agente llamar el tool de grounding ANTES de
ejecutar; el payload lleva los contratos (`delegation_protocol`,
`brd_graph_persistence_contract`, `source_exploration_contract`, etc.).

## Modelo de delegación (estilo Gentle AI)

```
Usuario ──► Orquestador (la MENTE: pregunta, decide, coordina)
               │  pasa: graph id + artifact store + REFERENCIAS (nunca contenido)
               │
               │  [setup]   resolver grafo + workspace + artifact store
               │  [intake]  rama intake_paths:
               │              datasource → brainds-source-explorer → brainds-graph-mapper
               │              human_org  → entrevista propia + brainds-graph-mapper
               ├──► brainds-source-explorer   (scan de magnitud / documentación seccionada)
               ├──► brainds-graph-mapper      (consolida artefactos → update_node/add_edge → UI)
               │  [map]     brainds-connection-mapper (estructural + cross-cutting)
               ├──► brainds-connection-mapper (suggest_connections → add_edge / diferidos)
               │  [brd]     brainds-brd-writer (BRD 14 secciones)
               ├──► brainds-brd-writer        (BRD 14 secciones → nodo brd-<slug> + Engram)
                │  [verify]  compliance gate → verify-<slug>-<fecha>.md
                │              └──► brainds-semantic-verifier (juez de coherencia/consistencia, advisory)
                 ├──► brainds-currency-elicitor  (assess_currency → preguntas priorizadas → insert_pending_question)
                 ├──► brainds-kpi-composer      (on-demand: get_kpi_dossier → propose → confirm → add_edge)
                 │  [archive] mover artefactos si verify pasó
                └──► brainds-query-consultant  (preguntas sobre el grafo)
               ▲
               └── cada sub-agente devuelve: status, executive_summary,
                   artifacts, next_recommended, risks  (el orquestador
                   se queda SOLO con el resumen)
```

Reglas duras:
- El orquestador NUNCA lee fuentes ni compone el BRD él mismo.
- Sub-agentes NO re-delegan (rol bloqueado en su prompt). En OpenCode además
  está forzado por el allowlist `permission.task` (`*: deny`).
- Skills: SOLO las de brain_ds. Prohibido invocar skills/agentes de otros
  proyectos instalados en la máquina (`sdd-*`, `gentle-*`, etc.).

## Pipeline lineal (`pipeline_stages`)

El flujo sigue **6 etapas ordenadas** definidas en `DELEGATION_PROTOCOL.pipeline_stages`
(fuente de verdad: `grounding.py`):

| Etapa | Agente(s) | Descripción |
|---|---|---|
| `setup` | `brainds-orchestrator` | Resolver grafo org, artifact store, workspace. |
| `intake` | `brainds-source-explorer`, `brainds-graph-mapper` | Ingestar/documentar fuentes de datos. Rama según `intake_paths`. |
| `map` | `brainds-connection-mapper` | Mapeo estructural + cross-cutting de conexiones. |
| `brd` | `brainds-brd-writer` | BRD 14 secciones → nodo `brd-<slug>` + Engram. |
| `verify` | `brainds-orchestrator` | Compliance gate; escribe `verify-<slug>-<fecha>.md`. |
| `archive` | `brainds-orchestrator` | Mueve artefactos a `.elicit/changes/<change>/` solo si `verify` pasó. |

### Currency elicitation (Brick E)

Cuando `assess_currency` detecta brechas de recencia, el orquestador puede delegar
la entrevista focalizada a `brainds-currency-elicitor`. El sub-agente soporta
`open` (ranking global por staleness × criticality) y `scoped` (vecindario primero),
usa `retrieve_context` para contexto acotado y devuelve preguntas contestadas y
pending questions stakeholder-tagged via `insert_pending_question`. Un pending NO confirma currency ni resetea
staleness.

### KPI dossier composer (on-demand)

`brainds-kpi-composer` NO es una etapa de `pipeline_stages`. El orquestador lo
delegará solo ante una solicitud explícita de dossier de KPI o una acción del
cluster KPI en el viewer. El flujo es: `get_kpi_dossier` para estado actual,
`suggest_connections` para candidatos, `insert_pending_question` para que el
humano confirme, `resolve_confirmation` para leer el veredicto y `add_edge` solo
si el veredicto fue confirmado. Usa `measured-from` para KPI → DataContainer y
`depends-on` para KPI → Heuristic/Project/Decision. Rechazados, abstenciones y
pendientes no crean edges; DataField requiere confirmación humana explícita.

### Ramificación del intake (`intake_paths`)

`DELEGATION_PROTOCOL.intake_paths` define dos caminos para la etapa `intake`:

- **`datasource`** — existe un nodo Data Source con fuente explorable:
  `brainds-source-explorer` (SCOPE + DOCUMENT) → `brainds-graph-mapper` (CONSOLIDATE + PUSH).
- **`human_org`** — el conocimiento viene del usuario, no de una fuente explorable:
  `brainds-orchestrator` (entrevista elicit) → `brainds-graph-mapper` (push al grafo).

## Configuración de sesión (artifact store)

El orquestador pregunta UNA vez por sesión dónde guardar artefactos intermedios:

| Opción | Dónde | Cuándo conviene |
|---|---|---|
| `engram` | memoria persistente, topic keys `org/<slug>/<fase>/<fecha-o-sección>` | default si Engram está disponible |
| `.elicit` | archivos `.elicit/<fase>-<slug>-<fecha>.md` en el proyecto | sin Engram, o para commitear artefactos |
| `both` | ambos | recuperación cross-sesión + trazabilidad local |

Fases con artefactos: `elicit`, `source-exploration`, `source-docs`, `map`, `brd`, `verify`, `archive`.

## Flujo de exploración de data sources (por etapas)

1. **SCOPE** — `brainds-source-explorer` en Modo A: scan de magnitud (contenedores,
   tablas/hojas, estimación de filas). Devuelve recomendación mono/multi-agente.
2. **PLAN** — el orquestador parte la documentación en secciones disjuntas
   (por tabla/hoja/endpoint). Los documentadores nunca se pisan.
3. **DOCUMENT** — N × `brainds-source-explorer` en Modo B, cada uno documenta SOLO
   sus secciones (formato `hierarchy_template`) y guarda en el artifact store.
4. **CONSOLIDATE + PUSH** — `brainds-graph-mapper` lee todos los artefactos,
   consolida y persiste al grafo (`update_node` con card_sections + `add_edge`).
   Recién ahí la fuente documentada se ve en la UI.

## Persistencia del BRD (gap cerrado 2026-06-12)

`/generate-brd --save` escribe DOS stores (ambos obligatorios):
1. **Nodo del grafo** `brd-<slug>` (`label: BRD`, `type: Unknown`,
   `card_sections[0] = {title: "Contenido", content: <markdown>, order: 0}`) —
   es lo que el panel BRD de la UI lee (`brain_ds/ui/src/panels/brd-panel.ts`).
2. **Espejo Engram** `org/<slug>/domain/brd/<timestamp>`.

El contrato vive en `BRD_GRAPH_PERSISTENCE_CONTRACT` (`grounding.py`) y se
entrega en el payload de `generate_brd`, así CUALQUIER cliente MCP sabe cómo
meter el BRD al grafo.

## Notas por nodo (UI)

La sección de notas existe por nodo en el reader (`split-pane.ts`): markdown con
wikilinks, edición inline, autosave (`PATCH /api/nodes/:id` →
`details.notes`). No hay sección de notas global — las notas viven en cada nodo.

## Instalación y paridad

- `brain_ds setup --agent both` (default `both`) — escribe `.mcp.json` y
  `.opencode/opencode.json` con el mismo root absoluto.
- `install-opencode.ps1 -Global -Agent` / `install-opencode.sh --global --agent` —
  despliega skills, comandos, orquestador + 4 sub-agentes con allowlist en el
  config global de OpenCode.
- **`brain_ds check`** — checker de paridad (20 checks): entradas MCP de ambos
  clientes alineadas, mirror de skills byte-idéntico, agentes de Claude
  presentes con grants correctos, orquestador/sub-agentes/comandos globales sin drift. Exit 1 si
  algo falla. Guard de CI: `tests/test_harness_check.py`.

## Contrato de artefactos `.elicit` (canonical dual-contract)

Cada archivo `.elicit/<fase>-<slug>-<fecha>.md` sigue el **dual-contract**:
- Prosa markdown legible por humanos.
- UN bloque JSON canónico (`\`\`\`json ... \`\`\``) al FINAL del archivo (el
  verificador selecciona el ÚLTIMO bloque; bloques de ejemplo anteriores son
  ignorados). El bloque puede estar precedido por `<!-- canonical-payload -->`.
- El payload incluye `artifact_type` (string con el nombre de la fase) como clave
  de nivel superior.

El contrato por fase vive en `ARTIFACT_CONTRACT` (`grounding.py`) y se entrega en
los 3 payloads de grounding (`artifact_contract`). `brainds-connection-mapper`
tiene `Write` en su lista de tools para poder escribir `.elicit/map-*.md`.

## Pendientes conocidos

- [ ] OpenCode: agregar `brainds-query-consultant` como sub-agente global.
- [ ] `brain_ds setup` podría desplegar también `.claude/agents/` en workspaces
      ajenos al repo (hoy los agentes de Claude solo existen dentro del repo).
- [x] Convención de limpieza para `.elicit/` (retención de artefactos) — resuelta en `.elicit/README.md` con naming activo y archivo bajo `.elicit/changes/<change-name>/`.
