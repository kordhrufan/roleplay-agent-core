# AUDIT-GENERALIZATION

Estado: **GENERALIZATION AUDIT PARTIAL**  
Fecha: 2026-09-13  
Fuente solicitada: `reference/nozomu-legacy/`.

## 1. EXECUTIVE SUMMARY

La carpeta indicada existe, pero está vacía. La inspección local con `Get-Item` y `Get-ChildItem -Force`, incluida enumeración recursiva de archivos, devuelve **0 entradas y 0 archivos**. No hay código, índices, documentación ni configuraciones que auditar dentro del objetivo.

La raíz de trabajo contiene un proyecto de Nozomu, pero no se ha considerado una copia equivalente del legado solicitado. No puede establecerse esa equivalencia a partir de la existencia de nombres similares. Las instrucciones de inicio y los índices de la raíz se leyeron como contexto, no como evidencia del contenido de la carpeta vacía.

Este informe es la única escritura, conforme a la entrega expresamente solicitada. No se modificó el legado ni se implementaron cambios. No se copiaron archivos, instalaron dependencias, ejecutaron tests, iniciaron servicios, accedió al foro o invocó Discord. No se leyeron secretos, cookies ni credenciales. Las propuestas siguientes son criterios para reanudar la auditoría; no son conclusiones sobre una implementación inspeccionada.

## 2. LEGACY MAP

| Archivo o módulo | Clasificación | Evidencia y razón |
|---|---|---|
| `reference/nozomu-legacy/` | UNCERTAIN | Directorio existente sin entradas; no permite determinar componentes ni responsabilidades. |

No localizables dentro del objetivo: AGENTS.md, instrucciones, perfiles, memoria, especialistas, Forum Watch, parser, reader, narrative, Discord, scheduler, SQLite/storage, tests, documentación, reglas, lore, técnicas, inventario, drafts, configuraciones, scripts y dependencias. No se clasifican como LEGACY_ONLY: ausencia de material no demuestra obsolescencia.

## 3. GENERIC CORE CANDIDATES

Pendiente de evidencia. Como hipótesis para evaluar: identidad estable de fuentes, seguimiento de temas, detección de revisiones, procedencia de memoria, versionado de borradores, revisión humana y control de vigencia. Ninguno queda acreditado como extracción reutilizable del legado.

Cada candidato deberá superar la pregunta: ¿seguiría teniendo sentido sin Nozomu, Naruto Rol y Jcink? La respuesta debe fundamentarse en responsabilidades y dependencias reales, no en renombrar símbolos.

## 4. CHARACTER PACKAGE EXTRACTION

No hay perfil del legado disponible. Queda pendiente localizar identidad, historia, psicología, personalidad, gustos, disgustos, objetivos, defectos, relaciones, voz, persona narrativa, diálogo, conocimientos, estado actual, inventario, capacidades y autonomía.

Criterio propuesto, sin schema: FACT requiere fuente y alcance; INFERENCE conserva su justificación sin convertirse en hecho; UNKNOWN expresa ausencia de evidencia; RUNTIME_STATE conserva contexto de ejecución o escena. Estas dimensiones pueden coexistir: un estado de escena puede ser un hecho documentado. Separar personalidad estable, pertenencias al mundo, capacidades sujetas a reglas y recursos restantes por escena. No trasladar valores de Nozomu a defaults globales.

## 5. WORLD PACKAGE EXTRACTION

No se localizaron fuentes de ambientación, geografía, facciones, política, tecnología, economía, historia o cultura en el objetivo.

Propuesta a validar: WORLD_CANON conserva fuente, versión y alcance del mundo; CHARACTER_KNOWLEDGE acredita qué información conoce un personaje y cómo la adquirió. Que el lector o el agente disponga de lore no demuestra conocimiento IC. No se pueden señalar puntos concretos de fuga OOC/IC sin archivos.

## 6. RULES PACKAGE EXTRACTION

No se inspeccionaron reglas ni un Combat & Build Agent del legado. Están pendientes combate, atributos, recursos, daño, movimiento, distancias, inventario, técnicas, habilidades, progresión, creación, restricciones, misiones y economía mecánica.

Separación propuesta: RULE TEXT conserva texto y versión; RULE INTERPRETATION conserva interpretación y autoridad; CHARACTER STATE representa capacidades y posesiones; COMBAT STATE representa recursos, efectos y posiciones de una escena. No se proponen fórmulas universales.

Para `combat_system = NONE`, evaluar la ausencia explícita de resolución mecánica: no inventar estadísticas, costes o daño; mantener intención narrativa, control de otros personajes y revisión humana. La ausencia de sistema debe distinguirse de un sistema desconocido o no cargado.

## 7. FORUM ADAPTER EXTRACTION

No existen reader/parser inspeccionables en la ruta. Login, verificación de identidad, selectores, URLs, paginación, IDs de posts/autores, extracción BBCode, cierre de temas y supuestos de publicación quedan sin verificar.

Interfaz conceptual mínima candidata: leer un tema autorizado y devolver identidad de plataforma/tema, posts con identidad y autor, contenido con formato declarado, orden, evidencia de revisión y estado/completitud de lectura. Capacidades opcionales deben declarar qué puede verificarse, incluida identidad y cierre. No equiparar lectura incompleta a ausencia de posts.

Un ManualAdapter podría recibir texto aportado y procedencia declarada, con identificadores de importación estables. No acreditaría login, identidad de cuenta, publicación ni completitud remota. No se propone publicación automática ni implementación de adapters.

## 8. NARRATIVE ENGINE EXTRACTION

Sin motor ni prompts del legado disponibles. Candidatos conceptuales: separación IC/OOC, control limitado al personaje, interpretación de turnos, contexto, intención, acceso al conocimiento, borradores y escalado humano. Persona narrativa, voz y formato de diálogo deben evaluarse como configuración del personaje y capacidades de presentación de la plataforma.

Autonomía pendiente de auditoría: social, combate, romance, relaciones, decisiones mayores, gasto de recursos, desarrollo y publicación son posibles ámbitos independientes, sin valores por defecto propuestos. Deben distinguirse permiso para sugerir, preparar un borrador, aprobar, registrar y ejecutar una acción externa. No se han localizado decisiones manuales hardcoded.

## 9. MEMORY EXTRACTION

No se localizaron almacenes ni registros del legado. Pendientes hechos, impresiones, relaciones, intenciones, resultados sin confirmar, cronología, escenas paralelas, consolidación, deduplicación y fuentes.

Evaluar procedencia y revisiones como candidatos genéricos; separar contenido específico del personaje/mundo/reglas. Los estados DRAFT, APPROVED, PUBLISHED y CANON son requisitos a investigar, no estados cuya implementación se haya comprobado. No asumir una transición automática entre ellos. FACT, IMPRESSION, PENDING_INTENTION y UNCONFIRMED_OUTCOME también necesitan contrastarse con los registros reales. Una publicación puede documentar un intento sin confirmar su resultado.

## 10. RUNTIME / INTEGRATIONS

El flujo scheduler → reader → change detection → narrative evaluation → draft → Discord procede del encargo; no está verificado en código.

Hipótesis de separación: coordinación y detección en runtime/core; lectura de plataforma en adapter; notificación en integración; temporización concreta en operaciones; identidades y autorizaciones en configuración; cursores, intentos, locks y entregas en estado operativo. SQLite es una posible implementación de almacenamiento, no un contrato de dominio demostrado. No se ha confirmado tecnología, versión ni grafo de dependencias.

## 11. TEST CLASSIFICATION

Tests encontrados en el objetivo: **0**. Pruebas **NO EJECUTADAS**, incluidas las de paridad.

No hay archivos asignables con evidencia a GENERIC_REUSABLE, JCINK_SPECIFIC, NARUTO_RULES_SPECIFIC, NOZUMU_SPECIFIC, WINDOWS_SPECIFIC o DISCORD_SPECIFIC.

Futuros contract tests a evaluar: lectura completa/incompleta e identidad de ForumAdapter; validación de referencias y campos ausentes en CharacterPackage; sistema NONE frente a desconocido en RulesPackage; revisión/versionado/vigencia de drafts; procedencia y deduplicación de memoria; reintentos de notificación y ejecución. Esto no afirma que existan tests equivalentes actualmente.

## 12. COUPLING REPORT

**Acoplamientos confirmados: ninguno evaluable por ausencia del código.** No confundir el bloqueo de entrada con un acoplamiento arquitectónico.

| Prioridad de investigación | Acoplamiento que buscar | Qué impediría si se confirma |
|---|---|---|
| CRITICAL COUPLING | Identidad/cuenta 59 o tema 275 como invariantes de dominio | Operar con otros personajes y temas; separar autorización de lógica. |
| CRITICAL COUPLING | Borrador/aprobación convertidos implícitamente en publicación o canon | Preservar revisión humana y resultados no confirmados. |
| HIGH | Jcink HTML, URLs, paginación y selectores dentro del seguimiento | Incorporar otra plataforma sin cambiar el core. |
| HIGH | Fórmulas, atributos Aptitud/Evasión o técnicas Naruto en lógica universal | Usar otro sistema o NONE. |
| HIGH | Acceso narrativo indiscriminado a lore y memoria OOC | Garantizar límites del conocimiento IC. |
| MEDIUM | Discord como destino obligatorio o scheduler Windows embebido | Ejecutar con otras integraciones y entornos. |
| MEDIUM | Imports/rutas absolutas de Nozomu y estado local compartido | Aislar personajes, instalaciones y ejecuciones. |
| LOW | Nombre, primera persona o color de diálogo como constantes de presentación | Cambiar voz y formato; elevar prioridad si también condicionan validación o permisos. |

Estas son hipótesis priorizadas solicitadas para una futura búsqueda, no hallazgos. No hay líneas de código que citar.

## 13. PROPOSED CONTRACTS

Todos son candidatos sin interfaces ni schemas finales. Para todos, las piezas legacy que los alimentarían están **no disponibles**; la columna de alimentación identifica qué localizar cuando exista el material.

| Candidato / necesidad a evaluar | Responsabilidad; inputs → outputs | Alimentación legacy a localizar / detalles fuera del core | Dependencias y riesgos |
|---|---|---|---|
| CharacterPackage / probablemente necesario | Identidad, voz y referencias; fuentes aprobadas → perfil contextual | Perfil, maestro, instrucciones / valores Nozomu | Fuentes, mundo y reglas opcionales; mezclar ficha con estado de escena. |
| WorldPackage / opcional | Referencias del mundo; consulta contextual → lore con procedencia | Índices y lore / Naruto y geografía | Versiones y conocimiento; filtrar OOC como IC. |
| RulesPackage / opcional | Reglas versionadas; capacidades y consulta → restricciones documentadas | Reglamentos y catálogos / fórmulas Naruto | Fuentes y estado; interpretación presentada como regla. |
| ForumAdapter / si hay importación | Normalizar lecturas; tema autorizado → posts y evidencia de lectura | Reader/parser / Jcink y selectores | Identidad y transporte; lectura parcial, cambios de HTML. |
| MemoryStore / probablemente necesario | Guardar y recuperar procedencia; eventos/consulta → registros y revisiones | Memoria, entidades, índices / contenido específico | Identificadores, persistencia; duplicados y canon indebido. |
| ThreadTracker / si hay seguimiento | Comparar snapshots; lectura previa/nueva → cambios y vigencia | Detección/cursor / IDs concretos y paginación de foro | ForumAdapter, RuntimeState; ediciones omitidas. |
| NarrativeEngine / si hay generación | Proponer texto contextual; personaje, escena, conocimiento e intención → borrador y dudas | Prompts/narrative / voz Nozomu y proveedor concreto | Memoria, aprobación, reglas opcionales; metagaming. |
| CombatEngine / opcional | Evaluar acciones mecánicas; reglas y escena → opciones/resultados condicionados | Especialista de combate / fórmulas y builds concretas | RulesPackage, procedencia; resolver impactos sin evidencia. |
| DraftStore / probablemente necesario | Versionar texto y contexto; borrador/revisión → versión recuperable | Drafts y registros / rutas nominales | Fuentes y workflow; sobrescribir o aprobar versión equivocada. |
| NotificationAdapter / opcional | Entregar avisos; evento autorizado → resultado de entrega | Discord / webhook y formato de transporte | Secretos externos y reintentos; duplicar avisos o equiparar envío a aprobación. |
| SchedulerAdapter / opcional | Disparar trabajo; planificación → ejecución identificada | Scripts/tareas / Windows Task Scheduler | RuntimeState; concurrencia y relojes. |
| ApprovalWorkflow / necesario para el alcance pedido | Vincular decisión humana a versión; decisión y contexto → transición explícita | Revisión/estados / decisiones implícitas del personaje | DraftStore, vigencia; aprobar contenido obsoleto. |
| RuntimeState / si hay automatización | Aislar cursores, locks e intentos; ejecución → checkpoint | SQLite/storage/config / rutas locales y cuentas concretas | Almacenamiento y aislamiento; mezclar operaciones con historia IC. |

No se demuestra todavía que cada candidato deba ser un módulo separado; algunos podrían ser capacidades de un mismo componente mínimo.

## 14. PROPOSED TARGET STRUCTURE

No se puede derivar una estructura definitiva de un directorio vacío. Hipótesis para contrastar, no árbol a crear:

```text
core/                         # procedencia, seguimiento y revisión, si se confirman
packages/characters/nozomu/    # identidad, voz y referencias específicas
packages/worlds/naruto-rol/    # lore documentado
packages/rules/naruto-rol/     # reglas e interpretaciones diferenciadas
adapters/jcink/                # lectura específica de plataforma
adapters/manual/               # importación sin garantías remotas
integrations/discord/          # entrega de avisos
runtime/                       # composición y operaciones
tests/                         # contratos, fixtures y paridad
reference/nozomu-legacy/        # original conservado
```

El estado operativo escribible y los secretos necesitan ubicaciones separadas de paquetes de personaje y referencias. No se fija una ruta hasta inspeccionar el runtime real.

## 15. MIGRATION PLAN

1. **PHASE 0 — Completar auditoría:** disponer del legado en la ruta acordada o recibir una corrección explícita de alcance; leer índices, inventariar y aportar hallazgos por archivo/línea. Bloqueada actualmente.
2. **PHASE 1 — Contratos:** documentar entradas, salidas, capacidades opcionales, procedencia y transiciones a partir del comportamiento verificado; sin exigir todos los candidatos.
3. **PHASE 2 — Core mínimo:** extraer una ruta pequeña con fixtures locales: fuente → seguimiento → borrador → revisión. Mantener el flujo existente en paralelo.
4. **PHASE 3 — Adapters:** aislar lectura Jcink y contrastarla con las mismas fixtures; introducir importación manual para comprobar que el core no exige HTML ni login.
5. **PHASE 4 — CharacterPackage Nozomu:** separar identidad y voz conservando revisiones, referencias y restricciones existentes.
6. **PHASE 5 — Mundo y reglas:** separar lore, conocimiento IC, reglas y estado; probar conceptualmente NONE sin estadísticas artificiales.
7. **PHASE 6 — Runtime e integraciones:** conectar almacenamiento operativo, scheduler y Discord detrás de límites verificados; no habilitar acciones externas por defecto durante migración.
8. **PHASE 7 — Paridad integral:** reunir evidencias de las comprobaciones incrementales y del flujo completo antes de sustituirlo. Las comprobaciones de paridad deben acompañar cada fase, no comenzar aquí.
9. **PHASE 8 — Segundo caso:** demostrar diferencias de mundo, voz, reglas, plataforma y autonomía sin editar el core para acomodarlas.

Cada fase debe conservar una vía de retorno al comportamiento anterior. No se autoriza ni ejecuta ninguna fase de implementación mediante este informe.

## 16. PARITY CRITERIA

Criterios propuestos; baseline legacy pendiente y pruebas no ejecutadas:

| Área | Evidencia futura exigible |
|---|---|
| Seguimiento y cambios | Fixtures equivalentes producen los mismos posts nuevos/editados, orden y deduplicación; lectura parcial no elimina historia. |
| Login/identity | Identidad correcta e incorrecta y sesión expirada tienen resultados explícitos; conservar el alcance autorizado. |
| Borradores y primera persona | La configuración Nozomu conserva voz y persona aprobadas; comparar restricciones y contenido, no exigir identidad literal de salida generativa. |
| IC/OOC | Información solo OOC no aparece como conocimiento del personaje. |
| STALE | Si el contexto cambia, evaluar e invalidar la revisión correspondiente; significado exacto pendiente del legacy. |
| Discord | Misma intención de aviso y evidencia de entrega/reintento; recibir un aviso no aprueba ni publica. |
| Scheduler | Ejecuciones repetidas o concurrentes no duplican efectos; comparar horarios y recuperación documentados. |
| Memoria | Fuente, alcance, revisiones, incertidumbres y escenas paralelas se conservan. |
| Combat delegation | Consultas mecánicas llegan al componente apropiado con reglas y estado; NONE no inventa resolución mecánica. |
| Drafts/aprobación | Cada decisión identifica versión y contexto; aprobación y publicación permanecen distintas. |
| Seguridad/publicación | Secretos separados, lectura limitada al alcance autorizado y ausencia de publicación automática. |

Los escenarios de servicios externos requerirán autorización y entorno adecuados en una tarea posterior; esta auditoría no los ejecuta.

## 17. SECOND CHARACTER TEST STRATEGY

Elegir posteriormente un caso de otro mundo, con tercera persona y diálogo distinto, sin combate mecánico, importado manualmente o desde otra plataforma y con permisos de autonomía diferentes. No se diseña aquí el personaje ni se fijan esos permisos.

Validaría que identidad, voz, conocimiento y autonomía son configurables; que la ausencia de reglas está soportada; que seguimiento, fuentes, revisión y memoria no dependen de Jcink, Naruto ni de las estadísticas de Nozomu. Una validación posterior con un segundo sistema mecánico sería adicional: NONE por sí solo no demuestra extensibilidad a reglas mecánicas diferentes.

## 18. OPEN QUESTIONS

- ¿Es `reference/nozomu-legacy/` la ruta correcta, pendiente de recibir el legado, o se pretendía auditar el proyecto situado en la raíz actual?
- ¿La raíz actual es el nuevo proyecto donde debe permanecer este informe? Se utiliza como destino disponible fuera del legado, sin crear otro proyecto.
- Tras disponer de fuentes: ¿qué versión y comportamiento constituyen la baseline y qué funcionalidades están implementadas frente a solo documentadas?
- ¿Qué estados de aprobación, publicación, canon y STALE existen realmente, y qué evidencia acredita sus transiciones?

## 19. BLOCKERS

**B1 — Fuente de auditoría vacía.** `reference/nozomu-legacy/` tiene 0 entradas y 0 archivos, incluidos ocultos. Impide mapa real de módulos, trazabilidad por líneas, clasificación de tests, dependencias, acoplamientos comprobados y diseño de extracción sustentado en código.

No se han invocado especialistas: no hay material del objetivo que recuperar o evaluar mecánicamente, y no corresponde sustituirlo por continuidad de otro árbol. Tampoco se ha copiado el proyecto raíz para subsanar la ausencia, conforme a la prohibición del encargo.

## 20. RECOMMENDED NEXT STEP

Confirmar la ruta de origen o proporcionar el legado en la ubicación acordada. Después, reanudar **PHASE 0** y reemplazar las hipótesis de este informe por hallazgos sustentados, conservando la restricción de no modificar el legado.

No procede declarar GENERALIZATION AUDIT COMPLETE. Resultado actual: **GENERALIZATION AUDIT PARTIAL**.
