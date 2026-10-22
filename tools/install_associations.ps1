param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path $Executable).Path
if (-not (Test-Path $resolved -PathType Leaf)) { throw 'Ruster executable was not found' }
$classes = 'HKCU:\Software\Classes'
New-Item -Path "$classes\.ruster" -Force | Out-Null
Set-Item -Path "$classes\.ruster" -Value 'Ruster.Project'
New-Item -Path "$classes\Ruster.Project" -Force | Out-Null
Set-Item -Path "$classes\Ruster.Project" -Value 'Ruster Project'
New-Item -Path "$classes\Ruster.Project\shell\open\command" -Force | Out-Null
Set-Item -Path "$classes\Ruster.Project\shell\open\command" -Value "`"$resolved`" `"%1`""
Write-Host 'Registered .ruster files for the current Windows user.'
