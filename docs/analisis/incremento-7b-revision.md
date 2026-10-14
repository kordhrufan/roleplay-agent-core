# Revisión 7b — instrucciones de instancia v2 y migración

Versión verificada: estado de trabajo sin commit de
`feature/incremento-7-memoria-narrativa` sobre `31c6af9`, a 2026-10-14, con las correcciones de
REV7B-01..03 y los casos de prueba adicionales descritos en el encargo. Se mantuvieron fuera de
alcance los cambios ajenos ya indicados por el usuario.

## Veredicto

**APROBADO — 7b COMPLETO.** REV7B-01..03 están resueltos. Las correcciones restauran la
independencia operativa entre corpus e instrucciones, clasifican correctamente las alteraciones
concurrentes y cierran el modelo público sin introducir regresiones relacionadas. Los huecos de
prueba registrados en la revisión anterior están cubiertos. No quedan hallazgos abiertos dentro
del alcance de esta verificación.

## Hallazgos verificados

### REV7B-01 — Media — RESUELTO — `core/runtime/instance.py:752-793`; `tests/test_instance_update.py:820-857`

**Problema original.** Una ampliación preparada sobre instrucciones v1 quedaba inutilizable tras
migrar la misma instancia a instrucciones v2 porque 5a ligaba el hash del manifiesto completo.

**Verificación.** `_legacy_manifest_sha256` solo se habilita para instrucciones v2 y reconstruye el
único manifiesto v1 equivalente: parte de los estáticos actuales, elimina descriptor e integridad,
renderiza AGENTS/CLAUDE con la terna v1 y conserva el `schema_version`. `_plan_update` sigue
exigiendo igualdad de revisión, corpus, `instance.json` y snapshot, y acepta únicamente el hash del
manifiesto actual o el de esa reconstrucción determinista. No se ha retirado ninguna huella de los
demás estáticos.

La regresión demuestra que el intento cuya confirmación coincide con la migración termina en
`CONFLICT`, mientras un retry con confirmación nueva aplica la ronda ya cerrada y conserva byte a
byte las instrucciones v2. Una segunda prueba comprueba que, sin la equivalencia explícita, la
ronda se rechaza y que el manifiesto reconstruido coincide exactamente con el ligado por el
workspace. Cumple el criterio de resolución.

### REV7B-02 — Media — RESUELTO — `core/runtime/instance.py:1019-1028`; `tests/test_instance_instruction_update.py:160-210`

**Problema original.** Una alteración durante el prompt que rompiera la carga podía propagarse
como `INVALID_STATE` antes de comparar la huella, en vez de producir `CONFLICT`.

**Verificación.** Ya bajo el cerrojo común, la operación compara `_tree_bytes(root)` con el árbol
confirmado antes de volver a cargarlo. Si difiere, aborta con `CONFLICT`; después conserva la carga
estable y la segunda comparación para detectar cambios durante la relectura. Las regresiones
corrompen por separado `AGENTS.md` y el `state.json` de un tema durante el prompt: ambos casos dan
`CONFLICT`, no crean el descriptor y dejan como única diferencia la corrupción introducida por la
propia prueba. Cumple el criterio de resolución.

### REV7B-03 — Baja — RESUELTO — `core/runtime/instance.py:272-290`; `tests/test_instance_instruction_update.py:375-385`

**Problema original.** `LoadedInstance.instructions` era opcional y tenía `None` por defecto pese a
ser un componente obligatorio de toda instancia cargada.

**Verificación.** El campo es ahora `InstanceInstructions` obligatorio, está situado antes de los
campos con default y `LoadedInstance.__post_init__` rechaza cualquier otro valor. La única
construcción de producción continúa usando argumentos por nombre. La prueba fija la ausencia de
default, rechaza `replace(..., instructions=None)` y confirma la carga concreta antes y después de
migrar. Cumple el criterio de resolución.

## Huecos de prueba verificados

- La migración inyecta fallos de `fsync`, carga del staging y limpieza del staging. Conserva v1
  intacta; si la limpieza falla, informa de la ruta recuperable y el resto bloquea el siguiente
  intento hasta retirarlo.
- Se añadieron casos para `work/` como junction y `work/instructions.json` como symlink. La carga
  los rechaza mediante la inspección común de componentes. El junction se ejecutó en esta
  verificación; la creación local del symlink no está permitida por este proceso de Windows y ese
  subcaso quedó omitido aquí. El encargo aporta su ejecución sin omisiones en las suites completas.
- `TemplateV2JsonShapesTest` extrae las cinco formas JSON mostradas y contrasta sus claves con los
  parsers reales de propuesta, post, semilla, borrador y publicación; comprueba además respuesta de
  staff y la forma de las citas. La paridad ya fijada entre AGENTS/CLAUDE extiende la comprobación a
  ambas plantillas.

## Regresiones relacionadas

- 5a sigue rechazando bases realmente distintas y conserva instrucciones v1 o v2 durante una o
  varias rondas; la excepción añadida solo representa la migración v1→v2 determinista del mismo
  estado estático.
- La migración mantiene el mismo lock, la huella completa, las autorizaciones separadas, el no-op
  v2 y las garantías de staging/backup. No se observó una ruta que reutilice una confirmación sobre
  un plan cambiado.
- La obligatoriedad de `instructions` no rompe cargas v1/v2 ni los dos schemas de instancia; todas
  las construcciones internas son nominales.

## Verificación ejecutada

- `py -3.14 -B -m unittest tests.test_instance_update.InstructionsAxisTest
  tests.test_instance_instruction_update.ConcurrencyTest
  tests.test_instance_instruction_update.FailureTest
  tests.test_instance_instruction_update.ModelTest
  tests.test_instance_templates.TemplateV2JsonShapesTest -v`: 18 OK, 1 omitido por falta de
  permiso local para crear el symlink; el caso de junction sí se recorrió.
- Las suites completas aportadas para esta versión dan 626 OK tanto en Python 3.11 como en 3.14,
  incluidos ambos enlaces sin omisiones. Python 3.11 no está instalado en este entorno y no se
  repitió aquí.
- `git diff --check`: limpio; solo aparecen los avisos de conversión de fin de línea ya declarados
  para archivos ajenos.
- No se modificó código de producción ni pruebas durante esta verificación.

## Pendiente no bloqueante

Sigue pendiente la validación funcional manual con TTY real y sobre una copia de la instancia real,
ya declarada desde la revisión inicial. No hay un hallazgo abierto asociado.
