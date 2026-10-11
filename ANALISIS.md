# Análisis de tarea

## Tarea

Generalizar Nozomu Agent como `roleplay-agent-core`: un núcleo reutilizable para agentes de
foro de rol, configurable por personaje, mundo, sistema, plataforma e instancia. Este documento
define la extracción y un plan para Claude; no implementa código ni altera el legado.

Versión base de esta continuación: commit `17d83e1` a 2026-10-11, rama
`feature/incremento-2-paquetes-puertos`, creada desde el incremento 1 aprobado y sin cambios al
iniciar este análisis. El commit inicial fue `96eca81`. `reference/migration-source/` es la copia
inmutable inspeccionada. La auditoría anterior se trata como hipótesis histórica porque declara que
su fuente estaba vacía; no se usa como prueba de la implementación actual.

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
- `tests/test_{provenance,review_models}.py` — 37 pruebas aprobadas que el incremento 2 debe conservar.

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
| `instructions/combate.md` | Especialista técnico, cálculo solo con entradas explícitas, cita de reglas, snapshots de escena y salida condicionada (`Instructions`, `Profile`, `Knowledge`, `Respuesta`). | **G:** política de asimilación/consulta en `core/rules` y orquestación en `core/runtime`. **E:** perfil Nozomu es candidato a paquete de personaje o estado externo, pendiente de decisión; reglas Naruto no se empaquetan. |
| `forum_watch/README.md` | Identidad de tema, baseline, captura completa, revisiones A→B→A, rechazo de desapariciones/reordenación, transacciones y concurrencia (`Registro`, `Contrato`, `Normalización`, `Persistencia`). | **G:** `core/runtime/tracking.py` y puertos internos. **E:** URL/host/cuenta a `adapters/jcink` y configuración de instancia. |
| `forum_watch/READER.md` | Lector autenticado con verificación por ejecución, completitud, doble barrido, límites y fallos conservadores (`Identidad`, `Navegación`). Selectores, Edge y tema 275 son Jcink/instancia. | **G:** contrato `ForumAdapter.read`. **E:** `adapters/jcink`; perfil de navegador fuera del repo. |
| `forum_watch/NARRATIVE.md` | Evaluación aislada, entrada no confiable, contexto mínimo, contrato de decisión, propuestas de memoria, draft versionado y STALE (`Evaluación`, `Contexto`, `Persistencia`). La invocación Codex/Nozomu es local. | **G:** `core/runtime/narrative.py`, `core/review` y orquestación en `core/runtime`. **E:** proveedor de modelo interno de runtime y paquete Nozomu. |
| `forum_watch/DISCORD.md` | Proyección de eventos a avisos, deduplicación, entrega incierta, reintentos y secreto fuera del repo (`Fuentes`, `Entrega`). Webhook/DPAPI/payload son Discord/Windows. | **G:** puerto de notificación en runtime. **E:** `integrations/discord` y almacén de secretos de instancia. |
| `forum_watch/WORKFLOW.md` | Fases recuperables, locks, silencio sin trabajo, barreras de acceso, auditoría de runs y ausencia de transacción global (`Un ciclo`, `Datos operativos`). Tarea Windows y valores concretos son locales. | **G:** `core/runtime`. **E:** `integrations/scheduler/windows.py`, configuración y datos operativos externos. |
| `memory/index.md` | Índice vigente, enlaces, pendientes, diferencia entre ficha total y recursos de escena, aprobación sin publicación. | **G:** vistas/índices de `core/memory`. **E:** semilla de migración de la instancia Nozomu; no dato estático del paquete. |
| `memory/entities/nozomu-yamamoto.md` | Entidad revisada por anotaciones, procedencia y separación entre estado narrativo/mecánico/editorial. | **G:** patrón de entidad en `core/memory`. **E:** identidad/interpretación estable puede ir a `packages/characters/nozomu`; historia dinámica queda en instancia y la ficha mecánica está pendiente de decisión. |
| `memory/entities/arashi-hozuki.md` | Lo dicho/observado frente a lo OOC, relación no recíproca y propuestas aún no oídas (`Conocimiento`, `Límites`). | **G:** modelo de conocimiento/relación en `core/memory`. **E:** memoria de instancia Nozomu; no perfil universal de Arashi. |
| `memory/topics/ficha-mecanica/summary.md` | Estado declarado, procedencia, alias/IDs, aprendido≠utilizable, valores máximos≠recursos actuales y pendientes. | **G:** procedencia y separación de estado en `core/character`, `core/rules` y `core/memory`. **E:** ficha Nozomu pendiente de decidir entre paquete de personaje y perfil operativo externo; ninguna fórmula/regla va al paquete de sistema. |
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
| `character` | Cargar identidad, interpretación y límites de conocimiento estables; componerlos con un perfil operativo sin convertir reglas en datos del paquete. | Manifest/paquete + `SourceRef` + perfil externo opcional + referencias a mundo/sistema → `CharacterContext` validado y pendientes. | Puede depender de procedencia y contratos de paquete. No de Jcink, Discord, proveedor de modelo ni SQLite. El destino de la ficha mecánica estable de Nozomu queda abierto. |
| `world` | Consultar ambientación aportada y aprobada con cita, versión, vigencia, autoridad y alcance; nunca inferir huecos ni afirmar que el personaje la conoce. | Consulta dirigida + versión aprobada del corpus externo → pasajes literales, afirmaciones/interpretaciones aprobadas, conflictos, lagunas y citas. | No almacena lore en el paquete ni depende de personaje. El filtro IC se hace al componer con memoria/personaje. Si no hay corpus aprobado, devuelve desconocido, no canon externo. |
| `rules` | Representar `ABSENT` de forma explícita o consultar/evaluar normas aportadas y aprobadas; separar literal, interpretación, propuesta e incertidumbre. | Selección de sistema (`ABSENT` o corpus+versión) + consulta/snapshot/acción → secciones relevantes, evaluación condicionada, fórmula/unidades solo si están respaldadas, riesgos y `REQUIERE CONFIRMACIÓN`. | No contiene reglas Naruto ni depende de paquetes con reglas. Solo consume entradas aprobadas con `SourceRef`; una extracción pendiente/rechazada no es utilizable. `ABSENT` no simula ceros ni resolución mecánica. |
| `memory` | Ingerir eventos fuente, deduplicar, preservar revisiones y proyectar conocimiento IC/OOC, relaciones, pendientes y estado por escena. | Evento + fuentes + revisión opcional → registro inmutable/revisión; consulta contextual → hechos, creencias, lagunas y referencias. | Depende de un puerto de repositorio, no de SQLite. No recibe borradores como hechos ni escribe paquetes. |
| `review` | Versionar borradores y registrar decisiones humanas por versión exacta; aportar el vocabulario de revisión también a candidatos de asimilación sin tratarlos como publicaciones. | Borrador/candidato + versión + decisión/evidencia → estado explícito e historial. | No publica, canoniza ni activa una fuente por sí mismo. `DraftVersion` conserva sus tres ejes actuales; la asimilación tendrá su propio registro y reutilizará `ReviewStatus`, no `PublicationStatus`. |
| `runtime` | Alojar narrativa, seguimiento y `assimilation.py`; componer una instancia y ejecutar fases recuperables. La asimilación registra documentos/secciones literales, crea candidatos manuales o mediante puerto de modelo, solicita revisión y construye un índice dirigido solo con entradas aprobadas. | Fuentes aportadas + metadatos/versiones → candidatos citados; decisión humana → corpus consultable; consulta → secciones relevantes. Además conserva los flujos de escena, tracking y `RunReport`. | `assimilation.py`, `narrative.py` y `tracking.py` son submódulos internos. Depende de puertos y de modelos de `rules`/`world`; el camino manual funciona sin `ModelProvider`. No contiene reglas/lore concretos ni selectores Jcink. |

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
| Personaje | Identidad; rasgos y límites de interpretación; objetivos; trasfondo; POV/voz/formato; conocimientos iniciales y exclusiones meta; referencias a mundo/sistema; procedencia por afirmación o bloque. Evidencia: maestro §§1–5, 7–8, 11 e `instructions/interprete.md`. La ficha mecánica estable queda pendiente de decisión. | Reglas o fórmulas, memoria de escenas mutable, borradores, recursos actuales, secretos/configuración, cuenta/tema, selectores y cualquier dato derivado de lore/reglamento no aportado para ese personaje. |
| Mundo | En esta fase, solo el manifiesto común identifica y versiona el namespace del mundo y sus dependencias. Las entradas de ambientación se registran después como corpus externo versionado y revisado, no como payload del paquete. | Texto, extractos o datos estructurados derivados de lore; presunción de conocimiento IC; reglas, voz de personaje o estado operativo. |
| Sistema | En esta fase, solo el manifiesto común identifica y versiona el namespace del sistema y sus dependencias. Las normas, schemas de ficha/técnica aportados por el foro, tablas, fórmulas y valores viven en el corpus externo versionado y revisado. `ABSENT` es una selección explícita de instancia, no un paquete con valores cero. | Texto/extractos reglamentarios y todo dato estructurado derivado; valores de Nozomu, defaults mecánicos, decisiones narrativas, selectores o estado operativo. |

La identidad e interpretación estables y aprobadas del personaje entran en
`packages/characters/nozomu`; su historia ya jugada y la memoria dinámica viven fuera del repo,
sujeto a la duda específica sobre ficha mecánica. Los
diseños no aprobados se conservan como referencia histórica, nunca como repertorio adquirido.
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
- JSON estricto para manifests/estado, JSONL para eventos append-only y texto literal externo para
  fuentes aportadas; Markdown solo para voz/documentación humana expresamente autorizada. Esto no
  autoriza incorporar lore, reglas ni derivados en paquetes. Validadores propios pequeños al
  inicio, como el legado, sin afirmar soporte de JSON Schema completo.
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

### Incrementos posteriores

3. [ ] **Catálogo literal, versiones y revisión de asimilación (sin modelo).** Añadir modelos de
   documento/sección/versiones, vigencia y candidatos en `core/runtime/assimilation.py`, repositorio
   en memoria detrás de puerto y decisiones humanas con `SourceRef`/`ReviewStatus`. El material de
   prueba se aporta por API/fixtures y el almacenamiento efectivo se configura fuera del repo.
   Criterio: pendiente/rechazado no es consultable; aprobar una cita no aprueba otra; una versión
   nueva conserva la anterior y una vigencia ambigua falla con `REQUIERE CONFIRMACIÓN`.
4. [ ] **Recuperación dirigida y contratos `rules`/`world` (sin modelo).** Crear índices de secciones
   deterministas y consultas separadas para reglas/ambientación; implementar selección de sistema
   `ABSENT`. Criterio: una consulta devuelve solo pasajes relevantes con cita, distingue literal,
   interpretación, propuesta e incertidumbre y nunca rellena un hueco.
5. [ ] **Puerto de modelo y extracción asistida opcional.** Definir `ModelProvider` en
   `core/runtime/ports.py`; la extracción devuelve candidatos aún pendientes y no activa nada.
   Criterio: todos los tests/core funcionan sin proveedor; un doble demuestra que la salida del
   modelo necesita citas válidas y revisión humana.
6. [ ] **Puertos de repositorio y memoria.** Implementar eventos con procedencia, deduplicación,
   revisión por anotación y consultas IC/OOC; repositorio en memoria primero. Criterio: una
   corrección conserva el evento previo y un resultado no confirmado nunca sale como hecho.
7. [ ] **Narrativa interna sin modelo y puertos mínimos de ejecución.** Añadir
   `core/runtime/narrative.py`, constructor de contexto, `PublicationPort` y dobles; ningún adaptador
   implementa publicación. Criterio: pensamiento privado/OOC no puede ser `FACT` e incertidumbre
   material no produce borrador automático.
8. [ ] **Seguimiento interno y adaptador manual.** Añadir `core/runtime/tracking.py`, `ForumReader`
   y `adapters/manual.py` con fixtures locales. Criterio: A→B→A conserva tres revisiones y una
   captura incompleta no avanza estado.
9. [ ] **Primer repositorio SQLite y runtime de un ciclo.** Persistir corpus/memoria/operación fuera
   del repo, añadir `core/runtime/config.schema.json` y `config.example.json` sin autorizaciones
   reales, y conectar fases sin red/modelo mediante puertos de reloj/lock. Criterio:
   reinicio/concurrencia no duplican trabajos y fallo tardío no revierte una fase confirmada.
10. [ ] **Payload de personaje Nozomu.** Tras resolver la duda de la ficha mecánica, migrar solo los
    datos autorizados; mundo/sistema permanecen manifest-only y las normas/lore se aportan al corpus
    externo. Criterio: no aparece texto ni derivado reglamentario/lore y ninguna propuesta figura
    como aprendida, utilizable o canon.
11. [ ] **Evaluador técnico genérico.** Consumir exclusivamente corpus aprobado y snapshots por
    escena; no implementar reglas Naruto. Criterio: ausencias permanecen desconocidas, cálculos citan
    cada fórmula/unidad y ambigüedades conservan `REQUIERE CONFIRMACIÓN`.
12. [ ] **Adaptador Jcink offline.** Extraer selectores/paginación/autenticación detrás de
    `ForumReader` con contract tests saneados. Criterio: core pasa sin Playwright y el adaptador
    rechaza identidad/completitud no verificables; no implementa `PublicationPort`.
13. [ ] **Proveedor e integraciones opcionales.** Migrar, uno por vez, proveedor Codex CLI,
    Discord y scheduler Windows. Criterio: deshabilitarlos no afecta core; secretos/configuración
    efectiva quedan externos y no hay publicación real.
14. [ ] **Paridad y segundo caso de generalidad (incremento final).** Elegir el caso solo cuando las
    bases estén afinadas y ejecutar paridad con fixtures legacy saneadas. Criterio: incorporar el
    caso elegido sin modificar el core para acomodar nombres, voz, temática o mecánicas específicas.

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

Claude debe detenerse antes del incremento afectado y pedir decisión; no elegir por suposición. No
hay una duda que bloquee el incremento 2.

1. **Antes del incremento 10: ¿dónde vive la ficha mecánica de Nozomu —atributos invertidos,
   inventario, IDs/técnicas y estados aprendido/utilizable— si depende de un sistema cuyas reglas y
   derivados no se empaquetan?**
   - A: toda la ficha dependiente del sistema vive como perfil operativo versionado fuera del repo;
     el paquete de personaje solo conserva identidad/interpretación independiente del sistema.
   - B: el paquete de personaje puede conservar hechos mecánicos estables aportados y su
     procedencia (atributos declarados, inventario, IDs, aprendido/utilizable), pero no fórmulas,
     totales derivados ni reglas; recursos de escena siguen fuera.
   - C: no crear payload del personaje más allá del manifest hasta que el usuario aporte una fuente
     nueva y delimite campo por campo qué se puede versionar.
2. **Para el incremento final, ¿qué segundo caso de generalidad se usará?** Decisión
   intencionadamente aplazada hasta que las bases estén afinadas; no condiciona los incrementos
   2–13 y no se detallan opciones todavía.

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
