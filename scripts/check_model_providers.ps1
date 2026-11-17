param(
  [string]$LmStudioModelsUrl = $(if ($env:TRANSCIBIO_LMSTUDIO_MODELS_URL) { $env:TRANSCIBIO_LMSTUDIO_MODELS_URL } else { "http://127.0.0.1:1234/v1/models" }),
  [string]$OllamaTagsUrl = $(if ($env:TRANSCIBIO_OLLAMA_TAGS_URL) { $env:TRANSCIBIO_OLLAMA_TAGS_URL } else { "http://127.0.0.1:11434/api/tags" })
)

function Test-HttpEndpoint {
  param(
    [Parameter(Mandatory = $true)][string]$Url
  )
  try {
    $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 2 -UseBasicParsing
    [pscustomobject]@{
      Url = $Url
      Reachable = $true
      StatusCode = [int]$response.StatusCode
      Error = ""
    }
  } catch {
    [pscustomobject]@{
      Url = $Url
      Reachable = $false
      StatusCode = $null
      Error = $_.Exception.Message
    }
  }
}

$piperBin = if ($env:TRANSCIBIO_PIPER_BIN) { $env:TRANSCIBIO_PIPER_BIN } else { (Get-Command piper -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue) }
$piperModel = if ($env:TRANSCIBIO_PIPER_MODEL) { $env:TRANSCIBIO_PIPER_MODEL } else { "" }

$lm = Test-HttpEndpoint -Url $LmStudioModelsUrl
$ollama = Test-HttpEndpoint -Url $OllamaTagsUrl

Write-Host "== Local Model Provider Checks ==" -ForegroundColor Cyan
Write-Host ("LM Studio : {0} ({1})" -f $(if ($lm.Reachable) { "reachable" } else { "unreachable" }), $lm.Url)
if (-not $lm.Reachable) { Write-Host ("  -> {0}" -f $lm.Error) -ForegroundColor DarkYellow }

Write-Host ("Ollama    : {0} ({1})" -f $(if ($ollama.Reachable) { "reachable" } else { "unreachable" }), $ollama.Url)
if (-not $ollama.Reachable) { Write-Host ("  -> {0}" -f $ollama.Error) -ForegroundColor DarkYellow }

Write-Host ("Piper bin : {0}" -f $(if ($piperBin) { $piperBin } else { "not found" }))
Write-Host ("Piper model env (TRANSCIBIO_PIPER_MODEL): {0}" -f $(if ($piperModel) { $piperModel } else { "not configured" }))

[pscustomobject]@{
  lmstudio = $lm
  ollama = $ollama
  piper = [pscustomobject]@{
    binary_found = [bool]$piperBin
    binary_path = $piperBin
    model_configured = [bool]$piperModel
    model_path = $piperModel
  }
}
