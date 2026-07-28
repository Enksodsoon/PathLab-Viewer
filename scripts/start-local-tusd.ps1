$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$goPath = (& go env GOPATH).Trim()
$bundledTusd = Join-Path $goPath 'bin\tusd.exe'
$tusdCommand = Get-Command tusd -ErrorAction SilentlyContinue
$tusdPath = if ($tusdCommand) { $tusdCommand.Source } elseif (Test-Path $bundledTusd) { $bundledTusd } else { $null }

if (-not $tusdPath) {
    throw 'tusd was not found. Install the pinned local version with: go install github.com/tus/tusd/v2/cmd/tusd@v2.9.2'
}

$uploadDirectory = Join-Path $repositoryRoot 'var\tus'
New-Item -ItemType Directory -Path $uploadDirectory -Force | Out-Null

Push-Location $repositoryRoot
try {
    & $tusdPath `
        '-host=127.0.0.1' `
        '-port=8080' `
        '-base-path=/api/v1/uploads/' `
        '-upload-dir=./var/tus' `
        '-hooks-enabled-events=pre-create,post-finish' `
        '-hooks-http=http://127.0.0.1:8000/api/v1/internal/tus/hooks'
}
finally {
    Pop-Location
}
