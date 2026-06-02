param(
  [switch]$NoBackend,
  [switch]$NoFrontend,
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$backendCmd = ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port $BackendPort --reload"
$frontendCmd = "npm run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort"
$frontendCmdEscaped = $frontendCmd.Replace('"', '\"')

function Test-PortInUse {
  param([int]$Port)

  try {
    return [bool](Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue)
  } catch {
    return $false
  }
}

Write-Host "== Transcibio vNext Start Helper ==" -ForegroundColor Cyan
Write-Host ("Repo root    : {0}" -f $repoRoot)
Write-Host ("Backend URL  : http://127.0.0.1:{0}" -f $BackendPort)
Write-Host ("Frontend URL : http://127.0.0.1:{0}" -f $FrontendPort)

if (-not (Test-Path $venvPython) -and -not $NoBackend) {
  Write-Warning "Backend venv python not found at $venvPython"
  Write-Host "Create it first (example): uv venv --python 3.10 .venv" -ForegroundColor Yellow
}

if (-not $NoBackend) {
  if (Test-PortInUse -Port $BackendPort) {
    Write-Warning "Backend port $BackendPort is already in use. Reusing the existing listener or choose a different port."
  } else {
    Write-Host "Starting backend in a new PowerShell window..." -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
      "-ExecutionPolicy",
      "Bypass",
      "-NoExit",
      "-Command",
      "Set-Location '$repoRoot'; $backendCmd"
    ) | Out-Null
  }
}

if (-not $NoFrontend) {
  if (Test-PortInUse -Port $FrontendPort) {
    Write-Warning "Frontend port $FrontendPort is already in use. Reusing the existing listener or choose a different port."
  } else {
    Write-Host "Starting frontend in a new terminal window..." -ForegroundColor Green
    Start-Process cmd.exe -ArgumentList @(
      "/k",
      "cd /d `"$repoRoot\frontend`" && $frontendCmdEscaped"
    ) | Out-Null
  }
}

Write-Host ""
Write-Host "If startup fails, run scripts\\check_vnext_env.ps1 first." -ForegroundColor Cyan
