# One-click launcher for Transcibio on Windows (Docker Desktop + Ollama). Linux, macOS and the
# DGX Spark use scripts/transcibio.sh, which does the same.
#
#   Transcibio.bat -> transcibio.ps1 start   checks, first-run setup, start, browser; then the
#                                            window stays open and Ctrl+C stops the app
#   transcibio.ps1 stop                      stop from another window (data stays)
#   transcibio.ps1 logs                      follow the logs
#
# With an NVIDIA GPU it uses docker-compose.yml, without one also docker-compose.cpu.yml.
# Messages are ASCII on purpose: Windows PowerShell 5.1 reads scripts without a BOM as ANSI.
param([Parameter(Position = 0)][ValidateSet("start", "stop", "logs")][string]$Command = "start")

# "Stop" would turn docker's normal stderr output into errors in Windows PowerShell 5.1;
# exit codes are checked explicitly instead.
$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot ".env"
$UiUrl = "http://localhost:8080"
$HealthUrl = "http://127.0.0.1:8080/api/v1/healthz"
$OllamaUrl = "http://127.0.0.1:11434"
$DefaultModel = "gpt-oss-20b"   # keep in sync with backend/app/services/local_llm.py
$HealthTimeoutSeconds = 600

function Write-Info([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
# Started by Transcibio.bat: keep the window open so the message can be read.
function Exit-WithError([string]$Message) {
    Write-Host "Fehler: $Message" -ForegroundColor Red
    if ($env:TRANSCIBIO_FROM_DESKTOP -eq "1") { Read-Host "Enter druecken zum Schliessen" | Out-Null }
    exit 1
}
function Test-Command([string]$Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Test-Docker {
    docker info *> $null
    $LASTEXITCODE -eq 0
}

function Test-Url([string]$Url) {
    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
        $true
    } catch {
        $false
    }
}

function Get-OllamaTags {
    try { Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5 } catch { $null }
}

# Retry every 3 s until the condition is true; $false after $Seconds.
function Wait-Until([int]$Seconds, [scriptblock]$Condition) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 3
    }
    return [bool](& $Condition)
}

# gpu | cpu. The GPU setup needs the NVIDIA driver; Docker Desktop (WSL 2) passes the GPU on.
function Get-Variant {
    if (Test-Command "nvidia-smi") {
        nvidia-smi -L *> $null
        if ($LASTEXITCODE -eq 0) { return "gpu" }
    }
    return "cpu"
}

# docker compose arguments that select the compose files for the variant.
function Get-ComposeArgs([string]$Variant) {
    $files = @("docker-compose.yml")
    if ($Variant -eq "cpu") { $files += "docker-compose.cpu.yml" }
    $composeArgs = @("compose", "--project-directory", $RepoRoot)
    foreach ($file in $files) { $composeArgs += @("-f", (Join-Path $RepoRoot $file)) }
    return $composeArgs
}

# Runs docker compose with the files for the variant; $true on success.
function Invoke-Compose([string]$Variant, [string[]]$Arguments) {
    $composeArgs = Get-ComposeArgs $Variant
    & docker @composeArgs @Arguments | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# $true while the backend container exists (running or restarting).
function Test-AppContainer([string]$Variant) {
    $composeArgs = Get-ComposeArgs $Variant
    $id = & docker @composeArgs ps -q backend 2>$null
    return [bool]$id
}

# Read a value the way the backend does: process env wins, then the last line in .env.
function Get-EnvValue([string]$Key, [string]$Default) {
    $fromProcess = [Environment]::GetEnvironmentVariable($Key)
    if ($fromProcess) { return $fromProcess }
    $value = ""
    if (Test-Path $EnvFile) {
        foreach ($line in [IO.File]::ReadAllLines($EnvFile)) {
            if ($line -match "^\s*$Key\s*=\s*(.*)$") {
                $value = ($Matches[1] -replace '\s+#.*$', '').Trim().Trim('"', "'")
            }
        }
    }
    if ($value) { return $value }
    return $Default
}

# Replace the KEY= line in .env, or append one. Written as UTF-8 without BOM.
function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = [Collections.Generic.List[string]]([IO.File]::ReadAllLines($EnvFile))
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith("$Key=")) { $index = $i; break }
    }
    if ($index -ge 0) { $lines[$index] = "$Key=$Value" } else { $lines.Add("$Key=$Value") }
    [IO.File]::WriteAllLines($EnvFile, $lines)
}

function Initialize-Docker {
    if (-not (Test-Command "docker")) {
        Exit-WithError "Docker Desktop ist nicht installiert: https://docs.docker.com/get-docker/"
    }
    if (Test-Docker) { return }
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Write-Info "Starte Docker Desktop ..."
        Start-Process $dockerDesktop
    }
    if (-not (Wait-Until 180 { Test-Docker })) {
        Exit-WithError "Docker Desktop laeuft nicht. Bitte Docker Desktop oeffnen und erneut versuchen."
    }
}

# First start: create .env from .env.example (laptop defaults) and ask once for the optional
# Hugging Face token.
function Initialize-EnvFile {
    if (Test-Path $EnvFile) { return }
    Copy-Item (Join-Path $RepoRoot ".env.example") $EnvFile
    Write-Info "Einstellungen angelegt: $EnvFile (Laptop: gemma4:e4b, Whisper medium)"
    Write-Host ""
    Write-Host "Sprechererkennung (optional): Hugging Face Token einfuegen."
    Write-Host "Anleitung: readme.md, Abschnitt `"Sprechererkennung`". Spaeter aenderbar in .env."
    $token = (Read-Host "Token (Enter = ueberspringen)").Trim()
    if ($token) { Set-EnvValue "HF_TOKEN" $token }
    Write-Host ""
}

function Initialize-Ollama {
    if (Get-OllamaTags) { return }
    $ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
    if (Test-Path $ollamaApp) {
        Write-Info "Starte Ollama ..."
        Start-Process $ollamaApp
        if (Wait-Until 30 { [bool](Get-OllamaTags) }) { return }
    }
    Exit-WithError "Ollama ist nicht erreichbar ($OllamaUrl). Installieren: https://ollama.com/download"
}

# Download the chat model from .env on first use.
function Initialize-Model {
    $model = Get-EnvValue "TRANSCIBIO_OLLAMA_MODEL" $DefaultModel
    $names = @((Get-OllamaTags).models | ForEach-Object { $_.name })
    $installed = ($names -contains $model) -or (($model -notlike "*:*") -and ($names -contains "${model}:latest"))
    if ($installed) {
        Write-Info "Docker und Ollama ok (Chat-Modell: $model)."
        return
    }
    $hint = "Modellname pruefen: TRANSCIBIO_OLLAMA_MODEL in $EnvFile (Liste: ollama list)."
    if (-not (Test-Command "ollama")) { Exit-WithError "Chat-Modell $model fehlt und ollama ist nicht im PATH. $hint" }
    Write-Info "Lade das Chat-Modell $model herunter (einmalig, mehrere GB) ..."
    & ollama pull $model
    if ($LASTEXITCODE -ne 0) { Exit-WithError "Download von $model fehlgeschlagen. $hint" }
}

# Download every Whisper model the Settings presets use (small, medium, large-v3), so no
# preset waits for a download. Cached models are skipped; failures don't stop the start.
function Initialize-WhisperModels([string]$Variant) {
    Write-Info "Pruefe Whisper-Modelle (beim ersten Start ca. 5 GB) ..."
    $prefetch = @("exec", "-T", "backend", "python", "-m", "backend.app.services.whisper_prefetch")
    if (-not (Invoke-Compose $Variant $prefetch)) {
        Write-Info "Hinweis: Nicht alle Whisper-Modelle geladen; fehlende laedt die App bei Bedarf nach."
    }
}

function Start-Transcibio {
    Initialize-Docker
    Initialize-EnvFile
    Initialize-Ollama
    Initialize-Model
    $variant = Get-Variant
    $label = if ($variant -eq "gpu") { "mit NVIDIA-GPU" } else { "ohne GPU" }
    Write-Info "Starte Transcibio ($label). Der erste Start dauert eine Weile ..."
    $script:Started = $true
    if (-not (Invoke-Compose $variant @("up", "-d", "--build"))) {
        if ($variant -ne "gpu") { Exit-WithError "Start fehlgeschlagen. Logs: scripts\transcibio.ps1 logs" }
        Write-Info "Start mit GPU fehlgeschlagen, starte ohne GPU ..."
        $variant = "cpu"
        if (-not (Invoke-Compose $variant @("up", "-d", "--build"))) {
            Exit-WithError "Start fehlgeschlagen. Logs: scripts\transcibio.ps1 logs"
        }
    }
    Write-Info "Warte, bis Transcibio bereit ist ..."
    if (-not (Wait-Until $HealthTimeoutSeconds { Test-Url $HealthUrl })) {
        Invoke-Compose $variant @("ps") | Out-Null
        Exit-WithError "Transcibio nach $HealthTimeoutSeconds s nicht bereit. Logs: scripts\transcibio.ps1 logs"
    }
    Initialize-WhisperModels $variant
    Start-Process $UiUrl
    Write-Host ""
    Write-Info "Transcibio laeuft: $UiUrl"
    Write-Info "Dieses Fenster offen lassen. Beenden: Strg+C druecken."
    # Wait until Ctrl+C, or until the app is stopped elsewhere (stop, another window).
    while (Test-AppContainer $variant) { Start-Sleep -Seconds 5 }
    Write-Info "Transcibio wurde beendet."
}

function Stop-Transcibio {
    if (-not (Test-Command "docker") -or -not (Test-Docker)) {
        Write-Info "Docker laeuft nicht, Transcibio ist also schon gestoppt."
        return
    }
    Write-Info "Stoppe Transcibio ..."
    if (-not (Invoke-Compose (Get-Variant) @("down", "--remove-orphans"))) {
        Exit-WithError "Stoppen fehlgeschlagen."
    }
    Write-Info "Transcibio ist gestoppt."
}

# Ctrl+C ends the script; "finally" still runs and stops the app.
$script:Started = $false
switch ($Command) {
    "start" {
        try { Start-Transcibio } finally { if ($script:Started) { Write-Host ""; Stop-Transcibio } }
    }
    "stop" { Stop-Transcibio }
    "logs" { Invoke-Compose (Get-Variant) @("logs", "-f") | Out-Null }
}
exit 0
