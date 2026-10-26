# Estado

_Actualizado 2026-10-25 · Claude Code_

## Probar

- Safari con el backup real (1.01 GB): carga inicial, lazy loading, búsqueda en conversación, Actualizar carpeta y memoria de Safari Web Content (1.9 GB antes del lazy loading). Cómo: Abrir viewer.html en Safari, elegir respaldos-llms, abrir un proyecto sin abrir conversación, después una conversación larga; probar buscar una palabra del final. _(«Definir próximos pasos» · Codex · 19/08)_
- Project Home reordenado (índice de Activity / Conversations / Project review / Project facts) y buscador conectado con debounce de 200 ms. Cómo: Recargar el viewer completo, abrir un proyecto, ver si en el primer pantallazo están Activity y Conversations, usar los 4 accesos y buscar una palabra al final de una conversación. _(«Definir próximos pasos» · Codex · 19/08)_
- Activar con Enter los pills de conteo de la conversación: Lucas reportó que apretaba Enter y no pasaba nada; el handoff dice que ya está cubierto. Cómo: En una conversación enfocar un pill de turnos/tools con Tab y apretar Enter, debe filtrar. _(«Definir próximos pasos» · Codex · 19/08)_
- Conversaciones Codex recuperadas de x-stock-market (task secundaria caducada): se reconstruyó el .md y se dio el prompt para retomarla en una task nueva. Cómo: Buscar 'Sincronizar main preservando backup pre-sync' en x-stock-market y confirmar si queda algo funcional pendiente. _(«Evaluar recuperación» · Codex · 19/08)_

## Destrabar

- Tu checkout local de `main` quedó atrás de `origin/main` (el merge de open items se pusheó directo para no pisar lo que tenés sin commitear); `docs/agent-handoff.md` y `scripts/test-codex-subagents.cjs` cambiaron en los dos lados. **Recomiendo:** commitear lo tuyo y hacer `git pull`; si choca, es en esos dos archivos. (opciones: commitear y pull / stash con nombre, pull y aplicar / dejarlo para la próxima sesión) _(«Rescate de pendientes en Trailkeep» · Claude Code · 25/10)_

## Último cambio

- 2026-10-26 · feat(viewer): separador de día entre turnos cuando la conversación cambia de fecha

## Próxima sesión

Leé STATUS.md, BACKLOG.md y docs/agent-handoff.md. El layer de open items ya está en main y corrió sobre todo el historial (61 proyectos en `_open_items.json`, STATUS.md en 30 repos); la automation `trailkeep-generative-review` sigue pausada, no reabrirla.
Próximo: que `write_status.py` mande lo pendiente al backlog y marque `[PRIORIDAD]`, después corrida incremental y partir las conversaciones gigantes (ver BACKLOG.md).
