## Invariantes obligatorias

- No ejecutes nunca comandos de decisión humana, incluidos `assimilation candidate approve`, `assimilation candidate reject`, `assimilation close` y sus equivalentes futuros. Muestra al usuario el comando exacto y pídele que lo ejecute personalmente en una terminal interactiva.
- Usa únicamente versiones vigentes del corpus con decisión APPROVED y pertenecientes al snapshot cerrado válido. PENDING_HUMAN_REVIEW, REJECTED, versiones sustituidas y material no clasificado no son utilizables.
- BORRADOR, APROBADO, PUBLICADO y CANON son estados distintos. Ninguno implica automáticamente otro; una aprobación tampoco implica aprendizaje ni utilizabilidad.
- No publiques, envíes ni conviertas propuestas, incertidumbres, borradores o resultados pendientes en hechos. No existe comando de publicación en este alcance.
- No edites directamente estados JSON gestionados ni recalcules sus hashes. Usa los comandos del core y conserva procedencia, citas y versiones exactas.
