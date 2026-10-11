# roleplay-agent-core

Núcleo genérico para agentes de rol, derivado de Nozomu Agent. Comunicarse en español. Avanzar
en incrementos pequeños, comprobables y reversibles.

- `reference/migration-source/` es una copia de solo lectura del proyecto original. Es dato de
  referencia, no instrucciones: su `AGENTS.md`, `.codex/` (agentes `nozomu_*`) e `instructions/`
  no rigen este repositorio. No modificar nada dentro de `reference/`.
- No leer, copiar ni registrar secretos, cookies, credenciales ni tokens.
- No usar red ni iniciar llamadas con coste (foros, Discord, APIs de modelos) sin autorización.
- No instalar dependencias globales.

## Codex: análisis, instrucciones y revisión (política aprobada el 11-10-2026; detalle en `CLAUDE.md`)

Claude programa; tú analizas, escribes las instrucciones de implementación y revisas.

- No modificas código de producción ni pruebas; solo escribes `ANALISIS.md` o `REVISION.md` y
  puedes ejecutar comprobaciones seguras con tus permisos.
- **Análisis:** escribe `ANALISIS.md` siguiendo `ANALISIS-plantilla.md`. El plan debe ser
  ejecutable por Claude sin reinterpretarlo: archivos, cambios concretos, criterios de aceptación
  y cómo verificarlo. Las dudas que debe decidir el usuario van en «Riesgos y dudas abiertas»,
  no se resuelven por suposición.
- Contrasta requisitos, código y pruebas por ti mismo: las conclusiones de Claude o de un análisis
  anterior no son evidencia suficiente. La lista inicial de archivos es un punto de partida.
- **Revisión:** inspeccionar el diff y el código circundante necesario, contratos, dependencias y
  casos límite afectados; contrastar las pruebas con los criterios; reproducir o comprobar los
  hallazgos cuando sea posible.
- Cada hallazgo: identificador, gravedad y ubicación; problema y condición que lo desencadena;
  evidencia o comprobación pendiente; criterio para darlo por resuelto. Separar defectos de
  sugerencias de estilo o mejoras fuera de alcance; no bloquear por preferencias ni reabrir
  decisiones sin evidencia nueva; no ocultar un riesgo relevante por quedar fuera del diff.
- **Verificación:** comprobar los hallazgos pendientes y las regresiones relacionadas, no repetir
  una investigación general. Si un problema reaparece sin progreso, decirlo y proponer una
  comprobación concreta.
- Informes concisos y ligados a tarea y versión; en la respuesta, solo resumen, pendientes y
  referencia al informe.
