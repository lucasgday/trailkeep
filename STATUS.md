# Estado

_Actualizado 2026-10-20 · Claude Code (rescate trailkeep)_

## Probar

- Safari con el backup real (1.01 GB): carga inicial, lazy loading, búsqueda en conversación, Actualizar carpeta y memoria de Safari Web Content (1.9 GB antes del lazy loading). Cómo: Abrir viewer.html en Safari, elegir respaldos-llms, abrir un proyecto sin abrir conversación, después una conversación larga; probar buscar una palabra del final. _(«Definir próximos pasos» · Codex · 19/08)_
- Project Home reordenado (índice de Activity / Conversations / Project review / Project facts) y buscador conectado con debounce de 200 ms. Cómo: Recargar el viewer completo, abrir un proyecto, ver si en el primer pantallazo están Activity y Conversations, usar los 4 accesos y buscar una palabra al final de una conversación. _(«Definir próximos pasos» · Codex · 19/08)_
- Activar con Enter los pills de conteo de la conversación: Lucas reportó que apretaba Enter y no pasaba nada; el handoff dice que ya está cubierto. Cómo: En una conversación enfocar un pill de turnos/tools con Tab y apretar Enter, debe filtrar. _(«Definir próximos pasos» · Codex · 19/08)_
- Conversaciones Codex recuperadas de x-stock-market (task secundaria caducada): se reconstruyó el .md y se dio el prompt para retomarla en una task nueva. Cómo: Buscar 'Sincronizar main preservando backup pre-sync' en x-stock-market y confirmar si queda algo funcional pendiente. _(«Evaluar recuperación» · Codex · 19/08)_

## Destrabar

Nada.

## Pendiente sin backlog

- Commitear en partes lo que está sin commit: búsqueda dentro de la conversación, índice de Project Home, sticky de Analytics, perfil del agente colapsable y fix del modelo unknown de Codex (viewer.html, docs/index.html, extract_ledger.py, DESIGN/PRODUCT/ROADMAP). _(«Definir próximos pasos» · Codex · 19/08)_
- Pushear a origin/main los 7 commits locales (deploy_url, continuidad Claude, tokens, viewer) para que la demo de GitHub Pages tome el viewer nuevo. _(«Revisar actualización de deploy URL» · Codex · 19/08)_
- Correr open-items (trailkeep) en el resto del historial después del 2026-10-25; featherlist-web es la mitad del costo. _(sesión 2026-10-20)_
- Recuperar los raws de Claude de las 132 sesiones históricas con tokens legacy (TRAILKEEP_CLAUDE_RAW_EXTRA) para normalizarlas; hoy quedan excluidas del ranking por modelo. _(«Corrige conversaciones faltantes» · Codex · 19/08)_

## Último cambio

- 2026-10-04 · docs: add CLAUDE.md importing AGENTS.md (8243ad5)

## Próxima sesión

Leé docs/agent-handoff.md y ROADMAP.md. Mergeá a main el branch `claude/open-items-rescue-ec4e91` (layer simple de open items, `skills/trailkeep-open-items/`); la automation `trailkeep-generative-review` queda pausada.
Después del reinicio semanal del 2026-10-25, revisá el presupuesto y corré open-items en el resto de los proyectos (piloto hecho: tercyon, agentlog, facturante-conversion).
Hay trabajo sin commitear en viewer.html, docs/index.html y extract_ledger.py: commitealo en partes y pusheá los 7 commits locales.
