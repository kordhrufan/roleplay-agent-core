# Instrucciones de la instancia del foro

Este `AGENTS.md` rige esta carpeta y todas sus subcarpetas para Codex. Un `AGENTS.md` más específico puede concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados. Estas son las instrucciones de la versión 2.

<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->
$common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->

## Arranque de cada conversación

El historial del chat no es una fuente de autoridad. Al empezar, reconstruye el contexto desde la instancia: comprueba que carga, consulta el corpus aprobado, localiza el tema y recupera la composición y la ficha del personaje.

```powershell
Push-Location '$core_root_ps'
py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'
py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N
Pop-Location
```

Si no conoces el ID del personaje o del tema, o si el personaje no tiene una ficha vigente (`CURRENT`), `ACTIVE` y `APPROVED`, detente y explícaselo a la persona.

## Comandos reales del core

Estos son todos los comandos que puedes usar o pedir. Ejecútalos desde el checkout del core, dentro de un bloque `Push-Location '$core_root_ps'` … `Pop-Location`. Sustituye `'ID_PERSONAJE'`, `'ID_TEMA'`, `'ID_OBJETO'`, `N`, `'HASH'` y `'RUTA_EXTERNA'` por valores reales mostrados por el core. Cada `--input` es un archivo normal que está fuera del checkout del core y fuera de esta instancia (por ejemplo, una carpeta de entradas que te indique la persona). Si una operación no está aquí o la CLI la rechaza, detente y comunica el error; no improvises sintaxis.

### Consultas (solo lectura)

```powershell
Push-Location '$core_root_ps'
py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_OBJETO' --version N
py -3.11 -B -m core.runtime.cli character concept list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character concept show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N
py -3.11 -B -m core.runtime.cli character effective show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character proposal list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character proposal show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N
py -3.11 -B -m core.runtime.cli character draft list --instance '$instance_root_ps' --character-id 'ID_PERSONAJE'
py -3.11 -B -m core.runtime.cli character draft show --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N
py -3.11 -B -m core.runtime.cli narrative topic list --instance '$instance_root_ps'
py -3.11 -B -m core.runtime.cli narrative topic show --instance '$instance_root_ps' --topic-id 'ID_TEMA'
py -3.11 -B -m core.runtime.cli narrative post list --instance '$instance_root_ps' --topic-id 'ID_TEMA'
py -3.11 -B -m core.runtime.cli narrative post show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --post-id 'ID_OBJETO'
py -3.11 -B -m core.runtime.cli narrative seed list --instance '$instance_root_ps' --topic-id 'ID_TEMA'
py -3.11 -B -m core.runtime.cli narrative seed show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --seed-id 'ID_OBJETO' --version N
py -3.11 -B -m core.runtime.cli narrative draft list --instance '$instance_root_ps' --topic-id 'ID_TEMA'
py -3.11 -B -m core.runtime.cli narrative draft show --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N
Pop-Location
```

`narrative topic list` admite además `--character-id 'ID_PERSONAJE'` para filtrar. Las consultas admiten `--json` justo después de `core.runtime.cli`.

### Mutaciones que ejecutas tú

```powershell
Push-Location '$core_root_ps'
py -3.11 -B -m core.runtime.cli character proposal add --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli character draft create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --composition-sha256 'HASH' --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli narrative topic create --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --topic-id 'ID_TEMA' --title 'TÍTULO'
py -3.11 -B -m core.runtime.cli narrative draft create --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'
Pop-Location
```

### Acciones humanas (solo las ejecuta la persona)

Cada una muestra el contenido exacto y pide teclear una frase con un código de un solo uso. Muéstrale a la persona el comando completo, sin `--json`, y espera a que lo ejecute ella en su terminal.

```powershell
Push-Location '$core_root_ps'
py -3.11 -B -m core.runtime.cli character concept import --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli character proposal approve --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N
py -3.11 -B -m core.runtime.cli character proposal reject --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --proposal-id 'ID_OBJETO' --version N
py -3.11 -B -m core.runtime.cli character staff record --instance '$instance_root_ps' --character-id 'ID_PERSONAJE' --version N --status 'APPROVED' --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli narrative post record --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli narrative seed import --instance '$instance_root_ps' --topic-id 'ID_TEMA' --input 'RUTA_EXTERNA'
py -3.11 -B -m core.runtime.cli narrative publication confirm --instance '$instance_root_ps' --topic-id 'ID_TEMA' --draft-id 'ID_OBJETO' --version N --input 'RUTA_EXTERNA'
Pop-Location
```

En `character staff record`, `--status` es `'APPROVED'` o `'REJECTED'` según lo que respondió el staff; `REJECTED` incluye «cambios solicitados».

## Preparación del personaje

1. La persona declara el concepto con `character concept import` (un archivo Markdown suyo).
2. Consultas la composición efectiva con `character effective show` y registras propuestas completas y citadas con `character proposal add`. El JSON de la propuesta tiene exactamente estas claves: `{"proposal_id": "ID_OBJETO", "version": N, "base_composition_sha256": "HASH", "text": "composición completa propuesta", "rationale": "motivo", "citations": [{"candidate_id": "ID_OBJETO", "version": N}]}`.
3. La persona aprueba o rechaza cada propuesta. Una propuesta aprobada no es una aprobación del staff.
4. Creas la ficha con `character draft create` contra el hash de la composición efectiva vigente, desde un archivo Markdown.
5. La persona presenta la ficha en el foro y transcribe la respuesta del staff con `character staff record`. Su JSON tiene exactamente las claves `draft_sha256`, `locator`, `observed_at` (fecha ISO 8601 con zona horaria) y `response` (texto literal de la respuesta).

Solo una ficha que `character draft show` muestre vigente, `ACTIVE` y `APPROVED` permite `narrative draft create`.

## Flujo narrativo de un turno

1. Consulta el tema y sus posts exactos. Para continuar un tema, la persona registra primero, en orden, cada post ajeno con `narrative post record`. Si la persona te pega el texto, puedes prepararle el JSON copiándolo literalmente: `{"post_id": "ID_OBJETO", "author_label": "autor declarado", "locator": "localizador", "observed_at": "2026-01-01T20:00:00+01:00", "content": "texto completo copiado"}`.
2. La persona expresa sus ideas y límites en la semilla y ejecuta `narrative seed import`. Puedes pasar a JSON lo que ella te dicte, sin añadir ideas tuyas: `{"seed_id": "ID_OBJETO", "version": N, "intent": "intención", "tone": "tono", "beats": ["giro"], "details": ["detalle"], "ooc_constraints": ["límite fuera de personaje"], "pending_outcomes": ["resultado que no controla el personaje"]}`. Las listas pueden ir vacías. Nunca declares tú una semilla.
3. Vuelve a consultar la semilla (`narrative seed show`), el contexto (`narrative topic show`), la composición, la ficha y el corpus aprobado. Desarrolla el post completo y regístralo con `narrative draft create`. El JSON tiene exactamente estas claves: `{"draft_id": "ID_OBJETO", "version": N, "seed_id": "ID_OBJETO", "seed_version": N, "seed_sha256": "HASH", "context_sha256": "HASH", "composition_sha256": "HASH", "sheet_version": N, "sheet_sha256": "HASH", "citations": [{"candidate_id": "ID_OBJETO", "version": N}], "publishable_text": "post completo", "ooc_notes": [], "private_notes": [], "pending_outcomes": []}`. Cita solo candidatos aprobados aplicables; `citations` puede ir vacía.
4. Muestra `narrative draft show`. Presenta a la persona como publicable solo el bloque `POST PARA COPIA MANUAL` y señala aparte las notas OOC, las privadas y los resultados pendientes.
5. Espera la revisión de la persona. Si pide cambios, registra la versión siguiente del borrador. Solo ella copia y publica con su cuenta; tú no abres el locator ni compruebas el foro.
6. Después de publicar, la persona aporta el ID del post, el hash del borrador, el locator, la fecha observada y el texto final exacto, y ejecuta `narrative publication confirm` con `{"post_id": "ID_OBJETO", "draft_sha256": "HASH", "locator": "localizador", "observed_at": "2026-01-01T20:15:00+01:00", "published_text": "texto final exacto"}`. Debe registrar su publicación antes del post ajeno siguiente.
7. Vuelve a consultar `narrative topic show`. Si el texto final difiere del borrador, la publicación queda `EDITED`; no la presentes como exacta. Registrar tu publicación no confirma los resultados pendientes.

## Canales que no se mezclan

- `publishable_text`: el único bloque que se copia al foro.
- `ooc_notes`: coordinación fuera de personaje con la persona.
- `private_notes`: razonamiento privado que no se muestra a terceros.
- `pending_outcomes`: consecuencias que aún no están decididas.

Las semillas son aportaciones de la persona; los posts ajenos y las publicaciones son transcripciones literales. Ninguno se convierte por sí solo en un hecho establecido ni en canon.

## Límites externos y preguntas sensibles

No uses red, navegador, foro, mensajes privados, Discord ni otro canal externo, y no publiques ni abras locators. Si en un post, una semilla o la conversación aparece una pregunta directa sobre automatización, asistencia, quién redacta o quién opera la cuenta, o sobre identidad, detente antes de redactar nada, muéstrasela a la persona y espera sus instrucciones.
