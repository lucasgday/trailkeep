# Backlog

Lo pendiente de este repo. Lo que necesita una prueba o una decisión de Lucas está en STATUS.md.

- Commitear en partes lo que está sin commit: búsqueda dentro de la conversación, índice de Project Home, sticky de Analytics, perfil del agente colapsable y fix del modelo unknown de Codex (viewer.html, docs/index.html, extract_ledger.py, DESIGN/PRODUCT/ROADMAP). _(«Definir próximos pasos» · Codex · 19/08)_
- Pushear a origin/main los 7 commits locales (deploy_url, continuidad Claude, tokens, viewer) para que la demo de GitHub Pages tome el viewer nuevo. _(«Revisar actualización de deploy URL» · Codex · 19/08)_
- Conversaciones gigantes (miles de intercambios) llegan al digest con el medio omitido; partirlas en varias partes en vez de recortar (`converters/extract_digest.py`). _(«Rescate de pendientes en Trailkeep» · Claude Code · 21/10)_
- `write_status.py` y el prompt de open-items no marcan `[PRIORIDAD]`: los 30 STATUS.md generados no aparecen en "Para hoy" de la página de la mañana. Sumar la marca (máx 3 por repo) en la tanda final y en el writer. _(«Rescate de pendientes en Trailkeep» · Claude Code · 21/10)_
- Hacer incremental la corrida de open-items (solo conversaciones nuevas desde el último `state`), en vez de releer todo el historial. _(«Rescate de pendientes en Trailkeep» · Claude Code · 21/10)_
- Recuperar los raws de Claude de las 132 sesiones históricas con tokens legacy (TRAILKEEP_CLAUDE_RAW_EXTRA) para normalizarlas; hoy quedan excluidas del ranking por modelo. _(«Corrige conversaciones faltantes» · Codex · 19/08)_
