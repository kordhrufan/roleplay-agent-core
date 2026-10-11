# Cómo rellenar el expediente del foro

El expediente es una carpeta con un archivo `expediente.md` (copia
`expediente.template.md`) y, si quieres, otros archivos de texto con el material del foro.
El agente no interpreta nada que no esté aquí y nada se usa hasta que tú lo apruebes.

## Estructura

1. **Cabecera** (cuatro primeras líneas, sin líneas en blanco entre ellas): título fijo,
   `forum_id` (minúsculas, dígitos y guiones), `nombre` y `versión_expediente`.
2. **Secciones**, una vez cada una y en este orden: Normas generales, Ambientación, Creación de
   fichas, Revisión del staff, Plataforma y formato, Sistema de combate, Creación de técnicas o
   habilidades y Material suelto.
3. En cada sección (salvo Material suelto):
   - `Estado: FALTA` si aún no tienes el material, o `Estado: NO APLICA` (solo en Sistema de
     combate y Creación de técnicas o habilidades) si el foro no lo tiene.
   - Si aportas material, **borra la línea `Estado:`** y añade una o más fuentes.
   - Una línea `Nota: ...` opcional, antes de las fuentes.
4. **Material suelto**: textos que aún no sabes dónde encajan. Puedes sugerir secciones con
   `sugerencias`; no se clasifican ni se usan hasta que se revisen.

Fuera de los bloques de texto solo se admiten esas líneas y líneas en blanco: sin sangrías,
espacios al final ni comentarios. Si algo está mal, el error indica la línea y la causa.

## Fuentes

Cada fuente empieza con `### Fuente` y una línea `Metadatos:` con campos `clave=valor`
separados por ` | ` (espacio, barra, espacio), en cualquier orden. Los textos van entre comillas
dobles.

| Clave | Obligatoria | Valor |
| --- | --- | --- |
| `id` | Sí | Identificador de la fuente, p. ej. `"reglamento"`. |
| `versión` | Sí | Versión de esa fuente, p. ej. `"3"` o `"2026-10-11"`. |
| `autoridad` | Sí | Quién la emite, p. ej. `"Staff"`. |
| `alcance` | Sí | A qué se aplica, p. ej. `"foro"` o `"combate"`. |
| `desde`, `hasta` | No | Vigencia `"AAAA-MM-DD"`; sin fecha, omítela o escribe `null`. |
| `pasaje` | No | Parte concreta citada, p. ej. `"Capítulo 2"`. |
| `archivo` | No | Ruta relativa a la carpeta del expediente, con `/`. |
| `sugerencias` | No | Solo en Material suelto: lista de secciones, p. ej. `["Ambientación"]`. |

- **Con `archivo`**: el texto se lee de ese archivo tal cual. No lleva bloque de texto.
- **Sin `archivo`**: la línea siguiente abre un bloque con cuatro o más virgulillas y la
  palabra `texto`, y otra línea con las mismas virgulillas lo cierra. Lo de dentro se guarda
  exactamente como lo pegues, aunque tenga `#`, listas o tablas.
- Si el texto pegado contiene virgulillas seguidas (`~~~~`), usa una valla más larga que la
  racha más larga del texto (p. ej. `~~~~~~`).
- Puedes citar la misma fuente en varias secciones repitiendo `id` y `versión` con otro
  `pasaje`; el resto de campos y el contenido deben coincidir. Si el texto cambió, usa otra
  `versión`.

## Ejemplo completo

````markdown
# Expediente del foro
forum_id: foro-de-ejemplo
nombre: Foro de ejemplo
versión_expediente: 2026-10-11

## Normas generales
### Fuente
Metadatos: id="reglamento" | versión="3" | autoridad="Staff" | alcance="foro" | archivo="materiales/reglamento.md" | pasaje="Normas"

## Ambientación
Nota: Resumen del mundo publicado por el staff.
### Fuente
Metadatos: autoridad="Staff" | id="mundo" | alcance="foro" | versión="1" | desde="2026-01-01"
~~~~ texto
# El mundo
Texto pegado tal cual, con **formato** y listas:
- Primera región
- Segunda región
~~~~

## Creación de fichas
### Fuente
Metadatos: id="reglamento" | versión="3" | autoridad="Staff" | alcance="foro" | archivo="materiales/reglamento.md" | pasaje="Fichas"

## Revisión del staff
Estado: FALTA

## Plataforma y formato
### Fuente
Metadatos: id="formato" | versión="1" | autoridad="Staff" | alcance="posts"
~~~~ texto
Los diálogos van en negrita.
~~~~

## Sistema de combate
Estado: NO APLICA
Nota: El foro no tiene combate mecánico.

## Creación de técnicas o habilidades
Estado: NO APLICA

## Material suelto
### Fuente
Metadatos: id="dudas-resueltas" | versión="1" | autoridad="Staff" | alcance="foro" | sugerencias=["Creación de fichas"]
~~~~~~ texto
Respuesta del staff que incluye una valla corta:
~~~~
y por eso este bloque usa seis virgulillas.
~~~~~~
````
