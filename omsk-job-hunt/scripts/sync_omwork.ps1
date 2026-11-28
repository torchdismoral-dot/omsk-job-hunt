<#
.SYNOPSIS
    Зеркалирует код проекта в omwork — отдельный git-репозиторий, из которого
    Amvera собирает образ (amvera.yml обязан лежать в корне репозитория, а корень
    нашего репозитория — D:\CLAUDE CODE, поэтому деплой идёт из копии).

.USAGE
    .\scripts\sync_omwork.ps1                              # только скопировать
    .\scripts\sync_omwork.ps1 -Push                        # + коммит и push на Amvera
    .\scripts\sync_omwork.ps1 -Push -Message "Добавить hh.ru"

Секреты (.env), базы (.db) и логи в omwork не перезаписываются: они не входят
в список синхронизации и исключены из .gitignore.
#>
param(
    [switch]$Push,
    [string]$Message = "Синхронизация кода из корня проекта"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root 'omwork'

foreach ($dir in 'src', 'tests', 'scripts') {
    robocopy (Join-Path $root $dir) (Join-Path $target $dir) /MIR /XD __pycache__ .pytest_cache /NFL /NDL /NJH /NJS | Out-Null
    # robocopy возвращает 0-7 как успех; 8+ — настоящая ошибка
    if ($LASTEXITCODE -ge 8) { throw "robocopy ${dir}: код ошибки $LASTEXITCODE" }
}

$files = @(
    'main.py', 'conftest.py', 'pytest.ini', 'config.yaml',
    'requirements.txt', 'requirements-dev.txt',
    'README.md', 'SPEC.md', 'amvera.yml', 'Dockerfile',
    '.dockerignore', '.gitignore', '.env.example'
)
foreach ($name in $files) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $target $name) -Force
}

Write-Host "Синхронизировано в $target"

if ($Push) {
    Push-Location $target
    try {
        git add -A
        git commit -m $Message
        git push -f amvera master
    }
    finally {
        Pop-Location
    }
}
