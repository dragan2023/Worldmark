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

    # 先用合成样本自检检查器本身，再扫描当前库；空库 0 问题不等于内容可靠。
    & $python -m app.scripts.check_data_quality --self-test
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $python -m app.scripts.check_data_quality
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $python -m pytest -q -p no:cacheprovider --basetemp=.pytest-verification\run
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
