# Análisis de tarea

## Tarea

Generalizar Nozomu Agent como `roleplay-agent-core`: un núcleo reutilizable para agentes de
foro de rol, configurable por personaje, mundo, sistema, plataforma e instancia. Este documento
define la extracción y un plan para Claude; no implementa código ni altera el legado.

Versión base del detalle del sub-incremento 4d2: commit `67a7284` (4d1 aprobado), a 2026-10-12,
rama `feature/incremento-4-rebanada-vertical`. El único cambio de trabajo al iniciar este análisis
es la nota de validación funcional de 4d1 al final de este documento; debe conservarse intacta.
`main` permanece en `96eca81`; los incrementos 1–3 siguen en ramas apiladas sin fusionar.
`reference/migration-source/` es la copia inmutable inspeccionada. La auditoría anterior se trata
como hipótesis histórica porque declara que su fuente estaba vacía; no se usa como prueba de la
implementación actual.

### Decisiones del usuario (11-10-2026 y 12-10-2026)

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
- La barrera humana es la opción A: los comandos de decisión solo funcionan con stdin y stdout
  TTY, muestran ID, versión, hash y decisión, generan un nonce mediante `secrets` y exigen que el
  usuario teclee la frase completa. El nonce no se admite por argumento, archivo ni variable de
  entorno; `AGENTS.md` y `CLAUDE.md` ordenarán al agente mostrar el comando y pedir al usuario que
  lo ejecute. Se implementa en 4c1. Reduce la automatización accidental, pero no garantiza humanidad
  frente a un agente hostil capaz de crear y manejar una pseudo-TTY con el mismo usuario del SO.

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
- `core/runtime/assimilation.py` y `core/runtime/templates/` — incremento 3 aprobado: expediente
  Markdown cerrado, modelos inmutables, fuentes literales/hash y diagnósticos.
- `core/runtime/{persistence,workspace,cli}.py` y `adapters/manual.py` — incremento 4a aprobado:
  workspace externo íntegro, sobre de estado atómico, importación manual y CLI init/status; el
  corpus nace vacío.
- `core/runtime/{assimilation,workspace,cli}.py` — incrementos 4b–4c1 aprobados: candidatos
  manuales inmutables, citas resueltas desde `quote`, historial/versionado, decisiones con barrera
  TTY, cierre terminal, cerrojo provisional y recarga íntegra del estado cerrado.
- `core/runtime/{instance,workspace,cli}.py` — 4c2 aprobado: instancia cerrada autocontenida,
  plantillas congeladas, consultas del corpus aprobado, creación Windows con publicación segura y
  recarga que rechaza cualquier entrada no declarada.
- Las dieciocho suites actuales suman 391 pruebas aprobadas tras 4d1 que los incrementos
  siguientes deben conservar.

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
| `runtime` | Alojar expediente/asimilación, materialización de instancia, CLI, narrativa y seguimiento; ejecutar fases recuperables. La asimilación registra literales, crea candidatos manuales o mediante puerto de modelo, solicita revisión y construye un índice dirigido solo con entradas aprobadas. | Expediente → workspace externo; fuentes/metadatos → candidatos citados; decisiones/cierre humanos → instancia y corpus consultable; consulta → secciones relevantes. Además conserva los flujos de escena, tracking y `RunReport`. | `assimilation.py`, `cli.py`, `narrative.py` y `tracking.py` son submódulos internos. Depende de puertos y de modelos de `rules`/`world`; el camino manual funciona sin `ModelProvider`. No contiene reglas/lore concretos ni selectores Jcink. |

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
Rechaza una ruta dentro del checkout o del workspace y una carpeta no vacía que no sea un retry
idéntico. El usuario elige solo la ruta; `forum_id` y el snapshot proceden del workspace cerrado.
No es una decisión humana ni lleva barrera TTY: materializa de forma transaccional contenido ya
decidido y deja auditable el origen de cada archivo.

Antes de esa instancia existe un **workspace de asimilación**, también externo y elegido mediante
`--workspace` explícito. No es un agente ni una instancia: carece de `AGENTS.md`, `CLAUDE.md`,
personajes, memoria y especialistas. Aloja únicamente la copia del expediente, candidatos y
decisiones necesarias para que el core pueda impedir materializar antes de la aprobación:

```text
<workspace-asimilacion>/
  workspace.json
  dossier/
  corpus/state.json
  work/integrity.json
```

Tras el cierre humano del snapshot exacto, `instance init --workspace ... --output ...` copia el
expediente y **todo** el `corpus/state.json` cerrado a la carpeta final: historial, decisiones y
cierre. No crea una segunda proyección autoritativa. Las consultas de instancia filtran en runtime
solo la última versión `APPROVED` de cada ID; pendientes, rechazadas y sustituidas permanecen
auditables pero no son consultables como corpus utilizable. El workspace puede conservarse como
expediente histórico, pero la instancia no depende de él tras crearse.

```text
<instancia-foro>/
  AGENTS.md                        # generado, no estado
  CLAUDE.md                        # generado, no estado
  instance.json                    # schema, forum_id, core_root y paquetes/versiones
  dossier/                         # copia literal del expediente y sus fuentes
  corpus/state.json                # desde 4c1: candidatos, decisiones y cierre, con historial
  work/integrity.json              # hashes de archivos gestionados estáticos
```

4c2 no crea `characters/`, `memory/` ni `specialists/`: los dos primeros aparecerán cuando sus
incrementos tengan estado real; los especialistas se aplazan hasta el evaluador técnico del
incremento 11. En particular, un `LITERAL` de combate aprobado no basta por sí solo para prometer
una capacidad que todavía no existe.

Solo las plantillas están en el repo, bajo `core/runtime/templates/`: expediente, configuración y
ambos archivos de instrucciones; más adelante, plantillas de especialistas genéricos. Una política
común `instance-policy.template.md` se inserta entre los marcadores exactos
`<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->` y
`<!-- END ROLEPLAY-AGENT-CORE:COMMON -->` de `AGENTS.template.md` y `CLAUDE.template.md`; un test
compara byte a byte esos bloques generados. Fuera del bloque común solo se permiten instrucciones
propias, también en español: `AGENTS.md` declara su alcance para Codex y la jerarquía de
`AGENTS.md`; `CLAUDE.md` declara el alcance equivalente para Claude. Ambos muestran el mismo patrón
PowerShell renderizado. Ninguno redefine estados, autoridad, decisiones o publicación.
`instance.json` se renderiza desde `instance.template.json` y los demás datos proceden del
expediente, decisiones humanas y comandos del core. En 4c2 `packages` es exactamente `[]` y no hay
especialistas. Nozomu, Naruto, reglas, memoria ni configuración efectiva se añaden a ninguna
plantilla.

#### Uso del core desde el agente generado

La instancia no instala ni copia el core. `instance.json` conserva la ruta absoluta del checkout
confirmada al crearla. Las instrucciones generan comandos PowerShell con rutas entre comillas:

```powershell
Push-Location '<core_root>'
py -3.11 -B -m core.runtime.cli <grupo> <comando> --instance '<instance_root>'
Pop-Location
```

Así `core` se importa desde la raíz del checkout, sin dependencia global ni `PYTHONPATH`. 4c2 no
ofrece `relink`: si el checkout se mueve, los comandos detectan que `core_root` ya no coincide y la
instancia debe recrearse desde el workspace mientras este exista. El CLI valida rutas y versiones,
recupera solo corpus aprobado y carece de comando de publicación. Los documentos futuros del
usuario se podrán editar, pero ningún cambio de corpus o estado se considera válido por editar
JSON/Markdown gestionado directamente: debe pasar por operaciones del core.

#### Persistencia provisional e integridad (incrementos 4a–4f)

Hasta la migración a SQLite del incremento 9 se usa **JSON, no JSONL**. El volumen de esta rebanada
es pequeño y reescribir un documento JSON permite una sustitución atómica portable; un append de
JSONL puede quedar truncado y no se puede confirmar junto con su índice mediante un solo
`os.replace`. Los historiales se conservan como arrays dentro del estado, no se sobrescriben
decisiones previas.

`workspace.json`, `instance.json` y `work/integrity.json` son JSON estricto UTF-8 sin BOM, con LF
final, claves ordenadas, sangría de dos espacios y rechazo de claves duplicadas, constantes no
estándar y claves desconocidas. La forma exacta de la configuración final `instance.json` es:

```json
{
  "core_root": "<ruta absoluta nativa del checkout>",
  "corpus": {
    "path": "corpus/state.json",
    "revision": 11,
    "sha256": "<64 hex de los bytes del sobre>",
    "size": 123,
    "snapshot_sha256": "<64 hex del cierre>"
  },
  "display_name": "<nombre del expediente>",
  "dossier": {
    "files": [
      {"path": "dossier/expediente.md", "sha256": "<64 hex>", "size": 123}
    ],
    "path": "dossier/expediente.md"
  },
  "dossier_version": "<versión_expediente>",
  "forum_id": "<forum_id>",
  "instance_root": "<ruta absoluta nativa de la instancia>",
  "kind": "forum-roleplay-instance",
  "packages": [],
  "schema_version": 1,
  "source_workspace": {
    "workspace_json_sha256": "<64 hex>"
  }
}
```

Tanto el workspace como la instancia usan `dossier.files`, que enumera, en orden lexicográfico
POSIX, el documento y cada `archivo` referenciado una sola vez; `size` y SHA-256 corresponden a
sus bytes copiados exactos. `packages` queda vacío en
la rebanada vertical: la selección/payload de paquetes pertenece al incremento 6 y no se inventa
un paquete neutro. `work/integrity.json` tiene exactamente `schema_version`, `algorithm="sha256"`
y `files`, otra lista ordenada de `{path, sha256, size}`. En el workspace cubre
`workspace.json` y `dossier/`; en la instancia cubre `AGENTS.md`, `CLAUDE.md`, `instance.json`,
`dossier/` y el snapshot cerrado de `corpus/`; nunca se incluye a sí misma. La instancia no guarda
la ruta del workspace y sigue operativa sin él: conserva su huella y una copia íntegra del estado.

Los estados gestionados (`corpus/state.json`, `characters/<id>/state.json` y
`profile.json`) usan un sobre común con claves exactas `schema_version`, `revision`, `content` y
`content_sha256`. El hash se calcula sobre los bytes JSON canónicos compactos
(`ensure_ascii=False`, `sort_keys=True`, `separators=(",", ":")`) del objeto formado por las tres
primeras claves; el archivo legible se serializa con el formato anterior. El corpus es mutable en
el workspace hasta cerrarse y su copia de instancia es inmutable; cada operación futura cambia un
solo estado autoritativo, conserva su historial dentro de `content` y lo sustituye atómicamente.

Toda escritura de archivo se hace en un temporal nuevo del mismo directorio, escribe bytes,
`flush` + `os.fsync` y termina con `os.replace`; el temporal se elimina ante error. La creación de
la carpeta usa un staging hermano y solo lo renombra al final. Esto da atomicidad frente a fallos
del proceso, no promete durabilidad ante pérdida eléctrica ni una transacción entre varios
archivos. Los blobs inmutables se escriben antes que el estado que los referencia; un blob huérfano
tras un fallo se ignora.

La idempotencia se basa en claves de negocio y hashes, no en la hora: repetir exactamente `init`,
un candidato, una decisión, una importación de concepto, una propuesta o un borrador devuelve el
resultado existente sin escribir; reutilizar la misma ID/versión con otro contenido falla cerrado.
`assimilation init` o `instance init` sobre un destino no vacío solo son excepción si ya contienen
respectivamente un workspace o instancia íntegros e idénticos; cualquier otro no vacío se rechaza.
Los comandos validan integridad antes de operar y una edición directa causa fallo hasta restaurar
el archivo o importar el cambio mediante una operación.

Estos hashes detectan ediciones accidentales, **no autentican al actor**: quien tenga los mismos
permisos de escritura puede recalcularlos o modificar el core. No deben presentarse como barrera de
seguridad ni como prueba de intervención humana. El archivo externo de concepto es entrada
editable del usuario; solo una importación por CLI crea una versión gestionada con su hash.

#### Candidatos manuales, decisiones y citas exactas (incrementos 4b–4c1)

En este flujo el agente, trabajando sobre el workspace previo, prepara un JSON de candidato y
ejecuta `assimilation candidate add --workspace <ruta> --input <archivo>`; el usuario también puede
crear candidatos, pero no necesita editar el estado. Crear un candidato no lo aprueba. Las clases son exactamente
`LITERAL`, `INTERPRETATION`, `PROPOSAL` y `UNCERTAINTY`, con dominio `RULES` o `WORLD`; toda
incertidumbre se muestra como `REQUIERE CONFIRMACIÓN` aunque después exista una decisión sobre el
registro.

Cada cita persistida guarda `dossier_section` (valor interno de `DossierSection`), `source_id`,
`source_version`, `source_sha256`, `declared_passage` (string o `null`), `start`, `end` y `quote`.
El JSON de entrada **no** aporta offsets: identifica la declaración por sección, ID, versión y
pasaje declarado, y aporta la cita literal. La CLI busca `quote` sin normalizar en `literal_text`
tal como lo entregó `load_dossier` —incluidos CRLF de archivo y LF canónicos inline— y calcula
`start`/`end` como offsets de caracteres Python, base 0 y rango semiabierto. Si hay varias
coincidencias, falla indicando el recuento; el autor debe ampliar la cita o añadir `occurrence`
base 1, una pista de entrada que no se persiste. Se cuentan también coincidencias solapadas.
La resolución final exige `0 <= start < end <= len(literal_text)`, hash/versión exactos y
`literal_text[start:end] == quote`; línea/columna base 1 son solo diagnóstico. Un `LITERAL` exige
una sola cita y `text == quote`; las otras clases pueden redactar una conclusión distinta, pero
todas sus citas deben resolver. En 4b `WORLD` solo admite fuentes de `setting`, `RULES` las otras
seis secciones de dominio y `Material suelto` no genera candidatos aunque declare sugerencias;
su clasificación queda para el incremento 5.

Una decisión conserva `candidate_id`, versión y SHA-256 del candidato exacto, `ReviewStatus`
(`APPROVED` o `REJECTED`) y un recibo `TTY_NONCE_V1`. El recibo guarda el SHA-256 de la frase
aceptada, no el nonce ni la frase en claro: permite ligar el registro al reto efímero ejecutado sin
presentarlo como autenticación independiente. El payload del recibo se serializa canónicamente y
origina un `SourceRef` con locator
`assimilation://<forum_id>/human-decisions/<decision_id>` y su SHA-256; no se inventan
`observed_at` ni fecha IC. Su `source_id` es `human-decision:<decision_id>` y
`section_or_passage` identifica `candidate:<candidate_id>:v<version>` o `assimilation-closure`.
Repetir la misma decisión devuelve el registro existente sin nuevo reto; una decisión opuesta o
sobre otro hash exige una versión nueva del candidato, no reescribe la anterior.

El cierre de asimilación es otra decisión humana, no una inferencia de la CLI. Solo se ofrece cuando
no queda pendiente ninguna versión vigente —la mayor de cada ID— y cada sección de dominio
`PROVIDED` tiene al menos un `LITERAL` vigente aprobado con cita en esa sección; las versiones
sustituidas siguen auditables y `Material suelto` no bloquea. La CLI muestra por separado
rechazos e `UNCERTAINTY` y el humano confirma el snapshot. El recibo guarda el SHA-256 canónico del
objeto `{candidates, decisions}` —excluye `closure` para evitar circularidad—. Tras cerrar, las API
de alta y decisión rechazan nuevas mutaciones; una edición directa que altere el digest invalida la
recarga y `instance init` exige que el recibo siga coincidiendo. Para corregir un snapshot cerrado
se crea otro workspace; no se sobrescribe el recibo terminal. Cerrar no convierte una
incertidumbre, interpretación o propuesta en literal ni aprueba entradas pendientes.

#### CLI mínimo de la rebanada

`core/runtime/cli.py` usa `argparse`, expone `main(argv: Sequence[str] | None = None) -> int` y se
ejecuta desde el checkout con `py -3.11 -B -m core.runtime.cli`. Texto español legible es la salida
predeterminada; el flag global `--json` anterior al grupo de comandos emite un único objeto JSON a
stdout. Los errores de aplicación van a stderr; en JSON usan
`{"ok":false,"code":"<código>","message":"<texto>"}`. Códigos de salida estables: `0` éxito o
repetición idempotente, `2` uso de `argparse`, `3` entrada/estado/integridad inválidos, `4` destino
inseguro o conflicto de versión/identidad y `5` error de E/S. No se captura `KeyboardInterrupt`.

Subcomandos acumulados: 4a añade `assimilation init --dossier RUTA --workspace RUTA` y
`assimilation status --workspace RUTA`; 4b añade `assimilation source list/show` y `assimilation
candidate add/list/show`; 4c1 añade decisiones/cierre humanos y 4c2,
`instance init --workspace RUTA --output RUTA`, `instance status` e `instance corpus list/show`;
4d1 añade `character concept import/list/show`; 4d2, `character effective show` y
`character proposal add/list/show/approve/reject`; 4e añade `character draft create/list/show` y
`character staff record`. `--workspace` y `--output` son siempre explícitos, sin defaults ni
variables de entorno. No existe ni se reserva `publish`, `send`, `post` o equivalente.

#### Reparto del adaptador manual

En 4a `adapters/manual.py` es exclusivamente la entrada local del expediente: recibe una carpeta,
llama a `load_dossier`, exige `ready_for_assimilation` y devuelve el `LoadedForumDossier` al
creador del workspace. No interpreta, crea candidatos, decide, lee turnos ni publica. En el
incremento 8 se ampliará —detrás de `ForumReader`— para importar capturas locales de turnos y
acreditar identidad y completitud; esa responsabilidad no se anticipa en la rebanada.

#### Creación de personaje y reparto de decisiones

| Paso | Decide/aporta el usuario | Hace el agente, siempre mediante el core |
| --- | --- | --- |
| Expediente | Fuentes, versión/autoridad/vigencia y marcadores `FALTA` o `NO APLICA`; aprueba/rechaza cada candidato exacto y cierra el snapshot revisado. | Valida literales y citas, clasifica solo como candidato, enumera faltantes/contradicciones y marca `REQUIERE CONFIRMACIÓN`; nunca aprueba ni cierra. |
| Instancia | Elige la ruta externa; las decisiones de contenido ya quedaron en el cierre. | Genera atómicamente configuración e instrucciones desde el snapshot; 4c2 no crea especialistas. |
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
- JSON estricto para manifests y el estado provisional hasta SQLite; no JSONL antes del incremento
  9 porque esta fase prioriza sustitución atómica sobre append. `expediente.md` usa la gramática
  cerrada descrita arriba para entrada humana y fuentes; Markdown también puede usarse para
  voz/documentación autorizada. Esto no autoriza lore, reglas ni derivados en paquetes.
  Validadores propios de biblioteca estándar, sin afirmar soporte Markdown general ni JSON Schema
  completo.
- SQLite será el primer repositorio operativo concurrente y sustituirá el JSON provisional en el
  incremento 9, detrás de puertos; transacciones y claves únicas ya demostraron rollback,
  idempotencia y concurrencia. No exponer SQL en contratos de dominio.
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

### Incremento 3 — contrato y carga del expediente (detallado; aprobado)

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

#### Incremento 4a — workspace externo e importación manual (siguiente; detallado)

Objetivo: copiar un expediente listo a un workspace externo íntegro donde 4b pueda preparar
candidatos, sin crear todavía la instancia/agente ni permitir saltarse la aprobación humana.

1. [x] Crear `core/runtime/persistence.py`, `core/runtime/workspace.py`, `core/runtime/cli.py`,
   `adapters/__init__.py` y `adapters/manual.py`; actualizar solo los exports públicos necesarios de
   `core/runtime/__init__.py`. No modificar `core/memory/provenance.py`,
   `core/review/models.py`, `core/runtime/{packages,assimilation}.py` ni sus tests aprobados.
2. [x] En `persistence.py`, implementar solo con biblioteca estándar:
   `PersistenceError(ValueError)` con `code` (`INVALID_STATE` o `IO`) y `reason`,
   `canonical_json_bytes(value: object, *, pretty: bool) -> bytes`,
   `load_strict_json(path: Path) -> object`, `atomic_write_bytes(path: Path, data: bytes) -> None`,
   `encode_state(content: object, *, revision: int) -> bytes` y
   `load_state(path: Path) -> tuple[int, object]`. La forma pretty usa UTF-8, LF final, sangría de
   dos espacios, claves ordenadas y `ensure_ascii=False`; la compacta usa exactamente
   `separators=(",", ":")`. El estado usa el sobre/hash definido en «Persistencia provisional».
   Rechazar BOM, UTF-8/JSON inválido, duplicados, `NaN`/`Infinity`, recursión, schema/hash/tipo
   incoherente y errores de E/S conservando `__cause__`.
3. [x] `atomic_write_bytes` crea un temporal exclusivo en el mismo directorio, escribe bytes,
   `flush` + `os.fsync`, ejecuta `os.replace` y limpia el temporal ante cualquier fallo; nunca abre
   el destino para truncarlo. Un test que sustituye `os.replace` por un fallo debe conservar los
   bytes anteriores. Esta garantía es por archivo y proceso, no una transacción multiarchivo ni una
   promesa frente a pérdida eléctrica.
4. [x] En `workspace.py`, definir `WORKSPACE_SCHEMA_VERSION = 1`,
   `INTEGRITY_SCHEMA_VERSION = 1`, `WorkspaceError(ValueError)` con atributos `code` y `reason`, y
   dataclasses inmutables `ManagedFile(path: str, sha256: str, size: int)`,
   `WorkspaceConfig(schema_version: int, forum_id: str, display_name: str,
   dossier_version: str, core_root: Path, dossier_path: str,
   dossier_files: tuple[ManagedFile, ...])`, `LoadedWorkspace(config: WorkspaceConfig,
   workspace_root: Path, dossier: LoadedForumDossier, corpus_revision: int)` y
   `WorkspaceInitResult(workspace: LoadedWorkspace, created: bool)`. Validar IDs/textos,
   hash/tamaño, rutas POSIX relativas, tipos, orden y unicidad. `code` solo puede ser
   `INVALID_STATE`, `CONFLICT`, `UNSAFE_DESTINATION` o `IO`; la CLI los mapea respectivamente a
   3, 4, 4 y 5.
5. [x] Exponer firmas exactas
   `create_workspace(dossier: LoadedForumDossier, *, dossier_dir: Path, workspace: Path,
   core_root: Path) -> WorkspaceInitResult` y
   `load_workspace(workspace_root: Path, *, expected_core_root: Path | None = None)
   -> LoadedWorkspace`. Reexportar desde `core/runtime/__init__.py` solo constantes, dataclasses,
   error y estas funciones; los helpers de persistencia siguen internos.
6. [x] En `adapters/manual.py`, definir `ManualAdapterError(ValueError)` y
   `load_manual_dossier(dossier_dir: Path) -> LoadedForumDossier`. Llamar al loader aprobado,
   exigir `assess_dossier(...).ready_for_assimilation` y conservar la causa del diagnóstico; una
   opcional `MISSING` no bloquea. No contener `ForumReader`, turnos, candidatos, decisiones,
   modelo ni publicación.
7. [x] `create_workspace` comprueba que dossier cargado y `dossier_dir` corresponden, que
   `core_root` es el checkout absoluto con `core/runtime/cli.py`, y resuelve el workspace explícito.
   Rechazar workspace igual/dentro del checkout; igual, ancestro o descendiente del expediente;
   symlink; padre inexistente/no directorio; controles C0 en rutas; y destino no vacío salvo retry
   idéntico. No crear padres. Todo rechazo previo deja el destino como estaba.
8. [x] Construir en un staging hermano exactamente `workspace.json`, `dossier/`,
   `corpus/state.json` y `work/integrity.json`. Copiar bytes originales de `expediente.md` y cada
   `DossierSourceSpec.path` único, conservando ruta; no copiar no referenciados. Recargar la copia y
   exigir igualdad de `ForumDossier`, literales y hashes. `dossier.files` ordena documento/archivos
   por ruta POSIX y no lista inline por separado.
9. [x] Crear solo `core/runtime/templates/workspace.template.json`; 4a no crea aún plantillas de
   instancia, `AGENTS.md` ni `CLAUDE.md`. Su forma exacta, renderizada con `string.Template` y cada
   valor previamente codificado con `json.dumps`, es:

   ```json
   {
     "core_root": $core_root_json,
     "display_name": $display_name_json,
     "dossier": {"files": $dossier_files_json, "path": "dossier/expediente.md"},
     "dossier_version": $dossier_version_json,
     "forum_id": $forum_id_json,
     "kind": "forum-assimilation-workspace",
     "schema_version": 1
   }
   ```

   Volver a parsear/validar y escribir JSON canónico; no concatenar valores. No hay timestamps,
   credenciales, permisos ni datos temáticos en la plantilla.
10. [x] Inicializar `corpus/state.json` con `revision=0` y contenido exacto
    `{"candidates":[],"closure":null,"decisions":[]}` dentro del sobre común. En 4a es el único
    estado mutable y no se añade a `integrity.json`; su hash autocontenido se valida por separado.
    `work/integrity.json` tiene claves exactas `schema_version`, `algorithm="sha256"` y `files`, y
    cubre `workspace.json` más todo `dossier/`, no a sí mismo.
11. [x] Renombrar el staging al workspace solo tras validar todo; ante error, eliminar únicamente
    ese staging conocido. Si el destino existía vacío, verificar otra vez que sigue vacío antes de
    retirarlo con `rmdir`; hacer inmediatamente `os.replace(staging, workspace)` y, si ese replace
    falla durante el proceso vivo, recrear el directorio vacío. Un corte del proceso entre ambos
    puede dejar la ruta ausente, nunca parcialmente poblada; documentar este límite de Windows.
    Un retry con mismo core, expediente, bytes, template y estado inicial devuelve
    `created=False` sin escribir/cambiar mtimes; cualquier diferencia da
    `WorkspaceError(code="CONFLICT")`.
12. [x] `load_workspace` rechaza root o hijos gestionados symlink, escapes, JSON no canónico/claves
    extra, hashes/tamaños distintos, corpus con sobre inválido, expediente que ya no carga,
    forum/version discordantes y `expected_core_root` distinto. Una edición manual simple de
    expediente/configuración/estado falla; no ofrece reparación ni un flag para recalcular hashes.
13. [x] En `cli.py`, crear `argparse` sin I/O al importar,
    `main(argv: Sequence[str] | None = None) -> int`, flag global `--json` y comandos exactos
    `assimilation init --dossier DOSSIER_DIR --workspace WORKSPACE_DIR` y
    `assimilation status --workspace WORKSPACE_DIR`. Ambos flags de ruta son obligatorios, sin
    entorno/default. `init` compone adaptador + workspace; `status` exige el checkout actual.
    Aplicar códigos 0/2/3/4/5 documentados. Éxitos JSON:
    `{"ok":true,"action":"assimilation.init","created":<bool>,"forum_id":<id>,
    "workspace":<ruta>}` y `{"ok":true,"action":"assimilation.status","forum_id":<id>,
    "integrity":"OK","workspace":<ruta>}`; texto equivalente en español. Terminar con
    `raise SystemExit(main())`; ayuda/parser no contienen publicación.
14. [x] Crear `tests/test_workspace_persistence.py`: JSON pretty/compacto y sobre exactos; loader
    estricto; atomicidad/limpieza; modelos inmutables; rutas/hash/schema; staging e idempotencia.
    Crear `tests/test_manual_adapter.py`: fixture neutra lista, obligatoria faltante, opcional
    faltante permitida, propagación y ausencia de turnos/publicación. Todo inválido en temporal.
15. [x] Crear `tests/test_assimilation_workspace_cli.py`: import sin efectos; flags ausentes; ruta
    relativa; workspace dentro del repo, solapado, symlink, padre ausente, vacío/no vacío; copia
    exacta solo de referenciados; JSON/schema/integridad; texto/JSON/códigos; manipulación de cada
    gestionado/estado; retry sin bytes/mtimes y conflicto. Probar `main` y un happy path con
    `subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", ...], cwd=<checkout>)`.
    Afirmar que `instance`, `publish`, `send` y `post` aún se rechazan.
16. [x] No crear instancia, instrucciones de agente, candidatos/decisiones reales, personajes,
    especialistas, configuración efectiva, secretos, puertos, SQLite ni JSONL. No tocar paquetes,
    `reference/` ni las notas cerradas de los incrementos 1–3.

Criterios de aceptación de 4a:

- El expediente neutro se importa a un workspace externo con bytes/hashes reproducibles; inline
  sigue embebido y un archivo no referenciado no cruza.
- No existe todavía una carpeta de instancia ni `AGENTS.md`/`CLAUDE.md`: 4a no permite eludir la
  aprobación y cierre que habilitarán 4c2.
- Falta de `--workspace`, destino inseguro/conflictivo o fallo previo al rename no deja workspace
  parcial; retry idéntico no escribe y cambiar una entrada falla cerrado.
- `assimilation status` detecta ediciones simples de gestionados/estado, sin afirmar autenticidad
  frente a quien puede recalcular hashes.
- Solo biblioteca estándar; sin red, modelo, SQLite, publicación ni lectura de turnos.

Verificación exacta de 4a desde PowerShell:

```powershell
py -3.11 -B -m unittest tests.test_workspace_persistence tests.test_manual_adapter tests.test_assimilation_workspace_cli -v
py -3.11 -B -m unittest discover -s tests -v
py -3.11 -B -m core.runtime.cli --json assimilation init --dossier tests/fixtures/dossiers/minimal-neutral --workspace <RUTA_TEMP_EXTERNA>
py -3.11 -B -m core.runtime.cli --json assimilation status --workspace <RUTA_TEMP_EXTERNA>
rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/runtime adapters/manual.py core/runtime/templates tests/test_workspace_persistence.py tests/test_assimilation_workspace_cli.py tests/test_manual_adapter.py
git diff --check
git diff --name-only 42e724a -- reference
git status --short
```

El quinto comando termina sin coincidencias y el séptimo sin salida. La comprobación manual usa
una ruta temporal explícita fuera del checkout y se elimina después; no usar un workspace real.
El estado solo incluye `ANALISIS.md` y los archivos enumerados para 4a.

#### Sub-incrementos restantes de la rebanada

4b. [x] **Candidatos manuales citados, aún pendientes (detallado).** Objetivo: permitir que un
    agente prepare candidatos reproducibles a partir de citas literales sin contar offsets, sin
    decidirlos, cerrar la asimilación ni crear una instancia.

    Alcance exacto de producción: modificar `core/runtime/{assimilation,workspace,cli,__init__}.py`.
    `persistence.py` no cambia: reutilizar `load_strict_json`, `load_state`, `encode_state` y
    `atomic_write_bytes`. Crear `tests/test_assimilation_candidates.py` y
    `tests/test_assimilation_cli.py`; no modificar fixtures aprobadas, adaptadores, review,
    paquetes, plantillas ni `reference/`.

    1. En `assimilation.py`, importar `ReviewStatus` y definir:
       - `AssimilationDomain(str, Enum)`: exactamente `RULES` y `WORLD`.
       - `CandidateClass(str, Enum)`: exactamente `LITERAL`, `INTERPRETATION`, `PROPOSAL` y
         `UNCERTAINTY`.
       - `AssimilationError(ValueError)` con `code` y `reason`; códigos admitidos
         `INVALID_STATE`, `CONFLICT` e `IO`.
       - `CandidateCitation(dossier_section: DossierSection, source_id: str,
         source_version: str, source_sha256: str, declared_passage: str | None, start: int,
         end: int, quote: str)`, dataclass `frozen=True, slots=True`.
       - `AssimilationCandidate(candidate_id: str, version: int, domain: AssimilationDomain,
         candidate_class: CandidateClass, text: str, scope: str,
         citations: tuple[CandidateCitation, ...], review_status: ReviewStatus =
         ReviewStatus.PENDING_HUMAN_REVIEW,
         candidate_sha256: str = field(init=False))`, también inmutable.
       - `CandidateAddResult(candidate: AssimilationCandidate, created: bool,
         corpus_revision: int)`, inmutable.
    2. Validar en los constructores tipos exactos (`bool` no es entero), enum real, ID ASCII con
       `[a-z0-9]+(?:-[a-z0-9]+)*`, versión positiva, textos UTF-8 no vacíos y `scope` sin espacios
       exteriores/C0. `text` y `quote` se conservan carácter por carácter tras decodificar JSON y
       pueden contener saltos; deben contener algún carácter no blanco. Las citas son una tupla no
       vacía, no repiten la misma coordenada fuente+`start`+`end`, y satisfacen rango semiabierto.
       Solo se admite `review_status=PENDING_HUMAN_REVIEW`; 4b nunca lo muta.
    3. El JSON de entrada es estricto y tiene exactamente estas claves de raíz:

       ```json
       {
         "candidate_id": "convivencia-respeto",
         "version": 1,
         "domain": "RULES",
         "class": "LITERAL",
         "text": "Trata con respeto al resto de participantes",
         "scope": "foro",
         "citations": [{"dossier_section": "forum_rules", "source_id": "manual-foro", "source_version": "1", "declared_passage": "Convivencia", "quote": "Trata con respeto al resto de participantes"}]
       }
       ```

       Cada cita de entrada exige las cinco claves mostradas; admite únicamente la sexta clave
       opcional `occurrence`, entero base 1. No admite `start`, `end`, `source_sha256`, estado,
       decisión ni hash del candidato. Rechazar claves desconocidas, duplicadas, BOM,
       `NaN`/`Infinity`, UTF-8/JSON inválido y recursión mediante `load_strict_json`; no exigir
       formato pretty/canónico al archivo de entrada.
    4. Resolver cada cita contra una declaración del expediente copiado que coincida exactamente en
       `dossier_section`, `source_id`, `source_version` y `declared_passage` (`null` también es un
       valor exacto). Declaraciones idénticas repetidas se colapsan para esta búsqueda. Cero
       coincidencias falla con los identificadores recibidos. No aceptar `loose_material`, aunque
       tenga `sugerencias`.
    5. Buscar `quote` literalmente, sin `strip`, normalización Unicode ni cambio de finales de
       línea. Enumerar todas las posiciones de inicio, incluidas las solapadas. Con cero, informar
       que la cita no está en ese literal; con más de una y sin `occurrence`, informar el número y
       pedir una cita más larga o `occurrence` base 1; con un índice fuera de rango, informar el
       total. Calcular `start` y `end=start+len(quote)` y copiar el SHA-256 cargado, sin persistir
       `occurrence`. El diagnóstico incluye línea y columna base 1 de cada coincidencia como ayuda,
       pero esos valores no forman identidad.
    6. Aplicar dominio↔sección: `WORLD` solo `setting`; `RULES` exactamente `forum_rules`,
       `character_creation`, `staff_review`, `platform_format`, `combat_system` y
       `ability_technique_creation`. Todas las citas de un candidato deben pertenecer a su dominio.
       `LITERAL` exige una única cita y `text == quote`; las otras clases exigen una o más citas y
       permiten texto distinto. `UNCERTAINTY` sigue mostrándose como `REQUIERE CONFIRMACIÓN`.
    7. Calcular `candidate_sha256` como SHA-256 de la forma JSON compacta canónica del registro con
       claves `candidate_id`, `version`, `domain`, `class`, `text`, `scope`, `citations` y
       `review_status`, excluyendo solo `candidate_sha256`. La lista de citas y su orden forman
       parte del hash. Usar `canonical_json_bytes(..., pretty=False)`; nunca hashear el JSON de
       entrada ni timestamps.
    8. Persistir cada elemento de `content.candidates` con esta forma exacta; `closure` permanece
       `null` y `decisions`, vacía en 4b:

       ```json
       {
         "candidate_id": "convivencia-respeto",
         "candidate_sha256": "<64 hex minúsculas>",
         "citations": [{"declared_passage": "Convivencia", "dossier_section": "forum_rules", "end": 54, "quote": "Trata con respeto al resto de participantes", "source_id": "manual-foro", "source_sha256": "<64 hex minúsculas>", "source_version": "1", "start": 12}],
         "class": "LITERAL",
         "domain": "RULES",
         "review_status": "PENDING_HUMAN_REVIEW",
         "scope": "foro",
         "text": "Trata con respeto al resto de participantes",
         "version": 1
       }
       ```

       Los números del ejemplo son ilustrativos; los tests obtienen los reales desde el literal.
       Al cargar, exigir claves exactas, reconstruir modelos, volver a resolver cada cita contra el
       expediente, comprobar substring/hash y recalcular `candidate_sha256`. Una edición manual,
       fuente inexistente o dato derivado discordante es `INVALID_STATE`.
    9. Añadir firmas públicas exactas en `assimilation.py`:
       `parse_candidate_input(value: object, *, dossier: LoadedForumDossier)
       -> AssimilationCandidate`,
       `decode_candidate_state(content: object, *, dossier: LoadedForumDossier)
       -> tuple[AssimilationCandidate, ...]`, y
       `add_candidate(state_path: Path, *, dossier: LoadedForumDossier,
       expected_revision: int, value: object) -> CandidateAddResult`.
       Reexportar error, enums, modelos y funciones desde `core/runtime/__init__.py`; los helpers de
       serialización y de selección de fuentes siguen privados.
    10. `decode_candidate_state` exige las tres claves de 4a, `closure is None`, `decisions == []`,
        candidatos en orden de inserción y claves `(candidate_id, version)` únicas. Para cada ID,
        las versiones empiezan en 1, son contiguas y aparecen en orden ascendente; la versión mayor
        es la vigente, sin borrar las anteriores. Esto prepara 4c1 para decidir solo versiones
        vigentes y conservar las sustituidas como historial.
    11. `add_candidate` vuelve a cargar el sobre y exige `revision == expected_revision`; valida el
        historial antes de añadir. Una clave nueva debe ser versión 1 o exactamente la siguiente de
        ese ID. Repetir la misma clave con el mismo registro/hash devuelve `created=False`, no
        escribe y conserva revisión/mtime; misma clave con otra resolución o contenido, salto de
        versión y una versión nueva con el mismo payload semántico que la anterior —ignorando solo
        `version` y `candidate_sha256`— son `CONFLICT`. Un alta real añade al final, incrementa la
        revisión en uno y sustituye el estado con
        `atomic_write_bytes(encode_state(...))`. Envolver `PersistenceError` conservando código,
        causa y mensaje. No prometer exclusión entre procesos; los locks llegan en el incremento 9.
    12. En `workspace.py`, ampliar `LoadedWorkspace` con
        `candidates: tuple[AssimilationCandidate, ...]`. Reordenar `_load_workspace` para cargar el
        expediente antes de validar el contenido del corpus y sustituir `_check_corpus` por la
        decodificación completa anterior. El estado inicial de 4a sigue válido y devuelve tupla
        vacía. No relajar integridad, rutas, junctions ni la comprobación del checkout.
    13. Añadir comandos exactos, todos con `--workspace RUTA` obligatorio:
        - `assimilation source list`;
        - `assimilation source show --section SECCIÓN --source-id ID --source-version VERSIÓN
          [--declared-passage TEXTO | --without-declared-passage]`;
        - `assimilation candidate add --input ARCHIVO`;
        - `assimilation candidate list`;
        - `assimilation candidate show --candidate-id ID [--version N]` (sin versión muestra la
          última; nunca la presupone en una operación de decisión futura).
        `SECCIÓN` usa los siete valores internos y `loose_material`. `source list/show` son vistas
        de solo lectura: incluyen el material suelto como `candidate_eligible=false`, no lo
        clasifican ni cambian revisión/mtime. Si `source show` no recibe selector de pasaje y hay
        varias declaraciones, falla e indica las opciones; las dos opciones de pasaje son
        mutuamente excluyentes.
    14. Salidas JSON de éxito, emitidas con `_emit`, tienen exactamente estas claves de raíz:
        - source list: `ok`, `action="assimilation.source.list"`, `sources`, `workspace`;
        - source show: `ok`, `action="assimilation.source.show"`, `source`, `workspace`;
        - candidate add: `ok`, `action="assimilation.candidate.add"`, `candidate_id`,
          `candidate_sha256`, `corpus_revision`, `created`, `version`, `workspace`;
        - candidate list: `ok`, `action="assimilation.candidate.list"`, `candidates`,
          `corpus_revision`, `workspace`;
        - candidate show: `ok`, `action="assimilation.candidate.show"`, `candidate`,
          `corpus_revision`, `workspace`.
        `sources` conserva el orden del expediente y cada elemento tiene exactamente
        `candidate_eligible`, `declared_passage`, `dossier_section`, `domain`, `source_id`,
        `source_sha256`, `source_version`; `source` añade `literal_text`. `candidates` en list usa
        resúmenes con `candidate_id`, `candidate_sha256`, `class`, `domain`, `review_status` y
        `version`; show devuelve el registro persistido completo. No incluir rutas fuente originales
        ni locator del expediente.
    15. Salida texto exacta: source list imprime una línea por fuente
        `SECCIÓN | ID | vVERSIÓN | pasaje=VALOR | sha256=HASH | dominio=DOMINIO | candidato=SI|NO`;
        `VALOR` y `DOMINIO` usan el literal `null` cuando no existen. Candidate list imprime una
        línea por candidato:
        `ID vVERSIÓN | CLASE | DOMINIO | PENDING_HUMAN_REVIEW | sha256=HASH` y, para
        `UNCERTAINTY`, añade ` | REQUIERE CONFIRMACIÓN`. Las listas vacías imprimen respectivamente
        `No hay fuentes.` o `No hay candidatos.`. Source show imprime primero la misma línea y luego
        el literal como `LÍNEA | CONTENIDO`, con número base 1 y ancho calculado; es una ayuda visual,
        no texto copiable exacto (el JSON sí entrega `literal_text`). Candidate show imprime su
        resumen, una línea por cita con sección/ID/versión/pasaje/SHA/rango y, tras `Texto:`, el
        texto sin modificar. Candidate add reutiliza el resumen precedido por `Candidato añadido:`
        o `Candidato ya existente:` y termina con `Revisión del corpus: N.`.
    16. Mantener el contrato de error JSON exacto `{"ok":false,"code","message"}`. Entrada,
        selector, cita, no encontrado o estado/hash inválido → código 3 `INVALID_STATE`; identidad,
        versión o revisión concurrente conflictiva → 4 `CONFLICT`; E/S al leer entrada o estado →
        5 `IO`; uso de argparse → 2. En texto, solo errores a stderr. No capturar
        `KeyboardInterrupt` ni introducir TTY/nonce en 4b.
    17. `tests/test_assimilation_candidates.py`: inmovilidad/enums/validación de cada modelo; forma
        de entrada y persistida exactas; cálculo de hash; cita única y multilínea, CRLF de archivo,
        Unicode, coincidencias cero/una/múltiples/solapadas y `occurrence`; pasaje nulo/declarado;
        seis secciones RULES y única WORLD; cruces de dominio; `LITERAL` y las otras clases;
        material suelto; claves/tipos/UTF-8; carga manipulada; versiones contiguas, vigente, retry
        sin escritura y conflictos; fallo de replace conserva estado anterior.
    18. `tests/test_assimilation_cli.py`: import sin efectos; ayuda y flags; los cinco comandos por
        `main`; source list/show texto y JSON, líneas y ambigüedad; add/list/show de las cuatro
        clases; última versión frente a `--version`; salidas/claves/códigos/stdout/stderr exactos;
        input ausente o inválido; workspace manipulado; subprocess happy path. Afirmar que no
        existen comandos de decisión, cierre, instancia, publicación, modelo, red ni turnos.

    Criterios de aceptación de 4b:

    - El autor solo transcribe una cita literal e identidad de fuente; el core calcula y persiste
      offsets/hash exactos, y una cita repetida nunca se resuelve por suposición.
    - Todo candidato válido queda inmutable y `PENDING_HUMAN_REVIEW`; no alimenta todavía consultas,
      cierre, instancia, personaje ni canon.
    - El registro conserva historia por ID/versión, un retry exacto no escribe y ninguna edición del
      estado o fuente pasa la recarga.
    - `source show` facilita citar sin crear una segunda representación autoritativa; material
      suelto se puede inspeccionar pero no citar en candidatos.
    - Solo biblioteca estándar; sin TTY/nonce aún, modelo, red, SQLite, publicación o contenido
      temático.

    Verificación exacta de 4b desde PowerShell:

    ```powershell
    py -3.11 -B -m unittest tests.test_assimilation_candidates tests.test_assimilation_cli -v
    py -3.11 -B -m unittest discover -s tests -v
    py -3.11 -B -m core.runtime.cli --json assimilation source list --workspace <RUTA_TEMP_EXTERNA>
    py -3.11 -B -m core.runtime.cli --json assimilation candidate add --workspace <RUTA_TEMP_EXTERNA> --input <CANDIDATO_JSON>
    py -3.11 -B -m core.runtime.cli --json assimilation candidate show --workspace <RUTA_TEMP_EXTERNA> --candidate-id convivencia-respeto --version 1
    rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/runtime tests/test_assimilation_candidates.py tests/test_assimilation_cli.py
    git diff --check
    git diff --name-only 91289a7 -- reference
    git status --short
    ```

    El `rg` y el diff de `reference/` terminan sin salida. La comprobación manual parte de un
    workspace temporal externo creado por 4a, usa una copia temporal del JSON de entrada y elimina
    ambos al terminar; no se usa un workspace real.

4c1. [x] **Decisiones y cierre con barrera humana (detallado).** Objetivo: registrar decisiones
     definitivas sobre candidatos vigentes y cerrar un snapshot exacto, sin crear todavía la
     instancia ni plantillas.

     Alcance exacto: modificar `core/runtime/{assimilation,workspace,cli,__init__}.py`; crear
     `tests/test_assimilation_decisions.py` y `tests/test_assimilation_decision_cli.py`.
     `persistence.py`, `core/review/models.py`, `core/memory/provenance.py`, adaptadores, plantillas,
     paquetes y `reference/` no cambian: se reutilizan `ReviewStatus`, `SourceRef` y las primitivas
     de estado atómico ya aprobadas.

     1. Añadir en `assimilation.py`, todos inmutables (`frozen=True, slots=True`):
        - `HumanConfirmationReceipt(method: str, confirmation_sha256: str)`, donde el único método
          admitido es `TTY_NONCE_V1` y el hash son 64 hex minúsculas.
        - `AssimilationDecision(decision_id: str, candidate_id: str, candidate_version: int,
          candidate_sha256: str, review_status: ReviewStatus,
          receipt: HumanConfirmationReceipt, evidence: SourceRef)`; solo `APPROVED` o `REJECTED`.
        - `AssimilationClosure(closure_id: str, base_revision: int, snapshot_sha256: str,
          receipt: HumanConfirmationReceipt, evidence: SourceRef)`, con ID exacta
          `assimilation-closure`.
        - `AssimilationState(candidates: tuple[AssimilationCandidate, ...],
          decisions: tuple[AssimilationDecision, ...], closure: AssimilationClosure | None)`,
          `DecisionResult(decision, created, corpus_revision)` y
          `ClosureResult(closure, created, corpus_revision)`.
        - `Terminal(Protocol)` con firmas `is_interactive() -> bool`, `write(text: str) -> None` y
          `read_line() -> str | None`. `None` significa EOF. No incluye método para aportar nonce.
     2. `decode_candidate_state` pasa a
        `decode_candidate_state(content: object, *, dossier: LoadedForumDossier, revision: int)
        -> AssimilationState`. Conserva todas las comprobaciones 4b y además decodifica decisiones
        y cierre con claves exactas, reconstruye `SourceRef`, recalcula todos los hashes y verifica
        referencias. `workspace._load_workspace` le pasa la revisión del sobre; `LoadedWorkspace`
        añade `decisions` y `closure` sin eliminar `candidates`.
     3. Cada decisión usa `decision_id="candidate:<candidate_id>:v<version>"`, único y derivable.
        Debe apuntar a una versión existente y al SHA exacto. Puede permanecer sobre una versión
        luego sustituida, pero una decisión nueva solo se admite para la versión mayor de ese ID.
        Hay como máximo una decisión por versión: repetir mismo estado/hash es idempotente; el
        opuesto o un hash distinto es `CONFLICT` y exige crear otra versión del candidato.
     4. Forma persistida exacta de cada elemento de `content.decisions`:

        ```json
        {
          "candidate_id": "convivencia-respeto",
          "candidate_sha256": "<hash del candidato>",
          "candidate_version": 1,
          "decision_id": "candidate:convivencia-respeto:v1",
          "evidence": {"locator": "assimilation://foro-neutral/human-decisions/candidate%3Aconvivencia-respeto%3Av1", "section_or_passage": "candidate:convivencia-respeto:v1", "sha256": "<hash del payload del recibo>", "source_id": "human-decision:candidate:convivencia-respeto:v1"},
          "receipt": {"confirmation_sha256": "<hash de la frase aceptada>", "method": "TTY_NONCE_V1"},
          "review_status": "APPROVED"
        }
        ```

        El SHA de `evidence` se calcula sobre JSON compacto canónico del registro excluyendo
        `evidence`; el locator codifica `decision_id` con percent-encoding y `safe=""`. No se
        guardan `observed_at`, fecha IC, usuario, hora, nonce ni frase en claro.
     5. El reto usa `secrets.choice` ocho veces sobre el alfabeto exacto
        `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`: 32 símbolos sin `I`, `O`, `0` ni `1`, 40 bits de
        espacio y lectura razonable. No existe parámetro, archivo, variable de entorno, semilla ni
        callback para sustituir el nonce en producción; los tests pueden parchear `secrets.choice`
        dentro del módulo, nunca mediante la CLI.
     6. Firmas públicas exactas:
        `record_candidate_decision(state_path: Path, *, dossier: LoadedForumDossier,
        expected_revision: int, candidate_id: str, version: int,
        review_status: ReviewStatus, terminal: Terminal) -> DecisionResult` y
        `close_assimilation(state_path: Path, *, dossier: LoadedForumDossier,
        expected_revision: int, terminal: Terminal) -> ClosureResult`. Reexportar los modelos,
        protocolo y funciones; helpers de reto, hash y forma JSON quedan privados.
     7. La API exige primero `terminal.is_interactive()`, comprueba precondiciones e idempotencia y
        solo crea el nonce para una mutación nueva. Para una decisión nueva muestra por
        `terminal.write`, exactamente y con LF:

        ```text
        DECISIÓN HUMANA REQUERIDA
        Candidato: <candidate_id>
        Versión: <version>
        SHA-256: <candidate_sha256>
        Decisión: APROBAR|RECHAZAR
        Escribe exactamente: APROBAR|RECHAZAR <candidate_id> v<version> <nonce>
        >␠
        ```

        `␠` representa un espacio ASCII: la última salida son los dos bytes `> `, sin LF. Las
        frases exactas son
        `APROBAR <id> v<n> <nonce>` y `RECHAZAR <id> v<n> <nonce>`; ID y versión son ASCII por el
        contrato 4b. Se permite un solo intento. Al leer, quitar únicamente un terminador LF y el
        CR inmediatamente anterior; no hacer `strip`, case-fold ni normalización Unicode.
     8. En la CLI real, una clase privada `_SystemTerminal` devuelve exactamente
        `sys.stdin.isatty() and sys.stdout.isatty()`, escribe siempre mediante `_write_exact` y lee
        con `sys.stdin.readline()` (`""` → `None`). No se exige TTY a stderr: redirigir solo errores
        no permite responder al reto y evita romper usos legítimos. La terminal integrada de
        VS Code en Windows es una consola real y satisface ambas comprobaciones; PowerShell con
        stdout o stdin redirigido falla antes de generar nonce o leer entrada y no escribe estado.
     9. Respuesta distinta consume el único intento y produce `INVALID_STATE`/salida 3 sin escribir.
        EOF hace lo mismo con mensaje de cancelación. `KeyboardInterrupt`/Ctrl+C no se captura,
        conserva el contrato actual y no escribe porque la confirmación precede a la mutación; si
        interrumpe durante la sustitución se aplican las garantías atómicas ya documentadas.
     10. Tras recibir la frase exacta, volver a cargar el estado y exigir la misma revisión y el
         mismo sujeto antes de escribir; un cambio concurrente es `CONFLICT`. Después se calcula
         `confirmation_sha256=SHA256(frase UTF-8 sin terminador)`, se crea el recibo/evidencia y se
         añade la decisión al final del historial con revisión +1 y `atomic_write_bytes`. El nonce
         no se guarda en claro porque deja de tener uso al aceptar la frase; el hash de la frase
         registra el reto aceptado sin autenticar al actor ni convertirse en secreto.
     11. `add_candidate` decodifica el estado ampliado, conserva `decisions` en vez de reiniciarlas
         y sigue permitiendo una versión nueva antes del cierre. Si `closure` existe, rechaza toda
         alta nueva con `CONFLICT`; el cierre es terminal y una corrección requiere otro workspace.
         Un retry exacto de candidato o decisión ya existente sigue sin reto, escritura ni cambio
         de mtime/revisión.
     12. Para cerrar, todas las versiones vigentes —máxima por ID— deben tener una decisión exacta;
         las sustituidas pendientes no bloquean. Cada sección `PROVIDED` debe estar cubierta por al
         menos un `LITERAL` vigente `APPROVED` que la cite. `MISSING`, `NOT_APPLICABLE` y material
         suelto no exigen cobertura. Un `REJECTED` no es utilizable; un `UNCERTAINTY`, incluso
         aprobado, continúa como `REQUIERE CONFIRMACIÓN` y no satisface cobertura literal.
     13. `snapshot_sha256` es SHA-256 del JSON compacto canónico exacto
         `{"candidates":[...],"decisions":[...]}` reconstruido desde los modelos, sin `closure`.
         El prompt de cierre enumera además IDs/versiones rechazadas e incertidumbres vigentes, en
         el orden de los candidatos vigentes y separados por `, `, y muestra exactamente:

         ```text
         CIERRE HUMANO REQUERIDO
         Foro: <forum_id>
         Revisión del corpus: <revision>
         Snapshot SHA-256: <snapshot_sha256>
         Vigentes: <total>; aprobados: <n>; rechazados: <n>
         Rechazados: <id vN, ...>|ninguno
         Incertidumbres: <id vN, ...>|ninguna
         Escribe exactamente: CERRAR <forum_id> r<revision> <nonce>
         >␠
         ```

         La frase es `CERRAR <forum_id> r<revision> <nonce>`, con las mismas reglas, único intento y
         segunda lectura del estado. El cierre se escribe con revisión +1.
     14. Forma exacta de `content.closure`:

         ```json
         {
           "base_revision": 7,
           "closure_id": "assimilation-closure",
           "evidence": {"locator": "assimilation://foro-neutral/human-decisions/assimilation-closure", "section_or_passage": "assimilation-closure", "sha256": "<hash del payload del recibo>", "source_id": "human-decision:assimilation-closure"},
           "receipt": {"confirmation_sha256": "<hash de la frase aceptada>", "method": "TTY_NONCE_V1"},
           "snapshot_sha256": "<hash canónico de candidates+decisions>"
         }
         ```

         Al cargar, exigir `base_revision + 1 == revision`, digest vigente, evidencia recalculada y
         todas las precondiciones de cierre. Alterar candidato, decisión, cierre, revisión o hash —
         incluso recalculando solo el sobre— falla cerrado. Repetir un cierre íntegro devuelve el
         existente sin reto ni escritura.
     15. Añadir comandos exactos:
         - `assimilation candidate approve --workspace RUTA --candidate-id ID --version N`;
         - `assimilation candidate reject --workspace RUTA --candidate-id ID --version N`;
         - `assimilation decision list --workspace RUTA` (solo lectura);
         - `assimilation close --workspace RUTA`.
         La versión es siempre obligatoria en decisiones. No admitir `--yes`, `--force`,
         `--nonce`, `--confirmation`, `--input`, stdin no TTY ni equivalentes. Los tres comandos
         humanos rechazan el flag global `--json` con `INVALID_STATE`/3 antes del reto: no hay modo
         de éxito automatizable ni se mezclan prompt y JSON. `decision list` sí conserva texto/JSON
         normal. En texto imprime por decisión
         `<id> v<n> | APPROVED|REJECTED | sha256=<candidate_sha256> | evidencia=<evidence_sha256>`.
         En JSON usa exactamente las claves de raíz `ok`,
         `action="assimilation.decision.list"`, `decisions`, `corpus_revision`, `workspace`; cada
         resumen contiene `candidate_id`, `candidate_sha256`, `candidate_version`, `decision_id`,
         `evidence_sha256` y `review_status`.
     16. Tras éxito interactivo, el texto exacto final es
         `Decisión registrada: <id> v<n> | APPROVED|REJECTED | sha256=<candidate_sha256>` o
         `Asimilación cerrada: <forum_id> | revisión base <n> | snapshot sha256=<hash>`, seguido de
         `Revisión del corpus: <n>.`; el retry cambia «registrada/cerrada» por «ya existente/ya
         cerrada». Todo pasa por `_write_exact`. Mantener errores JSON exactos para comandos no
         interactivos y códigos 0/2/3/4/5 existentes.
     17. La costura `Terminal` se usa para éxitos **solo en tests de la API Python**. La CLI siempre
         construye `_SystemTerminal` sin fábrica inyectable. Un agente hostil puede importar el
         módulo y pasar un terminal falso, o manejar una pseudo-TTY/modificar el core: es el límite
         aceptado de la opción A, no una garantía criptográfica y debe constar en docstrings y
         mensajes sin presentarse como seguridad fuerte.
     18. `tests/test_assimilation_decisions.py`: modelos/forma/hash/evidencia; referencias y estado
         manipulado; decisión vigente, sustitución e idempotencia; estados opuestos; preservación al
         añadir v2; cobertura por sección; pendientes/rechazos/incertidumbres; digest y cierre
         terminal; retry/mtime; fake `Terminal` para TTY/no TTY, prompts/frases exactos, alfabeto y
         longitud, un intento, CRLF, espacios/case, EOF, Ctrl+C y cambio entre prompt/escritura;
         fallo de replace conserva los bytes anteriores; el JSON persistido no contiene nonce.
     19. `tests/test_assimilation_decision_cli.py`: parser y comandos exactos; versión requerida;
         `decision list` texto/JSON; stdout o stdin no TTY, `--json` y ausencia de cualquier bypass;
         errores/códigos/salidas por `_write_exact`; subprocess con stdout redirigido que falla sin
         mutar. No simular una TTY para éxito CLI: esos éxitos se cubren por la API y se comprueban
         manualmente una vez en terminal integrada.

     Criterios: ninguna mutación humana ocurre sin frase exacta en stdin+stdout TTY; cada decisión
     y cierre se recarga y verifica contra candidato/snapshot exactos; solo aprobados vigentes
     pueden cubrir el corpus; cierre terminal e idempotencia no pierden historial; no hay instancia,
     plantilla, modelo, red, publicación, SQLite ni secretos.

     Verificación exacta de 4c1 desde PowerShell:

     ```powershell
     py -3.11 -B -m unittest tests.test_assimilation_decisions tests.test_assimilation_decision_cli -v
     py -3.11 -B -m unittest discover -s tests -v
     py -3.11 -B -m core.runtime.cli assimilation candidate approve --workspace <RUTA_TEMP_EXTERNA> --candidate-id <ID> --version 1
     py -3.11 -B -m core.runtime.cli assimilation close --workspace <RUTA_TEMP_EXTERNA>
     rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/runtime tests/test_assimilation_decisions.py tests/test_assimilation_decision_cli.py
     git diff --check
     git diff --name-only 91205fc -- reference
     git status --short
     ```

     Los dos comandos interactivos se ejecutan manualmente en una terminal integrada real sobre un
     workspace temporal; se prueba además que redirigir stdout los bloquea. El `rg` y el diff de
     `reference/` terminan sin salida.

4c2. [x] **Instancia cerrada e instrucciones generadas (detallado).** Objetivo: materializar desde
     un workspace cerrado una instancia externa, autocontenida y solo consultable, con instrucciones
     listas para Codex y Claude; no añadir personaje, memoria, especialista ni publicación.

     **Alcance cerrado y archivos.** Crear `core/runtime/instance.py` y las cuatro plantillas
     `core/runtime/templates/{instance.template.json,instance-policy.template.md,
     AGENTS.template.md,CLAUDE.template.md}`; modificar `core/runtime/{cli,__init__}.py`; crear
     `tests/test_{instance,instance_cli,instance_templates}.py`. `assimilation.py`, `workspace.py` y
     `persistence.py` son dependencias ya aprobadas y no se modifican salvo un defecto demostrado
     por estos tests. No tocar otros archivos, `reference/`, las notas inferiores ni los formatos
     persistidos de 4a–4c1.

     **Modelo y API de `instance.py`.** Constantes: `INSTANCE_SCHEMA_VERSION = 1`,
     `INSTANCE_KIND = "forum-roleplay-instance"`, `INSTANCE_FILE = "instance.json"`,
     `INSTANCE_CORPUS = "corpus/state.json"`, `INSTANCE_INTEGRITY = "work/integrity.json"` y los
     cuatro paths de plantilla. Añadir modelos `frozen=True, slots=True`:

     - `InstanceCorpus(path: str, revision: int, sha256: str, size: int,
       snapshot_sha256: str)`; path exacto `corpus/state.json`, revisión no negativa, tamaño no
       negativo y hashes SHA-256 minúsculos.
     - `SourceWorkspace(workspace_json_sha256: str)`; es una huella, no autenticación ni vínculo.
     - `InstanceConfig(schema_version: int, forum_id: str, display_name: str,
       dossier_version: str, core_root: Path, instance_root: Path, dossier_path: str,
       dossier_files: tuple[ManagedFile, ...], corpus: InstanceCorpus,
       source_workspace: SourceWorkspace, packages: tuple[str, ...])`; en 4c2 `packages == ()`.
     - `ApprovedCorpusEntry(candidate: AssimilationCandidate, decision: AssimilationDecision)`;
       valida misma clave/hash y `decision.review_status is APPROVED`.
     - `LoadedInstance(config: InstanceConfig, instance_root: Path, dossier: LoadedForumDossier,
       corpus_revision: int, candidates: tuple[AssimilationCandidate, ...],
       decisions: tuple[AssimilationDecision, ...], closure: AssimilationClosure)` e
       `InstanceInitResult(instance: LoadedInstance, created: bool)`.
     - `InstanceError(code: str, reason: str)` admite exactamente `INVALID_STATE`, `CONFLICT`,
       `UNSAFE_DESTINATION`, `IO`.

     Firmas públicas exactas:

     ```python
     def create_instance(workspace_root: Path, *, output: Path,
                         core_root: Path) -> InstanceInitResult: ...
     def load_instance(instance_root: Path, *,
                       expected_core_root: Path | None = None) -> LoadedInstance: ...
     def approved_corpus(instance: LoadedInstance) -> tuple[ApprovedCorpusEntry, ...]: ...
     def get_approved_candidate(instance: LoadedInstance, *, candidate_id: str,
                                version: int) -> ApprovedCorpusEntry: ...
     ```

     `core/runtime/__init__.py` reexporta esos seis modelos, `InstanceError`, las cuatro funciones e
     `INSTANCE_SCHEMA_VERSION`, sin retirar ningún export previo.

     `approved_corpus` recorre `AssimilationState.current_versions()` en su orden estable y conserva
     solo las que tienen decisión efectiva `APPROVED`; no devuelve pendientes, rechazadas ni
     versiones sustituidas. Conserva `UNCERTAINTY` aprobada con `requires_confirmation=True`: puede
     consultarse como incertidumbre, nunca convertirse en hecho por la aprobación.
     `get_approved_candidate` exige la versión explícita y que sea a la vez vigente y aprobada; en
     cualquier otro caso da `INVALID_STATE` sin caer implícitamente a otra versión.

     **Forma persistida y copia.** `instance.template.json` se parsea con `parse_strict_json` y se
     reemite mediante `canonical_json_bytes(..., pretty=True)`. Su contenido completo es:

     ```json
     {
       "core_root": $core_root_json,
       "corpus": {
         "path": "corpus/state.json",
         "revision": $corpus_revision,
         "sha256": $corpus_sha256_json,
         "size": $corpus_size,
         "snapshot_sha256": $snapshot_sha256_json
       },
       "display_name": $display_name_json,
       "dossier": {
         "files": $dossier_files_json,
         "path": "dossier/expediente.md"
       },
       "dossier_version": $dossier_version_json,
       "forum_id": $forum_id_json,
       "instance_root": $instance_root_json,
       "kind": "forum-roleplay-instance",
       "packages": [],
       "schema_version": 1,
       "source_workspace": {
         "workspace_json_sha256": $workspace_json_sha256_json
       }
     }
     ```

     Los valores `_json` son `json.dumps(..., ensure_ascii=False)`; enteros se sustituyen sin
     comillas. `core_root` e `instance_root` son absolutos, resueltos y con spelling canónico.
     `source_workspace` **no guarda la ruta**: el hash de los bytes canónicos de `workspace.json`,
     los metadatos repetidos, los hashes del expediente y los dos hashes del corpus permiten
     cotejar el origen sin crear una dependencia móvil ni filtrar una ruta local innecesaria.

     Copiar byte a byte todos los archivos declarados de `dossier/` y el `corpus/state.json`
     completo del workspace, incluido historial, recibos, decisiones y cierre. No copiar
     `workspace.json`, su lock ni `work/integrity.json`, y no generar `approved.json`. El estado se
     carga con `load_state` + `decode_candidate_state`; se exige `closure is not None`, que
     `closure.snapshot_sha256` ya haya superado su validación contra candidatos/decisiones y que no
     exista `corpus/state.json.lock` (si existe, `CONFLICT` con su ruta). `InstanceCorpus.sha256`
     cubre los bytes exactos del sobre;
     `snapshot_sha256` cubre el contenido previo al cierre; el sobre conserva además su hash propio.

     `work/integrity.json` mantiene la forma de 4a (`schema_version: 1`, `algorithm: "sha256"`,
     `files` ordenados de `ManagedFile`) y cubre exactamente `AGENTS.md`, `CLAUDE.md`,
     `instance.json`, todos los archivos declarados bajo `dossier/` y `corpus/state.json`; no se
     incluye a sí mismo. Layout exacto de 4c2: esos tres archivos raíz y solo `dossier/`, `corpus/`
     y `work/`; no crear `characters/`, `memory/`, `specialists/` ni directorios vacíos.

     **Seguridad de rutas, atomicidad e idempotencia.** Reproducir en `instance.py` el algoritmo de
     4a, sin cambiar su contrato: identidad por ruta absoluta/real/normcase y prefijos de dispositivo
     normalizados; rechazo de symlinks y junctions en cada componente; `output` explícito, padre ya
     existente, carpeta inexistente o vacía; rechazo si output coincide, contiene o está contenido
     en el checkout o el workspace, incluso con spelling alternativo. Leer solo archivos regulares.
     Crear un sibling `.<nombre>.staging-<secrets.token_hex(8)>`, escribir con `xb`+flush+fsync,
     recargar allí y publicar con `os.replace`; nunca sobrescribir el ganador de una carrera.
     El destino vacío que cambie, un árbol extranjero o una carrera distinta da `CONFLICT`; una
     carrera con árbol byte a byte idéntico devuelve `created=False`. Limpiar staging como en 4a e
     informar el path si no se puede borrar.

     Antes de preparar y justo antes de publicar, volver a `load_workspace(...,
     expected_core_root=core_root)`, comprobar ausencia del lock y comparar bytes de
     `workspace.json`, dossier gestionado y corpus con la primera lectura; si cambia, abortar con
     `CONFLICT`. El cierre es terminal, por lo que ninguna API aprobada puede mutarlo; esta doble
     lectura protege la carrera ordinaria sin introducir otro cerrojo. Un retry sobre destino no
     vacío solo es idempotente si `_tree_bytes(output)` coincide exactamente con el árbol que se
     generaría ahora; no reescribe bytes ni mtimes. `instance init` es una operación normal sin TTY,
     nonce ni confirmación: crea archivos elegidos por el usuario, pero no toma una decisión sobre
     contenido ya cerrado.

     **Recarga.** `load_instance` rechaza links/junctions, JSON no canónico, claves extra/faltantes,
     paths o hashes inválidos, extras dentro de `dossier/`/`corpus/`/`work/`, archivos raíz extra y
     cualquier byte gestionado alterado. Comprueba identidad de `instance_root`, y de `core_root`
     cuando se pasa `expected_core_root`; recarga expediente y estado, exige cierre válido y compara
     forum/dossier, revisión, tamaño, hash del sobre y snapshot con `instance.json`. También vuelve a
     renderizar ambos archivos de instrucciones para la raíz declarada y exige bytes idénticos. La
     recarga privada del staging recibe `logical_root=output`: lee del staging, pero valida config y
     plantillas contra el destino final; la API pública usa la raíz física y exige identidad. Tras
     crearla, `status` y las consultas no abren el workspace: si este se mueve o borra, la instancia
     sigue funcionando. No hay sincronización; cualquier corrección exige otro workspace y otra
     instancia. Si se mueve el checkout o la propia instancia, falla cerrado; 4c2 no implementa
     relink.

     **Plantillas de instrucciones.** Todos los archivos son UTF-8 sin BOM, LF y newline final.
     `instance-policy.template.md` contiene **exactamente**, sin marcadores:

     ```text
     ## Invariantes obligatorias

     - No ejecutes nunca comandos de decisión humana, incluidos `assimilation candidate approve`, `assimilation candidate reject`, `assimilation close` y sus equivalentes futuros. Muestra al usuario el comando exacto y pídele que lo ejecute personalmente en una terminal interactiva.
     - Usa únicamente versiones vigentes del corpus con decisión APPROVED y pertenecientes al snapshot cerrado válido. PENDING_HUMAN_REVIEW, REJECTED, versiones sustituidas y material no clasificado no son utilizables.
     - BORRADOR, APROBADO, PUBLICADO y CANON son estados distintos. Ninguno implica automáticamente otro; una aprobación tampoco implica aprendizaje ni utilizabilidad.
     - No publiques, envíes ni conviertas propuestas, incertidumbres, borradores o resultados pendientes en hechos. No existe comando de publicación en este alcance.
     - No edites directamente estados JSON gestionados ni recalcules sus hashes. Usa los comandos del core y conserva procedencia, citas y versiones exactas.
     ```

     `AGENTS.template.md` contiene exactamente (el valor de `$common_policy` termina en LF):

     ````text
     # Instrucciones de la instancia del foro

     Este `AGENTS.md` rige esta carpeta y todas sus subcarpetas para Codex. Un `AGENTS.md` más específico puede concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados.

     <!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->
     $common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->

     ## Consultas disponibles

     Ejecuta el core desde su checkout con estos patrones PowerShell ya renderizados:

     ```powershell
     Push-Location '$core_root_ps'
     py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'
     py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'
     py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_DEL_CANDIDATO' --version 1
     Pop-Location
     ```

     `corpus list` devuelve solo versiones vigentes aprobadas. `corpus show` exige el ID y la versión mostrados por la lista y presenta texto, decisión y citas exactas. Una entrada `UNCERTAINTY` sigue requiriendo confirmación aunque esté aprobada. Estos comandos son de solo lectura.

     ## Trabajo posterior

     En 4d el concepto de personaje lo aportará la persona y las mejoras del agente serán propuestas separadas; en 4e la ficha seguirá siendo un borrador distinto de la respuesta del staff. Hasta que el core implemente esas operaciones, no inventes comandos ni crees o edites sus JSON. Si una operación futura requiere decisión humana, muestra a la persona el comando exacto y espera a que ella lo ejecute en su propia terminal.
     ````

     `CLAUDE.template.md` contiene exactamente:

     ````text
     # Instrucciones de la instancia del foro

     Este `CLAUDE.md` da a Claude las instrucciones de proyecto para esta carpeta y todas sus subcarpetas. Instrucciones más específicas pueden concretar trabajo futuro, pero no debilitar el bloque común. Esta carpeta es una instancia local y autocontenida del foro «$display_name» (ID «$forum_id»), generada desde un snapshot de asimilación cerrado; no es el checkout del core ni un lugar para editar estados gestionados.

     <!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->
     $common_policy<!-- END ROLEPLAY-AGENT-CORE:COMMON -->

     ## Consultas disponibles

     Ejecuta el core desde su checkout con estos patrones PowerShell ya renderizados:

     ```powershell
     Push-Location '$core_root_ps'
     py -3.11 -B -m core.runtime.cli instance status --instance '$instance_root_ps'
     py -3.11 -B -m core.runtime.cli instance corpus list --instance '$instance_root_ps'
     py -3.11 -B -m core.runtime.cli instance corpus show --instance '$instance_root_ps' --candidate-id 'ID_DEL_CANDIDATO' --version 1
     Pop-Location
     ```

     `corpus list` devuelve solo versiones vigentes aprobadas. `corpus show` exige el ID y la versión mostrados por la lista y presenta texto, decisión y citas exactas. Una entrada `UNCERTAINTY` sigue requiriendo confirmación aunque esté aprobada. Estos comandos son de solo lectura.

     ## Trabajo posterior

     En 4d el concepto de personaje lo aportará la persona y las mejoras del agente serán propuestas separadas; en 4e la ficha seguirá siendo un borrador distinto de la respuesta del staff. Hasta que el core implemente esas operaciones, no inventes comandos ni crees o edites sus JSON. Si una operación futura requiere decisión humana, muestra a la persona el comando exacto y espera a que ella lo ejecute en su propia terminal.
     ````

     Sustituir `$display_name`/`$forum_id` literalmente (el modelo ya rechaza CR/LF y controles);
     para PowerShell, resolver las rutas y duplicar cada `'` como `''` antes de sustituir
     `$core_root_ps`/`$instance_root_ps`. No usar shell, variable de entorno ni `PYTHONPATH`. Extraer
     de cada resultado los bytes entre marcadores: deben ser `instance-policy.template.md` byte a
     byte, incluida su LF final. No aparece un nonce, una frase de confirmación ni una forma de
     ejecutar decisiones automáticamente.

     **CLI exacta.** Ampliar la descripción a workspace e instancias, capturar `InstanceError` en
     `main` y añadir `instance` con:

     ```text
     instance init --workspace RUTA --output RUTA
     instance status --instance RUTA
     instance corpus list --instance RUTA
     instance corpus show --instance RUTA --candidate-id ID --version N
     ```

     Todos los argumentos mostrados son obligatorios; `version` es entero positivo. `--json` sigue
     siendo global y va antes de `instance`. Ningún comando de instancia muta corpus ni acepta
     nonce. Salidas de éxito exactas en texto:

     ```text
     Instancia creada para el foro «FORUM_ID» en RUTA (snapshot sha256=HASH).
     La instancia del foro «FORUM_ID» ya existía con el mismo contenido: RUTA (snapshot sha256=HASH).
     Instancia íntegra del foro «FORUM_ID» en RUTA (revisión del corpus N; snapshot sha256=HASH).
     No hay candidatos aprobados vigentes.
     ID vN | CLASS | DOMAIN | APPROVED | scope=SCOPE_JSON | sha256=HASH[ | REQUIERE CONFIRMACIÓN]
     ```

     `corpus show` imprime exactamente: la línea de lista; `Decisión: APPROVED (evidencia=HASH).`;
     por cada cita, `Cita I: SECTION | SOURCE_ID | vSOURCE_VERSION |
     pasaje=VALOR | sha256=HASH | caracteres START-END`, luego `Cita I (exacta, hasta «Fin de la
     cita I.»):`, sus bytes UTF-8 y `Fin de la cita I.`; finalmente `Texto (exacto, hasta «Fin del
     texto.»):`, el texto y `Fin del texto.`. Si un bloque no termina en LF, `_write_exact` añade
     solo el LF separador antes del marcador; el JSON conserva la terminación exacta. `pasaje=null`
     o el texto literal; `SCOPE_JSON` usa `json.dumps(..., ensure_ascii=False)`.

     JSON, emitido por `_emit` con claves ordenadas/ASCII como hoy:

     - init: `{"ok":true,"action":"instance.init","created":BOOL,"forum_id":ID,
       "instance":RUTA,"snapshot_sha256":HASH}`;
     - status: `{"ok":true,"action":"instance.status","corpus_revision":N,"forum_id":ID,
       "instance":RUTA,"integrity":"OK","snapshot_sha256":HASH}`;
     - list: `{"ok":true,"action":"instance.corpus.list","candidates":[...],
       "corpus_revision":N,"instance":RUTA,"snapshot_sha256":HASH}`, donde cada resumen tiene
       exactamente `candidate_id`, `candidate_sha256`, `class`, `decision: "APPROVED"`, `domain`,
       `requires_confirmation`, `scope`, `version`;
     - show: `{"ok":true,"action":"instance.corpus.show","candidate":RECORD,
       "corpus_revision":N,"decision":DECISION_SUMMARY,"effective_review_status":"APPROVED",
       "instance":RUTA,"snapshot_sha256":HASH}`. `RECORD` reutiliza `_candidate_record(...,
       include_hash=True)` y `DECISION_SUMMARY` la forma ya pública por CLI de 4c1.

     Errores conservan `{"ok":false,"code","message"}` y texto `Error (CODE): MESSAGE`, siempre
     mediante `_write_exact`: 0 éxito; 2 sintaxis; 3 JSON/modelo/estado/cierre/consulta inválidos;
     4 conflicto, destino inseguro, retry distinto o carrera; 5 E/S. Stdout redirigido no bloquea
     estos comandos normales; solo los comandos humanos de 4c1 requieren TTY.

     **Tests.** `test_instance.py`: validación e inmutabilidad de todos los modelos; workspace sin
     cierre/cierre manipulado/lock; copia exacta del dossier y del sobre completo; hashes/revisión;
     historial preservado; filtro de vigente+APPROVED (rechazado, pendiente y sustituido ocultos;
     incertidumbre marcada); lookup explícito; fuente borrada tras init; config sin ruta del
     workspace; manipulación de cada estático/snapshot/config/integrity y extras; core/instance
     movidos; retry exacto sin cambio de bytes/mtime; output inexistente/vacío/no vacío, padres,
     solapes/spellings, symlinks y junctions Windows; cambio de fuente entre lecturas, replace fallido,
     staging limpiado y carreras idéntica/distinta.

     `test_instance_templates.py`: bytes UTF-8/LF/newline; parseo de las cuatro plantillas; contenido
     completo; escaping JSON/PowerShell con espacios, Unicode y `'`; comandos renderizados entre
     comillas y ejecutables sintácticamente; ausencia de nonce, bypass, nombres temáticos,
     `specialists/` y comandos futuros; ambos marcadores aparecen una vez y el interior extraído es
     idéntico entre archivos y exactamente igual a la política, incluida LF final.

     `test_instance_cli.py`: parser/obligatoriedad y `--json`; cuatro comandos texto/JSON con claves,
     orden, UTF-8 y LF exactos; init creado/retry; status sin workspace; list/show solo aprobados con
     citas y terminaciones con/sin LF; versión requerida, inexistente/sustituida/rechazada; códigos
     2/3/4/5; stdout redirigido funciona y no hay TTY/nonce. Mantener y ejecutar además las doce
     suites previas.

     **Criterios de aceptación.** Solo un cierre 4c1 íntegro materializa; la instancia contiene la
     copia exacta y auditable, pero su API/CLI de consulta nunca entrega pendiente, rechazada o
     sustituida como utilizable. Creación externa explícita, atómica, idempotente y segura ante
     links/races; recarga independiente del workspace; estáticos y snapshot cubiertos por hashes;
     instrucciones españolas completas, rutas PowerShell seguras y bloque común sin divergencia.
     No hay barrera nueva, especialista, personaje, memoria, red, modelo, publicación, SQLite,
     JSONL, secreto ni contenido temático.

     Verificación exacta desde PowerShell:

     ```powershell
     py -3.11 -B -m unittest tests.test_instance tests.test_instance_templates tests.test_instance_cli -v
     py -3.11 -B -m unittest discover -s tests -v
     py -3.11 -B -m core.runtime.cli instance init --workspace '<RUTA_WORKSPACE_CERRADO>' --output '<RUTA_INSTANCIA_EXTERNA>'
     py -3.11 -B -m core.runtime.cli instance status --instance '<RUTA_INSTANCIA_EXTERNA>'
     py -3.11 -B -m core.runtime.cli instance corpus list --instance '<RUTA_INSTANCIA_EXTERNA>'
     py -3.11 -B -m core.runtime.cli instance corpus show --instance '<RUTA_INSTANCIA_EXTERNA>' --candidate-id '<ID_APROBADO>' --version 1
     rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/runtime/instance.py core/runtime/templates tests/test_instance.py tests/test_instance_templates.py tests/test_instance_cli.py
     git diff --check
     git diff --name-only 8e3185c -- reference
     git status --short
     ```

     Las cuatro comprobaciones funcionales usan temporales externos; después se aparta o borra el
     workspace y se repiten status/list/show. El `rg` y el diff de `reference/` terminan sin salida.
4d1. [x] **Estado de personaje y declaración del concepto humano (detallado).** Objetivo: abrir un
     namespace mutable estrictamente validado dentro de la instancia e importar versiones de texto
     que la persona declara como su concepto; todavía no crear propuestas ni ficha.

     **Decisiones previas.** No modificar ninguna plantilla ni
     `tests/expected_instance_templates.py`: `INSTANCE_SCHEMA_VERSION == 1` fija también el set de
     instrucciones v1 y sus cuatro plantillas quedan inmutables. La política v1 ya dice que el
     concepto procede de la persona y que cualquier acción humana futura se ejecuta personalmente.
     Cuando sea imprescindible cambiar instrucciones se crearán archivos v2 nuevos y un schema de
     instancia v2; `load_instance` despachará por schema y conservará el renderizador v1. No habrá
     actualización implícita ni se reinterpretarán instancias antiguas con plantillas actuales.

     `work/integrity.json` continúa cubriendo **solo** los estáticos de 4c2 y no se reescribe. El
     nuevo `characters/` es el único root mutable permitido; cada `characters/<character_id>/state.json`
     es un sobre autohasheado, se valida por su propio decoder y usa
     `characters/<character_id>/state.json.lock`. No hay lock global: dos personajes distintos
     pueden avanzar; todas las operaciones sobre uno se serializan. La lista de entradas permitidas
     sigue cerrada, no se acepta ningún otro archivo/directorio dinámico.

     El concepto es Markdown libre, no un formulario. Se conserva carácter a carácter dentro de un
     único estado JSON; no se mantiene un `concept.md` duplicado, evitando una transacción de dos
     archivos. El input debe ser archivo regular externo a checkout e instancia, UTF-8 sin BOM, no
     vacío, sin NUL ni controles salvo TAB/CR/LF; no se normalizan CRLF, espacios ni LF final. La
     importación es acción humana con barrera A: el prompt enseña texto, SHA-256, bytes y terminación
     LF, y la persona lo declara como propio. Esto acredita adopción humana explícita, no demuestra
     quién redactó originalmente el archivo frente a pseudo-TTY, API con `Terminal` falso o core
     modificado; se mantiene el límite aceptado de la barrera A.

     **Archivos.** Crear `core/character/{__init__,models}.py` y `core/runtime/character.py`;
     modificar `core/runtime/{assimilation,instance,cli,__init__}.py`; crear
     `tests/test_{character_models,character_state,character_cli}.py`. No modificar
     `persistence.py`, `workspace.py`, plantillas, expected templates, fixtures ni código anterior
     salvo el pequeño factor común de confirmación descrito abajo.
     `core/character/__init__.py` reexporta modelos/codec; `core/runtime/__init__.py` añade sus
     modelos, tres operaciones y `confirm_human_action`, sin retirar exports previos.

     **Modelos inmutables.** En `core/character/models.py`, todos `frozen=True, slots=True`:

     - `ConceptAuthorship(str, Enum)` con único valor `HUMAN_DECLARED`.
     - `ConceptVersion(version: int, text: str, authorship: ConceptAuthorship,
       receipt: HumanConfirmationReceipt, evidence: SourceRef, concept_sha256: str = init=False,
       utf8_size: int = init=False)`. Versión positiva; texto con las reglas anteriores; hash y
       tamaño se calculan sobre `text.encode("utf-8")`; receipt/evidence obligatorios.
     - `CharacterState(character_id: str, concepts: tuple[ConceptVersion, ...],
       proposals: tuple = (), proposal_decisions: tuple = ())`. ID
       `[a-z0-9]+(?:-[a-z0-9]+)*`; al menos un concepto, versiones contiguas 1..N; en 4d1 las dos
       tuplas reservadas deben estar vacías. `current_concept()` devuelve la última versión.
     - `LoadedCharacter(character_root: Path, state_revision: int, state: CharacterState)` y
       `ConceptImportResult(character: LoadedCharacter, concept: ConceptVersion, created: bool)`.
     - `CharacterError(code, reason)` admite `INVALID_STATE`, `CONFLICT`,
       `UNSAFE_DESTINATION`, `IO` y llega al mapeo CLI 3/4/5 existente.

     Reutilizar `HumanConfirmationReceipt` y `Terminal` de `assimilation.py`, sin copiar el modelo
     ni ofrecer otro canal. Para evitar el ciclo `runtime.__init__` → `instance` →
     `character.models` → `runtime`, `models.py` usa anotación diferida/`TYPE_CHECKING` y hace el
     import local del tipo solo al validar o reconstruir, nunca al importar el módulo. Firmas puras:

     ```python
     def make_concept_version(*, forum_id: str, character_id: str, version: int,
                              text: str, receipt: HumanConfirmationReceipt) -> ConceptVersion: ...
     def decode_character_state(content: object, *, forum_id: str,
                                revision: int) -> CharacterState: ...
     def encode_character_content(state: CharacterState) -> dict[str, object]: ...
     ```

     `make_concept_version` crea el `SourceRef`; el decoder reconstruye todo, recalcula hash, tamaño
     y evidencia y rechaza bytes/registro incoherentes. `revision` debe ser entero positivo y no se
     confunde con la versión de concepto.

     **Persistencia exacta.** Primera importación: sobre común con `revision: 1`; cada versión nueva
     incrementa en uno. `content` tiene exactamente:

     ```json
     {
       "character_id": "ejemplo",
       "concepts": [
         {
           "authorship": "HUMAN_DECLARED",
           "concept_sha256": "<sha256 de UTF-8 exacto>",
           "evidence": {
             "locator": "instance://<forum_id>/characters/ejemplo/concepts/v1",
             "section_or_passage": "concept:ejemplo:v1",
             "sha256": "<sha256 de payload canónico>",
             "source_id": "human-concept:ejemplo:v1"
           },
           "receipt": {
             "confirmation_sha256": "<sha256 de la frase aceptada>",
             "method": "TTY_NONCE_V1"
           },
           "text": "Texto exacto del concepto",
           "utf8_size": 25,
           "version": 1
         }
       ],
       "proposal_decisions": [],
       "proposals": []
     }
     ```

     El payload de evidencia contiene exactamente `authorship`, `character_id`, `concept_sha256`,
     `receipt`, `text`, `utf8_size` y `version`, sin `evidence`; se hashea como JSON canónico
     compacto. Percent-encodear `forum_id`/ID al construir el locator aunque sus regex actuales ya
     sean seguras. No guardar path de input, nonce, hora ni identidad supuesta de la persona.

     Misma ID/versión y mismo texto devuelve el registro existente sin escribir ni retar de nuevo,
     pero el comando sigue exigiendo stdin+stdout TTY. Misma ID/versión y otro texto da `CONFLICT`;
     una versión debe ser exactamente N+1 y no puede repetir el texto/hash de N. Cada nueva versión
     humana pasa a ser el concepto vigente; las anteriores permanecen auditables.

     **Carga de instancia y escritura.** Separar en `instance.py` `_STATIC_ROOT_DIRS` (`dossier`,
     `corpus`, `work`) de `_MUTABLE_ROOT_DIRS` (`characters`). El paseo del manifiesto se limita a
     estáticos. `characters/` puede faltar o estar vacío; si existe, no puede ser link/junction y
     cada hijo debe ser un directorio cuyo nombre sea un ID válido, con exactamente `state.json` y,
     durante una operación o tras caída, el opcional `state.json.lock`, ambos regulares. Recargar
     cada sobre/decoder y añadir `characters: tuple[LoadedCharacter, ...]`, ordenada por ID, a
     `LoadedInstance`. Cualquier otro hijo, staging abandonado, profundidad extra o estado inválido
     hace fallar `load_instance`; un lock no invalida lectura/status, pero bloquea mutaciones.

     En `core/runtime/character.py`:

     ```python
     def import_concept(instance_root: Path, *, expected_core_root: Path,
                        character_id: str, version: int, input_path: Path,
                        terminal: Terminal) -> ConceptImportResult: ...
     def list_concepts(instance: LoadedInstance, *,
                       character_id: str) -> tuple[ConceptVersion, ...]: ...
     def get_concept(instance: LoadedInstance, *, character_id: str,
                     version: int) -> ConceptVersion: ...
     ```

     `import_concept` exige primero terminal interactivo; carga instancia e input, valida secuencia e
     idempotencia y comprueba lock antes de preguntar. Tras confirmar vuelve a cargar instancia e
     input y exige mismos bytes, revisión y ausencia/presencia del personaje. Para v1 crea
     `characters/` si falta, prepara el directorio completo en `.ID.staging-<token>` y lo publica con
     `_destination_state`/`_publish`; creación solo en Windows, mismas defensas de componentes,
     junctions, carrera y limpieza que 4c2 (ganador idéntico → `created=False`; distinto →
     `CONFLICT`). Para N>1 adquiere el lock por `O_CREAT|O_EXCL`, hace la recarga definitiva bajo el
     lock y usa `atomic_write_bytes(encode_state(...))`. No mantener lock mientras la persona escribe.
     Copiar la semántica de liberación de 4c1: lock huérfano → `CONFLICT` con path; fallo al quitarlo
     siempre se informa, diferenciando si se guardó o no. Revalidar `_linked_component` justo antes
     de crear/publicar/escribir.

     Añadir en `assimilation.py`, sin cambiar un byte de prompts existentes:

     ```python
     def confirm_human_action(terminal: Terminal, *, phrase_prefix: str,
                              prompt: str) -> HumanConfirmationReceipt: ...
     ```

     Valida terminal, genera internamente el nonce de 8 caracteres con el alfabeto aprobado,
     escribe `prompt + "Escribe exactamente: " + phrase_prefix + " " + nonce + "\n> "`, admite
     una sola línea y solo elimina un LF o CRLF final; EOF/Ctrl+C/error/frase distinta no guarda.
     Devuelve recibo con hash de la frase completa. Extraer un auxiliar privado común para lectura y
     hacer que `_confirm` de 4c1 lo use conservando sus salidas byte a byte. La CLI nunca inyecta
     terminal, nonce, archivo de respuesta, argumento ni variable de entorno; el bypass por API
     falsa sigue documentado.

     El prompt exacto de concepto es, sustituyendo mayúsculas y escribiendo `TEXT` literalmente; si
     no termina en LF se añade solo el LF visual antes del footer:

     ```text
     DECLARACIÓN HUMANA DE AUTORÍA
     Personaje: ID
     Versión: N
     SHA-256: HASH
     Bytes UTF-8: SIZE
     Termina en LF: SÍ|NO
     Concepto exacto (hasta «Fin del concepto.»):
     TEXT
     Fin del concepto.
     Declara que este texto es el concepto que tú aportas; no una propuesta del agente.
     Escribe exactamente: DECLARAR-CONCEPTO ID vN NONCE
     >␠
     ```

     En el bloque anterior `␠` representa un único espacio ASCII; los bytes finales del prompt son
     exactamente `> `, sin LF posterior.

     `phrase_prefix` exacto es `DECLARAR-CONCEPTO ID vN`. En terminal integrada de VS Code funciona
     como 4c1; stdout o stdin redirigido falla con código 3 antes de mutar.

     **CLI exacta.** Añadir:

     ```text
     character concept import --instance RUTA --character-id ID --version N --input RUTA
     character concept list --instance RUTA --character-id ID
     character concept show --instance RUTA --character-id ID --version N
     ```

     Todos los argumentos son obligatorios; versión positiva. `import` rechaza el flag global
     `--json` con `INVALID_STATE`: `las declaraciones humanas de concepto no admiten --json:
     ejecuta el comando en tu terminal y responde a la confirmación`; list/show sí lo admiten. Tras
     el prompt, texto exacto de éxito:

     ```text
     Concepto importado: ID vN | sha256=HASH | bytes=SIZE
     Revisión del personaje: R.
     ```

     Un retry idéntico imprime `Concepto ya existente:` con el resto igual y la misma revisión. List
     imprime una línea por versión: `ID vN | HUMAN_DECLARED | sha256=HASH | bytes=SIZE`; show imprime
     esa línea, `Evidencia: HASH`, `Texto (exacto, hasta «Fin del concepto.»):`, el texto y
     `Fin del concepto.` usando `_write_exact` y el mismo LF separador de 4c2. ID inexistente o
     versión ausente da código 3.

     JSON exacto: list emite `ok`, `action="character.concept.list"`, `character_id`, `concepts`
     (cada resumen: `authorship`, `concept_sha256`, `evidence_sha256`, `utf8_size`, `version`),
     `instance`, `state_revision`; show cambia `concepts` por `concept`, el registro persistido
     completo. Se mantienen `{"ok":false,"code","message"}`, `_write_exact` y códigos 0/2/3/4/5.

     **Tests.** `test_character_models.py`: IDs/versiones/texto Unicode, CRLF/LF/no LF/controles;
     hash/tamaño/receipt/evidencia/locator; forma cerrada, arrays reservados vacíos, secuencia,
     canonicalidad y manipulación. `test_character_state.py`: carga sin `characters`, vacío y varios
     IDs ordenados; estáticos intactos; extras, links/junctions y estados/locks; v1/N+1, idempotencia,
     conflictos y no-op; input externo/links; fake `Terminal` para prompt/frase/nonce/EOF/Ctrl+C;
     cambio entre prompt y lock; locks concurrentes/huérfanos/fallo de liberación; escritura atómica,
     staging/Windows y carreras. Comprobar que estado/recibo no contienen nonce/path de input y que
     borrar el workspace no afecta.

     `test_character_cli.py`: parser y comandos exactos, versión positiva, JSON permitido/prohibido,
     no TTY y stdout redirigido sin mutación, salidas list/show UTF-8+LF exactas y códigos. Mantener
     tests de 4c1 para demostrar que el factor común no cambia prompts; mantener las cuatro
     plantillas y `expected_instance_templates.py` byte a byte; suite completa 349+.

     **Criterios.** Sin declaración TTY de texto/hash exactos no nace concepto ni personaje. Cada
     versión sobrevive reinicio en un sobre verificable; el manifiesto estático no cambia y el loader
     solo abre el namespace dinámico definido. No hay propuesta, composición derivada, ficha,
     plantilla nueva, publicación, red, modelo, SQLite ni contenido temático.

     Verificación exacta desde PowerShell:

     ```powershell
     py -3.11 -B -m unittest tests.test_character_models tests.test_character_state tests.test_character_cli tests.test_assimilation_decisions tests.test_assimilation_decision_cli -v
     py -3.11 -B -m unittest discover -s tests -v
     py -3.11 -B -m core.runtime.cli character concept import --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --version 1 --input '<RUTA_EXTERNA_CONCEPTO>'
     py -3.11 -B -m core.runtime.cli character concept list --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo'
     py -3.11 -B -m core.runtime.cli character concept show --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --version 1
     rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/character core/runtime/character.py tests/test_character_models.py tests/test_character_state.py tests/test_character_cli.py
     git diff --check
     git diff --name-only 45f667a -- reference core/runtime/templates tests/expected_instance_templates.py
     git status --short
     ```

     El import se valida manualmente en TTY real; list/show se repiten tras reiniciar y apartar el
     workspace. El `rg` y el diff de rutas congeladas terminan sin salida.

4d2. [x] **Propuestas citadas y composición efectiva (detallado).** Objetivo: permitir que el
     agente registre alternativas completas, referidas a la composición vigente y al corpus cerrado
     aprobado, y que la persona las apruebe o rechace con barrera A. La aceptación solo compone el
     diseño del personaje: no modifica el concepto humano, el corpus ni ningún eje de staff,
     aprendizaje, utilizabilidad, publicación o canon.

     **Alcance cerrado.** Modificar `core/character/{models,__init__}.py` y
     `core/runtime/{character,instance,cli,__init__}.py`; crear
     `tests/test_{character_proposals,character_proposal_cli}.py` y ajustar únicamente las
     aserciones de compatibilidad necesarias en `tests/test_{character_models,character_state,
     character_cli,instance}.py`. No modificar `assimilation.py`, `persistence.py`, `workspace.py`,
     review, adaptadores, paquetes, las cuatro plantillas v1,
     `tests/expected_instance_templates.py` ni `reference/`. Reutilizar sin duplicar
     `ReviewStatus`, `HumanConfirmationReceipt`, `Terminal`, `confirm_human_action`,
     `_corpus_lock(..., guard=...)`, `_require_unlocked`, `_path_guard`, `load_strict_json`,
     `encode_state`, `atomic_write_bytes` y `get_approved_candidate`.

     **Modelos inmutables y vocabulario.** En `core/character/models.py`, todos
     `frozen=True, slots=True`, añadir:

     - `ConceptRef(version: int, concept_sha256: str)`; versión positiva y hash de 64 hex
       minúsculas. Siempre debe resolver al `ConceptVersion` exacto del mismo personaje.
     - `CorpusCandidateRef(candidate_id: str, version: int, candidate_sha256: str)`; ID con la
       regex ya usada, versión positiva y hash canónico. No guarda estado de revisión: al crear y
       recargar se resuelve la pareja solo mediante `get_approved_candidate`, que acredita que es
       la versión vigente `APPROVED` del snapshot inmutable.
     - `CharacterProposal(proposal_id: str, version: int, created_revision: int,
       concept: ConceptRef, base_composition_sha256: str, text: str, rationale: str,
       citations: tuple[CorpusCandidateRef, ...], proposal_sha256: str = init=False,
       result_composition_sha256: str = init=False, utf8_size: int = init=False)`.
       `proposal_id` usa la misma regex; versión/revisión son enteros positivos; texto y rationale
       son UTF-8 no vacíos, sin BOM/NUL ni controles salvo TAB/CR/LF, y se conservan carácter por
       carácter. Las citas son una tupla no vacía, ordenada por el autor y sin repetir
       `(candidate_id, version)`; su orden forma parte de la identidad.
     - `CharacterProposalDecision(decision_id: str, decision_revision: int, proposal_id: str,
       proposal_version: int, proposal_sha256: str, base_composition_sha256: str,
       result_composition_sha256: str, review_status: ReviewStatus,
       receipt: HumanConfirmationReceipt, evidence: SourceRef)`; solo `APPROVED` o `REJECTED`, y
       `decision_id` exacta `proposal:<proposal_id>:v<version>`.
     - `ProposalStatus(str, Enum)` exactamente `PENDING`, `APPROVED`, `REJECTED`, `OBSOLETE`.
       Es una vista, no se persiste. `ProposalView(proposal, status, decision,
       applied_to_effective)` exige coherencia: `APPROVED`/`REJECTED` tienen la decisión homónima;
       `PENDING`/`OBSOLETE` no tienen decisión; solo una aprobada puede estar aplicada.
     - `AppliedProposal(proposal: CharacterProposal, decision: CharacterProposalDecision)` exige
       la misma clave/hash/base/resultado y decisión `APPROVED`.
     - `EffectiveComposition(character_id: str, concept: ConceptRef, text: str,
       composition_sha256: str, applied_proposals: tuple[AppliedProposal, ...])`; conserva el
       texto completo y la cadena aprobada con su evidencia humana, en orden. Añadir resultados
       `ProposalAddResult(character, proposal, created)` y
       `ProposalDecisionResult(character, decision, created, effective)`.

     `CharacterState.proposals` pasa a `tuple[CharacterProposal, ...]` y
     `proposal_decisions` a `tuple[CharacterProposalDecision, ...]`; deja de rechazarlas. Conserva
     `concepts` y sus bytes sin cambio. Añadir `current_proposal(proposal_id)` y
     `decision_for(proposal)`. Reexportar los nuevos modelos y operaciones desde ambos
     `__init__.py`, sin retirar exports de 4d1.

     **Hashes y cadena efectiva.** No persistir un bloque `effective`: es una vista derivada para
     no crear una segunda autoridad. Usar `canonical_json_bytes(..., pretty=False)` y estas formas
     exactas:

     1. La raíz de cada concepto es SHA-256 de
        `{"character_id": ID, "concept": CONCEPT_REF, "text": TEXTO_CONCEPTO}`.
     2. `proposal_sha256` es SHA-256 del registro de propuesta con las claves
        `base_composition_sha256`, `citations`, `concept`, `created_revision`, `proposal_id`,
        `rationale`, `text`, `utf8_size`, `version`; excluye los dos hashes derivados.
     3. `result_composition_sha256` es SHA-256 de
        `{"base_composition_sha256": BASE, "character_id": ID, "concept": CONCEPT_REF,
        "proposal": {"proposal_id": ID_PROPUESTA, "proposal_sha256": HASH,
        "version": N}, "text": TEXTO_PROPUESTO}`.

     `CONCEPT_REF` tiene exactamente `concept_sha256`, `version`; cada cita persistida,
     `candidate_id`, `candidate_sha256`, `version`. Una aprobación válida sustituye el texto por el
     `text` completo de la propuesta y el hash efectivo por `result_composition_sha256`; no mezcla
     campos ni aplica un parche. El siguiente paso debe citar ese hash como base. Aunque dos textos
     coincidan, la cadena no puede volver accidentalmente a un hash anterior porque incluye base y
     propuesta exactas.

     **Orden de eventos y validación al recargar.** Cada alta real consume exactamente una revisión
     del sobre. `created_revision`/`decision_revision` las hacen auditables sin cambiar el JSON de
     conceptos de 4d1. Exigir que `revision == len(concepts) + len(proposals) +
     len(proposal_decisions)`, que las revisiones explícitas sean únicas y estén en `1..revision`;
     las posiciones restantes corresponden, en orden, a los conceptos v1..vN. Reproducir el evento
     de revisión 1 a N:

     - un concepto pasa a ser vigente y reinicia su cadena en la raíz anterior;
     - una propuesta debe citar el concepto vigente y la composición efectiva de ese instante,
       resolver todas sus citas aprobadas y ser la siguiente versión contigua de su ID;
     - una decisión debe aparecer después de su propuesta y ser la única para esa clave;
     - `APPROVED` exige que, en ese instante, la propuesta sea la versión mayor de su ID, cite el
       concepto vigente y tenga por base la composición efectiva actual; entonces avanza la cadena;
     - `REJECTED` puede registrar cualquier propuesta exacta anterior aún sin decisión, incluso si
       ya está obsoleta, y nunca cambia la cadena.

     Una edición, referencia no resuelta, revisión duplicada/fuera de orden, decisión opuesta,
     aprobación con base vieja o hash derivado discordante es `INVALID_STATE` al cargar. Esta
     reproducción también permite reconstruir la base completa que se mostró al decidir.

     El estado final de cada propuesta se deriva, sin reescribir historial: si tiene decisión es
     `APPROVED` o `REJECTED`; sin decisión solo es `PENDING` cuando pertenece al concepto vigente,
     es la versión mayor actual de su ID y su base coincide con la composición efectiva final; en
     cualquier otro caso es `OBSOLETE`. Una aprobada de un concepto anterior conserva
     `status=APPROVED` como hecho histórico, pero `applied_to_effective=false`; solo los pasos
     aprobados reproducidos desde el último concepto tienen `applied_to_effective=true`.

     **Compatibilidad 4d1 y codec.** Mantener las cuatro claves de `content`. Sustituir solo los
     arrays reservados por registros reales; un estado 4d1 con ambos `[]` carga sin migración ni
     reescritura, con `revision == len(concepts)`, y produce la raíz del último concepto. La forma
     de cada concepto y su evidencia no cambia. `encode_character_content` serializa los dos
     historiales; `decode_character_state` conserva `forum_id` y `revision` y añade el keyword
     opcional exacto
     `candidate_resolver: Callable[[str, int], AssimilationCandidate] | None = None`. Si los arrays
     están vacíos puede omitirse; si hay una cita debe existir y devolver el candidato exacto
     aprobado o se rechaza el estado. En `instance.py`, crear
     primero un `LoadedInstance` provisional con `characters=()` y pasar a `_load_characters` un
     resolver que invoque `get_approved_candidate(...).candidate`; así no se crea un ciclo de
     imports ni una segunda definición de «aprobado». `import_concept` conserva propuestas y
     decisiones al añadir el concepto y su nueva revisión pasa a ser el siguiente evento; no las
     borra ni las muta.

     **JSON de entrada y persistido.** `character proposal add` lee con `load_strict_json` un objeto
     con exactamente:

     ```json
     {
       "proposal_id": "ajuste-inicial",
       "version": 1,
       "base_composition_sha256": "<64 hex de character effective show>",
       "text": "Texto completo de la composición propuesta",
       "rationale": "Motivo del ajuste y relación con las citas",
       "citations": [
         {"candidate_id": "creacion-limites", "version": 1}
       ]
     }
     ```

     No admite hashes de candidato, concepto, propuesta o resultado, estado, decisión, revisión,
     receipt, evidence ni offsets. Rechazar claves extra/faltantes, duplicadas, BOM, JSON/UTF-8 no
     válido, constantes no estándar, recursión, tipos inexactos y lista vacía. El core toma el
     concepto vigente, exige que `base_composition_sha256` sea la composición efectiva actual y
     llama a `get_approved_candidate` por cada referencia; no acepta pendiente, rechazada ni
     sustituida. Una `UNCERTAINTY` aprobada se puede citar, pero sigue rotulada
     `REQUIERE CONFIRMACIÓN` y aceptarla no la convierte en literal.

     Cada elemento de `content.proposals` tiene exactamente:

     ```json
     {
       "base_composition_sha256": "<hash base>",
       "citations": [{"candidate_id": "creacion-limites", "candidate_sha256": "<hash candidato>", "version": 1}],
       "concept": {"concept_sha256": "<hash concepto>", "version": 1},
       "created_revision": 2,
       "proposal_id": "ajuste-inicial",
       "proposal_sha256": "<hash del registro>",
       "rationale": "Motivo del ajuste y relación con las citas",
       "result_composition_sha256": "<hash de la composición resultante>",
       "text": "Texto completo de la composición propuesta",
       "utf8_size": 43,
       "version": 1
     }
     ```

     Cada elemento de `content.proposal_decisions` tiene exactamente:

     ```json
     {
       "base_composition_sha256": "<hash base>",
       "decision_id": "proposal:ajuste-inicial:v1",
       "decision_revision": 3,
       "evidence": {
         "locator": "instance://foro-neutral/characters/ejemplo/proposals/ajuste-inicial/v1/decision",
         "section_or_passage": "proposal:ajuste-inicial:v1",
         "sha256": "<hash del payload de evidencia>",
         "source_id": "human-proposal-decision:ejemplo:ajuste-inicial:v1"
       },
       "proposal_id": "ajuste-inicial",
       "proposal_sha256": "<hash de propuesta>",
       "proposal_version": 1,
       "receipt": {"confirmation_sha256": "<hash de frase>", "method": "TTY_NONCE_V1"},
       "result_composition_sha256": "<hash resultante>",
       "review_status": "APPROVED"
     }
     ```

     El payload de evidencia contiene exactamente `character_id` y todas las claves persistidas de
     la decisión salvo `evidence`; su SHA-256 es canónico compacto. Percent-encodear los segmentos
     del locator. No guardar nonce, frase, hora, usuario, path del input, texto duplicado de la base,
     estado derivado ni una supuesta decisión de staff.

     **Operaciones e idempotencia.** En `core/runtime/character.py` añadir firmas públicas exactas:

     ```python
     def add_proposal(instance_root: Path, *, expected_core_root: Path,
                      character_id: str, value: object) -> ProposalAddResult: ...
     def list_proposals(instance: LoadedInstance, *,
                        character_id: str) -> tuple[ProposalView, ...]: ...
     def get_proposal(instance: LoadedInstance, *, character_id: str,
                      proposal_id: str, version: int) -> ProposalView: ...
     def get_effective_composition(instance: LoadedInstance, *,
                                   character_id: str) -> EffectiveComposition: ...
     def record_proposal_decision(instance_root: Path, *, expected_core_root: Path,
                                  character_id: str, proposal_id: str, version: int,
                                  review_status: ReviewStatus,
                                  terminal: Terminal) -> ProposalDecisionResult: ...
     ```

     `add_proposal` no es acción humana y admite otras propuestas pendientes: se pueden registrar
     varios IDs —o una versión siguiente de un ID— sobre la misma base. Repetir la misma clave con
     la misma entrada semántica y referencias resueltas devuelve `created=False` sin lock/escritura
     ni cambio de mtime; misma clave con otro contenido, salto de versión, o una nueva versión que
     repita la anterior ignorando `version`, `created_revision` y hashes derivados es `CONFLICT`.
     Un alta real toma el lock por personaje, con el `guard` de 4d1 antes/al tomar/antes de escribir,
     recarga instancia y estado, vuelve a resolver las citas/base y escribe revisión +1. No hace
     falta bloquear mientras se lee el input; un cambio antes de adquirir el lock se detecta por
     revisión/base.

     `record_proposal_decision` exige primero terminal interactiva y `APPROVED|REJECTED`; valida e
     identifica la propuesta antes del prompt y llama a `_require_unlocked`. Un retry idéntico
     devuelve la decisión existente sin nonce ni escritura; la decisión opuesta es `CONFLICT`.
     Para una aprobación nueva exige `status=PENDING`; para un rechazo admite `PENDING` u
     `OBSOLETE`. Tras la frase toma el mismo lock+guard, recarga y repite todas las condiciones;
     cualquier cambio es `CONFLICT`. Añade una sola decisión con revisión +1. Fallos de escritura y
     liberación conservan exactamente las garantías y mensajes del cerrojo 4d1.

     Al aprobar una propuesta, las demás pendientes que compartían la base pasan a `OBSOLETE` por
     cálculo, sin añadir decisiones falsas ni reescribirlas. Al importar un concepto humano nuevo,
     toda la cadena efectiva se reinicia en ese texto; propuestas anteriores siguen en los arrays y
     las no decididas pasan a `OBSOLETE`. Rechazar no cambia hash/texto efectivo ni el estado de las
     demás. Para recuperar una alternativa obsoleta, el agente crea una versión nueva completa
     basada en el hash efectivo vigente; nunca se «reactiva» el registro viejo.

     **Prompt exacto y textos largos.** Para aprobar/rechazar mostrar siempre la base citada y la
     propuesta completas, sin diff, truncado, paginador, prefijos por línea ni normalización. Para
     que un texto largo siga siendo navegable, preceder cada bloque con su rol, hash y tamaño y
     cerrarlo con un marcador distinto; la propuesta queda inmediatamente después de la base. Si
     un texto no termina en LF, añadir solo el LF visual antes del footer. `CITAS` conserva el orden
     y cada línea resuelve clase/dominio/estado/hash; una incertidumbre añade el sufijo indicado.
     El prompt exacto es:

     ```text
     DECISIÓN HUMANA SOBRE PROPUESTA
     Personaje: CHARACTER_ID
     Propuesta: PROPOSAL_ID vN
     Estado antes de decidir: PENDING|OBSOLETE
     Decisión: APROBAR|RECHAZAR
     Concepto humano citado: vC
     Concepto SHA-256: CONCEPT_HASH
     Base vigente ahora: SÍ|NO
     Base composición SHA-256: BASE_HASH
     Resultado composición SHA-256: RESULT_HASH
     Propuesta SHA-256: PROPOSAL_HASH
     Base bytes UTF-8: BASE_SIZE
     Propuesta bytes UTF-8: PROPOSED_SIZE
     Citas aprobadas (K):
     Cita 1: CANDIDATE_ID vV | CLASS | DOMAIN | APPROVED | sha256=CANDIDATE_HASH[ | REQUIERE CONFIRMACIÓN]
     Motivo exacto (hasta «Fin del motivo.»):
     RATIONALE
     Fin del motivo.
     BASE CITADA — texto exacto (hasta «Fin de la base.»):
     BASE_TEXT
     Fin de la base.
     PROPUESTA — texto completo que se aprueba/rechaza (hasta «Fin de la propuesta.»):
     PROPOSED_TEXT
     Fin de la propuesta.
     Esta decisión solo compone el diseño del personaje; no es aprobación de staff, aprendizaje, utilizabilidad, publicación ni canon.
     Escribe exactamente: APROBAR-PROPUESTA|RECHAZAR-PROPUESTA PROPOSAL_ID vN NONCE
     >␠
     ```

     En una aprobación, `Estado=PENDING` y `Base vigente ahora=SÍ`; un rechazo puede mostrar
     `OBSOLETE`/`NO`. `␠` es un espacio ASCII y no hay LF final. Usar `confirm_human_action` con
     `phrase_prefix="APROBAR-PROPUESTA <id> v<n>"` o
     `"RECHAZAR-PROPUESTA <id> v<n>"`; un intento, comparación byte a byte y mismo límite de
     barrera A. Esta presentación duplica visualmente dos textos largos de forma deliberada: los
     encabezados, hashes, tamaños y footers permiten distinguirlos, mientras que truncar o mostrar
     solo un parche impediría saber qué texto completo se acepta.

     **CLI exacta.** Añadir, con todos los argumentos mostrados obligatorios:

     ```text
     character effective show --instance RUTA --character-id ID
     character proposal add --instance RUTA --character-id ID --input ARCHIVO_JSON
     character proposal list --instance RUTA --character-id ID
     character proposal show --instance RUTA --character-id ID --proposal-id ID --version N
     character proposal approve --instance RUTA --character-id ID --proposal-id ID --version N
     character proposal reject --instance RUTA --character-id ID --proposal-id ID --version N
     ```

     `add/list/show/effective show` admiten `--json`; `approve/reject` lo rechazan antes del prompt
     con `INVALID_STATE`/3 y mensaje exacto `las decisiones humanas sobre propuestas no admiten
     --json: ejecuta el comando en tu terminal y responde a la confirmación`. No hay `--yes`,
     `--force`, nonce, respuesta por archivo/argumento/env ni selección implícita de versión.

     Salida texto:

     - add: `Propuesta añadida:` o `Propuesta ya existente:`, seguida de
       `ID vN | PENDING|OBSOLETE | concepto=vC:HASH | base=HASH | resultado=HASH |
       sha256=HASH | citas=K | aplicada=NO`, y `Revisión del personaje: R.`;
     - list: una línea con esa forma por propuesta, en orden de inserción; vacío,
       `No hay propuestas para «CHARACTER_ID».`; decisiones cambian el estado y
       `aplicada=SÍ|NO`;
     - show: la línea, `Decisión: ninguna (estado PENDING|OBSOLETE).` o
       `Decisión: APPROVED|REJECTED (evidencia=HASH).`, las líneas de cita del prompt, bloque de
       motivo, bloque completo de base y bloque completo de propuesta con los mismos footers;
     - effective show: `Composición efectiva: CHARACTER_ID | concepto=vC:HASH |
       sha256=COMPOSITION_HASH | pasos=K | bytes=SIZE`; una línea por paso
       `Paso I: ID vN | propuesta=HASH | resultado=HASH | evidencia=HASH`; después el bloque
       `Texto efectivo (exacto, hasta «Fin de la composición efectiva.»):`;
     - decisión: `Propuesta aprobada|rechazada:` o
       `Propuesta ya aprobada|ya rechazada: ID vN | sha256=HASH`,
       `Composición efectiva: HASH.` y `Revisión del personaje: R.`.

     JSON de éxito, con claves de raíz exactas:

     - add: `ok`, `action="character.proposal.add"`, `character_id`, `created`, `instance`,
       `proposal` (resumen), `state_revision`;
     - list: `ok`, `action="character.proposal.list"`, `character_id`, `instance`, `proposals`
       (resúmenes), `state_revision`;
     - show: `ok`, `action="character.proposal.show"`, `applied_to_effective`, `base`
       (`EffectiveComposition` completa en el instante de alta), `character_id`, `decision`
       (registro persistido o `null`), `instance`, `proposal` (registro persistido), `status`,
       `state_revision`;
     - effective show: `ok`, `action="character.effective.show"`, `character_id`, `composition`,
       `instance`, `state_revision`.

     Un resumen de propuesta tiene exactamente `applied_to_effective`,
     `base_composition_sha256`, `citation_count`, `concept`, `decision` (`null|APPROVED|REJECTED`),
     `proposal_id`, `proposal_sha256`, `result_composition_sha256`, `status`, `version`.
     `composition` tiene exactamente `applied_proposals` (cada paso: `decision_evidence_sha256`,
     `proposal_id`, `proposal_sha256`, `result_composition_sha256`, `version`),
     `composition_sha256`, `concept`, `text`, `utf8_size`. Mantener `_write_exact`, `_emit`,
     `{"ok":false,"code","message"}` y códigos 0/2/3/4/5. Entrada/modelo/hash/cita/no encontrado
     → 3; identidad/versión/base/revisión/lock/carrera → 4; E/S → 5.

     **Tests.** `test_character_proposals.py`: validación/inmutabilidad de todos los modelos;
     hashes con Unicode, CRLF y sin LF; JSON de entrada/persistido exactos; evidencia/locator;
     citas vacías, duplicadas, pendientes, rechazadas, sustituidas, aprobadas e incertidumbre;
     compatibilidad byte a byte con estados 4d1 vacíos; revisión como event log y toda manipulación;
     raíz, dos aprobaciones encadenadas y reinicio por concepto; varias pendientes admitidas;
     versión nueva y aprobación paralela vuelven obsoletas sin borrar; rechazo vigente/obsoleto;
     aprobado histórico no aplicado; idempotencia/mtime y conflictos; prompt completo exacto con
     base/propuesta largas, marcadores, hashes, LF/no LF, citas y frases; no TTY, error, EOF, case,
     espacios, Ctrl+C y cambio durante el prompt; lock/guard/junction swaps, fallo de liberación,
     replace fallido y concurrencia sin pérdida.

     `test_character_proposal_cli.py`: parser y obligatoriedad; los seis comandos; add/list/show y
     effective en texto/JSON con payload completo y LF/UTF-8 exactos; vacío, IDs/versiones/base
     desconocidos y cuatro estados; dos altas pendientes, aprobación de una y obsolescencia de la
     otra; concepto nuevo reinicia effective; `--json`, stdin/stdout no TTY y ausencia de bypass en
     decisiones; códigos 2/3/4/5 y subprocess no interactivo sin mutación. Las suites existentes
     prueban además que importar un concepto conserva historiales, que `load_instance` usa solo
     candidatos vigentes aprobados y que prompts 4c1/4d1 y plantillas v1 siguen byte a byte.

     **Criterios de aceptación.** El agente puede añadir varias propuestas completas sin decidirlas;
     solo una frase humana exacta puede crear una decisión. Únicamente aprobaciones que eran
     vigentes y estaban basadas en la composición efectiva del momento avanzan una cadena
     reproducible. Propuestas pendientes, rechazadas u obsoletas jamás aportan texto; un concepto
     nuevo es siempre la nueva raíz sin borrar historia. Toda cita se resuelve mediante
     `get_approved_candidate`; entrada, estado y prompt contienen texto/hashes exactos. No hay
     parche, modelo, red, SQLite, cambio de plantilla, staff, aprendizaje, uso, publicación ni canon.

     Verificación exacta desde PowerShell:

     ```powershell
     py -3.11 -B -m unittest tests.test_character_proposals tests.test_character_proposal_cli tests.test_character_models tests.test_character_state tests.test_character_cli tests.test_instance -v
     py -3.11 -B -m unittest tests.test_assimilation_decisions tests.test_assimilation_decision_cli -v
     py -3.11 -B -m unittest discover -s tests -v
     py -3.11 -B -m core.runtime.cli --json character effective show --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo'
     py -3.11 -B -m core.runtime.cli --json character proposal add --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --input '<PROPUESTA_JSON>'
     py -3.11 -B -m core.runtime.cli character proposal approve --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --proposal-id 'ajuste-inicial' --version 1
     py -3.11 -B -m core.runtime.cli --json character proposal show --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --proposal-id 'ajuste-inicial' --version 1
     rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/character core/runtime/character.py tests/test_character_proposals.py tests/test_character_proposal_cli.py
     git diff --check
     git diff --name-only 67a7284 -- reference core/runtime/templates tests/expected_instance_templates.py
     git status --short
     ```

     La validación funcional usa una instancia temporal externa: crear dos propuestas sobre la
     misma base, aprobar una en TTY real, comprobar que la otra queda `OBSOLETE`, importar un
     concepto v2, confirmar que effective vuelve a su raíz y verificar que todo el historial sigue
     visible. El `rg` y el diff de rutas congeladas deben terminar sin salida.
4e. [x] **Ficha mínima y respuesta del staff (detallado).** Objetivo: conservar una ficha redactada
     manualmente por el agente como Markdown libre, ligada a la composición efectiva exacta que la
     originó, y permitir que la persona usuaria transcriba una respuesta atribuida al staff sobre
     esa versión. Es un registro local y verificable, no acceso al foro ni autenticación del staff.

     **Alcance cerrado.** Modificar `core/character/{models,__init__}.py` y
     `core/runtime/{character,cli,__init__}.py`; ajustar solo el docstring/aserciones necesarios de
     `core/runtime/instance.py` y las pruebas de compatibilidad en
     `tests/test_{character_models,character_state,character_cli,character_proposals,
     character_proposal_cli,instance}.py`; crear
     `tests/test_{character_draft,staff_review_cli}.py`. No modificar `core/review/models.py`,
     `assimilation.py`, `persistence.py`, `workspace.py`, adaptadores, paquetes, las cuatro
     plantillas v1, `tests/expected_instance_templates.py` ni `reference/`. Reutilizar
     `DraftVersion`, `DraftLifecycle`, `ReviewStatus`, `PublicationStatus`, `approve`, `reject`,
     `mark_stale`, `SourceRef`, `HumanConfirmationReceipt`, `Terminal`, `confirm_human_action`,
     `_write_event`, `_read_input` (generalizado solo para rotular concepto/ficha),
     `get_approved_candidate`, `load_strict_json`, `_write_exact` y el codec/cierre de rutas actual.

     **Qué es la ficha mínima.** No interpretar Markdown ni imponer encabezados, campos, plantilla,
     temática o sistema de un foro. La entrada es un archivo UTF-8 sin BOM, fuera del checkout y de
     la instancia, no vacío y sin controles salvo TAB/CR/LF; sus caracteres, incluidos CRLF y la
     ausencia de LF final, se conservan exactamente. Hay una única serie por personaje, con
     `draft_id` interno fijo `character-sheet` y versiones `1, 2, 3…`; no se añade `--draft-id` ni
     una segunda clase de ficha. El agente puede redactarla y ejecutar `draft create`: no es una
     decisión humana y no usa TTY. El core acredita hashes y referencias, no que cada frase cumpla
     semánticamente las normas; esa limitación debe constar en docstring y ayuda.

     **Modelos inmutables.** En `core/character/models.py`, todos `frozen=True, slots=True`, añadir:

     - `CharacterDraftRecord(created_revision: int, composition_sha256: str,
       concept: ConceptRef, corpus_refs: tuple[CorpusCandidateRef, ...], draft: DraftVersion,
       draft_sha256: str = init=False)`. `draft.draft_id` es exactamente `character-sheet`; versión y
       revisión son positivas; contenido usa la validación libre anterior; refs de corpus no se
       repiten. En el evento de alta, `draft` debe ser exactamente `ACTIVE` +
       `PENDING_HUMAN_REVIEW` + `NOT_CONFIRMED`, con `stale_reason`, `review_evidence` y
       `publication_evidence` a `None`.
     - `StaffResponse(review_revision: int, draft_version: int, draft_sha256: str,
       composition_sha256: str, review_status: ReviewStatus, response: str,
       response_sha256: str, receipt: HumanConfirmationReceipt, evidence: SourceRef,
       staff_review_sha256: str = init=False)`. Solo `APPROVED` o `REJECTED`; la respuesta es el
       texto literal atribuido al staff. No hay staff ID, cuenta, rol ni afirmación de identidad.
     - `CharacterDraftView(record: CharacterDraftRecord, effective: DraftVersion,
       staff_response: StaffResponse | None, current: bool, base: EffectiveComposition)`. `record`
       conserva el alta; `effective` se obtiene aplicando `approve`/`reject` y después, si procede,
       `mark_stale`, nunca mutando el registro. `base` es la composición reproducida en la revisión
       de alta.
     - `DraftCreateResult(character: LoadedCharacter, draft: CharacterDraftView, created: bool)` y
       `StaffResponseResult(character: LoadedCharacter, draft: CharacterDraftView,
       response: StaffResponse, created: bool)`.

     Extender `CharacterState` con `drafts: tuple[CharacterDraftRecord, ...] = ()` y
     `staff_responses: tuple[StaffResponse, ...] = ()`; `revision` suma los cinco historiales de
     eventos. Añadir
     `current_draft()`, `draft_at(version)` y `staff_response_for(record)`. Mantener
     `CharacterReplay.views` para propuestas y añadir `draft_views`; reexportar modelos,
     serializadores y operaciones sin retirar exports de 4d.

     **Referencias, hashes y evidencia.** Al crear, exigir por argumento el
     `composition_sha256` mostrado por `character effective show` y capturar bajo el mismo evento:
     su `ConceptRef` y la unión estable, por primera aparición, de las `CorpusCandidateRef` de todas
     las propuestas aplicadas. Cero refs de corpus es válido para una composición que solo contiene
     el concepto. Resolver cada ref mediante `get_approved_candidate`; no aceptar refs aportadas por
     el JSON ni estados pendientes/rechazados/sustituidos.

     Construir el `DraftVersion` inicial con `content` exacto. `source_refs` contiene primero la
     evidencia ya existente del concepto y después un `SourceRef` determinista por candidato:
     `source_id="corpus-candidate:<id>:v<N>"`, locator
     `instance://<forum_id>/corpus/candidates/<id>/v<N>` con segmentos percent-encoded,
     `sha256=candidate_sha256`, `section_or_passage="candidate:<id>:v<N>"`, sin fechas.
     `context_refs` contiene, en ese orden, `character:<character_id>:composition:<hash>`,
     `character:<character_id>:concept:v<N>:<hash>` y una entrada
     `corpus:<id>:v<N>:<hash>` por ref. No duplicar el texto de la composición en el evento.

     `draft_sha256` es SHA-256 de `canonical_json_bytes(..., pretty=False)` del registro persistido
     de alta salvo la propia clave `draft_sha256`. Incluye `composition_sha256`, `concept`,
     `content`, `context_refs`, `corpus_refs`, `created_revision`, `draft_id`, los tres ejes y sus
     evidencias/razón nulas, `source_refs`, `utf8_size` y `version`. Por tanto liga contenido, base,
     referencias y posición del evento.

     La entrada de `staff record` es JSON estricto con exactamente:

     ```json
     {
       "draft_sha256": "<hash mostrado por draft show>",
       "locator": "<URL o localizador manual de la respuesta>",
       "observed_at": "2026-10-12T18:30:00+02:00",
       "response": "Texto literal pegado de la respuesta del staff"
     }
     ```

     `locator` es texto no vacío sin controles y no se abre ni verifica. `observed_at` es obligatorio,
     con offset, y debe ser ya la forma canónica devuelta por `datetime.fromisoformat(...).isoformat()`;
     no se inventa reloj ni se admite fecha IC. `response` conserva Unicode/CRLF/no LF y usa la misma
     validación libre. `response_sha256` es SHA-256 de sus bytes UTF-8. La evidencia de revisión es
     `SourceRef(source_id="staff-response:<character_id>:v<N>", locator=<entrada>,
     sha256=response_sha256, section_or_passage="character-sheet:<character_id>:v<N>",
     observed_at=<entrada>)`; no acredita que el locator, la atribución o la persona sean auténticos.
     `staff_review_sha256` es el hash canónico compacto de todas las claves persistidas de la
     respuesta salvo él mismo, incluidas evidencia, receipt y `review_revision`.

     **Persistencia y compatibilidad 4d.** Usar el mismo
     `characters/<id>/state.json`, no otro sobre. Un segundo archivo exigiría otra autoridad y otro
     cerrojo: una aprobación de propuesta podría cambiar la composición entre archivos sin poder
     marcar la ficha de forma atómica. El único escritor continúa siendo `_write_event`, con el
     lock, anti-junction, recarga completa, revisión esperada y `os.replace` ya probados.

     El decoder acepta exactamente dos formas de `content`: la forma 4d con las cuatro claves
     actuales, que equivale a `drafts=staff_responses=()`, o la forma 4e con esas cuatro más
     `drafts` y `staff_responses`; cinco claves o cualquier extra fallan. El encoder omite ambas
     claves nuevas cuando ambos historiales están vacíos y las incluye cuando alguno no lo está.
     Así un estado 4d1/4d2 carga y se recodifica byte a byte, y cualquier evento de concepto o
     propuesta anterior a la primera ficha conserva la forma de cuatro claves. No cambiar
     `schema_version=1`, el sobre ni `_load_characters`: su árbol permitido sigue siendo solo
     `state.json` y su lock.

     Forma persistida exacta de cada alta (los `SourceRef` de esta estructura usan las seis claves
     `ic_date`, `locator`, `observed_at`, `section_or_passage`, `sha256`, `source_id`, con `null`
     donde corresponda; no se cambia la forma corta de evidencias 4d):

     ```json
     {
       "composition_sha256": "<hash efectivo>",
       "concept": {"concept_sha256": "<hash>", "version": 1},
       "content": "Markdown exacto",
       "context_refs": ["character:ejemplo:composition:<hash>", "character:ejemplo:concept:v1:<hash>"],
       "corpus_refs": [{"candidate_id": "creacion-limites", "candidate_sha256": "<hash>", "version": 1}],
       "created_revision": 4,
       "draft_id": "character-sheet",
       "draft_sha256": "<hash del registro>",
       "lifecycle": "ACTIVE",
       "publication_evidence": null,
       "publication_status": "NOT_CONFIRMED",
       "review_evidence": null,
       "review_status": "PENDING_HUMAN_REVIEW",
       "source_refs": [{"ic_date": null, "locator": "<locator>", "observed_at": null, "section_or_passage": "<pasaje>", "sha256": "<hash>", "source_id": "<id>"}],
       "stale_reason": null,
       "utf8_size": 42,
       "version": 1
     }
     ```

     Cada respuesta persistida tiene exactamente:

     ```json
     {
       "composition_sha256": "<hash citado por la ficha>",
       "draft_id": "character-sheet",
       "draft_sha256": "<hash de ficha>",
       "draft_version": 1,
       "evidence": {"ic_date": null, "locator": "<entrada>", "observed_at": "2026-10-12T18:30:00+02:00", "section_or_passage": "character-sheet:ejemplo:v1", "sha256": "<hash de respuesta>", "source_id": "staff-response:ejemplo:v1"},
       "receipt": {"confirmation_sha256": "<hash de frase>", "method": "TTY_NONCE_V1"},
       "response": "Texto literal",
       "response_sha256": "<hash de respuesta>",
       "review_revision": 5,
       "review_status": "APPROVED",
       "staff_review_sha256": "<hash del registro>"
     }
     ```

     **Reproducción, vigencia y versiones.** Incorporar revisiones de alta y respuesta al mapa
     explícito de eventos de 4d2; exigir unicidad, orden ascendente por cada array y rango
     `1..revision`. Los huecos restantes siguen correspondiendo, en orden, a conceptos. Al
     reproducir un alta, la composición, concepto, refs, `DraftVersion`, fuentes/contexto y hashes
     deben coincidir exactamente con la `EffectiveComposition` de esa revisión; la versión debe ser
     la anterior + 1. Una respuesta debe ser posterior a su ficha, única para esa versión y coincidir
     en ambos hashes y composición; aplica `approve` o `reject` solo al eje de revisión y nunca toca
     la composición.

     Tras reproducir todo, solo la versión mayor es `current=True`. Esta queda `ACTIVE` únicamente
     si su `composition_sha256` aún coincide con la composición efectiva final; si cambió concepto o
     se aprobó otra propuesta, derivar `STALE` con razón exacta
     `EFFECTIVE_COMPOSITION_CHANGED:<hash_anterior>-><hash_actual>`. Todas las versiones menores son
     `STALE` con `SUPERSEDED_BY:character-sheet:v<N>` (esta razón tiene prioridad si además cambió la
     composición). La obsolescencia no se persiste ni consume revisión. Una respuesta tardía se
     puede registrar sobre una ficha `STALE`, porque es un hecho externo sobre esa versión; conserva
     `APPROVED`/`REJECTED` junto a `STALE`. `RETIRED` no se produce en 4e. Crear la versión siguiente
     exige la composición efectiva actual; esa nueva versión es la única vigente. El estado de
     publicación permanece siempre `NOT_CONFIRMED`.

     **Operaciones exactas, idempotencia y concurrencia.** Añadir en
     `core/runtime/character.py`:

     ```python
     def create_draft(instance_root: Path, *, expected_core_root: Path,
                      character_id: str, version: int, composition_sha256: str,
                      input_path: Path) -> DraftCreateResult: ...
     def list_drafts(instance: LoadedInstance, *,
                     character_id: str) -> tuple[CharacterDraftView, ...]: ...
     def get_draft(instance: LoadedInstance, *, character_id: str,
                   version: int) -> CharacterDraftView: ...
     def record_staff_response(instance_root: Path, *, expected_core_root: Path,
                               character_id: str, version: int,
                               review_status: ReviewStatus, input_path: Path,
                               terminal: Terminal) -> StaffResponseResult: ...
     ```

     `create_draft` rechaza hash base viejo, salto de versión y una versión siguiente semánticamente
     idéntica (misma base, refs y contenido). Repetir una versión con todo idéntico devuelve
     `created=False` sin lock, escritura ni cambio de mtime; misma versión con otra entrada da
     `CONFLICT`. `_write_event` vuelve a verificar bajo lock el estado completo y las refs resueltas;
     cualquier evento concurrente, aunque no cambie la composición, da `CONFLICT` y no crea una
     ficha silenciosamente sobre otra revisión.

     `record_staff_response` valida la ruta externa, carga con `load_strict_json` y exige TTY real
     antes de mutar. Una respuesta semánticamente idéntica
     ya registrada (estado, texto, locator, fecha y hashes) devuelve `created=False` sin nuevo reto;
     cualquier diferencia u otra decisión sobre la misma versión da `CONFLICT` y no reescribe
     historia. Antes del prompt comprobar ausencia de lock; después releer el archivo de entrada y,
     dentro de `_write_event`, toda la instancia: cambio de bytes, ficha, composición, refs o
     revisión durante la confirmación da `CONFLICT`. Mantener el guard antes/después del lock y antes
     del replace. EOF, frase distinta y Ctrl+C no escriben; no capturar `KeyboardInterrupt`.

     El prompt de staff se construye exactamente con LF y sin normalizar los dos textos:

     ```text
     REGISTRO HUMANO DE RESPUESTA ATRIBUIDA AL STAFF
     Personaje: CHARACTER_ID
     Ficha: character-sheet vN
     Vigencia actual: ACTIVE|STALE
     Resultado transcrito: APPROVED|REJECTED
     Ficha SHA-256: DRAFT_HASH
     Composición citada SHA-256: COMPOSITION_HASH
     Respuesta SHA-256: RESPONSE_HASH
     Respuesta bytes UTF-8: SIZE
     Locator declarado: LOCATOR
     Observada en: ISO_DATETIME
     Concepto citado: vC | sha256=HASH | evidencia=HASH
     Corpus citado (K):
     Cita 1: ID vN | sha256=HASH | APPROVED
     FICHA CITADA — texto exacto (hasta «Fin de la ficha citada.»):
     <contenido exacto; añadir LF solo para separar el footer>
     Fin de la ficha citada.
     RESPUESTA TRANSCRITA — texto exacto (hasta «Fin de la respuesta.»):
     <respuesta exacta; añadir LF solo para separar el footer>
     Fin de la respuesta.
     La persona usuaria declara que ha transcrito esta respuesta y su localizador sobre esta versión exacta.
     Este registro no autentica al staff, no cambia la composición y no implica publicación, canon, aprendizaje ni utilizabilidad.
     APPROVED acredita aprobación transcrita; REJECTED también abarca rechazo o cambios solicitados, cuyo detalle queda en la respuesta literal.
     Escribe exactamente: REGISTRAR-RESPUESTA-STAFF APPROVED|REJECTED character-sheet vN NONCE
     >␠
     ```

     En el bloque, `␠` representa un único espacio ASCII. Para cero citas,
     `Corpus citado (0):` no lleva líneas posteriores. `phrase_prefix` exacto es
     `REGISTRAR-RESPUESTA-STAFF <STATUS> character-sheet v<N>`. Los bytes finales son `> ` sin LF.
     La barrera A solo frena el camino automatizado: ni el recibo ni el nombre del comando prueban
     que contestó el staff; quien opera es la persona usuaria que transcribe.

     **CLI exacta.** Añadir:

     ```text
     character draft create --instance RUTA --character-id ID --version N --composition-sha256 HASH --input RUTA
     character draft list --instance RUTA --character-id ID
     character draft show --instance RUTA --character-id ID --version N
     character staff record --instance RUTA --character-id ID --version N --status {APPROVED,REJECTED} --input RUTA
     ```

     Todo es obligatorio; versión positiva y hash minúsculo canónico. `staff record` rechaza el flag
     global `--json` con `INVALID_STATE`: `las respuestas de staff transcritas no admiten --json:
     ejecuta el comando en tu terminal y responde a la confirmación`; los otros tres lo admiten.
     No añadir `publish`, `confirm-publication`, `export`, `send` ni sinónimo.

     Una línea resumen es exactamente `character-sheet vN | ACTIVE|STALE | CURRENT|SUPERSEDED |
     PENDING_HUMAN_REVIEW|APPROVED|REJECTED | NOT_CONFIRMED | composición=HASH | sha256=HASH |
     bytes=SIZE | corpus=K`. Texto:

     - create: `Ficha creada:` o `Ficha ya existente:` seguido del resumen, luego
       `Revisión del personaje: R.` y el bloque `Ficha para copia manual (no acredita publicación,
       hasta «Fin de la ficha.»):` / `Fin de la ficha.`;
     - list: una línea por versión; si estuviera vacío, `No hay fichas para «CHARACTER_ID».`;
     - show: resumen; `Respuesta del staff: ninguna.` o
       `Respuesta del staff: STATUS | respuesta=HASH | registro=HASH | locator=<JSON string> |
       observada=ISO.`, las líneas de concepto/corpus y los bloques exactos de ficha y, si existe,
       respuesta. El encabezado de copia deja claro que stdout sirve para copiar/pegar manualmente,
       no confirma que se haya publicado;
     - staff record: `Respuesta del staff registrada:` o `Respuesta del staff ya registrada:`,
       `character-sheet vN | STATUS | respuesta=HASH | registro=HASH`, después el resumen efectivo y
       `Revisión del personaje: R.`.

     JSON de éxito usa claves raíz exactas:

     - create: `ok`, `action="character.draft.create"`, `character_id`, `created`, `draft`
       (registro de vista completo), `instance`, `state_revision`;
     - list: `ok`, `action="character.draft.list"`, `character_id`, `drafts` (resúmenes),
       `instance`, `state_revision`;
     - show: `ok`, `action="character.draft.show"`, `character_id`, `draft` (registro de vista
       completo), `instance`, `staff_response` (registro persistido o `null`), `state_revision`.

     El resumen JSON contiene exactamente `composition_sha256`, `corpus_ref_count`, `current`,
     `draft_id`, `draft_sha256`, `lifecycle`, `publication_status`, `review_status`, `utf8_size`,
     `version`. La vista completa añade `concept`, `content`, `context_refs`, `corpus_refs`,
     `review_evidence`, `source_refs` y `stale_reason`; no incluye una supuesta identidad de staff.
     Mantener errores `{"ok":false,"code","message"}`, `_write_exact` y códigos 0/2/3/4/5:
     parser → 2; entrada/fecha/texto/formato de hash/estado/no encontrado → 3; hash bien formado
     que no corresponde a la ficha, identidad/versión/base/revisión/lock/carrera → 4; E/S → 5.

     **Tests.** `test_character_draft.py`: validación e inmutabilidad; Markdown Unicode, CRLF/LF/no
     LF/controles; refs derivadas sin citas, con citas repetidas entre pasos y orden estable; hashes,
     tamaños, locators percent-encoded y `SourceRef`; formas persistidas exactas; decoder de cuatro
     y seis claves y rechazo de cinco/extras; reencode byte a byte de estados 4d1/4d2; revisión como
     suma de cinco historiales de eventos y manipulación de cada campo/hash/ref/evidencia.

     Probar reproducción con ficha v1 pendiente, respuesta aprobada/rechazada, aprobación tardía
     sobre ficha stale, propuesta aprobada o concepto nuevo que vuelve stale sin escribir, v2 que
     sustituye v1, prioridad de razón, conservación de `NOT_CONFIRMED` y que staff jamás cambia
     `EffectiveComposition`. Cubrir idempotencia/mtime, versión repetida/saltada, base vieja, retry
     tras reinicio, entrada externa/link, cita que deja de resolver, lock/guard/junction swap,
     replace fallido, fallo de liberación y carreras sin pérdida.

     `test_staff_review_cli.py`: parser y cuatro comandos; create/list/show texto y JSON exactos;
     bloque de copia exacto; archivo vacío/BOM/UTF-8/controles; JSON staff con claves extra/faltantes/
     duplicadas, fecha sin zona/no canónica, locator y hash discordante; prompt completo con cero y
     varias citas, ficha/respuesta larga, marcadores y LF/no LF; frase, nonce de un intento, EOF,
     case, espacios, Ctrl+C, no TTY, stdin o stdout redirigido y `--json` sin mutación. Probar ambos
     resultados, «cambios solicitados» como `REJECTED` con texto literal, retry sin prompt,
     respuesta distinta, cambio de input/estado durante prompt, códigos y ausencia de subcomando de
     publicación. Las suites 4d prueban además que conceptos/propuestas preservan ambos historiales
     y que sus prompts/salidas no cambian; las plantillas v1 continúan byte a byte.

     **Criterios de aceptación.** La ficha es texto libre genérico y cada versión queda ligada a la
     composición, concepto y candidatos aprobados exactos de su alta. Nace `ACTIVE` +
     `PENDING_HUMAN_REVIEW` + `NOT_CONFIRMED`; cambios posteriores solo derivan `STALE` y una nueva
     versión sustituye a la anterior sin borrar historia. La persona usuaria, no una identidad de
     staff autenticada, transcribe texto/locator/fecha y supera barrera A para registrar
     `APPROVED`/`REJECTED` sobre hash y versión exactos. Staff no modifica composición, no aprueba
     propuestas de diseño, no publica, no canoniza, no enseña ni vuelve utilizable nada. La salida
     permite copia manual; no hay comando ni estado alcanzable de publicación. Sin red, modelo,
     SQLite, contenido temático, nuevo sobre, nueva plantilla ni cambio de schema.

     Verificación exacta desde PowerShell:

     ```powershell
     py -3.11 -B -m unittest tests.test_character_draft tests.test_staff_review_cli tests.test_character_models tests.test_character_state tests.test_character_cli tests.test_character_proposals tests.test_character_proposal_cli tests.test_instance -v
     py -3.11 -B -m unittest tests.test_review_models tests.test_assimilation_decisions tests.test_assimilation_decision_cli -v
     py -3.11 -B -m unittest discover -s tests -v
     py -3.11 -B -m core.runtime.cli --json character effective show --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo'
     py -3.11 -B -m core.runtime.cli character draft create --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --version 1 --composition-sha256 '<HASH_EFECTIVO>' --input '<FICHA_MD_EXTERNA>'
     py -3.11 -B -m core.runtime.cli character draft show --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --version 1
     py -3.11 -B -m core.runtime.cli character staff record --instance '<RUTA_INSTANCIA>' --character-id 'ejemplo' --version 1 --status APPROVED --input '<RESPUESTA_STAFF_JSON_EXTERNA>'
     rg -n "publish|confirm.publication|PublicationStatus.PUBLISHED|confirm_publication" core/runtime/cli.py core/runtime/character.py core/character
     rg -n "Nozomu|Naruto|Jcink|narutorol|account 59|275" core/character core/runtime/character.py tests/test_character_draft.py tests/test_staff_review_cli.py
     git diff --check
     git diff --name-only 130d0bf -- reference core/runtime/templates tests/expected_instance_templates.py
     git status --short
     ```

     La validación funcional usa una instancia temporal y entradas externas: crear v1 sobre el hash
     mostrado, copiar su bloque sin efectuar publicación, importar después un concepto v2 para verla
     `STALE` sin nueva revisión, crear v2 sobre la nueva composición y registrar en TTY real una
     respuesta atribuida al staff. Reiniciar entre fases, repetir create/record para comprobar no-op,
     verificar que ambas versiones/respuesta sobreviven y que composición, publicación, corpus y
     plantillas no cambiaron. Ambos `rg` y el diff de rutas congeladas deben quedar vacíos.
4f. [x] **Recorrido vertical y contrato integrado.** Alcance:
    `tests/fixtures/vertical-neutral/` solo para JSON/Markdown de entrada neutros,
    `tests/test_vertical_slice.py` y correcciones estrictamente necesarias en archivos 4a–4e.
    Copiar los inputs fixture a temporales externos antes de importarlos. Recorrer: expediente →
    workspace → cuatro clases de candidato →
    decisiones y cierre exactos → instancia → declaración humana de concepto → dos propuestas
    completas sobre la base exacta (una aceptada y otra rechazada/obsoleta) → composición efectiva
    → ficha v1 pendiente → concepto v2 y `STALE` derivado → ficha v2 → respuesta de staff
    transcrita sobre v2. Criterio: el recorrido sobrevive reinicio entre fases, las repeticiones no
    cambian historial, solo concepto declarado + corpus/propuestas aprobados forman las referencias
    de la ficha, la respuesta no altera composición ni publicación, instrucciones v1 no divergen y
    ninguna ruta invoca modelo, red, publicación o contenido temático.
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

No hay dudas bloqueantes que deba decidir el usuario para implementar 4e. El plan recomienda y fija:
Markdown libre sin campos de foro; una serie `character-sheet` versionada; `STALE` derivado, no
persistido; respuesta transcrita por la persona con texto, locator y fecha aportados; cambios
solicitados representados como `REJECTED` más respuesta literal; salida de copia manual sin
publicación; y eventos 4e en el mismo estado del personaje para conservar una sola autoridad y un
solo cerrojo. Estas elecciones reutilizan los ejes existentes y evitan confundir revisión de diseño,
staff y publicación. Si se desea distinguir `CHANGES_REQUESTED` como estado consultable —en vez de
detalle literal bajo `REJECTED`— debe decidirse antes de implementar porque ampliaría el enum
compartido `ReviewStatus`, sus transiciones y contratos anteriores; no se recomienda para este
subincremento mínimo. No se cambia la política de instrucciones v1.

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

### Incremento 4a — workspace externo e importación manual
- Rama: `feature/incremento-4-rebanada-vertical` (base `42e724a`); incluye el detalle del
  incremento 4 escrito por Codex.
- Cambios hechos: `core/runtime/{persistence,workspace,cli}.py`, exports en
  `core/runtime/__init__.py`, `adapters/{__init__,manual}.py`,
  `core/runtime/templates/workspace.template.json`,
  `tests/test_{workspace_persistence,manual_adapter,assimilation_workspace_cli}.py`.
- Resultado de los tests: las tres suites de 4a → 47 OK; suite completa → 192 OK en `py -3.11`
  y `py -3.14`, sin omitidos. Prueba manual de la CLI en un temporal externo: `init` crea,
  repetir `init` no escribe, `status` OK, una edición a mano da código 3, `init` sobre un
  workspace cambiado da 4 y un destino dentro del repo da 4 sin crear nada. `rg` sin
  coincidencias; `reference/` sin cambios desde `42e724a`; `git diff --check` limpio.
- Revisión de Codex: «requiere cambios» (REV4A-01 alta, REV4A-02..03 media, REV4A-04 baja);
  corregidos juntos:
  - REV4A-01: las rutas se comparan por una identidad canónica (`_identity`: sin prefijo de
    dispositivo `\\?\`/`\\.\`, `realpath` con nombres largos y enlaces resueltos, `normcase`) y
    `_is_link` rechaza symlinks y junctions (reparse points con el bit *name surrogate*) en
    destino, raíz y cada componente gestionado. Otros reparse points, como los marcadores de
    OneDrive, se tratan como contenido normal para no impedir workspaces en carpetas
    sincronizadas.
  - REV4A-02: si otro actor crea el destino durante la creación, nunca se sobrescribe: un árbol
    idéntico da resultado idempotente (`created=False`) y cualquier otro, `CONFLICT`.
  - REV4A-03: errores JSON con exactamente `{"ok":false,"code","message"}`.
  - REV4A-04: un temporal o staging que no se puede borrar se informa con su ruta en el error.
  - Resultado tras las correcciones: 57 tests de 4a y 202 en total, OK en `py -3.11` y
    `py -3.14`, sin omitidos (junctions creadas con `_winapi.CreateJunction`).
  - Riesgo conocido fuera de 4a: el loader de paquetes (incremento 2) y el de expediente
    (incremento 3) siguen usando `is_symlink()`, que no detecta junctions; el de expediente
    rechaza las que salen de la carpeta por la comprobación de ruta resuelta.
- Desviaciones del plan y decisiones de detalle que el plan no fijaba:
  - `adapters/manual.py` importa el mapa privado `_HEADINGS` de `assimilation.py` para nombrar
    en español las secciones que faltan, porque el plan prohíbe modificar ese módulo. Alternativa
    para revisar: exponerlo como constante pública en un incremento posterior.
  - `core/runtime/cli.py` importa `adapters.manual` (el runtime compone adaptadores; los
    adaptadores no importan el runtime).
  - Mensajes de persistencia y workspace en español, como los del expediente. Se añadió
    `parse_strict_json(raw, locator)` en `persistence.py` (no reexportado) para validar bytes ya
    leídos.
  - `load_state` exige que el archivo sea byte a byte su codificación canónica, no solo que el
    hash coincida; así una edición de espacios también falla.
  - Ruta del workspace: se admite relativa y se resuelve contra el directorio actual con
    `Path.absolute()` (no `resolve()`, para no seguir un symlink en el último componente).
    `core_root` se guarda resuelto y `expected_core_root` se compara resuelto.
  - Los archivos de material se copian desde los bytes del literal ya cargado y hasheado (no se
    releen); `expediente.md` sí se relee y la recarga de la copia debe coincidir con lo cargado.
  - Reintento de `init`: se compara el árbol completo (incluidas carpetas vacías) con lo que se
    generaría; si el corpus ya avanzó (`revision > 0`) el reintento es `CONFLICT`, no éxito.
  - `load_workspace` rechaza también archivos de `dossier/` que no figuren en `dossier.files` y
    un `corpus/state.json` ausente como `INVALID_STATE` (no `IO`).
  - Se rechaza además un workspace que sea ancestro del checkout o del expediente.
  - CLI: JSON con `ensure_ascii=True` para que no dependa de la codificación de la consola;
    errores de texto a stderr y, con `--json`, un único objeto de error en stdout. Los errores de
    expediente y de expediente no listo salen con código 3. (La forma de error JSON que anoté
    inicialmente se desviaba del contrato «CLI mínimo de la rebanada»; corregido en REV4A-03.)
- Revisión archivada en `docs/analisis/incremento-4a-revision.md` (veredicto final: aprobado
  tras dos verificaciones; REV4A-04 necesitó una segunda ronda por la rama de carrera idéntica).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Plan `01a12b46-…` (1 encargo: detalle y división del incremento 4); incremento respecto a
      la medición del incremento 3: entrada 8.281.699 (caché leída 8.100.096), salida 59.620
      (razonamiento 30.836). El hilo acumula 14,5 M de entrada: conviene abrir uno nuevo con
      resumen para el análisis de 4b–4f.
    - Revisión `01a12ccc-2724-74b0-91a5-f1d563f7be3f` (3 encargos: revisión + 2 verificaciones):
      entrada 3.809.127 (caché leída 3.684.224), salida 29.402 (razonamiento 15.746).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Sigue con él»; 39 respuestas de API):
    entrada 78, salida 75.000, caché leída 17.015.633, caché escrita 105.737. Coste NO
    DISPONIBLE.
  - Retrabajo: dos rondas de corrección (4 hallazgos + 1 pendiente); una prueba manual con ruta
    mal compuesta creó un workspace fuera del temporal, eliminado de inmediato; un literal de
    test mal escapado corregido antes de la verificación.

### Incremento 4b — candidatos manuales citados
- Rama: `feature/incremento-4-rebanada-vertical` (base `91289a7`); incluye la decisión de barrera
  A y el detalle de 4b escritos por Codex en un hilo nuevo.
- Cambios hechos: candidatos en `core/runtime/assimilation.py` (enums, `AssimilationError`,
  `CandidateCitation`, `AssimilationCandidate`, `CandidateAddResult`, `parse_candidate_input`,
  `decode_candidate_state`, `add_candidate`); `LoadedWorkspace.candidates` y decodificación
  completa del corpus en `core/runtime/workspace.py` (se eliminó `_check_corpus`); comandos
  `assimilation source list|show` y `assimilation candidate add|list|show` en
  `core/runtime/cli.py`; exports; `tests/test_assimilation_{candidates,cli}.py`.
- Resultado de los tests: las dos suites de 4b → 42 OK; suite completa → 245 OK en `py -3.11`
  y `py -3.14`, sin omitidos. Prueba manual en un temporal externo: `source list/show`, alta
  de las cuatro clases (revisiones 1–4), reintento sin escritura, `UNCERTAINTY` marcada como
  «REQUIERE CONFIRMACIÓN», cita ambigua rechazada con posiciones y `status` íntegro. `rg` sin
  coincidencias; `reference/` sin cambios desde `91289a7`; `git diff --check` limpio.
- Desviaciones del plan y decisiones de detalle que el plan no fijaba:
  - `cli.py` importa los auxiliares privados `_source_declarations`, `_SourceDeclaration` y
    `_candidate_record` de `assimilation.py` para no duplicar la selección de fuentes ni la
    forma persistida (la CLI es interna del core; no se reexportan).
  - `source list` colapsa las declaraciones idénticas (misma sección, id, versión y pasaje),
    igual que la resolución de citas; el material suelto aparece al final.
  - `candidate list` muestra todas las versiones (el historial) en orden de inserción.
  - El diagnóstico de cita ambigua lista como máximo diez posiciones y resume el resto.
  - `CandidateCitation` exige además `end - start == len(quote)`. `text` y `quote` admiten
    saltos y tabuladores (son literales); `scope` sigue la regla de texto sin controles.
  - Propiedades auxiliares `AssimilationCandidate.key`, `.requires_confirmation` y
    `CandidateCitation.coordinate`.
  - `source show` en texto quita el `\r` final de cada línea al mostrarla (es una ayuda visual
    numerada; el JSON entrega el literal exacto).
- Revisión de Codex: «requiere cambios» (REV4B-01 y REV4B-02, media); corregidos juntos:
  - REV4B-01: toda la salida de la CLI (texto, JSON y errores) pasa por `_write_exact`: UTF-8
    exacto con finales LF escrito en el buffer binario, sin traducción de saltos ni
    sustitución de caracteres, sea cual sea la página de códigos de la consola. Se retiró el
    `reconfigure(errors="replace")`. `candidate show` imprime `Texto (exacto, hasta «Fin del
    texto.»):`, el texto tal cual y, si no termina en salto, la línea
    `(el texto no termina en salto de línea)` antes de `Fin del texto.`.
  - REV4B-02: tests de colapso de declaraciones idénticas, ambigüedad de `source show` con
    ambos selectores, las seis secciones RULES con fuentes (y WORLD rechazado en cada una),
    historial completo en `candidate list`, inmutabilidad de `CandidateCitation` y
    `CandidateAddResult`, y texto exacto por `main` y por subproceso con
    `PYTHONIOENCODING=ascii:strict` (CRLF, salto final y Unicode).
  - Resultado tras las correcciones: 49 tests de 4b y 252 en total, OK en `py -3.11` y
    `py -3.14`, sin omitidos.
- Revisión archivada en `docs/analisis/incremento-4b-revision.md` (veredicto final: aprobado).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Análisis `01a12fb4-2c71-71c3-b73d-30683f51381c` (hilo nuevo, 1 encargo: barrera A y
      detalle de 4b): entrada 3.134.651 (caché leída 3.013.248), salida 24.491 (razonamiento
      11.745). Frente al encargo equivalente del hilo anterior (8,3 M de entrada), abrir un
      hilo nuevo redujo la entrada a menos de la mitad.
    - Revisión `01a12fc1-e87e-7580-8870-75dd6f5ed655` (2 encargos: revisión + verificación):
      entrada 4.441.362 (caché leída 4.274.432), salida 31.603 (razonamiento 19.580).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Nos vamos con la opción A»; 35
    respuestas de API): entrada 70, salida 73.183, caché leída 18.498.005, caché escrita
    560.611. Coste NO DISPONIBLE.
  - Retrabajo: una ronda de correcciones (2 hallazgos); un heredoc de shell fallido sin
    efectos; un retorno de carro colado en estas notas y corregido; un caso de test mal
    planteado corregido antes de la revisión.

### Incremento 4c1 — decisiones y cierre con barrera humana
- Rama: `feature/incremento-4-rebanada-vertical` (base `91205fc`); incluye el detalle de 4c1/4c2
  escrito por Codex en el hilo de análisis de 4b.
- Cambios hechos: en `core/runtime/assimilation.py`, modelos `HumanConfirmationReceipt`,
  `AssimilationDecision`, `AssimilationClosure`, `AssimilationState`, `DecisionResult`,
  `ClosureResult`, protocolo `Terminal`, `record_candidate_decision`, `close_assimilation` y
  `decode_candidate_state` ampliado (decisiones, cierre y revisión); `add_candidate` conserva
  las decisiones y rechaza altas tras el cierre. `LoadedWorkspace` añade `decisions` y
  `closure`. CLI: `assimilation candidate approve|reject`, `assimilation decision list` y
  `assimilation close`, con `_SystemTerminal` (stdin y stdout TTY). Exports. Tests nuevos
  `tests/test_assimilation_{decisions,decision_cli}.py`; ajustados el test de decodificación
  de 4b (nueva firma) y el test de comandos inexistentes de 4b (approve/reject/close ya
  existen).
- Resultado de los tests: suites de 4c1 → 31 OK; suite completa → 283 OK en `py -3.11` y
  `py -3.14`, sin omitidos. Prueba de API con terminal simulado: cinco aprobaciones, cierre en
  la revisión 11 (base 10), recarga íntegra y sin el código en el estado. Por subproceso sin TTY,
  `approve` y `close` salen con código 3 sin escribir. `rg` sin coincidencias; `reference/` sin
  cambios desde `91205fc`; `git diff --check` limpio.
- Revisión de Codex: «no aprobado» (REV4C1-01 alta, REV4C1-02 media, REV4C1-03 baja como
  sugerencia); corregidos juntos:
  - REV4C1-01: cerrojo de archivo `corpus/state.json.lock` creado con `O_CREAT|O_EXCL`. Toda
    mutación del corpus (`add_candidate` entera; en decisión y cierre, desde la segunda lectura
    hasta la escritura) ocurre bajo el cerrojo, así que una mutación concurrente da `CONFLICT`
    en vez de perderse. No se mantiene durante la espera de la frase. Un cerrojo huérfano tras
    una caída bloquea con `CONFLICT` y un mensaje que nombra el archivo a borrar; decisión y
    cierre lo comprueban antes de pedir la frase. Es la solución provisional hasta los locks del
    incremento 9.
  - REV4C1-02: el límite de la barrera A (frena la automatización, no autentica a la persona;
    un `Terminal` falso, una pseudo-TTY o un core modificado la eluden) consta en los docstrings
    de `Terminal`, `record_candidate_decision` y `close_assimilation`, y en la ayuda de
    `approve`, `reject` y `close`.
  - REV4C1-03: `candidate list` añade ` | decisión=APPROVED|REJECTED` en texto y la clave
    `decision` (`null` o estado) en JSON; `candidate show` añade la línea `Decisión: pendiente`
    o `Decisión: <estado> (evidencia=<sha>)` y la clave JSON `decision` (`null` o resumen). Es
    un cambio de contrato de salida de 4b: los tests de 4b se ajustaron a las claves nuevas.
  - REV4C1-04 (nuevo en la verificación): un fallo al borrar el cerrojo ya no se silencia. Tras
    una escritura correcta se informa `IO` con «el cambio se guardó, pero no se pudo borrar el
    cerrojo <ruta>»; tras un error, se conserva su código y se añade «no se guardó ningún cambio,
    pero no se pudo borrar el cerrojo <ruta>», con el error original como causa. Si falla el
    cierre del descriptor se intenta borrar el cerrojo y se informa si queda.
  - Resultado tras las correcciones: 43 tests de 4c1 y 295 en total, OK en `py -3.11` y
    `py -3.14`, sin omitidos.
- Validación funcional: el 12-10-2026 el usuario informó que ejecutó en la terminal integrada
  de VS Code los cinco `candidate approve` y el `close` sobre el workspace temporal preparado
  por Claude, sin incidencias. No verificado por Claude: el workspace ya se había borrado
  cuando intentó comprobar el estado. Se repetirá con verificación al terminar 4f.
- Decisiones de detalle que el plan no fijaba:
  - Orden en `record_candidate_decision`: terminal interactivo → estado pedido válido → carga
    con revisión esperada → candidato existente → decisión existente (idempotente u opuesta) →
    cierre → versión vigente. Un reintento idéntico tras el cierre devuelve la decisión
    existente sin reto.
  - `AssimilationState.current_versions()` y `.decision_for()` como auxiliares públicos del
    modelo.
  - `decision list` vacío imprime `No hay decisiones.`.
  - `candidate list/show` muestran la decisión efectiva junto al estado inmutable del registro
    (ver REV4C1-03).
  - `tests/test_assimilation_decision_cli.py` reutiliza `FakeTerminal` y los datos de
    `tests/test_assimilation_decisions.py`.
- Revisión archivada en `docs/analisis/incremento-4c1-revision.md` (veredicto final: aprobado
  tras dos verificaciones; la segunda encontró REV4C1-04, introducido por el cerrojo).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Análisis `01a12fb4-…` (1 encargo: detalle de 4c1/4c2); incremento respecto a la medición
      de 4b: entrada 3.695.304 (caché leída 3.623.680), salida 23.940 (razonamiento 13.822).
    - Revisión `01a12fdd-7db9-75a1-b075-83635b559645` (3 encargos: revisión + 2 verificaciones):
      entrada 5.149.814 (caché leída 5.002.624), salida 26.351 (razonamiento 13.675).
    - Incidencia: la llamada MCP de la segunda verificación se abortó en el lado de Claude tras
      4.575 s sin respuesta del servidor; Codex terminó el turno y escribió `REVISION.md`, que
      se leyó del disco. Escritura de caché 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde el segundo «Sigue con él»; 50
    respuestas de API): entrada 104, salida 79.055, caché leída 32.246.027, caché escrita
    784.886. Coste NO DISPONIBLE.
  - Retrabajo: dos rondas de corrección (3 hallazgos + 1 nuevo); dos tests mal planteados
    corregidos antes de la revisión; una espera con señal errónea (mtime en Windows) relanzada.

### Incremento 4c2 — instancia cerrada e instrucciones generadas
- Rama: `feature/incremento-4-rebanada-vertical` (base `8e3185c`); incluye el detalle de 4c2
  escrito por Codex y la nota de validación funcional de 4c1.
- Cambios hechos: `core/runtime/instance.py`; plantillas `core/runtime/templates/{instance.template.json,
  instance-policy.template.md,AGENTS.template.md,CLAUDE.template.md}` (comprobadas byte a byte
  contra los bloques de este plan); comandos `instance init|status` e `instance corpus list|show`
  en `core/runtime/cli.py`; exports; tests `tests/test_instance{,_templates,_cli}.py` y el
  auxiliar `tests/instance_support.py`.
- Resultado de los tests: suites de 4c2 → 40 OK; suite completa → 335 OK en `py -3.11` y
  `py -3.14`, sin omitidos. Prueba manual: `instance init` rechaza un workspace sin cierre;
  con cierre crea la instancia (rutas con comilla y «ñ»), el reintento no reescribe, y tras
  borrar el workspace `status`, `corpus list` y `corpus show` funcionan; una versión rechazada
  o sustituida da código 3. `reference/` sin cambios desde `8e3185c`; `git diff --check`
  limpio.
- Revisión de Codex: «no aprobado» (REV4C2-01 y REV4C2-02 altas, REV4C2-03 media, REV4C2-04
  baja); corregidos juntos:
  - REV4C2-01: `_linked_component` (en `workspace.py`) rechaza un symlink o junction en
    cualquier componente existente de la ruta, padres incluidos, al crear y al cargar; se repite
    justo antes de publicar.
  - REV4C2-02: `_destination_state` registra la identidad inicial del destino (ausente, o
    dispositivo+inodo de la carpeta vacía) y `_publish` la exige antes de publicar: ausente →
    aparecida, o vacía → sustituida, dan `CONFLICT` sin tocar el destino. Si el rename falla y
    el destino existe, `_ConcurrentDestination` lo trata como carrera (idéntica → idempotente;
    distinta → `CONFLICT`).
  - REV4C2-02 (segunda ronda, POSIX): en POSIX rename aún podía reemplazar una carpeta vacía
    creada en el instante final. Decisión de Claude, conservadora y reversible: crear
    workspaces e instancias solo se permite en Windows (`_require_publish_support`, código 4 con
    mensaje claro); leer y consultar siguen funcionando en cualquier sistema. El proyecto ya es
    de facto solo Windows (instrucciones PowerShell, lanzador `py`). Añadir soporte POSIX exige
    una publicación sin reemplazo con sus propias pruebas en ese sistema.
  - Ampliación de alcance (anotada para la verificación): REV4C2-01 y REV4C2-02 existían también
    en el workspace de 4a, porque la instancia reutiliza su lógica; se corrigieron en los
    auxiliares compartidos de `workspace.py`, que ahora usan ambos, con regresiones en
    `tests/test_workspace_persistence.py`.
  - REV4C2-03: la recarga rechaza directorios no implicados por los archivos gestionados,
    incluidos vacíos y anidados.
  - REV4C2-04: `tests/expected_instance_templates.py` congela las cuatro plantillas y se
    comparan byte a byte, igual que `AGENTS.md`/`CLAUDE.md` renderizados; `ExactOutputTest`
    compara salidas completas de `init`, `status`, `corpus list` y `corpus show` en texto y
    JSON.
  - Resultado tras las correcciones: 349 tests OK en `py -3.11` y `py -3.14`, sin omitidos.
- Desviaciones del plan y decisiones de detalle:
  - Seguridad de rutas: en lugar de reproducir en `instance.py` el algoritmo de 4a, se
    reutilizan los auxiliares ya revisados de `workspace.py` (`_checkout`, `_identity`,
    `_contains`, `_is_link`, `_tree_bytes`, `_remove_staging`, `_strip_device_prefix`,
    `_managed`, `_parse_managed_list`, `_check_managed_list`); sus `WorkspaceError` se
    convierten en `InstanceError` con el mismo código. Evita duplicar código delicado.
  - `render_instructions(template, config)` es pública para que `load_instance` y los tests
    comparen las instrucciones renderizadas con las del disco.
  - `instance_root` y `core_root` se guardan con `realpath` sin prefijo de dispositivo y con su
    capitalización real (no `normcase`); la comparación sigue usando la identidad canónica.
  - En `corpus show`, si una cita o el texto no terminan en LF se añade solo el LF separador,
    como fija el plan (el JSON conserva la terminación exacta); no se añade la línea aclaratoria
    de `candidate show`.
  - `--version` de `corpus show` usa un tipo de argparse que exige entero positivo (código 2).
  - Se ajustaron dos tests de 4a/4b que listaban `instance` como comando inexistente (ahora
    existe); siguen comprobando que no hay comandos de publicación.
  - El `rg` de verificación coincide únicamente en `tests/test_instance_templates.py`, que
    enumera esos nombres para afirmar que las plantillas renderizadas no los contienen.
- Revisión archivada en `docs/analisis/incremento-4c2-revision.md` (veredicto final: aprobado
  tras dos verificaciones; la segunda dejó solo la parte POSIX de REV4C2-02).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Análisis `01a12fb4-…` (1 encargo: detalle de 4c2); incremento respecto a la medición de
      4c1: entrada 1.974.224 (caché leída 1.691.520), salida 23.848 (razonamiento 10.678).
    - Revisión `01a13050-7451-72b0-b060-9cc1b54bde4f` (3 encargos: revisión + 2
      verificaciones): entrada 4.806.062 (caché leída 4.657.280), salida 32.537 (razonamiento
      18.252).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «primero acabemos con toda la
    configuración»; 35 respuestas de API): entrada 70, salida 81.781, caché leída 27.113.860,
    caché escrita 110.099. Coste NO DISPONIBLE.
  - Retrabajo: dos rondas de corrección (4 hallazgos, uno en dos pasos); un caso de 4a roto por
    el arreglo compartido y corregido antes de la verificación; limpieza errónea en un test
    corregida antes de la verificación.

### Incremento 4d1 — estado de personaje y declaración del concepto humano
- Rama: `feature/incremento-4-rebanada-vertical` (base `45f667a`); incluye el detalle de 4d1/4d2
  escrito por Codex.
- Cambios hechos: `core/character/{__init__,models}.py`; `core/runtime/character.py`
  (`import_concept`, `list_concepts`, `get_concept`, `find_character`); en
  `core/runtime/assimilation.py`, `confirm_human_action` y el auxiliar `_read_confirmation`
  que ahora usa `_confirm` (prompts de 4c1 sin cambios: sus tests pasan); en
  `core/runtime/instance.py`, el espacio mutable `characters/` y `LoadedInstance.characters`;
  comandos `character concept import|list|show`; exports. Tests nuevos
  `tests/test_character_{models,state,cli}.py`.
- Resultado de los tests: suites de 4d1 → 39 OK; suite completa → 388 OK en `py -3.11` y
  `py -3.14`, sin omitidos. Prueba de API con terminal simulado: v1, reintento sin escribir, v2,
  `list`/`show` por CLI, e `import` sin TTY o con `--json` rechazados con código 3. Plantillas y
  `tests/expected_instance_templates.py` sin cambios desde `45f667a`; `rg` sin coincidencias;
  `git diff --check` limpio.
- Revisión de Codex: «requiere correcciones» (REV4D1-01 alta, REV4D1-02 media); corregidos
  juntos:
  - REV4D1-01: `_path_guard` comprueba que la carpeta del personaje sigue siendo la misma
    (dispositivo+inodo) y sin enlaces en la ruta antes de tomar el cerrojo, justo después de
    tomarlo (nuevo parámetro `guard` de `_corpus_lock`) y justo antes de escribir; si falla, se
    libera el cerrojo y no se escribe nada. Límite documentado: entre la última comprobación y el
    reemplazo atómico queda una ventana que no se puede cerrar sin APIs relativas a un handle,
    que la biblioteca estándar no ofrece en Windows.
  - REV4D1-02: `_corpus_lock` informa un fallo de liberación tras cualquier error con `code` y
    `reason` (AssimilationError, CharacterError, PersistenceError…), conservando su tipo y
    código, y tras un `OSError`. Cualquier otra excepción (p. ej. `RuntimeError` o Ctrl+C) conserva
    su tipo, pero recibe con `add_note` el aviso del cerrojo huérfano (segunda verificación).
  - Riesgo conocido fuera de 4d1: las mutaciones del corpus del workspace (4b–4c1) no usan
    todavía un `guard` equivalente frente a la sustitución de carpetas por junctions durante el
    cerrojo.
  - Resultado tras las correcciones: 42 tests de 4d1 y 391 en total, OK en `py -3.11` y
    `py -3.14`, sin omitidos.
- Validación funcional: el 12-10-2026 el usuario ejecutó `character concept import` en la
  terminal integrada de VS Code sobre `%TEMP%\roleplay-prueba-4d1`. Claude lo verificó: `aria v1`
  con recibo `TTY_NONCE_V1`, revisión 1 y texto idéntico al archivo de entrada.
- Decisiones de detalle que el plan no fijaba:
  - Cerrojo: en lugar de copiar la semántica de 4c1, `_corpus_lock` y `_require_unlocked`
    reciben un `subject` («el corpus» por defecto, «este personaje» aquí) y se reutilizan; los
    mensajes de 4c1 no cambian salvo «cerrojo para el corpus» en el fallo al cerrar el
    descriptor.
  - El error de terminal no interactiva dice ahora «esta acción humana exige…» (antes «esta
    decisión…»), porque también lo usa la importación del concepto.
  - Un concepto en blanco (solo espacios o saltos) cuenta como vacío.
  - Orden de `import_concept`: terminal interactiva → ID y versión → carga de la instancia →
    archivo de entrada → idempotencia y conflictos → cerrojo libre → frase → segunda lectura de
    instancia y archivo → escritura (publicación atómica de `characters/<id>/` en la v1;
    cerrojo y escritura atómica en las siguientes).
  - Una v1 concurrente de otro proceso nunca es idéntica (lleva otro recibo), así que da
    `CONFLICT` sin tocar el ganador.
  - Una importación fallida puede dejar `characters/` vacío; el cargador lo acepta.
  - Tras añadir personajes, repetir `instance init` sobre la misma carpeta da `CONFLICT`
    (el árbol ya no es el generado), en vez de éxito idempotente.
  - Los IDs de personaje son solo minúsculas, así que no colisionan en un sistema de archivos
    que no distingue mayúsculas.
  - Auxiliares públicos añadidos: `check_character_id`, `check_concept_text`,
    `concept_summary`, `concept_record` (modelos) y `find_character` (runtime).
- Revisión archivada en `docs/analisis/incremento-4d1-revision.md` (veredicto final: aprobado
  tras dos verificaciones; la primera dejó pendiente el caso de excepciones sin código).
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions`:
    - Análisis `01a12fb4-…` (1 encargo: detalle de 4d1/4d2); incremento respecto a la medición
      de 4c2: entrada 3.704.651 (caché leída 3.526.528), salida 29.543 (razonamiento 18.161).
      El hilo acumula 12,5 M de entrada: el análisis de 4d2 debe abrir uno nuevo con resumen.
    - Revisión `01a1318b-af96-7330-a42a-3a3927110df1` (3 encargos: revisión + 2
      verificaciones): entrada 2.860.219 (caché leída 2.749.568), salida 23.908 (razonamiento
      11.965).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Sigue con el 4D»; 35 respuestas de
    API): entrada 70, salida 64.188, caché leída 29.974.149, caché escrita 893.410. Coste NO
    DISPONIBLE.
  - Retrabajo: dos rondas de corrección (2 hallazgos, uno en dos pasos); dos tests con
    particularidades de Windows (mayúsculas en nombres, saltos de `write_text`) corregidos
    antes de la revisión; reemplazos por línea de comandos fallidos sin efectos.

### Incremento 4d2 — propuestas citadas y composición efectiva
- Rama: `feature/incremento-4-rebanada-vertical` (base `67a7284`; estado de trabajo sin commit).
- Cambios hechos: `core/character/models.py` (modelos de propuesta, decisión, vista, paso
  aplicado y composición efectiva; reproducción de la cadena de eventos en
  `CharacterState`; codec con `candidate_resolver`), `core/character/__init__.py`;
  `core/runtime/character.py` (`add_proposal`, `list_proposals`, `get_proposal`,
  `get_effective_composition`, `record_proposal_decision`, más `citation_lines` y
  `proposal_blocks` para prompt y CLI), `core/runtime/instance.py` (instancia provisional y
  resolvedor vía `get_approved_candidate`), `core/runtime/cli.py` (`character effective show`,
  `character proposal add|list|show|approve|reject`) y `core/runtime/__init__.py`. Tests nuevos
  `tests/test_character_{proposals,proposal_cli}.py`; ajustes de compatibilidad en
  `tests/test_character_{models,state}.py`.
- Resultado de los tests: suites de 4d2 → 45 OK; suite completa → 436 OK en `py -3.11` y
  `py -3.14`, sin omitidos (tras la corrección de REV4D2-01: 46 y 437). Prueba por subprocess sobre una instancia temporal (ya borrada):
  `effective show --json`, `proposal add --json` (`created=true`, `PENDING`), `approve` sin TTY
  rechazado con código 3 sin escribir y `show --json` (`PENDING`, revisión 2). `rg` y el diff de
  rutas congeladas desde `67a7284` sin salida; `git diff --check` limpio.
- Validación funcional: el 12-10-2026 el usuario aprobó `ajuste-respeto v1` e importó el
  concepto v2 en la terminal integrada de VS Code sobre `%TEMP%\roleplay-prueba-4d2`
  (preparada por Claude con v1 importada por terminal simulada y dos propuestas). Claude lo
  verificó: decisión APPROVED en la revisión 4 y concepto v2 con recibo `TTY_NONCE_V1`,
  revisión 5, v2 idéntico al archivo, `ajuste-mundo` OBSOLETE, la aprobada con
  `aplicada=NO` y composición efectiva en la raíz de v2 (0 pasos).
- Desviaciones y decisiones de detalle:
  - `CharacterProposal` lleva `character_id` como primer campo (no se persiste; lo inyecta el
    decodificador), porque `result_composition_sha256` lo incluye y es `init=False`.
  - `ProposalView` añade `base`: la composición efectiva en el instante del alta, que el prompt
    y `proposal show` muestran completa y que el JSON de `show` exige.
  - `CharacterState` añade `replay` (`CharacterReplay(effective, views)`, `init=False`,
    excluido de la igualdad), `revision` (longitud del registro de eventos) y `view(id, n)`;
    la reproducción se ejecuta al construir el estado, así que un registro inválido no puede
    existir en memoria. `concept_root`, `make_proposal_decision`, `proposal_record`,
    `decision_record` y `composition_record` son auxiliares públicos.
  - `ReviewStatus` se importa arriba en `models.py`: `core.review.models` no importa
    `core.runtime`, así que no hay ciclo.
  - `_append_concept` usa ahora el mismo escritor de eventos que propuestas y decisiones
    (`_write_event`: cerrojo + `guard` antes, al tomar y antes de escribir; recarga la instancia
    completa bajo el cerrojo, con el resolvedor de citas). Sin ello, importar un concepto con
    propuestas citadas fallaba. El test 4d1 del cambio de junction antes de escribir intercepta
    ahora `encode_state` en lugar de `load_state` (mismo instante: tras la relectura y antes del
    último `guard`). El mensaje de conflicto 4d1 no cambia.
  - `proposal show` incluye la cabecera `Citas aprobadas (K):` antes de las líneas de cita, igual
    que el prompt. El JSON de `proposal add` informa `instance` como la raíz lógica de la
    instancia.
  - En `add`, las validaciones de entrada (ID, versión, hash con formato, textos) dan
    `INVALID_STATE` antes de comprobar identidad, versión y base (`CONFLICT`). Repetir la clave
    con la misma entrada compara base, texto, motivo y citas resueltas.
  - En `approve`/`reject`, una propuesta o versión inexistente se rechaza antes del prompt
    (`INVALID_STATE`); una decisión opuesta, aprobar algo no `PENDING` o cualquier cambio bajo el
    cerrojo es `CONFLICT`.
- Revisión de Codex: un hallazgo, REV4D2-01 (Baja): `ProposalView` aceptaba una decisión o una
  base ajenas a su propuesta. Corregido con validación de tipo, `decision.matches(proposal)` y
  base del mismo personaje, concepto y hash, más la regresión
  `test_views_reject_a_foreign_decision_or_base`. Verificación en el mismo hilo: resuelto y 4d2
  aprobado. Archivada en `docs/analisis/incremento-4d2-revision.md`.
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions` (hilos exclusivos de 4d2,
    totales = incremento de la tarea):
    - Análisis `01a1319f-76c3-7312-886a-45d699c33428` (1 encargo: detalle de 4d2): entrada
      3.281.871 (caché leída 3.140.608), salida 26.116 (razonamiento 13.733).
    - Revisión `01a131b7-fc84-7902-883d-caf9b8f63da3` (2 encargos: revisión + 1 verificación):
      entrada 4.762.289 (caché leída 4.616.448), salida 17.671 (razonamiento 9.609).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Vale, confirmo, puedes proseguir»
    hasta antes del commit; 71 respuestas de API deduplicadas por id): entrada 142, salida
    106.966, caché leída 14.923.883, caché escrita 203.846. Coste NO DISPONIBLE.
  - Retrabajo: una ronda de corrección (1 hallazgo). Antes de la revisión: un bug propio
    (importar un concepto con propuestas citadas no pasaba el resolvedor) detectado por los
    tests nuevos, un test 4d1 que fijaba una revisión arbitraria, un test propio con una
    aserción por subcadena, y un heredoc fallido sin efectos.

### Incremento 4e — ficha mínima y respuesta del staff
- Rama: `feature/incremento-4-rebanada-vertical` (base `130d0bf`; estado de trabajo sin commit).
  Plan detallado por Codex (hilo `01a131c8-38ca-74b3-8c0c-8d4df35e910c`).
- Decisión del usuario (12-10-2026): «cambios solicitados» se registra como `REJECTED` con el
  texto literal de la respuesta; no se añade `CHANGES_REQUESTED`.
- Cambios hechos: `core/character/models.py` (`CharacterDraftRecord`, `StaffResponse`,
  `CharacterDraftView`, resultados, reproducción de fichas y respuestas, codec de cuatro o seis
  claves, serializadores), `core/character/__init__.py`; `core/runtime/character.py`
  (`create_draft`, `list_drafts`, `get_draft`, `record_staff_response`, más
  `draft_reference_lines`, `sheet_block` y `response_block` para prompt y CLI; `_read_input`
  generalizado con `_read_external`), `core/runtime/cli.py` (`character draft create|list|show`,
  `character staff record`) y `core/runtime/__init__.py`. Tests nuevos
  `tests/test_{character_draft,staff_review_cli}.py`. `instance.py` y las suites 4d no
  necesitaron cambios.
- Resultado de los tests: suites 4e → 31 OK; suite completa → 468 OK en `py -3.11` y `py -3.14`,
  sin omitidos (tras la corrección de REV4E-01: 32 y 469). Prueba por subprocess sobre una instancia temporal (ya borrada):
  `effective show --json`, `draft create` (`ACTIVE | CURRENT | PENDING_HUMAN_REVIEW |
  NOT_CONFIRMED`), `draft show --json` y `staff record` sin TTY rechazado con código 3 sin
  escribir. `rg` de nombres del legado vacío; diff de rutas congeladas y de `core/review` desde
  `130d0bf` vacío; `git diff --check` limpio.
- Validación funcional: el 12-10-2026 el usuario registró en la terminal integrada de VS Code
  una respuesta `REJECTED` («cambios solicitados») sobre `character-sheet v1` e importó el
  concepto v2, en `%TEMP%\roleplay-prueba-4e` (preparada por Claude con terminal simulada:
  concepto v1, una propuesta aprobada y la ficha v1). Claude lo verificó: respuesta en la
  revisión 5 y concepto v2 en la 6, ambos con recibo `TTY_NONCE_V1`; texto, locator y fecha
  idénticos al JSON; v2 idéntico al archivo; la ficha v1 `STALE | CURRENT | REJECTED |
  NOT_CONFIRMED` con razón `EFFECTIVE_COMPOSITION_CHANGED`, persistida aún como `ACTIVE`.
- Desviaciones y decisiones de detalle:
  - `CharacterDraftRecord` lleva `character_id` y `forum_id`, y `StaffResponse` lleva
    `character_id`, como primeros campos no persistidos (los inyecta el decodificador), igual
    que `CharacterProposal` en 4d2: hacen falta para validar contexto, locators y evidencia en el
    propio modelo. `response_sha256` es derivado (`init=False`), no un argumento.
  - Auxiliares públicos añadidos: `DRAFT_ID`, `applied_corpus_refs`, `draft_context_refs`,
    `corpus_source_ref`, `make_draft_record`, `make_staff_response`, `check_locator`,
    `check_observed_at`, `parse_observed_at`, `draft_record`, `staff_response_record`,
    `draft_summary`, `draft_view_record`, `source_record`; `CharacterState.draft_view(n)`.
  - El decodificador rechaza la forma de seis claves con `drafts` y `staff_responses` ambos
    vacíos (el encoder nunca la produce), para que cada estado tenga una sola forma canónica.
  - Un archivo de entrada inexistente (ficha o respuesta) da `INVALID_STATE`/3, como
    `concept import` en 4d1 (el plan listaba E/S → 5 en general). `--composition-sha256` se
    valida en el core (3), no en el parser.
  - `create_draft` considera reintento idéntico la misma versión con el mismo hash de
    composición y el mismo contenido, aunque la composición vigente haya cambiado después.
  - Orden de `record_staff_response`: TTY → estado → IDs → instancia → lectura y validación del
    JSON externo → ficha y `draft_sha256` (`CONFLICT` si no coincide) → idempotencia/conflicto →
    cerrojo libre → frase → relectura de bytes del JSON → `_write_event`.
  - El `rg` de publicación del plan no queda vacío: coinciden el auxiliar de 4d1 `_publish`
    (publicación atómica de la carpeta del personaje en disco, de `workspace.py`) y docstrings
    que dicen que nada publica. No hay comando, función ni estado alcanzable de publicación.
- Revisión de Codex: un hallazgo, REV4E-01 (Baja): `CharacterDraftView` aceptaba combinaciones
  imposibles de vigencia y razón de obsolescencia. Corregido con `_check_stale_reason`
  (sustituida → `SUPERSEDED_BY:character-sheet:v<N>` con N mayor; vigente → sin razón o cambio
  exacto de su composición) y la regresión `test_views_reject_impossible_stale_reasons`.
  Verificación en el mismo hilo: resuelto y 4e aprobado. Archivada en
  `docs/analisis/incremento-4e-revision.md`.
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), contadores de `~/.codex/sessions` (hilos exclusivos de 4e,
    totales = incremento de la tarea):
    - Análisis `01a131c8-38ca-74b3-8c0c-8d4df35e910c` (1 encargo: detalle de 4e): entrada
      2.009.757 (caché leída 1.890.944), salida 28.479 (razonamiento 15.476).
    - Revisión `01a131f0-0339-7b81-ba6e-a3f0aff99ef0` (2 encargos: revisión + 1 verificación):
      entrada 4.241.252 (caché leída 3.954.432), salida 19.935 (razonamiento 10.652).
    - Escritura de caché 0; errores/cancelaciones 0; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Listo, vamos con la 4e» hasta antes
    del commit; incluye la verificación de la prueba manual de 4d2; 30 respuestas de API
    deduplicadas por id): entrada 60, salida 82.081, caché leída 8.179.838, caché escrita
    113.823. Coste NO DISPONIBLE.
  - Retrabajo: una ronda de corrección (1 hallazgo). Antes de la revisión: tres expectativas de
    test propias (archivo intruso que invalida la instancia, versión no pasada al JSON de
    respuesta, código 3 frente a 5); una rama creada por error y borrada sin commits; un
    heredoc fallido sin efectos.

### Incremento 4f — recorrido vertical y contrato integrado
- Rama: `feature/incremento-4-rebanada-vertical` (base `24874f3`; estado de trabajo sin commit).
  Sin análisis nuevo de Codex: la entrada 4f del plan (ajustada por Codex en 4e) basta para un
  subincremento solo de pruebas.
- Cambios hechos: `tests/fixtures/vertical-neutral/` (ocho candidatos de las cuatro clases,
  conceptos v1/v2, dos propuestas, fichas v1/v2, respuesta del staff y `LEEME.md`) y
  `tests/test_vertical_slice.py`. No hizo falta corregir ningún archivo de 4a–4e.
- Diseño del recorrido: el expediente es `tests/fixtures/dossiers/minimal-neutral`; expediente y
  entradas se copian a una carpeta temporal externa, y los marcadores
  `__BASE_COMPOSITION_SHA256__`/`__DRAFT_SHA256__` se sustituyen en copias con los hashes que
  devuelve la CLI. Cada paso del agente es un proceso nuevo de `core.runtime.cli --json`
  (reinicio entre fases); los pasos humanos (decisiones, cierre, conceptos, decisiones de
  propuestas y respuesta del staff) van por la API con terminal simulada, porque una TTY real no
  se puede automatizar, y recargan el estado del disco. «Sin red, modelo ni base de datos» se
  vigila sobre la ejecución con audit hooks de Python (eventos de red, procesos, SQLite, HTTP y
  navegador): en cada hijo, un intento deja un marcador y termina con `os._exit(97)`, que ningún
  `except` oculta; en los pasos humanos, un hook del padre (inerte fuera de `watched()`) lo
  registra y se comprueba después. Cada
  repetición (init, candidato, decisión, cierre, instancia, concepto, propuesta, rechazo, ficha y
  respuesta) se comprueba byte a byte sobre todo el workspace y la instancia.
- Contratos comprobados: corpus sin el candidato rechazado; ficha v1 citando solo el corpus de
  la propuesta aplicada; v1 `STALE` por composición sin nueva revisión y después por
  sustitución; propuestas `APPROVED` (no aplicada tras el concepto v2) y `REJECTED`; respuesta
  del staff que no cambia la composición ni la publicación (`NOT_CONFIRMED`); archivos estáticos
  de la instancia intactos y `characters/ejemplo/state.json` como único archivo nuevo;
  `AGENTS.md`/`CLAUDE.md` iguales a las plantillas v1 congeladas; ningún texto del legado.
  `GuardTest` demuestra que los vigilantes detectan un intento capturado por el propio código.
- Resultado de los tests: 5 tests nuevos; suite completa → 474 OK en `py -3.11` y `py -3.14`,
  sin omitidos. Sin cambios en `core/`, `reference/` ni `tests/expected_instance_templates.py`
  desde `24874f3`; `git diff --check` limpio; fixtures con LF.
- Revisión de Codex (hilo `01a13200-00e0-7b03-8679-c6f17f9292d4`): un hallazgo, REV4F-01 (Media):
  la lista negra global de imports de `core/` no equivalía al contrato (prohibía dependencias
  opcionales futuras no recorridas y no veía invocaciones dinámicas ni excepciones capturadas).
  Sustituida por la vigilancia con audit hooks descrita arriba y por `GuardTest`. Verificación en
  el mismo hilo: resuelto y 4f aprobado. Archivada en `docs/analisis/incremento-4f-revision.md`.
- Métricas por agente (solo telemetría verificable; ausente = NO DISPONIBLE):
  - Codex (`gpt-5.6-sol`, high), revisión `01a13200-…` (2 encargos: revisión + 1 verificación):
    entrada 2.149.852 (caché leída 2.055.424), salida 20.372 (razonamiento 13.925); escritura de
    caché 0; errores/cancelaciones 0; sin hilo de análisis; coste o cuota NO DISPONIBLE.
  - Claude (`claude-opus-5-5`, sesión `076da56b-…`, desde «Listo, prosigue con 4F» hasta antes
    del commit; incluye la verificación de la prueba manual de 4e; 17 respuestas de API
    deduplicadas por id): entrada 34, salida 28.511, caché leída 6.025.128, caché escrita
    38.064. Coste NO DISPONIBLE.
  - Retrabajo: una ronda de corrección (1 hallazgo); antes de la revisión, una clave JSON mal
    supuesta en el test (`entries` en lugar de `candidates`).
- Incremento 4 completo (4a–4f). Validación funcional de 4f: no aplica más allá de las de 4c1,
  4d1, 4d2 y 4e, ya hechas en TTY real; el recorrido completo en un foro real queda para cuando
  el usuario aporte su expediente.
