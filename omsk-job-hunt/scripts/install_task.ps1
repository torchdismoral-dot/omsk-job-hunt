# Регистрирует задачу «OmWork Bot»: запуск при входе в систему и
# автоперезапуск при падении. Запускать без прав администратора.
$ErrorActionPreference = "Stop"

$project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonw = Join-Path (Split-Path (Get-Command python.exe).Source) "pythonw.exe"
$launcher = Join-Path $project "run_bot.pyw"
$taskName = "OmWork Bot"

if (-not (Test-Path $pythonw)) {
    throw "Не найден pythonw.exe рядом с python.exe ($pythonw)"
}
if (-not (Test-Path $launcher)) {
    throw "Не найден $launcher"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonw `
    -Argument "`"$launcher`"" `
    -WorkingDirectory $project

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "OmWork — карьера в Омске: Telegram-бот. Старт при входе, автоперезапуск при падении." `
    -Force | Out-Null

Write-Host "Задача «$taskName» зарегистрирована."
Write-Host "  программа: $pythonw `"$launcher`""
Write-Host "  каталог:   $project"
