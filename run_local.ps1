param(
    [switch]$NoAbrirNavegador
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @("--version")
    )

    try {
        $null = & $Command @Arguments 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Get-SystemPython {
    foreach ($envName in @("PYTHON_BIN", "PYTHON")) {
        $envValue = [Environment]::GetEnvironmentVariable($envName)
        if ($envValue) {
            $envValue = $envValue.Trim().Trim('"')
            if (Test-PythonCandidate -Command $envValue) {
                return [PSCustomObject]@{ Command = $envValue; Args = @(); Source = $envName }
            }
        }
    }

    foreach ($candidate in @(
        @{ Command = "python"; Args = @(); TestArgs = @("--version") },
        @{ Command = "python3"; Args = @(); TestArgs = @("--version") },
        @{ Command = "py"; Args = @("-3.10"); TestArgs = @("-3.10", "--version") },
        @{ Command = "py"; Args = @("-3"); TestArgs = @("-3", "--version") }
    )) {
        if (Test-PythonCandidate -Command $candidate.Command -Arguments $candidate.TestArgs) {
            return [PSCustomObject]@{
                Command = $candidate.Command
                Args = @($candidate.Args)
                Source = "PATH"
            }
        }
    }

    throw "No se encontro una instalacion utilizable de Python."
}

$venvDir = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $systemPython = Get-SystemPython
    Write-Host "Creando entorno virtual con $($systemPython.Command)..." -ForegroundColor DarkCyan
    $venvArgs = @($systemPython.Args) + @("-m", "venv", $venvDir)
    & $systemPython.Command @venvArgs
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual."
    }
}

if (-not (Test-PythonCandidate -Command $venvPython)) {
    throw "El Python de .venv no se puede ejecutar. Elimina .venv y vuelve a intentarlo."
}

& $venvPython -c "import flask, playwright" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando dependencias..." -ForegroundColor DarkCyan
    & $venvPython -m pip install -r (Join-Path $projectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias."
    }
}

if (-not $env:APP_ENV) { $env:APP_ENV = "development" }
if (-not $env:HOST) { $env:HOST = "127.0.0.1" }
if (-not $env:PORT) { $env:PORT = "5000" }
if ($NoAbrirNavegador) {
    $env:OPEN_BROWSER = "0"
}
elseif (-not $env:OPEN_BROWSER) {
    $env:OPEN_BROWSER = "1"
}

$url = "http://$env:HOST`:$env:PORT"
Write-Host "Usando Python: $venvPython" -ForegroundColor DarkCyan
Write-Host "Fuente Python: .venv" -ForegroundColor DarkCyan
Write-Host "Iniciando backend local en $url" -ForegroundColor Cyan
Write-Host "Presiona Ctrl+C para detenerlo." -ForegroundColor Yellow

& $venvPython (Join-Path $projectRoot "app.py")
