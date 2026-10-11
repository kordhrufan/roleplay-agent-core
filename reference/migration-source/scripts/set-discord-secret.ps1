# Optional wrapper. No secret parameters, echo, file export or policy changes.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    python -B -m forum_watch configure-discord
    $configureExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $configureExit
