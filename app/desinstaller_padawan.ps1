# Desinstalleur du Projet Padawan : retire programmes, raccourcis, cle Run et inscription.
# Les donnees (Documents\Padawan : Grimoire, Archiveur) sont GARDEES, sauf si -SupprimerDonnees ou reponse O.
param([switch]$SupprimerDonnees, [switch]$Silent, [switch]$KeepDir)
$Dir = $PSScriptRoot
Write-Host "Desinstallation du Projet Padawan ($Dir)"
if (-not $Silent) {
  $a = Read-Host "Confirmer la desinstallation ? (O/N)"
  if (-not $a.Trim().ToUpper().StartsWith("O")) { exit 0 }
  $b = Read-Host "Supprimer AUSSI vos donnees (Grimoire, archives, favoris Arsenal) ? (O/N) [defaut N]"
  if ($b -and $b.Trim().ToUpper().StartsWith("O")) { $SupprimerDonnees = $true }
}
# fermer les programmes de ce dossier
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains($Dir) } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
# cle Run (seulement si elle pointe ici)
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$v = (Get-ItemProperty $run -Name Padawan -ErrorAction SilentlyContinue).Padawan
if ($v -and $v.Contains($Dir)) { Remove-ItemProperty $run -Name Padawan; Write-Host "  cle Run retiree" }
$vf = (Get-ItemProperty $run -Name Facteur -ErrorAction SilentlyContinue).Facteur
if ($vf -and $vf.Contains($Dir)) { Remove-ItemProperty $run -Name Facteur; Write-Host "  cle Run Facteur retiree" }
# raccourcis qui pointent ici
$ws = New-Object -ComObject WScript.Shell
$dirs = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) "Padawan"))
foreach ($d in $dirs) {
  Get-ChildItem $d -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
    $s = $ws.CreateShortcut($_.FullName)
    if (($s.Arguments + $s.WorkingDirectory).Contains($Dir)) { Remove-Item $_.FullName -Force; Write-Host "  retire $($_.Name)" }
  }
}
$sm = Join-Path ([Environment]::GetFolderPath("Programs")) "Padawan"
if ((Test-Path $sm) -and -not (Get-ChildItem $sm)) { Remove-Item $sm -Force }
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ProjetPadawan" -Recurse -ErrorAction SilentlyContinue
if ($SupprimerDonnees) {
  $data = Join-Path $env:USERPROFILE "Documents\Padawan"
  if (Test-Path $data) { Remove-Item $data -Recurse -Force; Write-Host "  donnees supprimees : $data" }
} else { Write-Host "  donnees gardees : $env:USERPROFILE\Documents\Padawan" }
# supprimer le dossier du programme apres la fin de ce script
if (-not $KeepDir) {
$cmd = "ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$Dir`""
Start-Process cmd.exe -ArgumentList "/c $cmd" -WindowStyle Hidden -WorkingDirectory $env:TEMP
}
Write-Host "Projet Padawan desinstalle."
if (-not $Silent) { Read-Host "Entree pour fermer" }

