$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$verificationDirectory = Join-Path $projectRoot '.pytest-verification'
$databaseFile = Join-Path $verificationDirectory 'mvp-verification.db'

if (-not (Test-Path $python)) {
    throw "Project virtual environment is missing: $python"
}

New-Item -ItemType Directory -Path $verificationDirectory -Force | Out-Null
if (Test-Path $databaseFile) {
    Remove-Item -LiteralPath $databaseFile -Force
}

$previousDatabaseUrl = $env:DATABASE_URL
$env:DATABASE_URL = "sqlite+pysqlite:///$($databaseFile -replace '\\', '/')"

try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $python -m app.scripts.check_data_quality
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    $env:DATABASE_URL = $previousDatabaseUrl
    if (Test-Path $databaseFile) {
        Remove-Item -LiteralPath $databaseFile -Force
    }
    if (Test-Path $verificationDirectory) {
        Remove-Item -LiteralPath $verificationDirectory -Recurse -Force
    }
}
