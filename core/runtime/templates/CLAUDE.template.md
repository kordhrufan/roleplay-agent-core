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
