param(
  [Parameter(Mandatory=$true)][string]$PythonW,
  [Parameter(Mandatory=$true)][string]$App
)
$App = [System.IO.Path]::GetFullPath($App)
$cmd = '"' + $PythonW + '" "' + $App + '"'
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Padawan" -Value $cmd -Force
Write-Host "  Run Padawan = $cmd"
# purge legacy
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
foreach ($n in @("Padawan.bat","Padawan.lnk")) {
  $p = Join-Path $startup $n
  if (Test-Path $p) { Remove-Item $p -Force; Write-Host "  legacy rm $p" }
}
# Facteur au demarrage (defaut ON, sauf si desactive manuellement)
$fac = Join-Path (Split-Path $App) "facteur1.py"
$flag = Join-Path $env:LOCALAPPDATA "Padawan\Facteur\demarrage_desactive.flag"
if ((Test-Path $fac) -and -not (Test-Path $flag)) {
  $fcmd = '"' + $PythonW + '" "' + $fac + '" --cache'
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Facteur" -Value $fcmd -Force
  Write-Host "  Run Facteur = $fcmd"
} elseif (Test-Path $flag) { Write-Host "  Facteur au demarrage : desactive (choix manuel conserve)" }
