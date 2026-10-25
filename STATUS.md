# Estado

_Actualizado 2026-10-24 · Claude Code_

## Probar

- Safari con el backup real (1.01 GB): carga inicial, lazy loading, búsqueda en conversación, Actualizar carpeta y memoria de Safari Web Content (1.9 GB antes del lazy loading). Cómo: Abrir viewer.html en Safari, elegir respaldos-llms, abrir un proyecto sin abrir conversación, después una conversación larga; probar buscar una palabra del final. _(«Definir próximos pasos» · Codex · 19/08)_
- Project Home reordenado (índice de Activity / Conversations / Project review / Project facts) y buscador conectado con debounce de 200 ms. Cómo: Recargar el viewer completo, abrir un proyecto, ver si en el primer pantallazo están Activity y Conversations, usar los 4 accesos y buscar una palabra al final de una conversación. _(«Definir próximos pasos» · Codex · 19/08)_
- Activar con Enter los pills de conteo de la conversación: Lucas reportó que apretaba Enter y no pasaba nada; el handoff dice que ya está cubierto. Cómo: En una conversación enfocar un pill de turnos/tools con Tab y apretar Enter, debe filtrar. _(«Definir próximos pasos» · Codex · 19/08)_
- Conversaciones Codex recuperadas de x-stock-market (task secundaria caducada): se reconstruyó el .md y se dio el prompt para retomarla en una task nueva. Cómo: Buscar 'Sincronizar main preservando backup pre-sync' en x-stock-market y confirmar si queda algo funcional pendiente. _(«Evaluar recuperación» · Codex · 19/08)_

## Destrabar

- [PRIORIDAD] Mergear a main el branch `claude/open-items-rescue-ec4e91` (layer simple de open items, ya pusheado). **Recomiendo:** mergearlo esta semana, antes de la próxima corrida de open-items, así sale desde main. (opciones: mergear ahora / revisar el diff primero / dejarlo en el branch) _(«Rescate de pendientes en Trailkeep» · Claude Code · 21/10)_

## Último cambio

- 2026-10-24 · feat(viewer): «Ir al último turno» pasa a botón flotante que aparece mientras el final no está a la vista

## Próxima sesión

Leé docs/agent-handoff.md y ROADMAP.md. Mergeá a main el branch `claude/open-items-rescue-ec4e91` (layer simple de open items, `skills/trailkeep-open-items/`); la automation `trailkeep-generative-review` queda pausada.
El rescate ya corrió sobre todo el historial (61 proyectos en `_open_items.json`, STATUS.md en 30 repos). Próximo paso: hacerlo incremental (solo conversaciones nuevas) y partir las conversaciones gigantes en vez de omitir el medio.
Hay trabajo sin commitear en viewer.html, docs/index.html y extract_ledger.py: commitealo en partes y pusheá los 7 commits locales.
