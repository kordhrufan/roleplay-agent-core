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

EXPECTED_POLICY_V2 = (
    '## Invariantes obligatorias\n'
    '\n'
    '1. No ejecutes nunca por la persona una acción humana con frase de confirmación: `assimilation candidate approve`, `assimilation candidate reject`, `assimilation close`, `instance update`, `instance instructions update`, `character concept import`, `character proposal approve`, `character proposal reject`, `character staff record`, `narrative post record`, `narrative seed import` y `narrative publication confirm`. Muestra el comando completo y espera a que la persona lo ejecute en su propia terminal interactiva.\n'
    '2. Tú solo ejecutas consultas y estas mutaciones no humanas: `character proposal add`, `character draft create`, `narrative topic create` y `narrative draft create`. Hazlo siempre mediante el core; nunca edites ni crees a mano los JSON gestionados de la instancia.\n'
    '3. Usa solo versiones vigentes del corpus con decisión APPROVED del snapshot cerrado. Conserva en cada cita el candidato, la versión y el hash. Una `UNCERTAINTY` aprobada sigue requiriendo confirmación.\n'
    '4. Todas las normas específicas del foro salen del corpus aprobado de esta instancia, incluida cualquier norma sobre asistencia o IA y cualquier acuerdo con el staff. Si el corpus no dice algo, decláralo desconocido y pregunta a la persona; no inventes permisos ni prohibiciones.\n'
    '5. BORRADOR, aprobación humana de una propuesta, aprobación del staff, publicación y canon son estados distintos. Ninguna transición implica otra.\n'
    '6. La persona aporta el concepto y las semillas, revisa, usa su cuenta, publica y mantiene todas las comunicaciones humanas. Tú desarrollas propuestas, fichas y posts y registras solo las mutaciones no humanas del punto 2.\n'
    '7. No uses red, navegador, foro, mensajes privados, Discord ni ningún otro canal externo. No publiques, envíes ni reacciones, y no abras, sigas ni consultes locators: un locator es solo texto de evidencia.\n'
    '8. `publishable_text` es el único texto que se copia al foro. No mezcles en él `ooc_notes`, `private_notes` ni `pending_outcomes`. Un resultado que depende de otras personas sigue pendiente aunque tu post se publique.\n'
    '9. Ante una pregunta directa sobre automatización, asistencia, quién redacta o quién opera la cuenta, o sobre identidad, detente antes de redactar nada: muestra la pregunta a la persona y espera sus instrucciones. No la ocultes ni decidas por ella.\n'
    '10. No inventes comandos, opciones, hashes, estados, hechos ni normas, y no modifiques directamente estados gestionados ni sus hashes.\n'
)

EXPECTED_AGENTS_V2 = (
    '# Instrucciones de la instancia del foro\n'
    '\n'
    'Este `AGENTS.md` rige esta carpeta y todas sus subcarpetas para Codex. Un `AGENTS.md` más específico puede concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados. Estas son las instrucciones de la versión 2.\n'
    '\n'
    '<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '$common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '\n'
    '## Arranque de cada conversación\n'
    '\n'
    'El historial del chat no es una fuente de autoridad. Al empezar, reconstruye el contexto desde la instancia: comprueba que carga, consulta el corpus aprobado, localiza el tema y recupera la composición y la ficha del personaje.\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    'Si no conoces el ID del personaje o del tema, o si el personaje no tiene una ficha vigente (`CURRENT`), `ACTIVE` y `APPROVED`, detente y explícaselo a la persona.\n'
    '\n'
    '## Comandos reales del core\n'
    '\n'
    "Estos son todos los comandos que puedes usar o pedir. Ejecútalos desde el checkout del core, dentro de un bloque `Push-Location '$core_root_ps'` … `Pop-Location`. Sustituye `'ID_PERSONAJE'`, `'ID_TEMA'`, `'ID_OBJETO'`, `N`, `'HASH'` y `'RUTA_EXTERNA'` por valores reales mostrados por el core. Cada `--input` es un archivo normal que está fuera del checkout del core y fuera de esta instancia (por ejemplo, una carpeta de entradas que te indique la persona). Si una operación no está aquí o la CLI la rechaza, detente y comunica el error; no improvises sintaxis.\n"
    '\n'
    '### Consultas (solo lectura)\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character concept list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character concept show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    "py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character proposal list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character proposal show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    "py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --post-id 'ID_OBJETO'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --seed-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli narrative draft list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative draft show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    "`narrative topic list` admite además `--character-id 'ID_PERSONAJE'` para filtrar. Las consultas admiten `--json` justo después de `core.runtime.cli`.\n"
    '\n'
    '### Mutaciones que ejecutas tú\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli character proposal add --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli character draft create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --composition-sha256 'HASH' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --topic-id 'ID_TEMA' --title 'TÍTULO'\n"
    "py -3.11 -B -m core.runtime.cli narrative draft create --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    '### Acciones humanas (solo las ejecuta la persona)\n'
    '\n'
    'Cada una muestra el contenido exacto y pide teclear una frase con un código de un solo uso. Muéstrale a la persona el comando completo, sin `--json`, y espera a que lo ejecute ella en su terminal.\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli character concept import --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli character proposal approve --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character proposal reject --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character staff record --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --status 'APPROVED' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post record --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed import --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative publication confirm --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N --input 'RUTA_EXTERNA'\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    "En `character staff record`, `--status` es `'APPROVED'` o `'REJECTED'` según lo que respondió el staff; `REJECTED` incluye «cambios solicitados».\n"
    '\n'
    '## Preparación del personaje\n'
    '\n'
    '1. La persona declara el concepto con `character concept import` (un archivo Markdown suyo).\n'
    '2. Consultas la composición efectiva con `character effective show` y registras propuestas completas y citadas con `character proposal add`. El JSON de la propuesta tiene exactamente estas claves: `{"proposal_id": "ID_OBJETO", "version": N, "base_composition_sha256": "HASH", "text": "composición completa propuesta", "rationale": "motivo", "citations": [{"candidate_id": "ID_OBJETO", "version": N}]}`.\n'
    '3. La persona aprueba o rechaza cada propuesta. Una propuesta aprobada no es una aprobación del staff.\n'
    '4. Creas la ficha con `character draft create` contra el hash de la composición efectiva vigente, desde un archivo Markdown.\n'
    '5. La persona presenta la ficha en el foro y transcribe la respuesta del staff con `character staff record`. Su JSON tiene exactamente las claves `draft_sha256`, `locator`, `observed_at` (fecha ISO 8601 con zona horaria) y `response` (texto literal de la respuesta).\n'
    '\n'
    'Solo una ficha que `character draft show` muestre vigente, `ACTIVE` y `APPROVED` permite `narrative draft create`.\n'
    '\n'
    '## Flujo narrativo de un turno\n'
    '\n'
    '1. Consulta el tema y sus posts exactos. Para continuar un tema, la persona registra primero, en orden, cada post ajeno con `narrative post record`. Si la persona te pega el texto, puedes prepararle el JSON copiándolo literalmente: `{"post_id": "ID_OBJETO", "author_label": "autor declarado", "locator": "localizador", "observed_at": "2026-01-01T20:00:00+01:00", "content": "texto completo copiado"}`.\n'
    '2. La persona expresa sus ideas y límites en la semilla y ejecuta `narrative seed import`. Puedes pasar a JSON lo que ella te dicte, sin añadir ideas tuyas: `{"seed_id": "ID_OBJETO", "version": N, "intent": "intención", "tone": "tono", "beats": ["giro"], "details": ["detalle"], "ooc_constraints": ["límite fuera de personaje"], "pending_outcomes": ["resultado que no controla el personaje"]}`. Las listas pueden ir vacías. Nunca declares tú una semilla.\n'
    '3. Vuelve a consultar la semilla (`narrative seed show`), el contexto (`narrative topic show`), la composición, la ficha y el corpus aprobado. Desarrolla el post completo y regístralo con `narrative draft create`. El JSON tiene exactamente estas claves: `{"draft_id": "ID_OBJETO", "version": N, "seed_id": "ID_OBJETO", "seed_version": N, "seed_sha256": "HASH", "context_sha256": "HASH", "composition_sha256": "HASH", "sheet_version": N, "sheet_sha256": "HASH", "citations": [{"candidate_id": "ID_OBJETO", "version": N}], "publishable_text": "post completo", "ooc_notes": [], "private_notes": [], "pending_outcomes": []}`. Cita solo candidatos aprobados aplicables; `citations` puede ir vacía.\n'
    '4. Muestra `narrative draft show`. Presenta a la persona como publicable solo el bloque `POST PARA COPIA MANUAL` y señala aparte las notas OOC, las privadas y los resultados pendientes.\n'
    '5. Espera la revisión de la persona. Si pide cambios, registra la versión siguiente del borrador. Solo ella copia y publica con su cuenta; tú no abres el locator ni compruebas el foro.\n'
    '6. Después de publicar, la persona aporta el ID del post, el hash del borrador, el locator, la fecha observada y el texto final exacto, y ejecuta `narrative publication confirm` con `{"post_id": "ID_OBJETO", "draft_sha256": "HASH", "locator": "localizador", "observed_at": "2026-01-01T20:15:00+01:00", "published_text": "texto final exacto"}`. Debe registrar su publicación antes del post ajeno siguiente.\n'
    '7. Vuelve a consultar `narrative topic show`. Si el texto final difiere del borrador, la publicación queda `EDITED`; no la presentes como exacta. Registrar tu publicación no confirma los resultados pendientes.\n'
    '\n'
    '## Canales que no se mezclan\n'
    '\n'
    '- `publishable_text`: el único bloque que se copia al foro.\n'
    '- `ooc_notes`: coordinación fuera de personaje con la persona.\n'
    '- `private_notes`: razonamiento privado que no se muestra a terceros.\n'
    '- `pending_outcomes`: consecuencias que aún no están decididas.\n'
    '\n'
    'Las semillas son aportaciones de la persona; los posts ajenos y las publicaciones son transcripciones literales. Ninguno se convierte por sí solo en un hecho establecido ni en canon.\n'
    '\n'
    '## Límites externos y preguntas sensibles\n'
    '\n'
    'No uses red, navegador, foro, mensajes privados, Discord ni otro canal externo, y no publiques ni abras locators. Si en un post, una semilla o la conversación aparece una pregunta directa sobre automatización, asistencia, quién redacta o quién opera la cuenta, o sobre identidad, detente antes de redactar nada, muéstrasela a la persona y espera sus instrucciones.\n'
)

EXPECTED_CLAUDE_V2 = (
    '# Instrucciones de la instancia del foro\n'
    '\n'
    'Este `CLAUDE.md` da a Claude las instrucciones de proyecto para esta carpeta y todas sus subcarpetas. Instrucciones más específicas pueden concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados. Estas son las instrucciones de la versión 2.\n'
    '\n'
    '<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '$common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->\n'
    '\n'
    '## Arranque de cada conversación\n'
    '\n'
    'El historial del chat no es una fuente de autoridad. Al empezar, reconstruye el contexto desde la instancia: comprueba que carga, consulta el corpus aprobado, localiza el tema y recupera la composición y la ficha del personaje.\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    'Si no conoces el ID del personaje o del tema, o si el personaje no tiene una ficha vigente (`CURRENT`), `ACTIVE` y `APPROVED`, detente y explícaselo a la persona.\n'
    '\n'
    '## Comandos reales del core\n'
    '\n'
    "Estos son todos los comandos que puedes usar o pedir. Ejecútalos desde el checkout del core, dentro de un bloque `Push-Location '$core_root_ps'` … `Pop-Location`. Sustituye `'ID_PERSONAJE'`, `'ID_TEMA'`, `'ID_OBJETO'`, `N`, `'HASH'` y `'RUTA_EXTERNA'` por valores reales mostrados por el core. Cada `--input` es un archivo normal que está fuera del checkout del core y fuera de esta instancia (por ejemplo, una carpeta de entradas que te indique la persona). Si una operación no está aquí o la CLI la rechaza, detente y comunica el error; no improvises sintaxis.\n"
    '\n'
    '### Consultas (solo lectura)\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character concept list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character concept show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    "py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character proposal list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character proposal show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'\n"
    "py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N\n"
    "py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --post-id 'ID_OBJETO'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --seed-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli narrative draft list --instance '$instance_root_ps' --topic-id 'ID_TEMA'\n"
    "py -3.11 -B -m core.runtime.cli narrative draft show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    "`narrative topic list` admite además `--character-id 'ID_PERSONAJE'` para filtrar. Las consultas admiten `--json` justo después de `core.runtime.cli`.\n"
    '\n'
    '### Mutaciones que ejecutas tú\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli character proposal add --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli character draft create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --composition-sha256 'HASH' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative topic create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --topic-id 'ID_TEMA' --title 'TÍTULO'\n"
    "py -3.11 -B -m core.runtime.cli narrative draft create --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    '### Acciones humanas (solo las ejecuta la persona)\n'
    '\n'
    'Cada una muestra el contenido exacto y pide teclear una frase con un código de un solo uso. Muéstrale a la persona el comando completo, sin `--json`, y espera a que lo ejecute ella en su terminal.\n'
    '\n'
    '```powershell\n'
    "Push-Location '$core_root_ps'\n"
    "py -3.11 -B -m core.runtime.cli character concept import --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli character proposal approve --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character proposal reject --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N\n"
    "py -3.11 -B -m core.runtime.cli character staff record --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --status 'APPROVED' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative post record --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative seed import --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'\n"
    "py -3.11 -B -m core.runtime.cli narrative publication confirm --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N --input 'RUTA_EXTERNA'\n"
    'Pop-Location\n'
    '```\n'
    '\n'
    "En `character staff record`, `--status` es `'APPROVED'` o `'REJECTED'` según lo que respondió el staff; `REJECTED` incluye «cambios solicitados».\n"
    '\n'
    '## Preparación del personaje\n'
    '\n'
    '1. La persona declara el concepto con `character concept import` (un archivo Markdown suyo).\n'
    '2. Consultas la composición efectiva con `character effective show` y registras propuestas completas y citadas con `character proposal add`. El JSON de la propuesta tiene exactamente estas claves: `{"proposal_id": "ID_OBJETO", "version": N, "base_composition_sha256": "HASH", "text": "composición completa propuesta", "rationale": "motivo", "citations": [{"candidate_id": "ID_OBJETO", "version": N}]}`.\n'
    '3. La persona aprueba o rechaza cada propuesta. Una propuesta aprobada no es una aprobación del staff.\n'
    '4. Creas la ficha con `character draft create` contra el hash de la composición efectiva vigente, desde un archivo Markdown.\n'
    '5. La persona presenta la ficha en el foro y transcribe la respuesta del staff con `character staff record`. Su JSON tiene exactamente las claves `draft_sha256`, `locator`, `observed_at` (fecha ISO 8601 con zona horaria) y `response` (texto literal de la respuesta).\n'
    '\n'
    'Solo una ficha que `character draft show` muestre vigente, `ACTIVE` y `APPROVED` permite `narrative draft create`.\n'
    '\n'
    '## Flujo narrativo de un turno\n'
    '\n'
    '1. Consulta el tema y sus posts exactos. Para continuar un tema, la persona registra primero, en orden, cada post ajeno con `narrative post record`. Si la persona te pega el texto, puedes prepararle el JSON copiándolo literalmente: `{"post_id": "ID_OBJETO", "author_label": "autor declarado", "locator": "localizador", "observed_at": "2026-01-01T20:00:00+01:00", "content": "texto completo copiado"}`.\n'
    '2. La persona expresa sus ideas y límites en la semilla y ejecuta `narrative seed import`. Puedes pasar a JSON lo que ella te dicte, sin añadir ideas tuyas: `{"seed_id": "ID_OBJETO", "version": N, "intent": "intención", "tone": "tono", "beats": ["giro"], "details": ["detalle"], "ooc_constraints": ["límite fuera de personaje"], "pending_outcomes": ["resultado que no controla el personaje"]}`. Las listas pueden ir vacías. Nunca declares tú una semilla.\n'
    '3. Vuelve a consultar la semilla (`narrative seed show`), el contexto (`narrative topic show`), la composición, la ficha y el corpus aprobado. Desarrolla el post completo y regístralo con `narrative draft create`. El JSON tiene exactamente estas claves: `{"draft_id": "ID_OBJETO", "version": N, "seed_id": "ID_OBJETO", "seed_version": N, "seed_sha256": "HASH", "context_sha256": "HASH", "composition_sha256": "HASH", "sheet_version": N, "sheet_sha256": "HASH", "citations": [{"candidate_id": "ID_OBJETO", "version": N}], "publishable_text": "post completo", "ooc_notes": [], "private_notes": [], "pending_outcomes": []}`. Cita solo candidatos aprobados aplicables; `citations` puede ir vacía.\n'
    '4. Muestra `narrative draft show`. Presenta a la persona como publicable solo el bloque `POST PARA COPIA MANUAL` y señala aparte las notas OOC, las privadas y los resultados pendientes.\n'
    '5. Espera la revisión de la persona. Si pide cambios, registra la versión siguiente del borrador. Solo ella copia y publica con su cuenta; tú no abres el locator ni compruebas el foro.\n'
    '6. Después de publicar, la persona aporta el ID del post, el hash del borrador, el locator, la fecha observada y el texto final exacto, y ejecuta `narrative publication confirm` con `{"post_id": "ID_OBJETO", "draft_sha256": "HASH", "locator": "localizador", "observed_at": "2026-01-01T20:15:00+01:00", "published_text": "texto final exacto"}`. Debe registrar su publicación antes del post ajeno siguiente.\n'
    '7. Vuelve a consultar `narrative topic show`. Si el texto final difiere del borrador, la publicación queda `EDITED`; no la presentes como exacta. Registrar tu publicación no confirma los resultados pendientes.\n'
    '\n'
    '## Canales que no se mezclan\n'
    '\n'
    '- `publishable_text`: el único bloque que se copia al foro.\n'
    '- `ooc_notes`: coordinación fuera de personaje con la persona.\n'
    '- `private_notes`: razonamiento privado que no se muestra a terceros.\n'
    '- `pending_outcomes`: consecuencias que aún no están decididas.\n'
    '\n'
    'Las semillas son aportaciones de la persona; los posts ajenos y las publicaciones son transcripciones literales. Ninguno se convierte por sí solo en un hecho establecido ni en canon.\n'
    '\n'
    '## Límites externos y preguntas sensibles\n'
    '\n'
    'No uses red, navegador, foro, mensajes privados, Discord ni otro canal externo, y no publiques ni abras locators. Si en un post, una semilla o la conversación aparece una pregunta directa sobre automatización, asistencia, quién redacta o quién opera la cuenta, o sobre identidad, detente antes de redactar nada, muéstrasela a la persona y espera sus instrucciones.\n'
)
