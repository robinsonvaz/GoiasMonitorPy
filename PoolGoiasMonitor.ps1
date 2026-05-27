$ErrorActionPreference = 'Stop'

$appRoot = 'D:\Sistemas\GoiasMonitorPy'
$poolIdentity = 'IIS AppPool\GoiasMonitorPool'
$writePaths = @(
  'D:\Sistemas\GoiasMonitorPy\logs'
)

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
  throw 'Execute este script em PowerShell elevado (Run as Administrator).'
}

if (-not (Test-Path -Path $appRoot)) {
  throw "Pasta da aplicacao nao encontrada: $appRoot"
}

foreach ($p in $writePaths) {
  if (-not (Test-Path -Path $p)) {
    New-Item -ItemType Directory -Path $p -Force | Out-Null
  }
}

# Uso de ${} para isolar o nome da variavel do caractere ':'
# /grant:r substitui ACE explicita existente para evitar duplicacao.
icacls $appRoot /grant:r "${poolIdentity}:(OI)(CI)RX" /T /C

foreach ($p in $writePaths) {
  icacls $p /grant:r "${poolIdentity}:(OI)(CI)M" /T /C
}

Write-Host 'Permissoes aplicadas com sucesso ao GoiasMonitorPool.'
