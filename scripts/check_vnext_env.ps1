param(
  [switch]$Json
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$frontendDir = Join-Path $repoRoot "frontend"

function Check-Command {
  param([string]$Name)
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  [pscustomobject]@{
    name = $Name
    found = [bool]$cmd
    path = if ($cmd) { $cmd.Source } else { "" }
  }
}

function Check-File {
  param([string]$Label, [string]$Path)
  [pscustomobject]@{
    name = $Label
    found = Test-Path $Path
    path = $Path
  }
}

$checks = @(
  (Check-File -Label ".venv python" -Path $venvPython),
  (Check-Command -Name "node"),
  (Check-Command -Name "npm"),
  (Check-Command -Name "ffmpeg"),
  (Check-Command -Name "ffprobe")
)

$providerCheck = & (Join-Path $PSScriptRoot "check_model_providers.ps1")

if ($Json) {
  [pscustomobject]@{
    repo_root = $repoRoot
    frontend_dir = $frontendDir
    checks = $checks
    providers = $providerCheck
  } | ConvertTo-Json -Depth 6
  exit 0
}

Write-Host "== Transcibio vNext Environment Check ==" -ForegroundColor Cyan
Write-Host ("Repo root : {0}" -f $repoRoot)
Write-Host ("Frontend  : {0}" -f $frontendDir)

foreach ($check in $checks) {
  $status = if ($check.found) { "OK" } else { "MISSING" }
  $color = if ($check.found) { "Green" } else { "Yellow" }
  Write-Host ("{0,-14} {1,-8} {2}" -f $check.name, $status, $check.path) -ForegroundColor $color
}

Write-Host ""
Write-Host "Recommended next steps:" -ForegroundColor Cyan
if (-not (Test-Path $venvPython)) {
  Write-Host "1. Create venv: uv venv --python 3.10 .venv" -ForegroundColor Yellow
  Write-Host '2. Install backend deps: uv pip install --python .venv\Scripts\python.exe ".[dev,vnext]"' -ForegroundColor Yellow
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
  Write-Host "3. Install FFmpeg and ensure ffmpeg + ffprobe are in PATH." -ForegroundColor Yellow
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Host "4. Install Node.js LTS (includes npm)." -ForegroundColor Yellow
}
Write-Host "5. Optional: start LM Studio/Ollama/Piper for full local-model behavior (fallbacks exist)." -ForegroundColor Yellow
