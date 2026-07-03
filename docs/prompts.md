# Canonical Prompts

These are the canonical user-facing prompts for trailkeep's optional generative
layer.

`docs/generative-layer.md` remains the source of truth for architecture, privacy,
schemas, sidecar contracts, model routing, evals, and automation rules. This file
only canonizes the prompts users copy into their coding agent.

The viewer is a standalone offline HTML file, so it embeds copies of these
prompts instead of loading this file at runtime. When changing prompt text, keep
these locations synchronized:

- `viewer.html`
- `docs/index.html`
- `docs/prompts.md`

## Initial Setup

Use this once to install or link the shared skill and configure the coding-agent
automation that runs after trailkeep's normal backup.

```text
Set up the optional trailkeep generative layer in my coding agent.

Context:
- trailkeep itself stays local and never makes network calls. The backup scripts and viewer never send data.
- This optional review layer is agent-powered and runs inside my coding agent after the normal trailkeep backup.
- If this agent uses a remote model provider, selected project context may be sent to that provider as part of the review.
- If this agent cannot prove the model is local/on-device, treat it as remote.
- Use the strongest available model with extremely high reasoning/effort for bootstrap, deep-review, design-system extraction, and global agent profile generation. If this agent cannot select reasoning effort or submodes directly, use its strongest available model/profile and record the actual model used.
- Set output_language for this automation:
  - If this setup prompt is Spanish, set output_language: "es".
  - If this setup prompt is English, set output_language: "en".
  - Use output_language for all generated sidecar prose in recurring runs.
  - Record output_language in _review_update_log.json for each run.
  - Keep JSON schema keys in English.
- Only send context selected by _review_run_plan.json unless I explicitly approve a wider deep-review scope.
- Remote-provider approval happens once during setup. Daily runs should not ask again merely because the provider is remote; they should ask only when the gate reports unresolved requires_approval, or when provider/model, scope, schedule, or output files materially change. possible_secret inputs with preprocessed_ref are already redacted locally.
- The optional automation may run git fetch in local project repos to check whether remote changes make a review stale. It must never run git pull or modify a worktree without my explicit approval.
- Do not start caffeinate, change pmset, or disable the screen saver. This review automation does not need host power-management changes; leave the user's sleep and screen-saver behavior untouched.
- Do not send secrets, API keys, tokens, credentials, private env files, or unrelated repo data.
- Do not add model calls to update-backup.sh or viewer.html.

Source of truth:
- In the local trailkeep repo, read docs/generative-layer.md and follow it exactly.
- Read skills/trailkeep-project-review/SKILL.md and use the mandatory wrapper at scripts/run-project-review-agent-gates.sh.
- If you cannot find docs/generative-layer.md, ask me for the trailkeep repo path before continuing.

Your tasks:
1. Resolve backup_dir as the folder containing markdown-* folders and the _review_run_plan.json you will consume.
2. Install or link the shared trailkeep-project-review skill from the repo if this agent supports local skills.
3. Resolve skill_dir as the installed skill path, or fallback to <trailkeep_repo>/skills/trailkeep-project-review.
4. Resolve review_gate_cmd as <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Use this wrapper for all pre-model, repo-sync, and finalizer gates. If skill_dir is outside the repo, pass --skill-dir <skill_dir> to the wrapper.
5. Before installing or enabling any recurring job that may call a remote or unproven-local model, or run git fetch in local project repos, show me the schedule, scope, provider/model tier, concrete model name or alias when known, repo remote-check behavior, estimated tokens to be processed, local files it will write, and that selected context may be sent to the provider. Wait for approval once.
6. Create a recurring review automation owned by this coding agent. Prefer a true post-backup trigger if this agent supports it. If only time-based scheduling is available, infer the daily trailkeep backup/update schedule from the installed launchd/cron job or recent backup_dir/log.json entries, then schedule the review 10-15 minutes after that update normally runs.
7. Create or use a dedicated coding-agent automation thread/subagent for recurring trailkeep review runs. Use the main/user-visible thread only for setup approval and intervention prompts.
8. Before any model call, read backup_dir/_review_run_plan.json and backup_dir/_review_eval_report.json.
9. Run <review_gate_cmd> pre --backup-dir <backup_dir>. It must validate that the plan/eval are current and aligned, and confirm backup_dir/log.json has a latest backup run less than 24 hours old. Continue to model calls only if it exits 0. Exit 0 may be partial; use only projects in _review_effective_plan.json.
10. If the wrapper pre command exits 0 with partial=true or pending_projects, continue only with the safe effective plan and surface the pending approval batch as a non-blocking intervention. Do not send skipped projects or inputs to the model. If it reports auto_excluded_secret_inputs, treat those as non-fatal privacy exclusions.
11. If the wrapper pre command exits 2, open or resume this coding-agent thread and ask me once with the full approval batch from the gate output. Use only sanitized project names and input ids. Do not ask project-by-project, and do not continue model calls until I choose. Do not ask on a daily run only because the provider is remote if the setup approval was already granted.
12. After I approve, exclude, or stop, write that choice to backup_dir/_review_gate_decisions.json scoped to the current plan generated_at and input content_hashes, then rerun <review_gate_cmd> pre --backup-dir <backup_dir>. Do not edit _review_run_plan.json. needs_approval is a transient pause, not a permanent blocker.
13. When the wrapper pre command exits 0, use backup_dir/_review_effective_plan.json for model context if it exists. Excluded inputs and skipped projects must not be sent to the model. For any selected input with preprocessed_ref, read the sanitized text from backup_dir/_review_preprocessed_inputs.json and use that instead of the raw markdown; it may be redacted for secrets, sanitized for instruction/context boilerplate, or both.
14. Before reviewing projects with local git repos, run <review_gate_cmd> repo-sync --backup-dir <backup_dir>. It may run git fetch to update remote-tracking refs, but must never pull or modify worktrees. Use _review_repo_sync.json to mark repo_may_be_stale, sync_uncertain, or needs_deep_review.
15. Run incrementally and cumulatively by default: compare current sessions, repo docs, metadata, git/repo-sync/deploy state with _project_reviews.json checkpoints; reuse previous summaries/reviews as compact memory; process only selected deltas; skip unchanged projects.
16. Do not reread full raw conversations just because time passed. Full raw reads are allowed only for bootstrap/deep-review modes, scoped to the project unless I approve a global full-archive pass. Escalate only for broad/conflicting changes, low confidence, evidence-backed stale checkpoints, remote commits ahead, or major metadata changes.
17. Preserve stable task ids, review notes, and previous conclusions unless new evidence changes them. Use cheaper model tiers for classification/summarization and stronger tiers only for deep project review or design-system extraction.
18. Respect requires_approval, possible_secret, preprocessed_ref, instruction_context, needs_deep_review, needs_deep_design_review, repo_may_be_stale, and sync_uncertain exactly as described in docs/generative-layer.md. Ground every durable generated claim with evidence_refs from selected conversations, conversation summaries, repo docs, metadata, repo sync, tool turns, or prior sidecars. Treat tool turns as execution evidence, not narrative: cite type:"tool" evidence for implemented/fixed/verified/test/build/pass/fail claims, and never paste long raw tool output into generated sidecars. Treat AGENTS/global/system/developer instruction blocks as constraints, not user intent: do not create summaries, decisions, tasks, next_step, roadmap_status, open_questions, or recommended repo-doc updates from instruction_context alone; use it only for repo conventions, agent profile, constraints, or verification/security rules. Do not create tasks, decisions, next steps, roadmap status, open questions, or recommended repo-doc updates without evidence; use unknown or an evidence-backed open_question when evidence is insufficient.
19. For bootstrap or deep-review runs, checkpoint continuously. Do not keep generated output only in memory until the end. Before writing each conversation summary, set summary_quality_version: "actionable-v3", include the coverage matrix fields from docs/generative-layer.md, and run <review_gate_cmd> validate-summary --summary-json <summary-entry.json> --session-id <session-id> --expected-content-hash <content-hash>. After each valid conversation summary, atomically merge backup_dir/_conversation_summaries.json using a temporary file and rename when possible. Run semantic/LLM quality sampling at least once every 25 generated summaries, and always for low-confidence, context-dependent, task_candidate/decision/blocker-producing, very long, preprocessed/redacted, or project-rollup summaries. Record the semantic sample in _review_update_log.json.semantic_quality_review; if it is skipped because model access is unavailable, mark the run needs_attention. After each project review, atomically merge backup_dir/_project_reviews.json. If usage/time/context/provider limits stop the run, update backup_dir/_review_update_log.json with status needs_attention, pending counts, and enough checkpoint metadata to resume. Next run must resume from matching content_hash and summary_quality_version checkpoints and skip already summarized conversations.
20. Write generated sidecars only at the root of backup_dir:
   - _conversation_summaries.json
   - _project_reviews.json
   - _agent_profile.json
   - _review_repo_sync.json
   - _review_update_log.json
21. After writing sidecars, run: <review_gate_cmd> finalize --backup-dir <backup_dir> --model-provider <provider_or_agent> --model-routing <available_or_unavailable> --model-used <concrete_model_or_alias_or_unknown> --output-language en
22. If the finalizer fails, do not mark the review run ok. If it records needs_attention, treat the run as completed with warnings and surface those warnings. Use _review_generated_eval_report.json and _review_update_log.json as the evidence.
23. Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
24. Never transmit the entire backup folder as an archive or unscoped dump. Use the _review_run_plan.json input manifest first.
25. Do not commit private backups or generated sidecars.

After setup, report:
- skill install path or fallback;
- automation schedule/trigger, including derived backup time and review offset if time-based;
- backup_dir;
- model tier routing availability and concrete model used or model alias;
- repo sync behavior and any stale/uncertain repos;
- sidecars that will be written;
- unresolved approvals or decisions.
```

## Initial Setup (Spanish)

Versión localizada del setup inicial. El viewer la copia cuando la UI está en
español.

```text
Configurá la capa generativa opcional de trailkeep en mi coding agent.

Contexto:
- trailkeep en sí se mantiene local y nunca hace llamadas de red. Los scripts de backup y el viewer nunca envían datos.
- Esta capa opcional de review corre dentro de mi coding agent después del backup normal de trailkeep.
- Si este agente usa un proveedor remoto de modelos, el contexto seleccionado de proyectos puede enviarse a ese proveedor como parte de la review.
- Si este agente no puede probar que el modelo es local/on-device, tratalo como remoto.
- Usá el modelo más fuerte disponible con razonamiento/esfuerzo extremely high para bootstrap, deep-review, extracción de design system y generación del perfil global del agente. Si este agente no puede elegir esfuerzo de razonamiento o submodos directamente, usá su modelo/perfil más fuerte disponible y registrá el modelo real usado.
- Seteá output_language para esta automatización:
  - Si este prompt de setup está en español, seteá output_language: "es".
  - Si este prompt de setup está en inglés, seteá output_language: "en".
  - Usá output_language para todo el contenido generado de sidecars en runs recurrentes.
  - Registrá output_language en _review_update_log.json en cada run.
  - Mantené las claves del schema JSON en inglés.
- Enviá solo el contexto seleccionado por _review_run_plan.json salvo que yo apruebe explícitamente un alcance más amplio de deep-review.
- La aprobación de proveedor remoto ocurre una sola vez durante el setup. Los runs diarios no deberían volver a preguntar solo porque el proveedor es remoto; solo deben preguntar cuando el gate reporte requires_approval sin resolver, o cuando cambien materialmente provider/model, alcance, schedule o archivos de output. Los inputs possible_secret con preprocessed_ref ya están redactados localmente.
- La automatización opcional puede correr git fetch en repos locales de proyectos para revisar si cambios remotos vuelven stale una review. Nunca debe correr git pull ni modificar un worktree sin mi aprobación explícita.
- No inicies caffeinate, no cambies pmset ni desactives el salvapantallas. Esta automatización de review no necesita cambios de energía del sistema; dejá intacto el comportamiento de sleep y salvapantallas del usuario.
- No envíes secretos, API keys, tokens, credenciales, archivos env privados ni datos no relacionados del repo.
- No agregues llamadas a modelos dentro de update-backup.sh ni viewer.html.

Fuente de verdad:
- En el repo local de trailkeep, leé docs/generative-layer.md y seguí esa spec exactamente.
- Leé skills/trailkeep-project-review/SKILL.md y usá el wrapper obligatorio en scripts/run-project-review-agent-gates.sh.
- Si no podés encontrar docs/generative-layer.md, pedime el path del repo de trailkeep antes de continuar.

Tus tareas:
1. Resolvé backup_dir como la carpeta que contiene carpetas markdown-* y el _review_run_plan.json que vas a consumir.
2. Instalá o linkeá la skill compartida trailkeep-project-review desde el repo si este agente soporta skills locales.
3. Resolvé skill_dir como el path de la skill instalada, o usá como fallback <trailkeep_repo>/skills/trailkeep-project-review.
4. Resolvé review_gate_cmd como <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Usá este wrapper para todos los gates pre-model, repo-sync y finalizer. Si skill_dir está fuera del repo, pasá --skill-dir <skill_dir> al wrapper.
5. Antes de instalar o habilitar cualquier job recurrente que pueda llamar a un modelo remoto o no comprobado como local, o correr git fetch en repos locales de proyectos, mostrame schedule, alcance, provider/model tier, nombre concreto de modelo o alias cuando se conozca, comportamiento de chequeo remoto de repos, tokens estimados a procesar, archivos locales que va a escribir, y que el contexto seleccionado puede enviarse al proveedor. Esperá mi aprobación una vez.
6. Creá una automatización recurrente de review propiedad de este coding agent. Preferí un trigger real post-backup si este agente lo soporta. Si solo hay scheduling por horario, inferí el horario diario de backup/update de trailkeep desde launchd/cron instalado o entradas recientes de backup_dir/log.json, y programá la review 10-15 minutos después de cuando normalmente corre ese update.
7. Creá o usá un thread/subagent dedicado del coding agent para los runs recurrentes de review de trailkeep. Usá el thread principal/visible para setup approval y prompts de intervención.
8. Antes de cualquier model call, leé backup_dir/_review_run_plan.json y backup_dir/_review_eval_report.json.
9. Corré <review_gate_cmd> pre --backup-dir <backup_dir>. Debe validar que plan/eval estén actualizados y alineados, y confirmar que backup_dir/log.json tenga un último backup de menos de 24 horas. Continuá a model calls solo si sale 0. Exit 0 puede ser parcial; usá solo proyectos en _review_effective_plan.json.
10. Si el comando pre del wrapper sale 0 con partial=true o pending_projects, continuá solo con el effective plan seguro y mostrale al usuario el batch pendiente de aprobación como intervención no bloqueante. No envíes proyectos ni inputs salteados al modelo. Si reporta auto_excluded_secret_inputs, tratalos como exclusiones de privacidad no fatales.
11. Si el comando pre del wrapper sale 2, abrí o retomá este thread del coding agent y preguntame una vez con el batch completo de aprobación del output del gate. Usá solo nombres de proyecto e input ids sanitizados. No preguntes proyecto por proyecto, y no continúes model calls hasta que yo elija. No preguntes en un run diario solo porque el proveedor es remoto si la aprobación de setup ya fue dada.
12. Después de que yo apruebe, excluya o frene, escribí esa decisión en backup_dir/_review_gate_decisions.json acotada al generated_at del plan actual y a los content_hashes de inputs, y después corré de nuevo <review_gate_cmd> pre --backup-dir <backup_dir>. No edites _review_run_plan.json. needs_approval es una pausa transitoria, no un bloqueo permanente.
13. Cuando el comando pre del wrapper salga 0, usá backup_dir/_review_effective_plan.json para el contexto del modelo si existe. Los inputs excluidos y proyectos salteados no deben enviarse al modelo. Para cualquier input seleccionado con preprocessed_ref, leé el texto saneado desde backup_dir/_review_preprocessed_inputs.json y usalo en lugar del markdown raw; puede estar redactado por secretos, saneado por boilerplate de instrucciones/contexto, o ambas.
14. Antes de revisar proyectos con repos git locales, corré <review_gate_cmd> repo-sync --backup-dir <backup_dir>. Puede correr git fetch para actualizar refs remote-tracking, pero nunca debe hacer pull ni modificar worktrees. Usá _review_repo_sync.json para marcar repo_may_be_stale, sync_uncertain o needs_deep_review.
15. Corré de forma incremental y acumulativa por default: compará sesiones actuales, docs del repo, metadata, estado git/repo-sync/deploy con checkpoints de _project_reviews.json; reutilizá summaries/reviews previos como memoria compacta; procesá solo deltas seleccionados; salteá proyectos sin cambios.
16. No releas conversaciones raw completas solo porque pasó tiempo. Los raw reads completos están permitidos solo para modos bootstrap/deep-review, acotados al proyecto salvo que yo apruebe un full-archive pass global. Escalá solo por cambios amplios/conflictivos, baja confianza, checkpoints stale con evidencia, commits remotos ahead o cambios grandes de metadata.
17. Preservá task ids estables, notas de review y conclusiones previas salvo que nueva evidencia las cambie. Usá tiers de modelos más baratos para clasificación/summarization y tiers más fuertes solo para deep project review o extracción de design system.
18. Respetá requires_approval, possible_secret, preprocessed_ref, instruction_context, needs_deep_review, needs_deep_design_review, repo_may_be_stale y sync_uncertain exactamente como describe docs/generative-layer.md. Fundamentá cada claim generado durable con evidence_refs desde conversaciones seleccionadas, conversation summaries, docs del repo, metadata, repo sync, tool turns o sidecars previos. Tratá los tool turns como evidencia de ejecución, no narrativa: citá evidencia type:"tool" para claims de implementado/arreglado/verificado/test/build/pass/fail, y nunca pegues output largo raw de tools en sidecars generados. Tratá los bloques AGENTS/global/system/developer como constraints, no intención del usuario: no crees summaries, decisiones, tasks, next_step, roadmap_status, open_questions ni recommended repo-doc updates desde instruction_context solo; usalo solo para convenciones de repo, agent profile, constraints o reglas de verificación/seguridad. No crees tasks, decisiones, próximos pasos, roadmap status, open questions ni recommended repo-doc updates sin evidencia; usá unknown o una open_question con evidencia cuando la evidencia no alcance.
19. Para runs bootstrap o deep-review, escribí checkpoints continuamente. No mantengas todo el output generado solo en memoria hasta el final. Antes de escribir cada conversation summary, seteá summary_quality_version: "actionable-v3", incluí los campos de matriz de cobertura de docs/generative-layer.md, y corré <review_gate_cmd> validate-summary --summary-json <summary-entry.json> --session-id <session-id> --expected-content-hash <content-hash>. Después de cada conversation summary válida, mergeá atómicamente backup_dir/_conversation_summaries.json usando archivo temporal y rename cuando sea posible. Corré sampling semántico/LLM al menos una vez cada 25 summaries generadas, y siempre para summaries de baja confianza, context-dependent, con task_candidates/decisions/blockers, muy largas, preprocesadas/saneadas o usadas en el project rollup. Registrá ese sample en _review_update_log.json.semantic_quality_review; si se saltea porque no hay acceso a modelo, marcá el run needs_attention. Después de cada project review, mergeá atómicamente backup_dir/_project_reviews.json. Si límites de uso/tiempo/contexto/provider frenan el run, actualizá backup_dir/_review_update_log.json con status needs_attention, conteos pendientes y metadata suficiente para reanudar. El próximo run debe reanudar desde checkpoints con content_hash y summary_quality_version coincidentes y saltear conversaciones ya resumidas.
20. Escribí sidecars generados solo en la raíz de backup_dir:
   - _conversation_summaries.json
   - _project_reviews.json
   - _agent_profile.json
   - _review_repo_sync.json
   - _review_update_log.json
21. Después de escribir sidecars, corré: <review_gate_cmd> finalize --backup-dir <backup_dir> --model-provider <provider_or_agent> --model-routing <available_or_unavailable> --model-used <concrete_model_or_alias_or_unknown> --output-language es
22. Si el finalizer falla, no marques el run de review como ok. Si registra needs_attention, tratá el run como completado con warnings y mostrale esos warnings al usuario. Usá _review_generated_eval_report.json y _review_update_log.json como evidencia.
23. No escribas sidecars generados dentro de repos de proyectos, carpetas raw de herramientas fuente, carpetas markdown-* ni el repo de trailkeep.
24. Nunca transmitas la carpeta completa de backups como archivo comprimido ni como dump sin scope. Usá primero el input manifest de _review_run_plan.json.
25. No commitees backups privados ni sidecars generados.

Después del setup, reportá:
- ruta de instalación de la skill o fallback;
- schedule/trigger de la automatización, incluyendo horario de backup derivado y offset de review si es por horario;
- backup_dir;
- disponibilidad de model tier routing y modelo concreto usado o alias;
- comportamiento de repo sync y repos stale/uncertain;
- sidecars que se van a escribir;
- aprobaciones o decisiones sin resolver.
```

## Manual Project Review

Use this only when refreshing one project immediately instead of waiting for the
daily post-backup automation. The viewer fills the placeholders with the
selected project's metadata and ledger stats. The model context comes from
`_review_effective_plan.json` after the pre gate passes, not from a recent
conversation list in the prompt.

```text
Update the incremental trailkeep review for this project.

Project: <project_name>

Known facts:
- path: <project_path_or_virtual>
- repo: <repo_url_or_none>
- git: <branch_commit_dirty_or_none>
- stack: <detected_stack_or_none>
- status: <active_inactive_gone_or_unknown>
- conversations: <conversation_count>

Activity:
<ledger_activity>

Instructions:
- Follow docs/generative-layer.md from the local trailkeep repo if available.
- Follow skills/trailkeep-project-review/SKILL.md if the repo skill is available.
- output_language: "en". Write generated sidecar prose for this run in English. Keep JSON schema keys in English.
- Resolve backup_dir as the folder containing markdown-* folders and the _review_run_plan.json for this run. If ambiguous, ask.
- Resolve skill_dir as the installed trailkeep-project-review skill path, or fallback to <trailkeep_repo>/skills/trailkeep-project-review.
- Resolve review_gate_cmd as <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Use this wrapper for all gates. If skill_dir is outside the repo, pass --skill-dir <skill_dir> to the wrapper.
- Before any model call, run <review_gate_cmd> pre --backup-dir <backup_dir>. It also confirms the plan/eval are current and aligned, and backup_dir/log.json has a latest backup run less than 24 hours old. Continue only if it exits 0; exit 0 may be partial, so use only _review_effective_plan.json.
- If the wrapper pre command exits 0 with partial=true or pending_projects, continue only with the safe effective plan and surface the pending approval batch; do not send skipped projects or inputs to the model.
- If the wrapper pre command exits 2, resolve approval through _review_gate_decisions.json, rerun <review_gate_cmd> pre --backup-dir <backup_dir>, and then use _review_effective_plan.json for model context.
- Before model calls for a project with a local git repo, run <review_gate_cmd> repo-sync --backup-dir <backup_dir>. It may run git fetch to update remote-tracking refs, but must never pull or modify worktrees. If _review_repo_sync.json marks repo_may_be_stale or sync_uncertain, reflect that in the project review.
- Write generated sidecars only at the root of backup_dir, especially backup_dir/_project_reviews.json.
- After writing sidecars, run <review_gate_cmd> finalize --backup-dir <backup_dir> --output-language en.
- If the finalizer fails, do not mark the review run ok. If it records needs_attention, treat the run as completed with warnings.
- Do not write generated sidecars into project repos, source-tool raw folders, markdown-* folders, or the trailkeep repo.
- First inspect the local repo if it exists.
- If ROADMAP.md, BACKLOG.md, TODO.md, docs/product-progress.md, docs/project-progress.md, docs/agent-handoff.md, docs/design-patterns.md, docs/design.md, design.md, AGENTS.md with continuity/product instructions, local issues/configs, or equivalents exist, treat those files as the source of truth.
- For next step, roadmap, and tasks, roadmap/backlog/product-progress win. For design-system extraction, design docs and real component files win. Conversations only explain recent decisions or undocumented changes.
- Preserve the user's existing priority/order from roadmap/backlog files. Suggested next steps should advance the existing roadmap when present.
- If conversations reveal new legitimate work not present in the roadmap, add it as a pending/candidate task or open question with evidence. Do not silently promote it above the existing roadmap priorities.
- If roadmap/backlog/todo/design docs are stale, duplicated, or contradictory, add focused recommendations to recommended_repo_doc_updates with file, reason, action, confidence, evidence_refs, and requires_user_approval=true. Never modify repo planning docs automatically during recurring runs.
- Ground every durable claim in this project entry with evidence_refs. summary, standing_context, next_step, roadmap_status, tasks, open_questions, and recommended_repo_doc_updates must cite selected conversations, conversation summaries, repo docs, metadata, repo sync, tool turns, or prior sidecars. Treat tool turns as execution evidence, not narrative: cite type:"tool" evidence for implemented/fixed/verified/test/build/pass/fail claims, and never paste long raw tool output into generated sidecars. Treat AGENTS/global/system/developer instruction blocks as constraints, not user intent: do not create product tasks, next_step, roadmap_status, open_questions, or recommended_repo_doc_updates from instruction_context alone; use it only for repo conventions, agent profile, constraints, or verification/security rules. Do not create tasks or conclusions without evidence; use unknown or an evidence-backed open_question when evidence is insufficient.
- Run design-system review daily, but incrementally: skip projects without UI/design changes; use design docs and component files as source of truth; use new conversations only as evidence for changes or undocumented decisions; update design_system only with new evidence; set needs_deep_design_review=true for broad or conflicting changes instead of rereading the full project automatically.
- Use selected inputs from _review_effective_plan.json as supporting evidence for recent decisions, completed work, and blockers. Do not use UI conversation titles as evidence.
- Do not re-read everything if unnecessary: compare against _project_reviews.json and process only deltas.
- Update or create this project's entry in _project_reviews.json.
- Preserve stable task ids unless there is clear evidence.
- If there are contradictions, add them to open_questions with evidence_refs.
- If context is insufficient, set needs_deep_review or needs_deep_design_review instead of inventing.

Return/write only the updated JSON entry for this project, compatible with the backup_dir/_project_reviews.json sidecar.
```

## Manual Project Review (Spanish)

Versión localizada del prompt manual de proyecto. Usalo solo para refrescar un
proyecto ahora, sin esperar la automatización diaria post-backup.

```text
Actualizá la review incremental de trailkeep para este proyecto.

Proyecto: <project_name>

Datos conocidos:
- path: <project_path_or_virtual>
- repo: <repo_url_or_none>
- git: <branch_commit_dirty_or_none>
- stack: <detected_stack_or_none>
- estado: <active_inactive_gone_or_unknown>
- conversaciones: <conversation_count>

Actividad:
<ledger_activity>

Instrucciones:
- Seguí docs/generative-layer.md del repo local de trailkeep si está disponible.
- Seguí skills/trailkeep-project-review/SKILL.md si la skill del repo está disponible.
- output_language: "es". Escribí el contenido generado de sidecars para este run en español. Mantené las claves del schema JSON en inglés.
- Resolvé backup_dir como la carpeta que contiene carpetas markdown-* y el _review_run_plan.json de este run. Si es ambiguo, preguntá.
- Resolvé skill_dir como el path de la skill trailkeep-project-review instalada, o usá como fallback <trailkeep_repo>/skills/trailkeep-project-review.
- Resolvé review_gate_cmd como <trailkeep_repo>/scripts/run-project-review-agent-gates.sh. Usá este wrapper para todos los gates. Si skill_dir está fuera del repo, pasá --skill-dir <skill_dir> al wrapper.
- Antes de cualquier model call, corré <review_gate_cmd> pre --backup-dir <backup_dir>. También confirma que plan/eval estén actualizados y alineados, y que backup_dir/log.json tenga un último backup de menos de 24 horas. Continuá solo si sale 0; exit 0 puede ser parcial, así que usá solo _review_effective_plan.json.
- Si el comando pre del wrapper sale 0 con partial=true o pending_projects, continuá solo con el effective plan seguro y mostrale al usuario el batch pendiente de aprobación; no envíes proyectos ni inputs salteados al modelo.
- Si el comando pre del wrapper sale 2, resolvé la aprobación mediante _review_gate_decisions.json, corré de nuevo <review_gate_cmd> pre --backup-dir <backup_dir>, y después usá _review_effective_plan.json como contexto del modelo.
- Antes de model calls para un proyecto con repo git local, corré <review_gate_cmd> repo-sync --backup-dir <backup_dir>. Puede correr git fetch para actualizar refs remote-tracking, pero nunca debe hacer pull ni modificar worktrees. Si _review_repo_sync.json marca repo_may_be_stale o sync_uncertain, reflejalo en la review del proyecto.
- Escribí sidecars generados solo en la raíz de backup_dir, especialmente backup_dir/_project_reviews.json.
- Después de escribir sidecars, corré <review_gate_cmd> finalize --backup-dir <backup_dir> --output-language es.
- Si el finalizer falla, no marques el run de review como ok. Si registra needs_attention, tratá el run como completado con warnings.
- No escribas sidecars generados dentro de repos de proyectos, carpetas raw de herramientas fuente, carpetas markdown-* ni el repo de trailkeep.
- Primero inspeccioná el repo local si existe.
- Si existen ROADMAP.md, BACKLOG.md, TODO.md, docs/product-progress.md, docs/project-progress.md, docs/agent-handoff.md, docs/design-patterns.md, docs/design.md, design.md, AGENTS.md con instrucciones de continuidad/producto, issues/configs locales o equivalentes, tratá esos archivos como fuente de verdad.
- Para próximo paso, roadmap y tasks, ganan roadmap/backlog/product-progress. Para extracción de design system, ganan docs de diseño y componentes reales. Las conversaciones solo explican decisiones recientes o cambios no documentados.
- Preservá la prioridad/orden existente del usuario en roadmap/backlog. Los próximos pasos sugeridos deben avanzar el roadmap existente cuando exista.
- Si las conversaciones revelan trabajo legítimo nuevo que no está en el roadmap, agregalo como task pendiente/candidata u open question con evidencia. No lo promociones silenciosamente por encima de las prioridades existentes del roadmap.
- Si roadmap/backlog/todo/design docs están stale, duplicados o contradictorios, agregá recomendaciones enfocadas a recommended_repo_doc_updates con file, reason, action, confidence, evidence_refs y requires_user_approval=true. Nunca modifiques docs de planificación del repo automáticamente durante runs recurrentes.
- Fundamentá cada claim durable de esta entrada de proyecto con evidence_refs. summary, standing_context, next_step, roadmap_status, tasks, open_questions y recommended_repo_doc_updates deben citar conversaciones seleccionadas, conversation summaries, docs del repo, metadata, repo sync, tool turns o sidecars previos. Tratá los tool turns como evidencia de ejecución, no narrativa: citá evidencia type:"tool" para claims de implementado/arreglado/verificado/test/build/pass/fail, y nunca pegues output raw largo de tools en sidecars generados. Tratá bloques AGENTS/global/system/developer como constraints, no intención del usuario: no crees product tasks, next_step, roadmap_status, open_questions ni recommended_repo_doc_updates desde instruction_context solo; usalo solo para convenciones de repo, agent profile, constraints o reglas de verificación/seguridad. No crees tasks ni conclusiones sin evidencia; usá unknown o una open_question con evidencia cuando la evidencia no alcance.
- Corré design-system review diariamente, pero incrementalmente: salteá proyectos sin cambios UI/diseño; usá docs de diseño y componentes como fuente de verdad; usá conversaciones nuevas solo como evidencia de cambios o decisiones no documentadas; actualizá design_system solo con evidencia nueva; seteá needs_deep_design_review=true para cambios amplios o conflictivos en vez de releer todo el proyecto automáticamente.
- Usá inputs seleccionados desde _review_effective_plan.json como evidencia de soporte para decisiones recientes, trabajo completado y bloqueos. No uses títulos de conversaciones de la UI como evidencia.
- No releas todo si no hace falta: compará contra _project_reviews.json y procesá solo deltas.
- Actualizá o creá la entrada de este proyecto en _project_reviews.json.
- Preservá task ids estables salvo que haya evidencia clara.
- Si hay contradicciones, agregalas a open_questions con evidence_refs.
- Si el contexto es insuficiente, seteá needs_deep_review o needs_deep_design_review en vez de inventar.

Devolvé/escribí solo la entrada JSON actualizada para este proyecto, compatible con el sidecar backup_dir/_project_reviews.json.
```

## Approval Intervention

Use this shape when `<review_gate_cmd> pre` exits `2`, or as a non-blocking
intervention when it exits `0` with `partial: true`. Do not show raw
conversation text, suspected secret values, or unscoped backup contents.

```text
Trailkeep needs your approval for some review inputs.

I have not sent the inputs below to a model. Safe projects may continue from
_review_effective_plan.json.

Reason:
- requires_approval was set in _review_run_plan.json.

possible_secret inputs with preprocessed_ref are redacted locally and should not
appear in this approval batch. If the gate excluded a possible-secret input
because no redacted replacement existed, report it as needs_attention instead of
asking for approval by default.

Flagged inputs:
<sanitized_input_ids_from_pre_model_gate>

Choose one:
- approve this run as planned;
- exclude specific input ids and rerun the gate;
- stop this review run.

After you choose, I will write `_review_gate_decisions.json` for the current plan and rerun the gate. I will continue only after the gate exits 0 and will use `_review_effective_plan.json` for model context.
```
