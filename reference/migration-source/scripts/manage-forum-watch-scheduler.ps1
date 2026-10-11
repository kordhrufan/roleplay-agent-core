# No webhook, passwords, browser data, dynamic commands or forum input accepted.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Status','Install','Disable','Enable','Remove','Run')]
    [string]$Action,
    [string]$PlanPath,
    [string]$ApprovedPlanSha256
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$taskName = 'NozomuForumWatch'
$marker = 'NozomuForumWatch Hito5 managed'
function Get-WatchTask {
    $all = @(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop)
    return $all | Where-Object { $_.TaskName -eq $taskName }
}
function Get-SafeStatus {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $task = Get-WatchTask
    $result = [ordered]@{
        task_name = $taskName
        task_exists = ($null -ne $task)
        current_user_sid = $identity.User.Value
        current_user_name = $identity.Name
    }
    if ($null -ne $task) {
        $owned = $task.Description.StartsWith($marker + ';')
        $result.owned = $owned
        $result.state = [string]$task.State
        $result.enabled = [bool]$task.Settings.Enabled
        if ($owned) {
            $info = Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
            $result.last_run_time = $info.LastRunTime.ToString('o')
            $result.next_run_time = $info.NextRunTime.ToString('o')
            $result.last_task_result = [long]$info.LastTaskResult
            $result.multiple_instances = [string]$task.Settings.MultipleInstances
            $result.start_when_available = [bool]$task.Settings.StartWhenAvailable
            $result.wake_to_run = [bool]$task.Settings.WakeToRun
            $result.interval = [string]$task.Triggers[0].Repetition.Interval
            $result.logon_type = [string]$task.Principal.LogonType
            $result.run_level = [string]$task.Principal.RunLevel
            $result.execute = [string]$task.Actions[0].Execute
            $result.working_directory = [string]$task.Actions[0].WorkingDirectory
        }
    }
    return $result
}
try {
    if ($Action -eq 'Install') {
        if ([string]::IsNullOrWhiteSpace($PlanPath) -or [string]::IsNullOrWhiteSpace($ApprovedPlanSha256)) {
            throw 'SCHEDULER_APPROVAL_REQUIRED'
        }
        $planFile = (Resolve-Path -LiteralPath $PlanPath).Path
        if ((Get-FileHash -LiteralPath $planFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ApprovedPlanSha256.ToLowerInvariant()) {
            throw 'SCHEDULER_PLAN_CHANGED'
        }
        $plan = Get-Content -LiteralPath $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($plan.task_name -ne $taskName -or $plan.description_marker -ne $marker -or $plan.schema_version -ne 1) {
            throw 'INVALID_SCHEDULER_PLAN'
        }
        if ($plan.current_user_sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) {
            throw 'WRONG_SCHEDULER_USER'
        }
        if ($null -ne (Get-WatchTask)) {
            # Even our own task is never overwritten by install.
            throw 'SCHEDULER_ALREADY_EXISTS'
        }
        if (-not [IO.Path]::IsPathRooted($plan.execute) -or -not (Test-Path -LiteralPath $plan.execute -PathType Leaf) -or
            -not (Test-Path -LiteralPath $plan.working_directory -PathType Container)) {
            throw 'INVALID_SCHEDULER_PATH'
        }
        if ((Get-FileHash -LiteralPath $plan.config_path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.config_file_sha256) {
            throw 'SCHEDULER_PLAN_CHANGED'
        }
        Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Xml $plan.xml | Out-Null
    } elseif ($Action -ne 'Status') {
        $task = Get-WatchTask
        if ($null -eq $task -or -not $task.Description.StartsWith($marker + ';')) {
            throw 'SCHEDULER_NOT_OWNED'
        }
        if ($Action -eq 'Disable') { Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null }
        if ($Action -eq 'Enable') { Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null }
        if ($Action -eq 'Remove') {
            if ([string]$task.State -eq 'Running') { throw 'SCHEDULER_RUNNING' }
            Unregister-ScheduledTask -TaskName $taskName -TaskPath '\' -Confirm:$false
        }
        if ($Action -eq 'Run') { Start-ScheduledTask -TaskName $taskName -TaskPath '\' }
    }
    Get-SafeStatus | ConvertTo-Json -Depth 5 -Compress
} catch {
    $safeCodes = @('SCHEDULER_APPROVAL_REQUIRED','SCHEDULER_PLAN_CHANGED','INVALID_SCHEDULER_PLAN',
                   'WRONG_SCHEDULER_USER','SCHEDULER_ALREADY_EXISTS','INVALID_SCHEDULER_PATH',
                   'SCHEDULER_NOT_OWNED','SCHEDULER_RUNNING')
    $code = 'SCHEDULER_OPERATION_FAILED'
    if ($safeCodes -contains $_.Exception.Message) { $code = $_.Exception.Message }
    @{ error = $code; hresult = $_.Exception.HResult } | ConvertTo-Json -Compress
    exit 2
}

