$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = $env:AUTOCATALYST_PYTHON

if (-not $launcher) {
  foreach ($candidate in @("py", "python", "python3")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
      $launcher = $candidate
      break
    }
  }
}

if (-not $launcher) {
  Write-Error "AutoCatalyst: could not find py, python, or python3 in PATH."
  exit 1
}

if ($launcher -eq "py") {
  & $launcher -3 (Join-Path $ScriptDir "bootstrap.py") @args
} else {
  & $launcher (Join-Path $ScriptDir "bootstrap.py") @args
}
