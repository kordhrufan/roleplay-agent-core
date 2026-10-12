"""Exact approved contents of the 4c2 templates (REV4C2-04).

Frozen from the plan; any change to a template must be deliberate and update this file.
"""

EXPECTED_INSTANCE_JSON = (
    '{\n'
    '  "core_root": $core_root_json,\n'
    '  "corpus": {\n'
    '    "path": "corpus/state.json",\n'
    '    "revision": $corpus_revision,\n'
    '    "sha256": $corpus_sha256_json,\n'
    '    "size": $corpus_size,\n'
    '    "snapshot_sha256": $snapshot_sha256_json\n'
    '  },\n'
    '  "display_name": $display_name_json,\n'
    '  "dossier": {\n'
    '    "files": $dossier_files_json,\n'
    '    "path": "dossier/expediente.md"\n'
    '  },\n'
    '  "dossier_version": $dossier_version_json,\n'
    '  "forum_id": $forum_id_json,\n'
    '  "instance_root": $instance_root_json,\n'
    '  "kind": "forum-roleplay-instance",\n'
    '  "packages": [],\n'
    '  "schema_version": 1,\n'
    '  "source_workspace": {\n'
    '    "workspace_json_sha256": $workspace_json_sha256_json\n'
    '  }\n'
    '}\n'
)

EXPECTED_POLICY = (
    '## Invariantes obligatorias\n'
    '\n'
    '- No ejecutes nunca comandos de decisión humana, incluidos `assimilation candidate approve`, `assimilation candidate reject`, `assimilation close` y sus equivalentes futuros. Muestra al usuario el comando exacto y pídele que lo ejecute personalmente en una terminal interactiva.\n'
    '- Usa únicamente versiones vigentes del corpus con decisión APPROVED y pertenecientes al snapshot cerrado válido. PENDING_HUMAN_REVIEW, REJECTED, versiones sustituidas y material no clasificado no son utilizables.\n'
    '- BORRADOR, APROBADO, PUBLICADO y CANON son estados distintos. Ninguno implica automáticamente otro; una aprobación tampoco implica aprendizaje ni utilizabilidad.\n'
    '- No publiques, envíes ni conviertas propuestas, incertidumbres, borradores o resultados pendientes en hechos. No existe comando de publicación en este alcance.\n'
    '- No edites directamente estados JSON gestionados ni recalcules sus hashes. Usa los comandos del core y conserva procedencia, citas y versiones exactas.\n'
)

EXPECTED_AGENTS = (
    '# Instrucciones de la instancia del foro\n'
    '\n'
    'Este `AGENTS.md` rige esta carpeta y todas sus subcarpetas para Codex. Un `AGENTS.md` más específico puede concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados.\n'
    '\n'
    '<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '$common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '\n'
    '## Consultas disponibles\n'
    '\n'
    'Ejecuta el core desde su checkout con estos patrones PowerShell ya renderizados:\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_DEL_CANDIDATO' --version 1\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    '`corpus list` devuelve solo versiones vigentes aprobadas. `corpus show` exige el ID y la versión mostrados por la lista y presenta texto, decisión y citas exactas. Una entrada `UNCERTAINTY` sigue requiriendo confirmación aunque esté aprobada. Estos comandos son de solo lectura.\n'
    '\n'
    '## Trabajo posterior\n'
    '\n'
    'En 4d el concepto de personaje lo aportará la persona y las mejoras del agente serán propuestas separadas; en 4e la ficha seguirá siendo un borrador distinto de la respuesta del staff. Hasta que el core implemente esas operaciones, no inventes comandos ni crees o edites sus JSON. Si una operación futura requiere decisión humana, muestra a la persona el comando exacto y espera a que ella lo ejecute en su propia terminal.\n'
)

EXPECTED_CLAUDE = (
    '# Instrucciones de la instancia del foro\n'
    '\n'
    'Este `CLAUDE.md` da a Claude las instrucciones de proyecto para esta carpeta y todas sus subcarpetas. Instrucciones más específicas pueden concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados.\n'
    '\n'
    '<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '$common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '\n'
    '## Consultas disponibles\n'
    '\n'
    'Ejecuta el core desde su checkout con estos patrones PowerShell ya renderizados:\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_DEL_CANDIDATO' --version 1\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    '`corpus list` devuelve solo versiones vigentes aprobadas. `corpus show` exige el ID y la versión mostrados por la lista y presenta texto, decisión y citas exactas. Una entrada `UNCERTAINTY` sigue requiriendo confirmación aunque esté aprobada. Estos comandos son de solo lectura.\n'
    '\n'
    '## Trabajo posterior\n'
    '\n'
    'En 4d el concepto de personaje lo aportará la persona y las mejoras del agente serán propuestas separadas; en 4e la ficha seguirá siendo un borrador distinto de la respuesta del staff. Hasta que el core implemente esas operaciones, no inventes comandos ni crees o edites sus JSON. Si una operación futura requiere decisión humana, muestra a la persona el comando exacto y espera a que ella lo ejecute en su propia terminal.\n'
)
