param(
    [switch]$NoAbrirNavegador
)

$runLocal = Join-Path $PSScriptRoot "run_local.ps1"

if ($NoAbrirNavegador) {
    & $runLocal -NoAbrirNavegador
}
else {
    & $runLocal
}
