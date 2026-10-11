# Análisis de tarea

## Tarea

Generalizar Nozomu Agent como `roleplay-agent-core`: un núcleo reutilizable para agentes de
foro de rol, configurable por personaje, mundo, sistema, plataforma e instancia. Este documento
define la extracción y un plan para Claude; no implementa código ni altera el legado.

Versión base: commit inicial `96eca81` a 2026-10-11. Incluye `reference/` y la configuración de
agentes; todavía no hay código propio del nuevo núcleo. `reference/migration-source/` es la copia
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
- Provisionalmente, los paquetes no incorporan texto de reglas ni lore de Naruto Rol y el core no
  presupone ninguna temática. El alcance exacto de «ninguna fuente» debe confirmarse antes del
  incremento 7.
- Primero se implementa el adaptador manual; Jcink viene después y el scheduler Windows es opcional.
- Solo se versionan el esquema y un ejemplo de configuración sin autorizaciones reales; la
  configuración efectiva es externa.
- El segundo caso de generalidad queda sin decidir hasta el incremento 11.

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
| `instructions/memoria.md` | Evento con fuente, deduplicación, correcciones sin borrado, hechos/creencias/secretos/propuestas/resultados y estado de combate por tema. | **G:** contrato de `core/memory`. **E:** nombres/campos mecánicos de `packages/systems/naruto-rol`. |
| `instructions/combate.md` | Especialista técnico, cálculo solo con entradas explícitas, cita de reglas, snapshots de escena y salida condicionada (`Instructions`, `Profile`, `Knowledge`, `Respuesta`). | **G:** política de `core/rules`. **E:** perfil Nozomu y formato Naruto en paquetes de personaje/sistema. |
| `forum_watch/README.md` | Identidad de tema, baseline, captura completa, revisiones A→B→A, rechazo de desapariciones/reordenación, transacciones y concurrencia (`Registro`, `Contrato`, `Normalización`, `Persistencia`). | **G:** `core/runtime/tracking.py` y puertos internos. **E:** URL/host/cuenta a `adapters/jcink` y configuración de instancia. |
| `forum_watch/READER.md` | Lector autenticado con verificación por ejecución, completitud, doble barrido, límites y fallos conservadores (`Identidad`, `Navegación`). Selectores, Edge y tema 275 son Jcink/instancia. | **G:** contrato `ForumAdapter.read`. **E:** `adapters/jcink`; perfil de navegador fuera del repo. |
| `forum_watch/NARRATIVE.md` | Evaluación aislada, entrada no confiable, contexto mínimo, contrato de decisión, propuestas de memoria, draft versionado y STALE (`Evaluación`, `Contexto`, `Persistencia`). La invocación Codex/Nozomu es local. | **G:** `core/runtime/narrative.py`, `core/review` y orquestación en `core/runtime`. **E:** proveedor de modelo interno de runtime y paquete Nozomu. |
| `forum_watch/DISCORD.md` | Proyección de eventos a avisos, deduplicación, entrega incierta, reintentos y secreto fuera del repo (`Fuentes`, `Entrega`). Webhook/DPAPI/payload son Discord/Windows. | **G:** puerto de notificación en runtime. **E:** `integrations/discord` y almacén de secretos de instancia. |
| `forum_watch/WORKFLOW.md` | Fases recuperables, locks, silencio sin trabajo, barreras de acceso, auditoría de runs y ausencia de transacción global (`Un ciclo`, `Datos operativos`). Tarea Windows y valores concretos son locales. | **G:** `core/runtime`. **E:** `integrations/scheduler/windows.py`, configuración y datos operativos externos. |
| `memory/index.md` | Índice vigente, enlaces, pendientes, diferencia entre ficha total y recursos de escena, aprobación sin publicación. | **G:** vistas/índices de `core/memory`. **E:** semilla de migración de la instancia Nozomu; no dato estático del paquete. |
| `memory/entities/nozomu-yamamoto.md` | Entidad revisada por anotaciones, procedencia y separación entre estado narrativo/mecánico/editorial. | **G:** patrón de entidad en `core/memory`. **E:** `packages/characters/nozomu` para lo estable; historia dinámica a datos de instancia. |
| `memory/entities/arashi-hozuki.md` | Lo dicho/observado frente a lo OOC, relación no recíproca y propuestas aún no oídas (`Conocimiento`, `Límites`). | **G:** modelo de conocimiento/relación en `core/memory`. **E:** memoria de instancia Nozomu; no perfil universal de Arashi. |
| `memory/topics/ficha-mecanica/summary.md` | Estado declarado, procedencia, alias/IDs, aprendido≠utilizable, valores máximos≠recursos actuales y pendientes. | **G:** procedencia y separación de estado. **E:** `packages/characters/nozomu` + `packages/systems/naruto-rol`. |
| `memory/topics/mision-d-pedidos-del-puerto/summary.md` | Una confirmación parcial consolida solo el núcleo sustentado, no todos los detalles/recompensas. | **G:** consolidación mínima en `core/memory`. **E:** memoria histórica de instancia; contenido no va al core. |
| `memory/topics/muelle-nozomu-arashi/summary.md` | Cronología por revisiones, IC/OOC, turno local frente a post remoto y consecuencias pendientes. | **G:** `core/memory`/`core/review`. **E:** memoria histórica de instancia. |
| `memory/topics/tecnicas-unicas/summary.md` | Historial de decisiones y ejes separados DRAFT, aprobación staff, aprendizaje y uso; propuestas sustituidas sin borrarlas. | **G:** procedencia/revisiones. **E:** sistema Naruto y estado de diseño de Nozomu; no enum global del core. |
| `drafts/misiones/2026-09-15-*`, `09-16-*`, `09-18-*`, `09-20-*`, `09-23-*` (5) | Cadena de posts con estado libre, aprobación comunicada, publicación no verificada y consecuencias abiertas. | **Solo referencia histórica**; estructura de versión/consecuencias alimenta `core/review`, muestras saneadas pueden ser fixtures. |
| `drafts/misiones/individual-d-pedidos-del-puerto.md` | Borrador largo, datos OOC, conteo editorial, confirmación posterior parcial y detalles no canonizados. | **Solo referencia histórica**; evidencia para pruebas de consolidación parcial y presentación Jcink. |
| `drafts/muelle-nozomu-arashi/*.md` (6) | Versiones, sustitución editorial, nota OOC, cuerpo IC y consecuencias; una v2 aprobada pero no publicada. | **Solo referencia histórica**; formato informa `core/review` y voz a `packages/characters/nozomu`. |
| `drafts/tecnicas-unicas/2026-09-11-rule-audit.md` | Auditoría de reglas, citas, incertidumbres y STOP; no confunde parámetros orientativos con autorización. | **G:** política de `core/rules`. **E:** `packages/systems/naruto-rol`; resultado Nozomu queda histórico. |
| `drafts/tecnicas-unicas/2026-09-11-02-identidad-conceptos.md` | Legalidad/identidad/contrajuego y alternativas propuestas, sin concederlas. | **G:** metodología de `core/rules`. **E:** diseño Nozomu/Naruto histórico. |
| `drafts/tecnicas-unicas/2026-09-11-03-guardia-abierta-variantes.md` | Comparación explícita de hipótesis, parámetros pendientes y límites de inferencia. | **G:** evaluación condicionada de reglas. **E:** sistema Naruto y borrador Nozomu histórico. |
| `drafts/tecnicas-unicas/2026-09-11-04-guardia-abierta-ficha.md` | Campos de técnica realmente usados: nombre, rama, rango, requisito, sellos, coste, potencia, alcance, efecto, activación, duración, limitaciones, contrajuego, escalado, balance, dudas y estado. | **E:** schema de técnica en `packages/systems/naruto-rol`; instancia propuesta de Nozomu, no core universal. |
| `drafts/tecnicas-unicas/2026-09-11-05-comparacion-genin.md` y `...guardia-abierta-genin.md` (2) | Precedentes con procedencia, alternativas de balance y ficha por rango; aprobación ajena no transfiere autoridad. | **G:** regla de procedencia. **E:** paquete de sistema/estado Nozomu; originales históricos. |
| `drafts/tecnicas-unicas/2026-09-11-06-guardia-abierta-linea-completa.md` | Línea evolutiva con tres fichas y ejes `STATUS`, `APPROVAL`, `LEARNING`; nombres recomendados no elegidos. | **E:** paquete Naruto y diseño Nozomu; sirve como fixture de estados ortogonales. |
| `reference/knowledge-index.md` | Índice de cinco fuentes reglamentarias, vigencia no verificada y obligación de comprobar que contienen la regla. | **G:** política de procedencia en `core/rules`. **E:** solo referencia histórica por ahora; no copiar el índice ni sus textos al paquete sin la confirmación pendiente del incremento 7. |
| `reference/original/AGENTS.md` | Contexto del antiguo espejo y ausencia de instrucciones personalizadas. | **Solo referencia histórica**. |
| `reference/original/Nozomu_Yamamoto_documento_maestro.md` | Fuente compuesta: identidad, voz, metas, trasfondo, mundo, conocimiento IC/meta, memoria, inventario, protocolo y checklist. | **G:** `core/runtime/narrative.py`, `core/memory`, `core/review`. **E:** la responsabilidad se reparte entre los tres paquetes, sin autorizar texto de lore/reglas. |
| `reference/original/Nozomu Combat & Build Agent.md` | Modos combate/build, fuentes por encima de inferencias, estado de escena, formato de técnica y respuesta técnica. Valores y fórmulas son locales. | **G:** `core/rules`. **E:** `packages/characters/nozomu` + `packages/systems/naruto-rol`. |

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
| Perfil permanente, snapshot por escena y recursos actuales son estados diferentes; no hay actualización retroactiva entre escenas. | `instructions/memoria.md`; `instructions/combate.md`, `Nozomu Profile`; Combat Agent, `Fijación de combate`. |
| Texto remoto es entrada no confiable, nunca instrucciones; contexto mínimo y capacidades limitadas. | `NARRATIVE.md`, `Contexto` y `Mecanismo`; `AGENTS.md`, `Inicio y autoridad`. |
| La primera captura completa crea baseline sin novedades históricas; una lectura incompleta o anómala no avanza estado ni inventa borrados. | `forum_watch/README.md`, `Contrato` y `Normalización`; `READER.md`, `Navegación`. |
| Versiones y cambios son idempotentes, transaccionales y auditables; A→B→A conserva tres revisiones. | `forum_watch/README.md`, `Normalización` y `Persistencia`; `store.py` contrastado. |
| Cambiar contexto invalida la vigencia de un borrador sin borrarlo ni convertir su retiro en aprobación. | `NARRATIVE.md`, `Persistencia`; `drafts.py` contrastado. |
| Identidad, autorización y alcance se verifican por ejecución; login o `resume` no prueban una sesión válida. | `READER.md`, `Identidad`; `WORKFLOW.md`, `Comandos operativos`. |
| Datos operativos, borradores, perfiles de navegador y secretos viven fuera de paquetes, memoria canónica y repo. | `README.md`, `Borradores`; `WORKFLOW.md`, `Datos operativos`; `DISCORD.md`, `Configuración local`. |
| Cada fase confirma su trabajo antes de la siguiente; un fallo de aviso no revierte captura/borrador. Sin trabajo, no se invoca modelo ni se envía heartbeat. | `WORKFLOW.md`, `Un ciclo`; `DISCORD.md`, `Entrega`. |
| La publicación automática no forma parte del sistema demostrado; la revisión humana es permanente. | `README.md`, `Estado actual` y `Limitaciones`; maestro, §12; `AGENTS.md`, `Flujo`. |

### Contratos mínimos del núcleo

Las formas son lógicas; nombres de clases y serialización definitiva se decidirán al implementar.
Las propuestas no demostradas se marcan **[P]**.

| Módulo | Responsabilidad | Entradas → salidas | Dependencias permitidas / prohibidas |
| --- | --- | --- | --- |
| `character` | Cargar identidad, interpretación, límites de conocimiento y estado específico del sistema de un personaje. | Paquete + `SourceRef` + referencias a mundo/sistema → `CharacterContext` validado, pendientes y estado opaco del sistema. | Puede depender de procedencia y contratos de paquete. No de Jcink, Discord, proveedor de modelo ni SQLite. |
| `world` | Recuperar lore con fuente, vigencia, autoridad y alcance; nunca afirmar que el personaje lo conoce. | Consulta + paquete de mundo → entradas de lore y lagunas con procedencia. | No depende de personaje; el filtro IC se hace al componer contexto con memoria/personaje. |
| `rules` | Consultar reglas y evaluar legalidad/cálculos con datos explícitos; distinguir regla, interpretación, propuesta e incertidumbre. | Sistema + snapshot de personaje/escena + acción → evaluación, fórmula/unidades, consumo propuesto, riesgos y dudas. | El sistema define sus propios campos. `NONE` **[P]** debe devolver ausencia explícita de resolución mecánica, no estadísticas inventadas. |
| `memory` | Ingerir eventos fuente, deduplicar, preservar revisiones y proyectar conocimiento IC/OOC, relaciones, pendientes y estado por escena. | Evento + fuentes + revisión opcional → registro inmutable/revisión; consulta contextual → hechos, creencias, lagunas y referencias. | Depende de un puerto de repositorio, no de SQLite. No recibe borradores como hechos ni escribe paquetes. |
| `review` | Versionar borradores, mantener vigencia y registrar decisiones humanas/publicación sobre una versión exacta. | Borrador + dependencias; decisión humana + evidencia; confirmación de publicación + evidencia → nueva versión/estado/eventos. | No publica por sí mismo ni canoniza resultados. Revisión, ciclo de vida, publicación y resolución son ejes separados. |
| `runtime` | Alojar internamente narrativa y seguimiento, componer una instancia y ejecutar fases recuperables con locks, autorizaciones, auditoría y notificaciones. | Escena no confiable + contextos de dominio → decisión/borrador/candidatos; `ForumAdapter` + snapshot previo → baseline/revisiones/cambios; configuración + trigger → `RunReport`. | `narrative.py` y `tracking.py` son submódulos internos, no paquetes hermanos. Depende de puertos; no contiene selectores Jcink, fórmulas Naruto, voz Nozomu, webhook o XML Windows. |

Los puertos no requieren una carpeta de primer nivel: los repositorios propios quedan junto al
módulo dueño (`core/memory/ports.py`, `core/review/ports.py`) y los límites de ejecución quedan en
`core/runtime/ports.py` (`ForumReader`, `ModelProvider`, `NotificationSink`, `Scheduler`, reloj/lock
y `PublicationPort`). `PublicationPort` se define y se prueba con un doble, pero ningún archivo de
`adapters/` lo implementa. El proveedor opcional Codex CLI, si se migra, queda en
`core/runtime/codex_cli_provider.py`; la interfaz es `ModelProvider`. El esquema y ejemplo de
configuración quedan en `core/runtime/config.schema.json` y `core/runtime/config.example.json`, sin
autorizaciones reales. El adaptador manual inicial es `adapters/manual.py`; Jcink permanece en
`adapters/jcink/`.

Contrato transversal mínimo de procedencia, respaldado por `events.jsonl`: identificador de fuente,
localizador, hash opcional, sección/pasaje, autor/aportante, identificador de turno y su alcance,
instante de importación/observación separado de fecha/orden IC, autoridad/estado y referencia a la
revisión corregida. El hash, pasaje o fecha IC pueden ser nulos; no se rellenan por inferencia.

#### Estados que no deben representarse con un único enum

- **Versión de contenido:** identificador y número/hash exactos.
- **Vigencia:** `ACTIVE | STALE | RETIRED` (demostrado por Forum Watch).
- **Revisión humana:** `PENDING_HUMAN_REVIEW | APPROVED | REJECTED`; rechazo está respaldado por
  el protocolo del maestro, aunque el CLI legado no lo persistía.
- **Publicación:** no confirmada o confirmada con fuente y versión exacta.
- **Memoria:** candidato pendiente frente a registro consolidado, con clase epistemológica.
  El registro consolidado con fuente y alcance es canon aunque no haya publicación; canon no es un
  estado de `DraftVersion`.
- **Resolución:** intento/acción publicada frente a consecuencia resuelta por participante,
  narrador, reglas o staff.
- **Mecánica específica:** aprobación staff, aprendizaje y disponibilidad pertenecen al paquete de
  sistema/estado de personaje; no son estados universales del borrador.

### Formato lógico de los paquetes

Se recomienda JSON para datos validados y, cuando corresponda, Markdown para voz/personaje, sin
YAML ni una dependencia nueva. La decisión provisional excluye texto de reglas y lore de los
paquetes. El envoltorio común `schema_version`, `package_type`, `package_id`, `version` y
dependencias entre paquetes es **[P]** de infraestructura; procede versionarlo porque el legado ya
versiona capturas, perfiles, borradores y componentes, pero esos nombres exactos no están impuestos.

| Paquete | Campos respaldados por el legado | Lo que no debe contener |
| --- | --- | --- |
| Personaje | Identidad; afiliación/rango/clan; rasgos y límites de interpretación; objetivos; familia/trasfondo; POV/voz/formato; conocimientos iniciales y exclusiones meta; referencias a mundo/sistema; estado mecánico específico con atributos, inventario, técnicas, aprendido/utilizable y pendientes; procedencia por afirmación o bloque. Evidencia: maestro §§1–5, 7–8, 11; `instructions/interprete.md`; `shared/profile.json`. | Memoria de escenas mutable, borradores operativos, recursos de otra escena, secretos, cuenta/tema del foro, selectores o fórmulas universales. |
| Mundo | El legado respalda entradas de lore con fuente, autoridad/vigencia, cronología, lugares, facciones, política/cultura/tecnología. La decisión provisional permite definir su contrato, pero no incorporar ese texto al paquete Naruto Rol hasta confirmar el alcance del incremento 7. | Texto o extractos de lore por ahora; presunción de conocimiento IC, reglas mecánicas, voz del personaje o canon externo. |
| Sistema | El legado respalda reglas, atributos/recursos/acciones/efectos, fórmulas, schemas de perfil/escena/objetos/técnicas, restricciones y estados de aprobación/aprendizaje/uso. La decisión provisional permite el contrato genérico, pero bloquea copiar texto reglamentario al paquete Naruto Rol; queda por confirmar si admite datos estructurados derivados. | Texto o extractos reglamentarios por ahora; valores de Nozomu como defaults, decisiones narrativas, selectores Jcink o estado operativo. Un sistema sin mecánicas es **[P]**, no se simula con ceros. |

Lo estable y aprobado del personaje entra en `packages/characters/nozomu`; su historia ya jugada y
la memoria dinámica viven fuera del repo. Los diseños no aprobados se conservan como fixtures
históricos, nunca como repertorio adquirido. Hasta la confirmación previa al incremento 7,
`packages/worlds/naruto-rol` y `packages/systems/naruto-rol` no reciben texto de fuentes, lore o
reglas. El core no presupone Naruto ni ninguna otra temática.

### Valoración de la estructura propuesta

| Elemento propuesto | Valoración |
| --- | --- |
| `core/{character,world,rules,memory,runtime,review}` | Estructura vinculante. Narrativa y seguimiento se implementan dentro de `core/runtime/` como archivos/submódulos internos; no se crean carpetas hermanas nuevas en `core/`. |
| `adapters/jcink` | Correcto. Debe contener URL, autenticación, selectores, paginación, BBCode/presentación y capacidades; no memoria ni generación. |
| `packages/{characters,worlds,systems}` | Correcto si son datos versionados y validados, no código con condicionales por Nozomu. El estado mutable no pertenece aquí. |
| `integrations/{discord,scheduler}` | Estructura vinculante. Discord queda en su carpeta; el soporte Windows es `integrations/scheduler/windows.py` y opcional. El proveedor de modelo queda dentro de `core/runtime/`, no crea otra integración hermana. |
| `reference/migration-source/` | Ruta definitiva del legado en este repo; se mantiene inmutable y no se renombra. |
| `tests` | Correcto; separar unitarios de core, contratos de puertos, fixtures saneadas y paridad legacy. |

El intérprete se implementa en `core/runtime/narrative.py`; combate y memoria son capacidades de
`core/rules` y `core/memory`, invocables directamente o mediante especialistas de solo lectura. El
coordinador y el seguimiento (`tracking.py`) viven en `core/runtime/`. Borradores/aprobación
pertenecen a `core/review`. La configuración real, memoria dinámica, SQLite, locks, drafts, perfiles,
cookies, autorizaciones y secretos viven fuera del repo; solo se versionan schema y ejemplo.

Árbol vinculante:

```text
core/
  character/
  world/
  rules/
  memory/
  runtime/                       # narrative.py, tracking.py, ports.py, proveedor y config de ejemplo
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
- JSON estricto para manifests/estado y JSONL para eventos append-only; Markdown para voz y
  documentación humana expresamente autorizada. Esto no autoriza incorporar lore/reglas Naruto
  Rol. Validadores propios pequeños al inicio, como el legado, sin afirmar soporte de JSON Schema
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

- [ ] Ningún módulo genérico contiene `Nozomu`, `Naruto`, `Jcink`, host, cuenta o tema concretos.
- [ ] Cada dato de personaje/mundo/regla conserva fuente, autoridad, alcance y pendientes.
- [ ] La composición impide usar lore/OOC/pensamientos privados como conocimiento IC sin una vía
  documentada.
- [ ] Revisión, vigencia, publicación, canon y resolución son transiciones explícitas por versión.
- [ ] No existe publicación automática ni consolidación canónica automática por defecto.
- [ ] El sistema admite reglas cargadas y ausencia explícita de sistema sin inventar mecánicas.
- [ ] Paquetes son inmutables durante una ejecución; memoria y estado operativo se escriben fuera.
- [ ] La memoria dinámica, configuración efectiva, autorizaciones y datos operativos permanecen
  fuera del repo; dentro solo existen schemas y ejemplos sin valores reales.
- [ ] Lectura de plataforma se limita a un alcance autorizado y devuelve completitud e identidad
  verificadas o un error; nunca una falsa ausencia de novedades.
- [ ] Capturas/revisiones son idempotentes y preservan baseline, correcciones e historial.
- [ ] El runtime recupera fases independientemente, evita duplicados y permanece silencioso sin
  trabajo.
- [ ] Discord, scheduler, proveedor de modelo, almacenamiento y navegador son opcionales y
  reemplazables.
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

2. [ ] **Contratos de paquetes y loaders.** Implementar manifests/versiones, validación de
   referencias y paquetes mínimos de personaje/mundo/sistema en las rutas decididas. Añadir en
   `core/runtime/ports.py` los puertos de modelo, lectura, notificación, scheduler y publicación;
   este último solo tendrá dobles de prueba. Criterio: cargar un fixture genérico, rechazar
   referencias rotas/campos desconocidos y comprobar que ningún adapter implementa publicación.
3. [ ] **Puertos de repositorio y memoria.** Implementar eventos con procedencia, deduplicación
   tema+turno+autor, revisión por anotación y consultas IC/OOC; repositorio en memoria primero.
   La interfaz vive en `core/memory/ports.py`; la memoria dinámica se prueba en temporales fuera del
   repo. Criterio: una corrección conserva el evento previo y un resultado no confirmado nunca sale
   como hecho.
4. [ ] **Review + narrativa interna sin modelo.** Añadir `core/runtime/narrative.py`, contrato de
   decisión, constructor de contexto y doble determinista. Criterio: pensamiento privado/OOC no
   puede ser `FACT`; combate/incertidumbre material no produce borrador automático.
5. [ ] **Seguimiento interno y adaptador manual.** Añadir `core/runtime/tracking.py` y
   `adapters/manual.py`: snapshot completo, baseline, revisiones, replay, anomalías y vigencia de
   borrador con fixtures locales. Criterio: A→B→A conserva tres revisiones y una captura incompleta
   no avanza estado.
6. [ ] **Primer repositorio SQLite y runtime de un ciclo.** Conectar fases y auditoría fuera del
   repo, sin red ni modelo. Criterio: reinicio/concurrencia no duplican trabajos y fallo tardío no
   revierte fase confirmada.
7. [ ] **Paquetes Nozomu/Naruto Rol, bloqueado por confirmación.** Antes de escribirlos, confirmar
   si «ninguna fuente» prohíbe solo texto/fragmentos o también datos estructurados derivados. Migrar
   después únicamente lo autorizado; la memoria dinámica sigue externa. Criterio: no hay texto de
   lore/reglas sin autorización y ninguna propuesta aparece como aprendida o canon.
8. [ ] **Rules y especialista técnico.** Implementar primero el contrato genérico y snapshots por
   escena. La implementación Naruto Rol depende de la decisión del incremento 7. Criterio: los datos
   ausentes permanecen desconocidos y la ambigüedad conserva `REQUIERE CONFIRMACIÓN`.
9. [ ] **Adaptador Jcink offline.** Extraer selectores/paginación/autenticación detrás de
   `ForumAdapter` y contract tests saneados. Criterio: core pasa sin Playwright y el adaptador
   rechaza identidad/completitud no verificables.
10. [ ] **Proveedor e integraciones opcionales.** Migrar el proveedor a
    `core/runtime/codex_cli_provider.py`, Discord a `integrations/discord/` y Windows a
    `integrations/scheduler/windows.py`, uno por vez. Criterio: deshabilitarlos no afecta core;
    secretos/configuración real quedan externos; ninguna pieza implementa `PublicationPort`.
11. [ ] **Paridad y segundo caso.** Comparar fixtures legacy y ejecutar el caso que el usuario elija
    al llegar a este incremento. Criterio común: introducirlo sin modificar el core para acomodar
    nombres, voz, temática o mecánicas específicas.

## Cómo verificarlo

- Test / comando general futuro: `py -3.11 -B -m unittest discover -s tests -v`, sin red ni
  servicios y sin instalar el proyecto.
- Comprobaciones estáticas: `rg` de nombres/IDs específicos dentro del core; imports del core sin
  Playwright/Discord/Windows; `git diff --check`; ausencia de cambios en `reference/`.
- Contract tests: paquetes, repositorios, ForumAdapter, proveedor de modelo, notificador, scheduler
  y reloj/locks con dobles locales.
- Paridad: snapshots saneados y eventos legacy seleccionados deben reproducir cambios, estados y
  límites semánticos, no texto generativo literal.
- Comprobación manual posterior y separada: solo con autorización expresa, entorno externo y plan
  revisado para foro/Discord/modelo; nunca forma parte de la suite normal.

## Riesgos y dudas abiertas

Claude debe detenerse antes del incremento afectado y pedir decisión; no elegir por suposición.

1. **Antes del incremento 7, ¿qué excluye exactamente «ninguna fuente» en los paquetes Naruto
   Rol?**
   - A: prohíbe texto y fragmentos, pero permite datos estructurados derivados con referencias/hash
     al legado.
   - B: prohíbe también datos derivados de lore/reglas; los paquetes solo contienen manifest,
     schemas/extensiones vacías y datos de personaje que no reproduzcan esas fuentes.
   - C: no crear contenido en los paquetes `worlds/naruto-rol` y `systems/naruto-rol` hasta recibir
     nuevas fuentes/configuración aportadas específicamente para ellos.
2. **¿Qué segundo caso se usará en el incremento 11?**
   - A: personaje de otro mundo sin sistema mecánico (`NONE`) y adaptador manual.
   - B: otro mundo con un segundo sistema mecánico.
   - C: segundo personaje de Naruto Rol; separa personaje, pero no demuestra independencia de
     mundo/sistema.

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
