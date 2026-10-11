# Análisis de tarea

## Tarea

Generalizar Nozomu Agent como `roleplay-agent-core`: un núcleo reutilizable para agentes de
foro de rol, configurable por personaje, mundo, sistema, plataforma e instancia. Este documento
define la extracción y un plan para Claude; no implementa código ni altera el legado.

Versión base de este rediseño: commit `e4da791` a 2026-10-11, rama
`feature/plan-expediente-foro`, creada desde el incremento 2 aprobado y sin cambios al iniciar el
análisis. `main` permanece en `96eca81`; los incrementos 1–2 siguen en ramas apiladas sin fusionar.
`reference/migration-source/` es la copia inmutable inspeccionada. La auditoría anterior se trata
como hipótesis histórica porque declara que su fuente estaba vacía; no se usa como prueba de la
implementación actual.

### Decisiones del usuario (11-10-2026)

- Se adopta literalmente el árbol solicitado: `core/{character,world,rules,memory,runtime,review}/`,
  `adapters/jcink/`, `packages/{characters/nozomu,worlds/naruto-rol,systems/naruto-rol}/`,
  `integrations/{discord,scheduler}/` y `tests/`. No habrá `src/` ni otros módulos hermanos bajo
  `core/`; narrativa y seguimiento serán componentes internos de `core/runtime/`.
- La memoria dinámica y todo estado operativo viven fuera del repo. Canon significa hechos
  consolidados con fuente y alcance, independientemente de su publicación.
- Se define un puerto de publicación, pero ningún adaptador lo implementa en este alcance. No habrá
  publicación real ni automática.
- `reference/migration-source/` conserva nombre, ruta y contenido.
- Los paquetes no incorporan texto de reglas/lore ni datos estructurados derivados de ellos
  (fórmulas, tablas, rangos u otros valores). Cada foro aporta sus propias normas y el core no
  presupone Naruto ni ninguna otra temática.
- Las normas y la ambientación aportadas por el usuario se asimilan como fuentes literales
  versionadas, con procedencia y vigencia, fuera del repo. Cada regla cita su fuente; texto literal,
  interpretación, propuesta e incertidumbre permanecen separados. Nada es utilizable sin revisión
  humana; los huecos no se completan y una ambigüedad se marca `REQUIERE CONFIRMACIÓN`.
- Un cambio reglamentario crea una versión nueva con su vigencia. La recuperación se dirige a las
  secciones pertinentes, no carga el reglamento completo. Se admite explícitamente un foro sin
  mecánicas. La extracción mediante modelo es opcional, atraviesa `ModelProvider` y no es necesaria
  para ejecutar el core ni sus tests.
- Primero se implementa el adaptador manual; Jcink viene después y el scheduler Windows es opcional.
- Solo se versionan el esquema y un ejemplo de configuración sin autorizaciones reales; la
  configuración efectiva es externa.
- El segundo caso de generalidad sigue sin decidir y se probará únicamente en el incremento final,
  cuando las bases estén afinadas.
- El producto se organiza por foro: **un agente por foro y uno o varios personajes dentro**. Su
  forma es una carpeta de trabajo externa al repo, abierta por el usuario con Codex o Claude, con
  instrucciones generadas, configuración/datos de instancia y solo los especialistas que exijan
  las normas aprobadas del foro. El core, no solo la prosa, hace cumplir procedencia, estados
  ortogonales, memoria con fuente y ausencia de publicación.
- El flujo de producto es: expediente del usuario → asimilación citada con
  `REQUIERE CONFIRMACIÓN` y aprobación humana → instancia externa → creación de personaje guiada
  por normas aprobadas → agente listo para rolear. La instancia nunca convierte una propuesta,
  un borrador ni una publicación en canon por implicación.
- El expediente es un único documento humano `expediente.md`, no un índice JSON. Usa encabezados
  fijos en español para normas, combate, fichas/técnicas, ambientación, plataforma/formato,
  revisión de staff y material suelto; puede referenciar varios archivos. Su parser lo convierte
  al mismo modelo inmutable, y cada fuente conserva versión, literal y procedencia.
- El concepto de cada personaje siempre lo aporta el usuario. El agente lo contrasta con normas
  aprobadas y puede ofrecer mejoras solo como `PROPUESTA`; nada propuesto se incorpora sin
  aceptación expresa. La ficha nace en `BORRADOR` pendiente del staff; aprobación, aprendizaje,
  utilizabilidad, publicación y canon siguen siendo ejes separados.
- Antes de completar todas las capas se hará una rebanada vertical con expediente y personaje
  temáticamente neutros, adaptador manual, almacenamiento local externo y sin modelo, red ni
  instalación. Nozomu/Naruto Rol será el primer caso real posterior y recorrerá el mismo camino,
  sin código específico.
- Cada instancia genera **ambos** `AGENTS.md` y `CLAUDE.md` desde una política común; una prueba
  impide que diverjan sus invariantes compartidas.
- No existe ubicación predeterminada de instancias: `--output` es siempre obligatorio. El core
  rechaza destinos dentro del checkout o carpetas no vacías.
- La ficha mecánica de Nozomu vive versionada dentro de la instancia externa del foro. El paquete
  `characters/nozomu` solo puede conservar identidad e interpretación independientes del sistema;
  no contiene atributos, inventario, técnicas, estados aprendido/utilizable ni derivados.
- La línea `Metadatos:` prioriza la escritura manual: solo `id`, `versión`, `autoridad` y `alcance`
  son obligatorias; las demás claves tienen valores por omisión, pueden aparecer en cualquier
  orden y no se repiten. El origen se infiere de `archivo`: string significa fichero; omisión o
  `null`, literal cercado en la línea siguiente. Los ejemplos copiables viven fuera del documento
  válido, en `core/runtime/templates/LEEME-expediente.md`.

## Contexto del código

- `reference/migration-source/` — legado de solo lectura; se leyeron sus 41 archivos `.md`.
- `reference/migration-source/AUDIT-GENERALIZATION.md` — auditoría parcial anterior, no evidencia
  del legado que hoy sí está presente.
- `reference/migration-source/shared/profile.json` y `memory/events.jsonl` — formatos reales de
  perfil mecánico, procedencia, revisiones, estados y eventos.
- `reference/migration-source/forum_watch/{models,adapter,result,drafts,store,workflow}.py` y
  `forum_watch/schemas/narrative-result.json` — contraste de los contratos documentados.
- `reference/migration-source/.codex/agents/*.toml` — confirma especialistas de solo lectura y
  coordinador único; son configuración específica, no una arquitectura universal obligatoria.
- `reference/migration-source/tests/` — confirma cobertura por contratos y acoplamientos. No se
  ejecutó ninguna prueba ni flujo del legado; no se abrió foro, Discord, navegador o modelo.
- `core/memory/provenance.py` — incremento 1 aprobado: `SourceRef` inmutable con hash, pasaje,
  observación y fecha IC independiente; no incluye todavía autoridad, versión o vigencia de corpus.
- `core/review/models.py` — incremento 1 aprobado: borrador, revisión, vigencia y publicación como
  ejes ortogonales; sus transiciones exigen versión/evidencia y no crean canon.
- `tests/test_{provenance,review_models}.py` y `tests/test_package_{manifest,loader}.py` — 89
  pruebas aprobadas en total que los incrementos siguientes deben conservar.

### Hallazgos de contraste

- El núcleo local es Python con biblioteca estándar, SQLite y `unittest`; Playwright es la única
  dependencia opcional de lectura (`forum_watch/requirements-reader.txt`).
- El seguimiento genérico ya existe conceptualmente —captura completa, revisiones, cambios,
  borradores y colas—, pero el código real fija `narutorol.jcink.net`, tema `275`, cuenta `59` y
  semántica Nozomu en `models.py`, `adapter.py`, `browser.py`, `narrative.py` y `context.py`.
- El borrador operativo tiene dos ejes persistidos, `review_status=PENDING_HUMAN_REVIEW` y
  `lifecycle=ACTIVE|STALE|RETIRED`; no tiene transición implementada a aprobado, publicado o canon
  (`forum_watch/drafts.py`, DDL de `narrative_drafts`). El legado narrativo sí registra aprobación y
  publicación como evidencias separadas (`memory/events.jsonl`).
- El contrato de salida separa hechos observables, OOC, pensamiento privado, propuestas,
  resultados no confirmados, combate e incertidumbre, y solo permite hechos IC respaldados
  (`forum_watch/schemas/narrative-result.json`, `forum_watch/result.py`).
- SQLite, Windows Task Scheduler, Discord y Codex CLI son implementaciones demostradas, no
  contratos de dominio. Deben quedar detrás de puertos.

### Mapa de conocimiento de los 41 Markdown

Leyenda: **G** = conocimiento genérico que sigue siendo válido sin Nozomu, Naruto ni Jcink;
**E** = contenido específico cuya responsabilidad semántica corresponde a un paquete/adaptador,
sin que ello autorice copiar texto de reglas o lore. Cuando un archivo contiene ambos, se indican
dos destinos. Los borradores se conservan como evidencia y posibles fixtures de paridad; su prosa
no se copia al núcleo.

| Fuente (cobertura) | Conocimiento y evidencia | Clasificación y destino |
| --- | --- | --- |
| `AGENTS.md` | Autoridad, coordinador único, especialistas consultivos, flujo fuente→contexto→borrador→confirmación→memoria y no publicación (`Inicio y autoridad`, `Delegación`, `Flujo`, `Persistencia`). La excepción de cuenta/tema es local. | **G:** `core/runtime`, `core/memory`, `core/review`. **E:** configuración de instancia y `adapters/jcink`. |
| `README.md` | Operación completa, estados de tema/borrador, separación de roles, seguridad narrativa y límites (`Uso diario`, `Borradores`, `Arquitectura`, `Reglas de seguridad`). IDs, rutas, periodicidad y comandos son locales. | **G:** `core/runtime/tracking.py`, `core/runtime/narrative.py`, `core/review` y orquestación en `core/runtime`. **E:** adaptador Jcink, integraciones Discord/scheduler y configuración de instancia. |
| `AUDIT-GENERALIZATION.md` | Catálogo de hipótesis elaborado sin legado: el propio documento declara 0 archivos y `GENERALIZATION AUDIT PARTIAL` (`Executive summary`, `Blockers`). | **Solo referencia histórica**; no importar contratos ni conclusiones sin otra evidencia. |
| `instructions/interprete.md` | Límites de personaje, IC/OOC, entrega OOC+IC+propuestas y preferencias de voz/POV/BBCode (`Intérprete`, `Preferencias`). | **G:** `core/runtime/narrative.py`. **E:** `packages/characters/nozomu` y presentación Jcink para BBCode. |
| `instructions/memoria.md` | Evento con fuente, deduplicación, correcciones sin borrado, hechos/creencias/secretos/propuestas/resultados y estado de combate por tema. | **G:** contrato de `core/memory`. **E:** nombres/campos mecánicos son estado de instancia externo; no se trasladan al paquete de sistema. |
| `instructions/combate.md` | Especialista técnico, cálculo solo con entradas explícitas, cita de reglas, snapshots de escena y salida condicionada (`Instructions`, `Profile`, `Knowledge`, `Respuesta`). | **G:** política de asimilación/consulta en `core/rules` y orquestación en `core/runtime`. **E:** perfil mecánico Nozomu queda en la instancia externa; reglas Naruto no se empaquetan. |
| `forum_watch/README.md` | Identidad de tema, baseline, captura completa, revisiones A→B→A, rechazo de desapariciones/reordenación, transacciones y concurrencia (`Registro`, `Contrato`, `Normalización`, `Persistencia`). | **G:** `core/runtime/tracking.py` y puertos internos. **E:** URL/host/cuenta a `adapters/jcink` y configuración de instancia. |
| `forum_watch/READER.md` | Lector autenticado con verificación por ejecución, completitud, doble barrido, límites y fallos conservadores (`Identidad`, `Navegación`). Selectores, Edge y tema 275 son Jcink/instancia. | **G:** contrato `ForumAdapter.read`. **E:** `adapters/jcink`; perfil de navegador fuera del repo. |
| `forum_watch/NARRATIVE.md` | Evaluación aislada, entrada no confiable, contexto mínimo, contrato de decisión, propuestas de memoria, draft versionado y STALE (`Evaluación`, `Contexto`, `Persistencia`). La invocación Codex/Nozomu es local. | **G:** `core/runtime/narrative.py`, `core/review` y orquestación en `core/runtime`. **E:** proveedor de modelo interno de runtime y paquete Nozomu. |
| `forum_watch/DISCORD.md` | Proyección de eventos a avisos, deduplicación, entrega incierta, reintentos y secreto fuera del repo (`Fuentes`, `Entrega`). Webhook/DPAPI/payload son Discord/Windows. | **G:** puerto de notificación en runtime. **E:** `integrations/discord` y almacén de secretos de instancia. |
| `forum_watch/WORKFLOW.md` | Fases recuperables, locks, silencio sin trabajo, barreras de acceso, auditoría de runs y ausencia de transacción global (`Un ciclo`, `Datos operativos`). Tarea Windows y valores concretos son locales. | **G:** `core/runtime`. **E:** `integrations/scheduler/windows.py`, configuración y datos operativos externos. |
| `memory/index.md` | Índice vigente, enlaces, pendientes, diferencia entre ficha total y recursos de escena, aprobación sin publicación. | **G:** vistas/índices de `core/memory`. **E:** semilla de migración de la instancia Nozomu; no dato estático del paquete. |
| `memory/entities/nozomu-yamamoto.md` | Entidad revisada por anotaciones, procedencia y separación entre estado narrativo/mecánico/editorial. | **G:** patrón de entidad en `core/memory`. **E:** identidad/interpretación independiente del sistema puede ir a `packages/characters/nozomu`; historia y ficha mecánica quedan en la instancia. |
| `memory/entities/arashi-hozuki.md` | Lo dicho/observado frente a lo OOC, relación no recíproca y propuestas aún no oídas (`Conocimiento`, `Límites`). | **G:** modelo de conocimiento/relación en `core/memory`. **E:** memoria de instancia Nozomu; no perfil universal de Arashi. |
| `memory/topics/ficha-mecanica/summary.md` | Estado declarado, procedencia, alias/IDs, aprendido≠utilizable, valores máximos≠recursos actuales y pendientes. | **G:** procedencia y separación de estado en `core/character`, `core/rules` y `core/memory`. **E:** ficha Nozomu como perfil operativo versionado de la instancia; ninguna fórmula/regla va a paquetes. |
| `memory/topics/mision-d-pedidos-del-puerto/summary.md` | Una confirmación parcial consolida solo el núcleo sustentado, no todos los detalles/recompensas. | **G:** consolidación mínima en `core/memory`. **E:** memoria histórica de instancia; contenido no va al core. |
| `memory/topics/muelle-nozomu-arashi/summary.md` | Cronología por revisiones, IC/OOC, turno local frente a post remoto y consecuencias pendientes. | **G:** `core/memory`/`core/review`. **E:** memoria histórica de instancia. |
| `memory/topics/tecnicas-unicas/summary.md` | Historial de decisiones y ejes separados DRAFT, aprobación staff, aprendizaje y uso; propuestas sustituidas sin borrarlas. | **G:** procedencia/revisiones. **E:** estado histórico externo de la instancia Nozomu; no contenido del sistema ni enum global del core. |
| `drafts/misiones/2026-09-15-*`, `09-16-*`, `09-18-*`, `09-20-*`, `09-23-*` (5) | Cadena de posts con estado libre, aprobación comunicada, publicación no verificada y consecuencias abiertas. | **Solo referencia histórica**; estructura de versión/consecuencias alimenta `core/review`, muestras saneadas pueden ser fixtures. |
| `drafts/misiones/individual-d-pedidos-del-puerto.md` | Borrador largo, datos OOC, conteo editorial, confirmación posterior parcial y detalles no canonizados. | **Solo referencia histórica**; evidencia para pruebas de consolidación parcial y presentación Jcink. |
| `drafts/muelle-nozomu-arashi/*.md` (6) | Versiones, sustitución editorial, nota OOC, cuerpo IC y consecuencias; una v2 aprobada pero no publicada. | **Solo referencia histórica**; formato informa `core/review` y voz a `packages/characters/nozomu`. |
| `drafts/tecnicas-unicas/2026-09-11-rule-audit.md` | Auditoría de reglas, citas por pasaje, incertidumbres y STOP; detecta una fórmula contradictoria sin corregirla, distingue techos de permisos y exige fuentes faltantes (`§§1–6`). | **G:** contrato de asimilación/evaluación de `core/rules` y revisión en `core/review`. **E:** resultado Naruto/Nozomu queda histórico; no se empaqueta. |
| `drafts/tecnicas-unicas/2026-09-11-02-identidad-conceptos.md` | Legalidad/identidad/contrajuego y alternativas propuestas, sin concederlas. | **G:** metodología de `core/rules`. **E:** diseño Nozomu/Naruto histórico, fuera de paquetes. |
| `drafts/tecnicas-unicas/2026-09-11-03-guardia-abierta-variantes.md` | Comparación explícita de hipótesis, parámetros pendientes y límites de inferencia. | **G:** evaluación condicionada de reglas. **E:** borrador histórico externo; no dato de sistema. |
| `drafts/tecnicas-unicas/2026-09-11-04-guardia-abierta-ficha.md` | Campos de técnica realmente usados: nombre, rama, rango, requisito, sellos, coste, potencia, alcance, efecto, activación, duración, limitaciones, contrajuego, escalado, balance, dudas y estado. | **G:** evidencia para admitir schemas de ficha aportados por cada foro en `core/rules`, sin hacerlos universales. **E:** propuesta Nozomu histórica; no schema del paquete Naruto. |
| `drafts/tecnicas-unicas/2026-09-11-05-comparacion-genin.md` y `...guardia-abierta-genin.md` (2) | Precedentes con procedencia, alternativas de balance y ficha por rango; aprobación ajena no transfiere autoridad. | **G:** procedencia y alcance en `core/rules`. **E:** estado Nozomu y fuentes Naruto históricos, no paquetes. |
| `drafts/tecnicas-unicas/2026-09-11-06-guardia-abierta-linea-completa.md` | Línea evolutiva con tres fichas y ejes `STATUS`, `APPROVAL`, `LEARNING`; nombres recomendados no elegidos. | **E:** diseño histórico externo de Nozomu; sirve como fixture saneado de estados ortogonales, no como dato empaquetado. |
| `reference/knowledge-index.md` | Índice de cinco fuentes reglamentarias, vigencia no verificada, conservación literal y obligación de comprobar que cada extracto contiene la regla (`Fuentes aportadas`). | **G:** índice versionado y recuperación dirigida en `core/runtime/assimilation.py`, con consumo por `core/rules`. **E:** índice y textos Naruto quedan solo como referencia histórica; no se copian a paquetes. |
| `reference/original/AGENTS.md` | Contexto del antiguo espejo y ausencia de instrucciones personalizadas. | **Solo referencia histórica**. |
| `reference/original/Nozomu_Yamamoto_documento_maestro.md` | Fuente compuesta: identidad, voz, metas, trasfondo, mundo, conocimiento IC/meta, memoria, inventario, protocolo y checklist. | **G:** `core/runtime/narrative.py`, `core/memory`, `core/review`. **E:** solo identidad/interpretación eventualmente autorizada puede ir al paquete de personaje; lore, reglas y estado dinámico no se empaquetan. |
| `reference/original/Nozomu Combat & Build Agent.md` | Modos combate/build, prioridad de fuente oficial, prohibición de inventar/extrapolar, estado de escena, formato de técnica y salida `REQUIERE CONFIRMACIÓN` (`Regla fundamental`, `Modos`, `Incertidumbre`). Valores y fórmulas son locales. | **G:** `core/rules` + flujo de asimilación en `core/runtime`. **E:** valores Nozomu/Naruto son referencia histórica o estado externo, nunca paquete de sistema. |

### Principios genéricos demostrados que deben conservarse

| Principio | Evidencia |
| --- | --- |
| Los estados no colapsan: borrador, aprobación, publicación, resolución y canon son acreditaciones distintas. Aprendido y utilizable también son ejes distintos. | `README.md`, `Uso diario`; `AGENTS.md`, `Flujo`; maestro, §§9 y 12; `memory/topics/tecnicas-unicas/summary.md`, `Histórico — auditoría inicial`. |
| Toda afirmación persistida necesita procedencia, alcance y versión; una corrección anota y preserva el original. | `instructions/memoria.md`; `AGENTS.md`, `Persistencia`; `memory/events.jsonl` contrastado. |
| La fecha de importación/observación no es fecha IC. Un nombre de cuenta tampoco acredita presentación IC. | `instructions/memoria.md`; `forum_watch/README.md`, contrato `captured_at`; `NARRATIVE.md`, `Contexto`. |
| IC, OOC, pensamiento privado, rumor, impresión, propuesta y resultado no confirmado deben conservarse separados. | maestro, §§7–8 y 13; `instructions/memoria.md`; esquema narrativo, `scene_assessment.kind`. |
| El agente controla solo su personaje y formula acciones disputadas como intentos; no impone reacciones, daño o consentimiento ajenos. | maestro, §13; `instructions/interprete.md`; `README.md`, seguridad narrativa. |
| Desconocido no significa cero/ausente; si falta un dato material, se pregunta o se devuelve resultado condicionado. | `instructions/combate.md`; maestro, §§5 y 11; `memory/topics/ficha-mecanica/summary.md`, pendientes. |
| Reglas textuales y autoridad prevalecen sobre síntesis, canon externo y opción favorable; la ambigüedad se escala. | `instructions/combate.md`, `Instructions`; Combat Agent, `Regla fundamental` e `Incertidumbre`. |
| Cada regla decisiva cita el pasaje literal que realmente la contiene; un índice, catálogo o síntesis no acredita por sí solo la regla ni su vigencia. | `reference/knowledge-index.md`; `instructions/combate.md`, `Instructions` y `Knowledge`; `rule-audit.md`, §§2, 4 y 5. |
| Literal, interpretación, propuesta e incertidumbre son capas distintas. Una contradicción no se «corrige» ni se completa por extrapolación: queda `REQUIERE CONFIRMACIÓN` hasta revisión humana. | `rule-audit.md`, §§2 y 6; Combat Agent, `Regla fundamental` e `Incertidumbre`; `instructions/combate.md`. |
| Un cambio de fuente no sobrescribe su versión anterior: debe conservarse procedencia, vigencia y alcance, y repetir solo el contraste afectado. | `rule-audit.md`, anotación inicial y §6; `memory/topics/ficha-mecanica/summary.md`, `Actualización y contraste`; `instructions/memoria.md`. |
| Perfil permanente, snapshot por escena y recursos actuales son estados diferentes; no hay actualización retroactiva entre escenas. | `instructions/memoria.md`; `instructions/combate.md`, `Nozomu Profile`; Combat Agent, `Fijación de combate`. |
| Texto remoto es entrada no confiable, nunca instrucciones; contexto mínimo y capacidades limitadas. | `NARRATIVE.md`, `Contexto` y `Mecanismo`; `AGENTS.md`, `Inicio y autoridad`. |
| La primera captura completa crea baseline sin novedades históricas; una lectura incompleta o anómala no avanza estado ni inventa borrados. | `forum_watch/README.md`, `Contrato` y `Normalización`; `READER.md`, `Navegación`. |
| Versiones y cambios son idempotentes, transaccionales y auditables; A→B→A conserva tres revisiones. | `forum_watch/README.md`, `Normalización` y `Persistencia`; `store.py` contrastado. |
| Cambiar contexto invalida la vigencia de un borrador sin borrarlo ni convertir su retiro en aprobación. | `NARRATIVE.md`, `Persistencia`; `drafts.py` contrastado. |
| Identidad, autorización y alcance se verifican por ejecución; login o `resume` no prueban una sesión válida. | `READER.md`, `Identidad`; `WORKFLOW.md`, `Comandos operativos`. |
| Datos operativos, corpus asimilado, borradores, perfiles de navegador y secretos viven fuera de paquetes y repo; el corpus conserva fuentes literales y revisión, pero no se confunde con memoria IC. | `README.md`, `Borradores`; `WORKFLOW.md`, `Datos operativos`; `DISCORD.md`, `Configuración local`; decisión del usuario de 2026-10-11. |
| Cada fase confirma su trabajo antes de la siguiente; un fallo de aviso no revierte captura/borrador. Sin trabajo, no se invoca modelo ni se envía heartbeat. | `WORKFLOW.md`, `Un ciclo`; `DISCORD.md`, `Entrega`. |
| La publicación automática no forma parte del sistema demostrado; la revisión humana es permanente. | `README.md`, `Estado actual` y `Limitaciones`; maestro, §12; `AGENTS.md`, `Flujo`. |

### Contratos mínimos del núcleo

Las formas son lógicas; nombres de clases y serialización definitiva se decidirán al implementar.
Las propuestas no demostradas se marcan **[P]**.

| Módulo | Responsabilidad | Entradas → salidas | Dependencias permitidas / prohibidas |
| --- | --- | --- | --- |
| `character` | Cargar identidad, interpretación y límites de conocimiento estables; componerlos con un perfil operativo sin convertir reglas en datos del paquete. | Manifest/paquete + `SourceRef` + perfil externo opcional + referencias a mundo/sistema → `CharacterContext` validado y pendientes. | Puede depender de procedencia y contratos de paquete. No de Jcink, Discord, proveedor de modelo ni SQLite. Toda ficha mecánica dependiente del foro, incluida Nozomu, queda en la instancia. |
| `world` | Consultar ambientación aportada y aprobada con cita, versión, vigencia, autoridad y alcance; nunca inferir huecos ni afirmar que el personaje la conoce. | Consulta dirigida + versión aprobada del corpus externo → pasajes literales, afirmaciones/interpretaciones aprobadas, conflictos, lagunas y citas. | No almacena lore en el paquete ni depende de personaje. El filtro IC se hace al componer con memoria/personaje. Si no hay corpus aprobado, devuelve desconocido, no canon externo. |
| `rules` | Representar `ABSENT` de forma explícita o consultar/evaluar normas aportadas y aprobadas; separar literal, interpretación, propuesta e incertidumbre. | Selección de sistema (`ABSENT` o corpus+versión) + consulta/snapshot/acción → secciones relevantes, evaluación condicionada, fórmula/unidades solo si están respaldadas, riesgos y `REQUIERE CONFIRMACIÓN`. | No contiene reglas Naruto ni depende de paquetes con reglas. Solo consume entradas aprobadas con `SourceRef`; una extracción pendiente/rechazada no es utilizable. `ABSENT` no simula ceros ni resolución mecánica. |
| `memory` | Ingerir eventos fuente, deduplicar, preservar revisiones y proyectar conocimiento IC/OOC, relaciones, pendientes y estado por escena. | Evento + fuentes + revisión opcional → registro inmutable/revisión; consulta contextual → hechos, creencias, lagunas y referencias. | Depende de un puerto de repositorio, no de SQLite. No recibe borradores como hechos ni escribe paquetes. |
| `review` | Versionar borradores y registrar decisiones humanas por versión exacta; aportar el vocabulario de revisión también a candidatos de asimilación sin tratarlos como publicaciones. | Borrador/candidato + versión + decisión/evidencia → estado explícito e historial. | No publica, canoniza ni activa una fuente por sí mismo. `DraftVersion` conserva sus tres ejes actuales; la asimilación tendrá su propio registro y reutilizará `ReviewStatus`, no `PublicationStatus`. |
| `runtime` | Alojar expediente/asimilación, materialización de instancia, CLI, narrativa y seguimiento; ejecutar fases recuperables. La asimilación registra literales, crea candidatos manuales o mediante puerto de modelo, solicita revisión y construye un índice dirigido solo con entradas aprobadas. | Expediente + ruta/paquetes elegidos → instancia externa; fuentes/metadatos → candidatos citados; decisión humana → corpus consultable; consulta → secciones relevantes. Además conserva los flujos de escena, tracking y `RunReport`. | `assimilation.py`, `cli.py`, `narrative.py` y `tracking.py` son submódulos internos. Depende de puertos y de modelos de `rules`/`world`; el camino manual funciona sin `ModelProvider`. No contiene reglas/lore concretos ni selectores Jcink. |

Los puertos no requieren una carpeta de primer nivel: los repositorios propios quedan junto al
módulo dueño (`core/memory/ports.py`, y el repositorio de corpus en `core/runtime/ports.py`) y los
límites de ejecución quedan en `core/runtime/ports.py` (`ForumReader`, `ModelProvider`,
`NotificationSink`, `Scheduler`, reloj/lock y `PublicationPort`). `PublicationPort` se define y se
prueba con un doble, pero ningún archivo de `adapters/` lo implementa. El proveedor opcional Codex
CLI, si se migra, queda en
`core/runtime/codex_cli_provider.py`; la interfaz es `ModelProvider`. El esquema y ejemplo de
configuración quedan en `core/runtime/config.schema.json` y `core/runtime/config.example.json`, sin
autorizaciones reales. El adaptador manual inicial es `adapters/manual.py`; Jcink permanece en
`adapters/jcink/`.

El `SourceRef` ya implementado en `core/memory/provenance.py` fija identificador, localizador, hash,
sección/pasaje, instante observado y fecha IC independiente. Los metadatos aún no implementados de
autoridad, versión, vigencia, aportante y supersesión pertenecen al registro de documento/corpus,
no se añadirán retroactivamente a `SourceRef` sin un incremento específico. Ningún campo ausente se
rellena por inferencia.

#### Contrato lógico de asimilación

Los nombres definitivos son **[P]**, pero las separaciones son requisitos. El componente vive en
`core/runtime/assimilation.py`; no crea otra carpeta de `core/` ni un primer nivel nuevo.

| Registro | Campos mínimos respaldados | Invariantes |
| --- | --- | --- |
| Versión de fuente | `document_id`, `version`, clase (`REGLAMENTO`, `COMBATE`, `FICHA`, `TECNICA`, `AMBIENTACION`), autoridad/alcance, `effective_from`/`effective_until` opcionales, `supersedes` opcional, bytes/texto literal y `SourceRef` con hash. | Una versión es inmutable. Un cambio crea otra; ausencia de vigencia sigue siendo desconocida y no se interpreta como vigente. La fuente literal y el corpus operativo viven fuera del repo. |
| Sección literal | ID estable dentro de la versión, título/orden, texto exacto y `SourceRef.section_or_passage`. | No parafrasear ni unir huecos. Hash/cita deben resolver al documento y versión exactos. |
| Entrada de asimilación | ID/versión, dominio `RULES` o `WORLD`, clase `LITERAL`, `INTERPRETATION`, `PROPOSAL` o `UNCERTAINTY`, texto/estructura, una o más citas, alcance, `ReviewStatus` y evidencia humana opcional. | Solo `APPROVED` con evidencia y fuente de vigencia inequívoca es utilizable. `REJECTED` y pendiente permanecen auditables. Fórmulas/tablas extraídas son interpretación estructurada salvo que la cita literal las contenga; nunca se guardan en paquetes. |
| Selección de instancia | Mundo/corpus/versión elegidos y modo de reglas `EXTERNAL` o `ABSENT`. | `ABSENT` es explícito y no genera atributos, ceros ni un evaluador mecánico. `EXTERNAL` exige corpus aprobado; no hay fallback a conocimiento del modelo. |

Flujo mínimo: (1) registrar versión literal y secciones; (2) crear entradas manualmente o solicitar
candidatos a `ModelProvider`; (3) validar que cada cita resuelve a un pasaje de esa versión; (4)
registrar decisión humana sobre la versión exacta; (5) indexar solo entradas aprobadas; (6) ante una
consulta, recuperar primero un subconjunto de secciones/entradas por clase, alcance y términos, y
entregarlo a `rules` o `world`. El índice inicial será determinista y de biblioteca estándar; ni la
consulta ni las pruebas requieren embeddings/modelo. La salida del modelo nunca cambia
`ReviewStatus` ni vigencia. Si faltan pasajes, hay versiones concurrentes o una interpretación no
está acreditada, la salida conserva las alternativas y `REQUIERE CONFIRMACIÓN`.

#### Plantilla de expediente del foro

El expediente es un directorio aportado por el usuario cuyo documento principal es
`expediente.md`; puede referenciar ficheros de texto relativos dentro del mismo directorio. La
plantilla versionada vive en `core/runtime/templates/expediente.template.md` y su guía copiable en
`core/runtime/templates/LEEME-expediente.md`; no se crea una carpeta de primer nivel ni un hijo
nuevo directo de `core/`. La instancia recibe una copia literal y con hash de las fuentes, nunca
modifica el expediente original. La gramática corresponde implícitamente al schema 1 y se
convierte a `ForumDossier`; Markdown no es la representación de estado interno.

Cabecera exacta, en las cuatro primeras líneas, sin líneas vacías intermedias:

```text
# Expediente del foro
forum_id: <id ASCII [a-z0-9]+(?:-[a-z0-9]+)*>
nombre: <texto no vacío sin espacios exteriores>
versión_expediente: <texto opaco no vacío sin espacios exteriores>
```

Después aparecen una vez, en este orden y con grafía exacta, estos encabezados. Cualquier
encabezado ATX (`#` a `######`) desconocido, duplicado o fuera de orden, fuera de un literal
cercado, es error; `### Fuente` es la única excepción repetible.

| Encabezado Markdown | Clave/modelo interno | Obligación |
| --- | --- | --- |
| `## Normas generales` | `forum_rules` | Obligatoria |
| `## Ambientación` | `setting` | Obligatoria |
| `## Creación de fichas` | `character_creation` | Obligatoria |
| `## Revisión del staff` | `staff_review` | Obligatoria |
| `## Plataforma y formato` | `platform_format` | Obligatoria |
| `## Sistema de combate` | `combat_system` | Opcional |
| `## Creación de técnicas o habilidades` | `ability_technique_creation` | Opcional |
| `## Material suelto` | `loose_material` | Cero o más fuentes, no es una octava sección de dominio |

En las siete secciones de dominio, la primera línea no vacía puede ser `Estado: FALTA` o
`Estado: NO APLICA`; si no existe, el estado es aportado (`PROVIDED`). `FALTA` mapea a `MISSING`;
`NO APLICA`, a `NOT_APPLICABLE`, y solo se admite en las dos opcionales. Tras el estado puede haber
como máximo una línea `Nota: <texto no vacío sin espacios exteriores>`; si se omite el marcador,
la nota sigue pudiendo aparecer antes de la primera fuente. Una sección aportada
exige una o más fuentes; `FALTA`/`NO APLICA` prohíben fuentes. Las obligatorias faltantes bloquean
`ready_for_assimilation`; una opcional `FALTA` se diagnostica sin bloquear todo el expediente.
`Material suelto` no acepta `Estado` ni `Nota`: puede estar vacío y mapea directamente a la tupla
`loose_material`.

Cada fuente comienza con `### Fuente` y, en la línea no vacía siguiente, una única línea con esta
gramática:

```text
Metadatos: <clave>=<json> | <clave>=<json> [ | <clave>=<json> ...]
```

Las claves admitidas son exactamente `id`, `versión`, `autoridad`, `alcance`, `desde`, `hasta`,
`pasaje`, `archivo` y `sugerencias`. Su orden es libre; una clave desconocida o repetida es error.
Cada campo es el nombre exacto, `=` y un literal JSON consumido desde ese punto con
`json.JSONDecoder.raw_decode`; después del literal solo se acepta el separador exacto ` | ` o fin
de línea. No se divide la línea por el separador. El resultado sigue siendo determinista porque
las claves son únicas y se proyectan a campos internos de orden fijo.

`id`, `versión`, `autoridad` y `alcance` son obligatorias y sus valores son strings no vacíos sin
espacios exteriores ni caracteres de control C0. Las demás son opcionales: omitir `desde`, `hasta`,
`pasaje` o `archivo` equivale a `null`, y omitir `sugerencias` equivale a `[]`. `desde` y `hasta`
son fechas reales `"YYYY-MM-DD"` o `null`; si ambas existen, desde ≤ hasta. `pasaje` es string no
vacío o `null`. `archivo` es una ruta string válida o `null`. `sugerencias` solo se permite en
`Material suelto`, como lista sin duplicados de los nombres españoles exactos de las siete
secciones de dominio; incluir la clave en una sección de dominio es error, incluso con `[]`.

El origen se deduce de `archivo`. Si tiene un string, la fuente es de archivo y no lleva cuerpo:
una apertura de valla en la línea física siguiente es error. Si `archivo` se omite o es `null`, la
fuente es en línea y la línea física inmediatamente posterior a `Metadatos:` debe ser la apertura
de su valla, sin línea vacía ni indentación. No existe la clave `texto_en_línea`.

Patrones mínimos copiables —el segundo demuestra que el orden no es semántico—:

```text
Metadatos: id="reglas-generales" | versión="2026-10-11" | autoridad="Staff" | alcance="foro" | archivo="materiales/reglas.md"
Metadatos: autoridad="Staff" | id="ambientacion" | alcance="foro" | versión="1" | pasaje="Introducción"
```

La primera es una fuente de archivo. La segunda es inline por omisión de `archivo`, de modo que su
línea física siguiente debe ser la apertura de la valla.

Una fuente de archivo no lleva cuerpo tras los metadatos. La ruta usa `/`, es relativa al
directorio del expediente, no contiene segmentos vacíos, `.` o `..`, y no puede ser absoluta,
UNC, con unidad Windows, symlink ni atravesar symlinks; el archivo regular resuelto debe permanecer
dentro del expediente. Se lee como UTF-8 estricto y se hashean sus bytes exactos, sin normalizar
finales de línea; debe contener al menos un carácter no blanco, aunque no se recorta.

Una fuente en línea lleva este cerco variable:

```text
~~~~~ texto
<literal arbitrario>
~~~~~
```

La valla es `N` virgulillas (`~`) con `N >= 4`; la apertura es exactamente `~` repetida `N` veces,
un espacio y `texto`, y el cierre es una línea con exactamente las mismas `N` virgulillas. `N`
debe ser estrictamente mayor que cualquier racha de virgulillas contenida en el literal. Así el
usuario aumenta `N` si el reglamento contiene `~~~~`, el propio delimitador corto o fences de
código. Dentro del cerco, encabezados, listas, tablas y bloques Markdown son bytes de la fuente y
no estructura del expediente. Un cierre ausente/ambiguo o texto estructural inesperado falla con
la línea del problema; no se intenta adivinar la intención.

`expediente.md` se lee como UTF-8 estricto sin BOM. Antes de reconocer líneas se convierte cada
CRLF a LF y se rechaza cualquier CR solitario. Esta canonización hace que guardar el mismo documento
en Windows o con checkout LF produzca el mismo literal/hash. El texto en línea es **exactamente**
la secuencia canónica entre el LF posterior a la apertura y el primer byte de la línea de cierre:
no se recorta, por lo que incluye el LF final anterior al cierre. Esos bytes UTF-8 canónicos son los
que se guardan y hashean; deben contener al menos un carácter no blanco. Su locator estable es
`<expediente.md>#inline:id=<id-citado>&version=<version-citada>`, usando
`urllib.parse.quote(value, safe="")`; editar otra zona no cambia locator ni hash.

Fuera de cercos solo se ignoran líneas totalmente vacías; espacios de sangría, trailing spaces o
prosa que no pertenezca a cabecera, estado, nota, fuente o metadatos son error. Repetir
`(id, version)` exige autoridad, alcance, vigencia, origen y hash idénticos; solo pueden diferir
`pasaje` y, en material suelto, `sugerencias`. Un mismo id con versiones distintas permanece como
fuentes distintas: este incremento no elige vigencia ni infiere supersesión.

Los comentarios HTML siguen siendo texto desconocido y, fuera de una valla, son error: no se abre
una excepción que vuelva ambigua la gramática cerrada. `LEEME-expediente.md` contiene ejemplos
completos y copiables de fuente de archivo y fuente en línea, explica las omisiones y recuerda que
la valla debe crecer si el literal contiene el delimitador. La plantilla válida remite a esa guía
desde una línea `Nota:` y no contiene comentarios ni ejemplos fingidos.

#### Carpeta de instancia externa

`instance init` exige siempre `--output <ruta>`: no consulta ni deriva ubicaciones por defecto.
Rechaza una ruta dentro del checkout o una carpeta no vacía. El usuario elige ruta, `forum_id`,
paquetes y confirma la creación; el runtime materializa de forma transaccional y deja auditable el
origen de cada archivo. Layout objetivo:

```text
<instancia-foro>/
  AGENTS.md                        # generado, no estado
  CLAUDE.md                        # generado, no estado
  instance.json                    # schema, forum_id, core_root y paquetes/versiones
  dossier/                         # copia literal del expediente y sus fuentes
  corpus/                          # candidatos, decisiones, versiones e índice aprobado
  characters/<character_id>/
    concept.md                     # entrada del usuario
    profile.json                   # ficha versionada y ejes separados
    proposals/                     # propuestas pendientes/aceptadas/rechazadas
    drafts/                        # borradores, nunca publicaciones implícitas
  memory/                          # eventos y vistas con SourceRef
  work/                            # colas, locks y auditoría de ejecución
  specialists/                    # solo capacidades exigidas por el foro aprobado
```

Solo las plantillas están en el repo, bajo `core/runtime/templates/`: expediente, configuración y
ambos archivos de instrucciones; más adelante, plantillas de especialistas genéricos. Una política
común renderiza los bloques invariantes de `AGENTS.md` y `CLAUDE.md`; un contract test compara esos
bloques para impedir divergencias, dejando aparte solo indicaciones propias de cada herramienta.
`instance.json` se renderiza desde plantilla y los demás datos proceden del expediente, decisiones
humanas y comandos del core. Un especialista de combate se genera solo si `combat_system` tiene
entradas aprobadas;
`NOT_APPLICABLE`, `MISSING` o candidatos pendientes no bastan. Nozomu, Naruto, reglas, memoria ni
configuración efectiva se añaden a ninguna plantilla.

#### Uso del core desde el agente generado

La instancia no instala ni copia el core. `instance.json` conserva la ruta absoluta del checkout
confirmada al crearla. Las instrucciones generan comandos PowerShell con rutas entre comillas:

```powershell
Push-Location '<core_root>'
py -3.11 -B -m core.runtime.cli --instance '<instance_root>' <comando>
Pop-Location
```

Así `core` se importa desde la raíz del checkout, sin dependencia global ni `PYTHONPATH`. Si el
checkout se mueve, una operación explícita de relink actualizará solo `core_root` con confirmación.
El CLI valida rutas y versiones, recupera solo corpus aprobado, crea `DraftVersion`, exige
`SourceRef` para decisiones/memoria y carece de comando de publicación. Los documentos del usuario
se pueden editar, pero ningún cambio de corpus, estado o memoria se considera válido por editar
JSON/Markdown directamente: debe pasar por las operaciones del core. Las instrucciones explican el
flujo; estas barreras ejecutables sostienen las invariantes.

#### Creación de personaje y reparto de decisiones

| Paso | Decide/aporta el usuario | Hace el agente, siempre mediante el core |
| --- | --- | --- |
| Expediente | Fuentes, versión/autoridad/vigencia y marcadores `FALTA` o `NO APLICA`; aprueba/rechaza cada candidato exacto. | Valida literales y citas, clasifica solo como candidato, enumera faltantes/contradicciones y marca `REQUIERE CONFIRMACIÓN`; nunca aprueba. |
| Instancia | Ruta, foro y paquetes/versiones; confirma materialización. | Genera desde plantillas y habilita especialistas solo por capacidades aprobadas. |
| Concepto | Escribe el concepto, fija lo irrenunciable y responde dudas. | Lo conserva como fuente, recupera normas aprobadas pertinentes y no usa reglas pendientes. |
| Ajuste | Acepta/rechaza cada mejora y elige entre alternativas. | Presenta diferencias con citas como `PROPUESTA`; una aceptación crea una versión nueva, no reescribe el concepto original ni acredita staff. |
| Ficha | Decide cuándo presentar y aporta la respuesta/evidencia del staff. | Valida cada campo contra normas aprobadas; ante hueco/ambigüedad bloquea la afirmación de conformidad. Crea `DraftVersion` en borrador y pendiente de revisión. |
| Juego | Decide intención, acepta borrador y publica externamente si quiere; aporta evidencia de publicación/resolución. | Redacta intentos con contexto mínimo y citas; no publica ni canoniza, y solo propone memoria respaldada. |

La aceptación del usuario de una propuesta de diseño, la aprobación del staff, el aprendizaje y
la utilizabilidad son acreditaciones distintas. La primera autoriza una nueva versión de ficha;
la segunda usa revisión humana con evidencia; aprendizaje y utilizabilidad se registran por
separado en el perfil operativo externo; publicación y canon continúan independientes. Una ficha
aprobada no queda aprendida ni utilizable, y una ficha publicada no queda aprobada ni canónica.

#### Estados que no deben representarse con un único enum

- **Versión de contenido:** identificador y número/hash exactos.
- **Vigencia:** `ACTIVE | STALE | RETIRED` (demostrado por Forum Watch).
- **Revisión humana:** `PENDING_HUMAN_REVIEW | APPROVED | REJECTED`; rechazo está respaldado por
  el protocolo del maestro, aunque el CLI legado no lo persistía.
- **Publicación:** no confirmada o confirmada con fuente y versión exacta.
- **Memoria:** candidato pendiente frente a registro consolidado, con clase epistemológica.
  El registro consolidado con fuente y alcance es canon aunque no haya publicación; canon no es un
  estado de `DraftVersion`.
- **Asimilación:** documento/versión vigente, candidato y decisión humana son ejes propios. Solo un
  candidato `APPROVED` para una versión vigente entra en consultas; sustituir una fuente no borra
  versiones ni decisiones previas. No se usa `PublicationStatus` para este fin.
- **Resolución:** intento/acción publicada frente a consecuencia resuelta por participante,
  narrador, reglas o staff.
- **Mecánica específica:** aprobación de staff, aprendizaje y disponibilidad pertenecen al perfil
  operativo del personaje y al corpus asimilado, no al paquete de sistema ni al borrador universal.

### Formato lógico de los paquetes

Se usa JSON estricto para datos validados y, únicamente en personaje, podrá usarse Markdown para
voz/guía interpretativa si se autoriza en su incremento. No se añade YAML ni dependencia. El
envoltorio común `schema_version`, `package_type`, `package_id`, `display_name`, `version` y
`requires` es **[P]** de infraestructura: el legado exige versión y procedencia, pero no impone esos
nombres. El incremento 2 implementa solo ese manifiesto y su loader; no define payloads.

| Paquete | Campos respaldados por el legado | Lo que no debe contener |
| --- | --- | --- |
| Personaje | Identidad; rasgos y límites de interpretación; objetivos; trasfondo; POV/voz/formato; conocimientos iniciales y exclusiones meta; referencias a mundo/sistema; procedencia por afirmación o bloque. Evidencia: maestro §§1–5, 7–8, 11 e `instructions/interprete.md`. | Reglas/fórmulas, ficha mecánica dependiente del sistema, memoria mutable, borradores, recursos actuales, secretos/configuración, cuenta/tema, selectores y cualquier derivado de lore/reglamento. |
| Mundo | En esta fase, solo el manifiesto común identifica y versiona el namespace del mundo y sus dependencias. Las entradas de ambientación se registran después como corpus externo versionado y revisado, no como payload del paquete. | Texto, extractos o datos estructurados derivados de lore; presunción de conocimiento IC; reglas, voz de personaje o estado operativo. |
| Sistema | En esta fase, solo el manifiesto común identifica y versiona el namespace del sistema y sus dependencias. Las normas, schemas de ficha/técnica aportados por el foro, tablas, fórmulas y valores viven en el corpus externo versionado y revisado. `ABSENT` es una selección explícita de instancia, no un paquete con valores cero. | Texto/extractos reglamentarios y todo dato estructurado derivado; valores de Nozomu, defaults mecánicos, decisiones narrativas, selectores o estado operativo. |

La identidad e interpretación estables y aprobadas de un personaje reutilizable pueden entrar en
un paquete de personaje; la creación guiada no genera paquetes en el repo, sino perfiles externos
dentro de la instancia. Para el caso legado, esos datos autorizados podrían entrar en
`packages/characters/nozomu`; su historia ya jugada y la memoria dinámica viven fuera del repo,
y toda su ficha mecánica vive en la instancia del foro. Los diseños no aprobados se conservan como
referencia histórica, nunca como repertorio adquirido.
`packages/worlds/naruto-rol` y `packages/systems/naruto-rol` serán manifiestos/identidades sin texto
ni datos derivados de reglas o lore. El material que aporte el usuario se conserva literalmente en
el almacenamiento externo de la instancia, con versiones, vigencia, citas y revisión. El core no
presupone Naruto ni ninguna otra temática.

### Valoración de la estructura propuesta

| Elemento propuesto | Valoración |
| --- | --- |
| `core/{character,world,rules,memory,runtime,review}` | Estructura vinculante. Narrativa y seguimiento se implementan dentro de `core/runtime/` como archivos/submódulos internos; no se crean carpetas hermanas nuevas en `core/`. |
| `adapters/jcink` | Correcto. Debe contener URL, autenticación, selectores, paginación, BBCode/presentación y capacidades; no memoria ni generación. |
| `packages/{characters,worlds,systems}` | Correcto como manifests versionados y datos autorizados de personaje. Mundo/sistema no alojan fuentes ni derivados; identifican namespaces seleccionables. El corpus asimilado y el estado mutable son externos. |
| `integrations/{discord,scheduler}` | Estructura vinculante. Discord queda en su carpeta; el soporte Windows es `integrations/scheduler/windows.py` y opcional. El proveedor de modelo queda dentro de `core/runtime/`, no crea otra integración hermana. |
| `reference/migration-source/` | Ruta definitiva del legado en este repo; se mantiene inmutable y no se renombra. |
| `tests` | Correcto; separar unitarios de core, contratos de puertos, fixtures saneadas y paridad legacy. |

El intérprete se implementa en `core/runtime/narrative.py`; asimilación en
`core/runtime/assimilation.py`; combate y memoria son capacidades de `core/rules` y `core/memory`,
invocables directamente o mediante especialistas de solo lectura. El coordinador y el seguimiento
(`tracking.py`) viven en `core/runtime/`. Borradores y vocabulario de revisión pertenecen a
`core/review`. La configuración real, corpus asimilado, memoria dinámica, SQLite, locks, drafts,
perfiles, cookies, autorizaciones y secretos viven fuera del repo; solo se versionan schemas y
ejemplos sin valores reales.

Árbol vinculante:

```text
core/
  character/
  world/
  rules/
  memory/
  runtime/                       # assimilation.py, narrative.py, tracking.py, ports.py, proveedor/config
  review/
adapters/
  manual.py
  jcink/
packages/
  characters/nozomu/
  worlds/naruto-rol/
  systems/naruto-rol/
integrations/
  discord/
  scheduler/                     # windows.py opcional
tests/
reference/migration-source/      # intacto
```

`core/`, `adapters/` e `integrations/` son paquetes Python en la raíz mediante `__init__.py`. Los
tests se ejecutan desde la raíz, que ya está en `sys.path`; no se instala el proyecto ni se manipula
`PYTHONPATH`. No hace falta `pyproject.toml` en el incremento 1: se difiere hasta que exista una
necesidad real de construir o distribuir el proyecto.

### Stack recomendado

- Python `>=3.11`, que es el mínimo documentado por el legado; en este equipo se usa siempre
  `py -3.11` (el comando `python` apunta a 3.10.6). Tipado, `dataclasses`, `enum`, `Protocol`,
  `pathlib`, `json`, `hashlib`, `sqlite3` y `unittest` de la biblioteca estándar.
- JSON estricto para manifests/estado, JSONL para eventos append-only y `expediente.md` con la
  gramática cerrada descrita arriba para entrada humana y fuentes; Markdown también puede usarse
  para voz/documentación autorizada. Esto no autoriza lore, reglas ni derivados en paquetes.
  Validadores propios de biblioteca estándar, sin afirmar soporte Markdown general ni JSON Schema
  completo.
- SQLite como primer repositorio operativo, detrás de puertos; transacciones y claves únicas ya
  demostraron rollback, idempotencia y concurrencia. No exponer SQL en contratos de dominio.
- `unittest` para conservar el stack demostrado. No introducir `pytest`, ORM, Pydantic o framework
  de agentes hasta que una necesidad concreta lo justifique.
- Playwright como extra opcional exclusivo de `adapters/jcink`; fijar versión y usar fixtures DOM
  offline. No instalar navegador desde el proyecto.
- `http.client`/`ssl` estándar para Discord es suficiente según el legado; secretos mediante un
  puerto, con DPAPI solo en la integración Windows.
- PowerShell/Task Scheduler solo como bridge opcional en `integrations/scheduler/windows.py`. El
  runtime recibe triggers y relojes por puerto.
- `ModelProvider` se define en `core/runtime/ports.py`; la implementación opcional Codex CLI queda
  en `core/runtime/codex_cli_provider.py`. No es requisito para cargar paquetes, memoria, revisar
  estados o ejecutar tests.

## Requisitos

- [ ] El producto materializa una carpeta externa por foro, con uno o varios personajes, desde
  plantillas genéricas; el repo no contiene instancias reales ni estado operativo.
- [ ] `expediente.md` tiene siete secciones fijas en español, fuentes/versiones explícitas y
  material suelto; informa por separado lo aportado, `FALTA` y `NO APLICA`, y los literales
  cercados no se confunden con estructura Markdown.
- [ ] La rebanada vertical neutra recorre expediente → revisión humana → instancia → concepto del
  usuario → ficha borrador, mediante adaptador manual y sin red/modelo.
- [ ] El agente generado invoca el core con `py -3.11 -B -m core.runtime.cli` desde el checkout, sin
  instalarlo, y las invariantes se validan en código antes de escribir estado.
- [ ] Las propuestas de ajuste de personaje están etiquetadas y requieren aceptación expresa;
  concepto, propuesta, ficha, aprobación de staff, aprendizaje y utilizabilidad no se colapsan.
- [ ] Ningún módulo genérico contiene `Nozomu`, `Naruto`, `Jcink`, host, cuenta o tema concretos.
- [ ] Cada dato de personaje y cada entrada asimilada de mundo/regla conserva fuente literal,
  versión, vigencia, autoridad, alcance, cita por regla y pendientes.
- [ ] La composición impide usar lore/OOC/pensamientos privados como conocimiento IC sin una vía
  documentada.
- [ ] Revisión, vigencia, publicación, canon y resolución son transiciones explícitas por versión.
- [ ] No existe publicación automática ni consolidación canónica automática por defecto.
- [ ] Texto literal, interpretación, propuesta e incertidumbre se representan por separado; solo
  entradas revisadas y aprobadas son utilizables, y las ambiguas dicen `REQUIERE CONFIRMACIÓN`.
- [ ] Una nueva versión del reglamento no sobrescribe la anterior; consultas con vigencia ambigua
  fallan de forma conservadora y muestran las fuentes en conflicto.
- [ ] La recuperación selecciona secciones relevantes antes de evaluar: no entrega por defecto el
  reglamento completo al runtime narrativo ni al proveedor de modelo.
- [ ] El sistema admite un corpus externo aprobado o ausencia explícita `ABSENT`, sin inventar
  mecánicas ni representar desconocidos como cero.
- [ ] Los paquetes de mundo/sistema no contienen texto de lore/reglas ni datos estructurados
  derivados; las fixtures de tests también son temáticamente neutras.
- [ ] Paquetes son inmutables durante una ejecución; memoria y estado operativo se escriben fuera.
- [ ] La memoria dinámica, configuración efectiva, autorizaciones y datos operativos permanecen
  fuera del repo; dentro solo existen schemas y ejemplos sin valores reales.
- [ ] Lectura de plataforma se limita a un alcance autorizado y devuelve completitud e identidad
  verificadas o un error; nunca una falsa ausencia de novedades.
- [ ] Capturas/revisiones son idempotentes y preservan baseline, correcciones e historial.
- [ ] El runtime recupera fases independientemente, evita duplicados y permanece silencioso sin
  trabajo.
- [ ] Discord, scheduler, proveedor de modelo, almacenamiento y navegador son opcionales y
  reemplazables; asimilación manual, consultas y tests funcionan sin modelo.
- [ ] Existe `PublicationPort`, pero ningún adaptador lo implementa y ninguna prueba realiza
  publicación real.
- [ ] Las pruebas normales no usan red, cuentas, secretos, navegador real, Discord ni modelos.
- [ ] `reference/migration-source/` no se modifica ni se usa como ruta operativa.

## Plan de implementación

### Incremento 1 — procedencia y estados de revisión genéricos (detallado)

Objetivo: fijar la invariante más crítica antes de migrar contenido o infraestructura. No conectar
foro, modelo, SQLite ni paquetes Naruto.

1. [x] No crear `pyproject.toml`: el incremento no construye ni instala un paquete. Crear
   `core/__init__.py`, `core/memory/__init__.py`, `core/memory/provenance.py`,
   `core/review/__init__.py` y `core/review/models.py`. Los `__init__.py` solo exponen la API pública
   necesaria y no ejecutan I/O.
2. [x] En `core/memory/provenance.py`, implementar con `@dataclass(frozen=True, slots=True)` un
   `SourceRef` con
   `source_id: str`, `locator: str`, `sha256: str | None = None`,
   `section_or_passage: str | None = None`, `observed_at: datetime | None = None` e
   `ic_date: str | None = None`. Validar en `__post_init__`: los dos primeros no vacíos; opcionales
   textuales no vacíos cuando existen; SHA-256 de 64 hexadecimales; `observed_at` con zona horaria.
   No inferir ni copiar un valor entre `observed_at` e `ic_date`.
3. [x] En `core/review/models.py`, importar `SourceRef` de `core.memory.provenance` y definir enums
   `str, Enum` independientes `DraftLifecycle`
   (`ACTIVE`, `STALE`, `RETIRED`), `ReviewStatus` (`PENDING_HUMAN_REVIEW`, `APPROVED`, `REJECTED`)
   y `PublicationStatus` (`NOT_CONFIRMED`, `PUBLISHED`). Definir `DraftVersion` inmutable con
   `draft_id: str`, `version: int`, `content: str`, `source_refs: tuple[SourceRef, ...]`,
   `context_refs: tuple[str, ...]`, los tres estados, `stale_reason: str | None`,
   `review_evidence: SourceRef | None` y `publication_evidence: SourceRef | None`. Defaults:
   `ACTIVE`, `PENDING_HUMAN_REVIEW`, `NOT_CONFIRMED` y evidencias/razón nulas. Validar ID y contenido
   no vacíos, versión positiva, al menos una fuente, referencias de contexto no vacías y coherencia
   de evidencia con el estado. No incluir campo `canon` ni estado de resultados en esta clase.
4. [x] Añadir `ReviewStateError(ValueError)` y estas funciones puras, implementadas con
   `dataclasses.replace`: `approve(draft, expected_version, evidence)`,
   `reject(draft, expected_version, evidence)`, `mark_stale(draft, reason)`, `retire(draft)` y
   `confirm_publication(draft, expected_version, evidence)`. Aprobar/rechazar solo cambia revisión;
   `mark_stale` exige razón y no cambia revisión/publicación; retirar solo cambia ciclo de vida;
   confirmar publicación solo cambia publicación. Toda función con `expected_version` debe fallar
   si no coincide. Confirmar publicación no crea memoria/canon ni confirma resultados ajenos. No
   exigir aprobación previa para registrar una publicación expresamente acreditada: el legado
   permite importar un texto ya publicado sin confirmación redundante.
5. [x] Crear `tests/__init__.py`, `tests/test_provenance.py` y `tests/test_review_models.py`. Importar
   directamente desde `core.memory.provenance` y `core.review.models`. Cubrir: separación de fecha
   observada/IC; rechazo de hash/versión inválidos; aprobación no publica; publicación no cambia
   revisión ni crea canon; STALE conserva una aprobación previa; retiro conserva contenido e
   historial; toda decisión exige versión exacta y evidencia; los tres ejes pueden coexistir.
6. [x] No crear todavía paquetes Nozomu, persistencia, CLI, adaptadores o integraciones. No copiar
   archivos del legado.

Criterios de aceptación del incremento 1:

- Solo usa biblioteca estándar y no realiza I/O fuera de la carga de tests.
- `core/` no contiene literales `Nozomu`, `Naruto`, `Jcink`, `narutorol`, `275`
  ni `account 59`.
- No existe método `approve_and_publish`, `publish_and_canonize` ni transición implícita análoga.
- Las pruebas demuestran los estados ortogonales y pasan en Python 3.11+.
- Los tests importan `core` desde la raíz sin instalación y sin alterar `PYTHONPATH`.
- No cambia ningún archivo bajo `reference/`.

Cómo verificar el incremento 1 desde PowerShell:

```powershell
py -3.11 -B -m unittest discover -s tests -v
rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core
git diff --check
git status --short
```

El segundo comando debe terminar sin coincidencias. `git status --short` debe mostrar únicamente
los archivos enumerados para el incremento, además de `ANALISIS.md` ya existente; ninguna ruta
`reference/` modificada.

### Incrementos siguientes

### Incremento 2 — manifiestos y loader de paquetes (detallado)

Objetivo: fijar el envoltorio común y comprobar dependencias sin definir payloads de dominio ni
puertos. Este incremento no asimila fuentes, no crea perfil de personaje, no usa modelo y no carga
reglas/lore. Los puertos del antiguo incremento 2 se dividen en incrementos posteriores.

1. [x] Crear `core/runtime/__init__.py` y `core/runtime/packages.py`. El `__init__.py` expone solo la
   API pública indicada abajo y no ejecuta I/O. No crear `pyproject.toml`: se sigue importando
   `core` desde la raíz con `py -3.11 -B -m unittest`; no modificar `sys.path` ni `PYTHONPATH`.
2. [x] En `core/runtime/packages.py`, implementar únicamente con biblioteca estándar:
   - `PackageType(str, Enum)`: `CHARACTER="character"`, `WORLD="world"`, `SYSTEM="system"`.
   - `PackageDependency` inmutable (`package_type: PackageType`, `package_id: str`,
     `version: str`).
   - `PackageManifest` inmutable (`schema_version: int`, `package_type: PackageType`,
     `package_id: str`, `display_name: str`, `version: str`,
     `requires: tuple[PackageDependency, ...]`).
   - `LoadedPackageManifest` inmutable (`manifest: PackageManifest`, `package_dir: Path`,
     `source_ref: SourceRef`).
   - `PackageManifestError(ValueError)`; todas las entradas/formas inválidas y dependencias no
     resolubles usan esta excepción, conservando el error original como `__cause__` cuando proceda.
   - Firmas públicas exactas:
     `parse_manifest(data: object) -> PackageManifest`,
     `load_manifest(package_dir: Path, *, expected_type: PackageType | None = None) -> LoadedPackageManifest`
     y
     `load_package_set(packages_root: Path) -> tuple[LoadedPackageManifest, ...]`.
3. [x] El único formato aceptado para `manifest.json` v1 es (el orden de claves no es semántico):

   ```json
   {
     "schema_version": 1,
     "package_type": "character",
     "package_id": "example-character",
     "display_name": "Example Character",
     "version": "1.0.0",
     "requires": [
       {"package_type": "world", "package_id": "example-world", "version": "1.0.0"},
       {"package_type": "system", "package_id": "example-system", "version": "1.0.0"}
     ]
   }
   ```

   Reglas de validación: objeto raíz y claves exactamente iguales a las seis anteriores; versión de
   schema entero `1` (rechazar `true`); enum conocido; `package_id` ASCII en minúsculas con patrón
   `[a-z0-9]+(?:-[a-z0-9]+)*`; `display_name` y `version` son texto no vacío sin espacios exteriores.
   `version` es opaca y se compara literalmente: no imponer SemVer porque el legado no lo respalda.
   `requires` debe ser lista; cada elemento tiene exactamente `package_type`, `package_id` y
   `version`, con las mismas validaciones. Rechazar dependencia a sí mismo y duplicados por
   `(package_type, package_id)`. Convertir listas válidas a tuplas; no mutar la entrada.
4. [x] `load_manifest` lee exclusivamente `<package_dir>/manifest.json`: directorio y archivo
   regulares, no symlinks; UTF-8 estricto; máximo 65.536 bytes **[P]**; JSON con claves duplicadas
   rechazadas. Debe comprobar que `package_id == package_dir.name` y, si se indicó,
   `package_type is expected_type`. Construir `SourceRef` ya existente con
   `source_id="package-manifest:<type>:<id>:<version>"`, `locator` igual a la ruta del manifest y
   SHA-256 de los bytes exactos; dejar `section_or_passage`, `observed_at` e `ic_date` en `None`.
   No modificar `SourceRef` ni fabricar una fecha observada.
5. [x] `load_package_set` solo descubre hijos directos `*/manifest.json` bajo las categorías fijas
   `characters`, `worlds` y `systems` (las categorías pueden estar vacías). Debe comprobar tipo contra
   categoría, ID contra directorio, unicidad `(type, id)`, existencia de cada dependencia con la
   versión literal pedida y ausencia de ciclos. Devuelve orden topológico determinista —dependencias
   antes que dependientes; empates por `(package_type.value, package_id, version)`—. Rechaza una
   categoría desconocida que contenga manifests; ignora archivos auxiliares que no sean manifests y
   no carga ningún payload.
6. [x] Crear solo estos manifiestos reales, todos con `schema_version: 1` y `version: "0.1.0"`:
   - `packages/characters/nozomu/manifest.json`: tipo `character`, nombre `Nozomu`, requiere mundo
     `naruto-rol` y sistema `naruto-rol` versión `0.1.0`.
   - `packages/worlds/naruto-rol/manifest.json`: tipo `world`, nombre `Naruto Rol`, `requires: []`.
   - `packages/systems/naruto-rol/manifest.json`: tipo `system`, nombre `Naruto Rol`, `requires: []`.

   No crear otros archivos bajo esas tres carpetas: estos nombres son identidad/dependencia, no
   incorporan reglas, lore, fórmulas, tablas, rangos ni ficha mecánica.
7. [x] Crear fixtures temáticamente neutras en
   `tests/fixtures/packages/valid/{characters/example-character,worlds/example-world,systems/example-system}/manifest.json`.
   Las versiones son `1.0.0`; el personaje requiere los otros dos; mundo y sistema no requieren
   nada. No añadir prosa ni datos mecánicos. Los escenarios inválidos se generan en
   `tempfile.TemporaryDirectory()` durante los tests, no como más fixtures versionadas.
8. [x] Crear `tests/test_package_manifest.py`. Cubrir objeto/claves/tipos, `true` como schema,
   enums, IDs, textos vacíos/con espacios, `requires` no lista, objeto de dependencia con claves
   desconocidas, autorreferencia y duplicado; confirmar tuplas, inmutabilidad y versión opaca.
9. [x] Crear `tests/test_package_loader.py`. Cubrir carga/hash `SourceRef` sin fechas inventadas,
   UTF-8 inválido, JSON mal formado o con clave duplicada, límite de tamaño, ID/directorio y
   tipo/categoría discordantes. Cargar fixture y `packages/` reales; comprobar orden topológico.
   Cubrir dependencia ausente, versión incompatible, categoría desconocida y
   ciclo. Ningún test usa red, modelo, navegador, SQLite ni escribe fuera del temporal del sistema.
10. [x] No crear todavía payloads de personaje/mundo/sistema, `ports.py`, adaptadores,
    configuración, repositorios ni integración alguna. No tocar `SourceRef`, `DraftVersion`, sus
    exports o las 37 pruebas aprobadas del incremento 1.

Criterios de aceptación del incremento 2:

- La suite completa pasa con `py -3.11`; los imports funcionan desde la raíz sin instalación.
- Los tres manifests reales solo contienen las seis claves del contrato y no incorporan contenido
  derivado; los fixtures no contienen nombres o conceptos del legado.
- Toda dependencia se resuelve por tipo+ID+versión exacta antes de devolver el conjunto, en orden
  determinista; un grafo parcial, incompatible o cíclico falla cerrado.
- Cada manifest cargado tiene un `SourceRef` con hash reproducible y sin confundir importación con
  fecha IC; no se modifica el contrato del incremento 1.
- El diff del incremento solo añade las rutas enumeradas y actualiza `ANALISIS.md`; no cambia
  `reference/`, no añade dependencias y no define ningún puerto ni publicación.

Cómo verificar el incremento 2 desde PowerShell:

```powershell
py -3.11 -B -m unittest tests.test_package_manifest tests.test_package_loader -v
py -3.11 -B -m unittest discover -s tests -v
rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core tests/fixtures/packages
git diff --check
git diff --name-only 17d83e1 -- reference
git status --short
```

El tercer comando debe terminar sin coincidencias y el quinto sin salida. La aparición de los
nombres específicos bajo `packages/` es intencional; nunca bajo `core/` ni fixtures genéricas.

### Incremento 3 — contrato y carga del expediente (siguiente; detallado)

Objetivo: fijar la entrada humana del nuevo flujo y detectar faltantes sin crear todavía corpus,
instancia, CLI, personaje ni estados de asimilación. Es un incremento de lectura/validación, sin
modelo, red, SQLite ni escritura fuera de temporales de tests.

1. [x] Crear `core/runtime/assimilation.py`. Actualizar `core/runtime/__init__.py` para reexportar
   solo la API pública nueva, conservando todos los exports del incremento 2. No modificar
   `core/memory/provenance.py`, `core/review/models.py` ni `core/runtime/packages.py`.
2. [x] Definir `DossierSection(str, Enum)` con valores exactos `forum_rules`, `setting`,
   `character_creation`, `staff_review`, `platform_format`, `combat_system` y
   `ability_technique_creation`; y `DossierSectionStatus(str, Enum)` con valores internos
   `PROVIDED`, `MISSING` y `NOT_APPLICABLE`. Las cinco primeras forman la constante pública
   `REQUIRED_SECTIONS`; las dos últimas, `OPTIONAL_SECTIONS`; ambas son tuplas en el orden anterior.
   Los marcadores Markdown mapean exactamente ausencia→`PROVIDED`, `FALTA`→`MISSING` y
   `NO APLICA`→`NOT_APPLICABLE`.
3. [x] Implementar dataclasses inmutables con `slots=True`:
   - `DossierSourceSpec(source_id: str, version: str, authority: str, scope: str,
     effective_from: date | None, effective_until: date | None,
     section_or_passage: str | None, path: str | None, inline_text: str | None)`.
   - `DossierSectionSpec(section: DossierSection, status: DossierSectionStatus,
     notes: str | None, sources: tuple[DossierSourceSpec, ...])`.
   - `LooseMaterialSpec(source: DossierSourceSpec,
     suggested_sections: tuple[DossierSection, ...])`.
   - `ForumDossier(schema_version: int, forum_id: str, display_name: str,
     dossier_version: str, sections: tuple[DossierSectionSpec, ...],
     loose_material: tuple[LooseMaterialSpec, ...])`.
   - `LoadedDossierSource(spec: DossierSourceSpec, literal_text: str,
     source_ref: SourceRef)`, `LoadedDossierSection(spec: DossierSectionSpec,
     sources: tuple[LoadedDossierSource, ...])`, `LoadedLooseMaterial(spec: LooseMaterialSpec,
     source: LoadedDossierSource)` y `LoadedForumDossier(dossier: ForumDossier,
     dossier_path: Path, sections: tuple[LoadedDossierSection, ...],
     loose_material: tuple[LoadedLooseMaterial, ...])`.
   - `DossierAssessment(missing_required: tuple[DossierSection, ...],
     missing_optional: tuple[DossierSection, ...], ready_for_assimilation: bool)`.
     `ready_for_assimilation` es verdadero solo si no falta ninguna obligatoria; una opcional
     `MISSING` se informa pero no bloquea por sí sola. Los constructores validan las mismas
     invariantes que el parser para que la API Python no pueda crear un expediente incoherente;
     en particular, `inline_text` ya es canónico y rechaza cualquier `\r`.
4. [x] Añadir `DOSSIER_NAME = "expediente.md"`, `DOSSIER_SCHEMA_VERSION = 1` y
   `DossierError(ValueError)`. Su constructor exacto es
   `DossierError(locator: str, line: int | None, reason: str)`; expone esos tres atributos y el
   número de línea es base 1. El mensaje es `<locator>:<line>: <reason>` o
   `<locator>: <reason>` si no hay línea. Toda forma,
   tipo, estructura, ruta o lectura inválida usa esta excepción y conserva `__cause__` cuando
   envuelve un error. Exponer firmas exactas
   `parse_dossier(text: str, *, locator: str = "expediente.md") -> ForumDossier`,
   `load_dossier(dossier_dir: Path) -> LoadedForumDossier` y
   `assess_dossier(dossier: ForumDossier) -> DossierAssessment`. Reexportar constantes, enums,
   dataclasses, error y funciones anteriores desde `core/runtime/__init__.py`. Ninguna función
   aprueba, interpreta, indexa ni persiste fuentes.
5. [x] Implementar `parse_dossier` como máquina de estados determinista de biblioteca estándar,
   no como parser Markdown general. Aplicar literalmente la gramática de «Plantilla de expediente
   del foro»: cabecera contigua de cuatro líneas; ocho encabezados fijos españoles, únicos y en
   orden; `### Fuente` solo dentro de una sección; estado antes de nota/fuentes; y solo líneas
   vacías fuera de esa estructura. Todo encabezado o texto desconocido falla. Guardar internamente
   la línea de cada ocurrencia para que validaciones posteriores informen la declaración culpable,
   sin añadir ese detalle de parser a las dataclasses públicas.
6. [x] Antes del parseo, exigir `str`, rechazar BOM, convertir CRLF a LF y rechazar CR solitario.
   Validar `forum_id` con `[a-z0-9]+(?:-[a-z0-9]+)*`; nombre y versión son no vacíos sin espacios
   exteriores. Las siete secciones se convierten en `DossierSectionSpec` en orden fijo; material
   suelto solo alimenta `LooseMaterialSpec`. Una obligatoria no admite `NO APLICA`; una aportada
   exige fuentes y `FALTA`/`NO APLICA` las prohíben; material suelto acepta cero o más fuentes, sin
   estado ni nota.
7. [x] Parsear `Metadatos:` como pares `clave=<json>` en cualquier orden usando
   `json.JSONDecoder.raw_decode` para cada valor y exigiendo después ` | ` o fin de línea. No usar
   `split`; rechazar caracteres de control decodificados y envolver `JSONDecodeError` o
   `RecursionError`. Admitir solo las nueve claves documentadas, cada una una vez; exigir `id`,
   `versión`, `autoridad` y `alcance`. Proyectar el mapa validado al orden fijo del modelo. Omitir
   `desde`, `hasta`, `pasaje` o `archivo` produce `None`; omitir `sugerencias` produce `()`. Validar
   strings obligatorios, fechas ISO y su orden, pasaje y ruta por tipo. `sugerencias` solo puede
   aparecer en material suelto y allí admite nombres españoles exactos de las siete secciones, sin
   repetición; su mera aparición en una sección de dominio es error, aunque sea `[]`. `version`
   sigue siendo opaca. Clave desconocida/repetida/ausente, tipo, separador o texto restante
   inválidos indican línea y causa.
8. [x] Inferir el origen sin flag: `archivo` string significa fuente de archivo; `archivo` omitido
   o `null`, fuente en línea. En el segundo caso exigir en la línea física inmediatamente siguiente
   un cerco de `N >= 4` virgulillas con apertura `~{N} texto` y cierre `~{N}` exacto, ambos sin
   espacios adicionales. En el primero, una apertura de valla inmediatamente posterior es error y
   no se consume cuerpo. Capturar sin interpretar todo el literal; validar que `N` es mayor que
   cualquier racha de `~` contenida en él. El literal canónico incluye todos los bytes UTF-8 entre
   el LF tras la apertura y el inicio del cierre, incluido el LF final, sin trim. Fuentes vacías,
   cierre ausente o contenido que colisiona con la valla fallan cerrado; el literal debe contener
   al menos un carácter no blanco. `#`, listas, tablas y fences internos no alteran el parser.
9. [x] `load_dossier` lee solo `<dossier_dir>/expediente.md` como bytes y decodifica UTF-8 estricto
   antes de normalizar; directorio y documento deben ser regulares y no symlinks, y se rechaza BOM.
   Para cada `archivo`, rechazar
   `\`, ruta vacía/absoluta/UNC/con unidad, segmentos vacíos, `.`/`..` y cualquier componente
   symlink; el archivo regular resuelto debe permanecer bajo `dossier_dir`. Leerlo como UTF-8
   estricto, conservar y hashear sus bytes exactos sin normalizar EOL. Las rutas de fuente se
   expresan con `/` en Markdown.
10. [x] Crear cada `SourceRef` con id/pasaje declarados, sin `observed_at` ni `ic_date`. Para archivo,
    usar SHA-256 de bytes exactos y locator de la ruta resuelta en POSIX. Para inline, usar SHA-256
    de los bytes UTF-8 canónicos y locator
    `<expediente.md>#inline:id=<quote(id)>&version=<quote(version)>`, donde ambos valores usan
    `urllib.parse.quote(value, safe="")` y la ruta del expediente conserva el mismo criterio
    relativo/absoluto recibido por el loader. Editar cabecera, nota u otra fuente no cambia hash ni
    locator de esa fuente inline.
11. [x] Al cargar, repetir `(source_id, version)` exige autoridad, alcance, vigencia, tipo/origen y
    hash idénticos; `section_or_passage` y las sugerencias de la ocurrencia pueden variar. El mismo
    id con versiones distintas permanece separado. La versión, autoridad, alcance y vigencia viven
    en `DossierSourceSpec`; no ampliar `SourceRef`, escoger vigencia ni inferir supersesión.
12. [x] Crear `core/runtime/templates/expediente.template.md`, válida y copiable: cabecera neutra,
    las cinco obligatorias y dos opcionales con `Estado: FALTA`, notas breves de qué aportar, y
    `## Material suelto` vacío. Una `Nota:` remite a la guía adyacente. Crear también
    `core/runtime/templates/LEEME-expediente.md`, que no se parsea como expediente y muestra
    ejemplos completos copiables de archivo e inline, claves opcionales/omisiones, `sugerencias`
    solo para material suelto y selección de una valla mayor que cualquier racha de `~` del
    literal. La plantilla no contiene comentarios HTML, reglas/lore, rutas reales ni fuentes
    ficticias. No crear todavía plantillas de instancia o instrucciones.
13. [x] Crear exactamente la fixture neutra
    `tests/fixtures/dossiers/minimal-neutral/expediente.md` y sus fuentes
    `materials/manual-foro.md` y `materials/material-suelto.md`. Las cinco obligatorias están
    aportadas, combate y técnicas usan
    `NO APLICA`, se repite coherentemente una fuente/versión con pasajes distintos y material suelto
    incluye archivo e inline, con el origen inferido; omite al menos una clave opcional y usa orden
    no canónico en otra fuente. Al menos un inline contiene `#`/`##`, lista, tabla, fence de
    backticks y una línea `~~~~`; su valla externa usa cinco o más `~`, demostrando cómo escapar el
    propio delimitador por longitud. No usar nombres ni conceptos del legado.
14. [x] Crear `tests/test_forum_dossier.py`. Cubrir: dataclasses/tuplas inmutables; template válida
    pero no lista; fixture lista; cabecera, orden/unicidad/grafía y encabezados desconocidos;
    estados/notas/fuentes; metadata en órdenes distintos con igual resultado; claves obligatorias,
    omisiones y valores por defecto; claves desconocidas/repetidas; separadores, JSON, tipos, null
    y fechas; `sugerencias` omitida/permitida en material suelto y rechazada en dominio incluso
    como `[]`; `archivo` string sin valla y omitido/`null` con valla inmediata; errores de valla tras
    archivo o valla ausente tras inline; fences variables/colisionados; literal con Markdown
    preservado y LF final; igualdad de literal/hash entre documento LF y CRLF; rechazo de CR
    solitario/BOM; hash/locator inline invariables al editar otra parte; bytes/EOL exactos de
    archivo; ruta
    absoluta, unidad/UNC, backslash, traversal y symlink; repetición coherente/incoherente y
    versiones distintas; diagnóstico separado de secciones; y `DossierError` con locator, línea y
    causa útil. Los casos inválidos usan `TemporaryDirectory()`; un test de symlink solo se omite si
    el SO niega crearlo y documenta el motivo.
15. [x] No crear `adapters/`, CLI, configuración de instancia, candidatos, aprobaciones, índice,
    payloads de paquete, personaje ni repositorio. No tocar `reference/` ni las notas cerradas de
    los incrementos 1–2.

Criterios de aceptación del incremento 3:

- La plantilla Markdown muestra todos los faltantes sin fingir contenido; el LEEME enseña ambos
  orígenes sin formar parte del documento válido, y la fixture neutra carga y queda lista aunque
  declare que no usa combate/técnicas.
- La línea de metadatos acepta cualquier orden con claves únicas, materializa los valores por
  defecto documentados e infiere el origen sin un flag redundante.
- La estructura dentro de un literal inline nunca se interpreta como estructura del expediente;
  la valla variable admite el delimitador corto en el propio reglamento.
- LF y CRLF del mismo `expediente.md` producen el mismo texto/hash inline; no se recorta ningún
  byte canónico y editar otra zona no cambia su locator. Los archivos externos se hashean tal cual.
- Ninguna ruta puede escapar del expediente ni atravesar symlinks; toda fuente cargada produce un
  `SourceRef` sin fechas inventadas, y cada error manual identifica locator, línea y causa.
- Material suelto y varias fuentes se aceptan, pero no se clasifican, aprueban ni vuelven
  consultables; este incremento no escribe una instancia.
- La suite completa sigue pasando con Python 3.11, sin instalación, red, modelo ni dependencias.

Verificación exacta desde PowerShell:

```powershell
py -3.11 -B -m unittest tests.test_forum_dossier -v
py -3.11 -B -m unittest discover -s tests -v
rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/runtime/assimilation.py core/runtime/templates tests/fixtures/dossiers
git diff --check
git diff --name-only e4da791 -- reference
git status --short
```

El tercer comando termina sin coincidencias y el quinto sin salida. El estado solo debe incluir
`ANALISIS.md` y los archivos enumerados para el incremento 3.

### Incrementos posteriores

4. [ ] **Rebanada vertical neutra, manual y sin modelo.** Añadir modelos mínimos de candidato citado
   y decisión humana en `assimilation.py`, `core/runtime/cli.py`, `adapters/manual.py` y plantillas
   de instancia. `instance init` exige `--output`; genera ambos `AGENTS.md`/`CLAUDE.md` desde una
   política común y un test compara sus bloques invariantes. Recorrer en un temporal:
   `expediente.md` neutro → literales/candidatos manuales → aprobación exacta → carpeta externa →
   concepto del usuario → propuesta aceptada/rechazada → ficha `DraftVersion` pendiente de staff.
   Criterio: sin `--output` o con destino dentro del repo/no vacío falla sin escribir; reiniciar es
   idempotente, solo se usa lo aprobado, no hay publicación y las barreras dependen del core.
5. [ ] **Asimilación completa y recuperación dirigida.** Añadir versiones/supersesión, vigencia,
   índice determinista y contratos `core/rules`/`core/world`, incluido `ABSENT`. Criterio:
   pendiente/rechazado no es consultable, conflictos devuelven `REQUIERE CONFIRMACIÓN` y la consulta
   entrega solo pasajes pertinentes con cita.
6. [ ] **Creación de personajes completa.** Implementar `core/character`, varias fichas por
   instancia, propuestas versionadas y ejes separados de staff/aprendizaje/utilizabilidad.
   Criterio: el agente nunca origina el concepto ni incorpora una propuesta sin aceptación, y una
   aprobación no implica aprendizaje, uso, publicación o canon.
7. [ ] **Memoria y narrativa.** Añadir puertos/repositorio en memoria, eventos con procedencia,
   correcciones por anotación y `core/runtime/narrative.py` con `PublicationPort` solo como contrato.
   Criterio: OOC/pensamiento/resultado pendiente no sale como hecho; ningún adaptador publica.
8. [ ] **Seguimiento y adaptador manual completo.** Añadir `core/runtime/tracking.py`, `ForumReader`
   y capturas locales al adaptador manual. Criterio: baseline, A→B→A y lecturas incompletas se
   comportan de forma conservadora; los borradores solo se exportan a un outbox local.
9. [ ] **Persistencia SQLite y runtime de un ciclo.** Persistir corpus, memoria y operación solo en
   la instancia; añadir schema/ejemplo de configuración en `core/runtime` y puertos de reloj/lock.
   Criterio: reinicio/concurrencia no duplican trabajo y un fallo tardío no revierte fases previas.
10. [ ] **Primer caso real: Nozomu / Naruto Rol.** Migrar por el mismo expediente/CLI, sin ramas
    específicas; mundo/sistema siguen manifest-only y toda ficha mecánica queda versionada en la
    instancia, no en `packages/characters/nozomu`. Criterio: no entra regla/lore/derivado o dato
    mecánico en paquetes y una propuesta no figura como aprendida/utilizable/canon.
11. [ ] **Evaluador técnico genérico.** Consumir solo corpus aprobado y snapshots por escena; crear
    especialista de combate solo si la instancia lo requiere. Criterio: ausencias siguen
    desconocidas y cada fórmula/unidad calculada tiene cita.
12. [ ] **Adaptador Jcink offline.** Extraer selectores, paginación y autenticación detrás de
    `ForumReader` con fixtures saneadas. Criterio: core no requiere Playwright, identidad/completitud
    dudosa falla cerrada y Jcink no implementa `PublicationPort`.
13. [ ] **Modelo e integraciones opcionales.** Añadir `ModelProvider` y, uno por vez, Codex CLI,
    Discord y scheduler Windows. Criterio: los candidatos del modelo siguen pendientes; deshabilitar
    integraciones no afecta el core y secretos/configuración efectiva permanecen externos.
14. [ ] **Segundo caso y paridad final.** Elegirlo entonces y ejecutar paridad con fixtures legacy
    saneadas. Criterio: otro foro/tema entra por expediente e instancia sin modificar el core para
    nombres, voz, temática o mecánicas concretas.

## Cómo verificarlo

- Test / comando general futuro: `py -3.11 -B -m unittest discover -s tests -v`, sin red ni
  servicios y sin instalar el proyecto.
- Comprobaciones estáticas: `rg` de nombres/IDs específicos dentro del core; imports del core sin
  Playwright/Discord/Windows; `git diff --check`; ausencia de cambios en `reference/`.
- Contract tests: paquetes, corpus/versiones/revisión, repositorios, `ForumReader`, proveedor de
  modelo, notificador, scheduler y reloj/locks con dobles locales.
- Paridad: snapshots saneados y eventos legacy seleccionados deben reproducir cambios, estados y
  límites semánticos, no texto generativo literal.
- Comprobación manual posterior y separada: solo con autorización expresa, entorno externo y plan
  revisado para foro/Discord/modelo; nunca forma parte de la suite normal.

## Riesgos y dudas abiertas

Las decisiones de formato, instrucciones, ruta de instancia y ficha mecánica están cerradas y no
bloquean los incrementos 3–13. Solo sigue abierta una decisión futura:

1. **Antes del incremento 14: ¿cuándo y cómo elegir el segundo caso de generalidad?**
   - A: mantener la elección aplazada y, al llegar al incremento 14, escoger un foro real no Naruto
     que contraste mecánicas/plataforma con el primero. **Recomendación:** A; evita diseñar ahora
     contra un caso hipotético y conserva la decisión previa.
   - B: fijar ya otro foro real; da un objetivo temprano, pero puede sesgar el core antes de validar
     la rebanada vertical y exige que el usuario aporte su expediente.
   - C: usar solo un segundo expediente sintético; es reproducible, pero demuestra menos
     generalidad de producto que un caso real aportado por el usuario.

---
## Notas de implementación (las rellena Claude)
- Rama: `feature/incremento-1-procedencia-revision` (base `96eca81`).
- Cambios hechos (incremento 1): `core/__init__.py`, `core/memory/{__init__,provenance}.py`,
  `core/review/{__init__,models}.py`, `tests/{__init__,test_provenance,test_review_models}.py`.
- Resultado de los tests: `py -3.11 -B -m unittest discover -s tests -v` → 37 OK tras las
  correcciones de REV1-01..03 (34 antes; también 37 OK con `py -3.14`). `rg` de nombres
  específicos en `core/` sin coincidencias; `git diff --check`
  limpio; ningún cambio en `reference/`.
- Desviaciones del plan y motivo: ninguna. Decisiones de detalle que el plan no fijaba:
  - `sha256` acepta mayúsculas o minúsculas (el legado usa mayúsculas, salida de
    `Get-FileHash`) y se guarda en minúsculas como forma canónica (REV1-01).
  - `context_refs` puede ser una tupla vacía (borrador manual sin contexto); cada elemento debe ser
    texto no vacío. `source_refs` sí exige al menos una.
  - Coherencia: `ACTIVE` sin `stale_reason`; `STALE` la exige; `RETIRED` la conserva si venía de
    `STALE`. Revisión pendiente ⇔ sin evidencia; publicación no confirmada ⇔ sin evidencia.
  - `approve`/`reject` exigen `PENDING_HUMAN_REVIEW` y la decisión es definitiva para esa versión
    (una rectificación futura exigirá una transición de supersesión explícita). Se registran en
    cualquier ciclo de vida: la decisión es un hecho sobre la versión y la vigencia la indica el
    eje de ciclo de vida, de modo que el resultado no depende del orden (REV1-02).
  - `mark_stale` solo desde `ACTIVE` (como el legado); `retire` desde `ACTIVE` o `STALE`, una vez.
  - `confirm_publication` se acepta en cualquier ciclo de vida y estado de revisión, una sola vez:
    la publicación es un hecho externo (texto ya publicado puede importarse sin aprobación).
  - Errores de campo → `ValueError`; incoherencia de estado o transición inválida →
    `ReviewStateError` (subclase de `ValueError`).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE; costes con tarifa =
  ESTIMACIÓN): modelo e ids de sesión; entrada, salida, lectura/escritura de caché (incrementos de
  esta tarea, no acumulados); invocaciones, errores, cancelaciones, verificaciones; retrabajo.
  - Revisión del incremento 1: veredicto inicial «requiere cambios» (REV1-01 media, REV1-02 media,
    REV1-03 baja); los tres se corrigieron juntos y la verificación los dio por resueltos
    (aprobado). Informe archivado en `docs/analisis/incremento-1-revision.md`.
  - Codex (`gpt-5.6-sol`, esfuerzo high; contadores finales de `~/.codex/sessions`, por hilo):
    - Análisis `01a12b0d-feb3-7ab1-b25e-2acea0a35df6` (2 encargos: análisis + decisiones del
      usuario): entrada 6.434.447 (caché leída 6.218.112), salida 38.999 (razonamiento 11.281).
    - Revisión `01a12b24-57e1-75a3-9a61-ab82bbeaf456` (2 encargos: revisión + verificación):
      entrada 992.302 (caché leída 914.432), salida 13.492 (razonamiento 6.795).
    - Escritura de caché: 0 en ambos. Llamadas al modelo dentro de cada encargo: NO DISPONIBLE.
      Errores/cancelaciones: 0. Coste o cuota: NO DISPONIBLE (suscripción ChatGPT).
    - Fuera de la tarea: prueba de conexión `01a12b0a-…` (entrada 13.501, salida 47).
  - Claude (`claude-opus-5-5`, sesión `076da56b-f3ec-4486-814a-781484ee0946`, transcript desde el
    encargo de esta tarea; 28 respuestas de API): entrada 56, salida 38.860, caché leída 4.071.815,
    caché escrita 90.043. Coste: NO DISPONIBLE.
  - Retrabajo: una ronda de correcciones (3 hallazgos); corrección del recuento de tests en estas
    notas (39 → 37).

### Incremento 2 — manifiestos y loader de paquetes
- Rama: `feature/incremento-2-paquetes-puertos` (base `17d83e1`).
- Cambios hechos: `core/runtime/{__init__,packages}.py`; `packages/{characters/nozomu,
  worlds/naruto-rol,systems/naruto-rol}/manifest.json` (solo las seis claves);
  `tests/fixtures/packages/valid/{characters/example-character,worlds/example-world,
  systems/example-system}/manifest.json`; `tests/test_package_{manifest,loader}.py`.
- Resultado de los tests: `py -3.11 -B -m unittest tests.test_package_manifest
  tests.test_package_loader` → 42 OK; suite completa → 79 OK en `py -3.11` y `py -3.14` (el test
  de symlink se ejecutó, no se omitió). `rg` en `core` y fixtures sin coincidencias; sin cambios en
  `reference/` desde `17d83e1`; `git diff --check` limpio.
- Revisión de Codex: «requiere cambios» (REV2-01..03 media, REV2-04..05 baja); corregidos juntos:
  - REV2-01: todo directorio dentro de una categoría es un paquete y exige `manifest.json`;
    los archivos sueltos se siguen ignorando.
  - REV2-02: cualquier directorio desconocido bajo la raíz con un `manifest.json` a cualquier
    profundidad (sin seguir symlinks) falla.
  - Symlinks (REV2-01/05): se rechaza cualquier symlink, incluso roto, como hijo directo de la
    raíz (categorías) o de una categoría (paquetes); no se siguen nunca.
  - REV2-03: `.gitattributes` con `eol=lf` para manifests reales y fixtures (desviación del plan
    pedida por la revisión); `git check-attr eol` devuelve `lf`; test de ausencia de CR.
  - REV2-04: `RecursionError` al decodificar se envuelve como `PackageManifestError`
    (reproducido en `py -3.11` con 1.000 niveles).
  - REV2-05: tests de symlink de paquete, categoría y rotos, y de `locator` relativo.
  - Resultado tras las correcciones: 52 tests del incremento y 89 en total, OK en `py -3.11` y
    `py -3.14`, sin tests omitidos.
- Desviaciones del plan: `.gitattributes` (REV2-03). Decisiones de detalle que el plan no fijaba:
  - Una categoría ausente bajo `packages_root` equivale a vacía; los archivos sueltos se ignoran.
    Un directorio desconocido sin manifests (p. ej. documentación) se ignora.
  - UTF-8 estricto rechaza también BOM; las constantes JSON no estándar (`NaN`, `Infinity`) se
    rechazan.
  - `locator` es la ruta del manifest tal como la recibe el loader, en formato POSIX (relativa si
    el llamador pasa una ruta relativa).
  - Añadidos `PackageManifest.key` y las constantes públicas `MANIFEST_NAME`,
    `MAX_MANIFEST_BYTES` y `SCHEMA_VERSION`.
  - Riesgo de finales de línea (`core.autocrlf=true`): resuelto por REV2-03.
- Revisión archivada en `docs/analisis/incremento-2-revision.md` (veredicto final: aprobado).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Análisis `01a12b0d-…` (1 encargo: decisiones nuevas + detalle del incremento 2); incremento
      respecto a la medición del incremento 1: entrada 1.872.131 (caché leída 1.788.032), salida
      25.814 (razonamiento 8.886).
    - Revisión `01a12b36-2178-7933-b30f-91d691f1fbe7` (2 encargos: revisión + verificación):
      entrada 1.364.282 (caché leída 1.266.304), salida 23.920 (razonamiento 15.121).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde el encargo del incremento 2; 23
    respuestas de API): entrada 46, salida 34.752, caché leída 4.997.719, caché escrita 59.446.
    Coste NO DISPONIBLE.
  - Retrabajo: una ronda de correcciones (5 hallazgos); reubicación de dos tests mal colocados y
    normalización de CRLF introducidos por Claude al editar con Python.

### Incremento 3 — contrato y carga del expediente
- Rama: `feature/plan-expediente-foro` (base `e4da791`); incluye el rediseño del plan de Codex.
- Cambios hechos: `core/runtime/assimilation.py`; exports en `core/runtime/__init__.py`;
  `core/runtime/templates/{expediente.template.md,LEEME-expediente.md}`;
  `tests/fixtures/dossiers/minimal-neutral/{expediente.md,materials/manual-foro.md,
  materials/material-suelto.md}`; `tests/test_forum_dossier.py`.
- Resultado de los tests: `tests.test_forum_dossier` → 53 OK; suite completa → 142 OK en
  `py -3.11` y `py -3.14`, sin tests omitidos (los symlinks se crean en este equipo). `rg` de
  términos del legado en el módulo, plantillas y fixtures sin coincidencias; `reference/` sin
  cambios desde `e4da791`; `git diff --check` limpio.
- Revisión de Codex: «requiere cambios» (REV3-01..02 media, REV3-03 baja); corregidos juntos:
  - REV3-01: sugerencias no textuales, errores de conversión de `raw_decode` (p. ej. enteros
    de más de 4.300 dígitos) y textos con sustitutos Unicode aislados dan `DossierError` en la
    línea de `Metadatos:`; los textos y rutas deben poder codificarse en UTF-8.
  - REV3-02: los fallos de E/S al leer o resolver el expediente (locator del documento, sin
    línea) o un material (línea de sus metadatos) y un `dossier_dir` no convertible a ruta se
    envuelven en `DossierError` con `__cause__`.
  - REV3-03: `Estado: NO APLICA` en una obligatoria se señala en la línea `Estado:`; una fuente
    tras `Estado:` se señala en su `### Fuente`.
  - Resultado tras las correcciones: 56 tests del expediente y 145 en total, OK en `py -3.11` y
    `py -3.14`, sin omitidos.
- Desviaciones del plan: ninguna. Decisiones de detalle que el plan no fijaba:
  - Los motivos de error están en español (el expediente se escribe a mano). Los constructores
    lanzan `DossierError` con el nombre de la clase como locator y sin línea; el parser los
    reenvuelve con su locator y la línea de la declaración culpable.
  - `pasaje`, `Nota`, `nombre` y `versión_expediente` siguen la misma regla de texto que los
    metadatos obligatorios: no vacío, sin espacios exteriores ni caracteres de control C0.
  - `archivo` rechaza además `:` en cualquier posición (unidades y flujos alternativos de NTFS)
    y segmentos que terminen en punto o espacio (Windows los recorta al abrir).
  - Locator de una fuente de archivo: `<dossier_dir>/<archivo>` en POSIX con el mismo criterio
    relativo/absoluto que recibe el loader (como en el incremento 2), no la ruta absoluta
    resuelta; la resolución solo se usa para comprobar que no sale del expediente.
  - Riesgo para revisar: en Python 3.11 `is_symlink()` no detecta *junctions* de Windows. Una que
    apunte fuera del expediente se rechaza por la comprobación de ruta resuelta; una que apunte
    dentro no se detecta.
  - Sin límite de tamaño para `expediente.md` ni para los archivos de material (el plan no lo
    fija; los manifests sí lo tienen).
  - Los archivos de material conservan sus bytes tal cual, incluido un BOM si lo tuvieran; solo
    `expediente.md` rechaza BOM.
  - Añadidos `DossierSourceSpec.key` y `ForumDossier.all_sources()`; el ejemplo completo de
    `LEEME-expediente.md` se valida con un test para que la guía no quede desfasada.
  - Mensaje de valla colisionada: indica también la línea de la valla abierta, porque una valla
    sin cerrar en mitad del documento se manifiesta como colisión con la valla siguiente.
- Revisión archivada en `docs/analisis/incremento-3-revision.md` (veredicto final: aprobado).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Rediseño del plan `01a12b46-c70e-7a31-b453-3294a459082e` (3 encargos: flujo de expediente,
      decisiones del usuario y enmienda de metadatos): entrada 6.226.818 (caché leída 6.011.264),
      salida 64.192 (razonamiento 26.494).
    - Revisión `01a12c9a-5399-7ba0-ad21-9444a928ae13` (2 encargos: revisión + verificación):
      entrada 3.085.008 (caché leída 2.947.072), salida 28.013 (razonamiento 15.760).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde la propuesta del flujo por foro; 36
    respuestas de API, incluye el diseño con el usuario): entrada 72, salida 85.372, caché leída
    11.064.747, caché escrita 424.377. Coste NO DISPONIBLE.
  - Retrabajo: una ronda de correcciones (3 hallazgos); cálculos de línea erróneos en tests
    corregidos por Claude antes de la revisión; un script de reemplazo fallido sin efectos.
