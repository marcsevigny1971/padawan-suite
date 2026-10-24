param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$PythonW,
  [switch]$StartMenu
)
$ErrorActionPreference = "Stop"
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$Root = [System.IO.Path]::GetFullPath($Root.Trim().Trim([char]34)).TrimEnd("\")

function New-AppShortcut($Name, $Script, $Ico) {
  $scriptPath = Join-Path $Root $Script
  if (-not (Test-Path $scriptPath)) {
    Write-Host "  saute $Name (script manquant)"
    return
  }
  $lnkPath = Join-Path $desktop ($Name + ".lnk")
  $s = $ws.CreateShortcut($lnkPath)
  $s.TargetPath = $PythonW
  $s.Arguments = '"' + $scriptPath + '"'
  $s.WorkingDirectory = $Root
  $s.Description = $Name
  $icoPath = Join-Path $Root $Ico
  if (Test-Path $icoPath) { $s.IconLocation = $icoPath }
  $s.Save()
  Write-Host "  OK $lnkPath"
  if ($StartMenu) {
    $smDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Padawan"
    New-Item -ItemType Directory -Force $smDir | Out-Null
    $smLnk = Join-Path $smDir ($Name + ".lnk")
    Copy-Item $lnkPath $smLnk -Force
    Write-Host "  OK $smLnk"
  }
}

New-AppShortcut "Padawan" "padawan39.py" "padawan_tray.ico"
New-AppShortcut "Gestionnaire de fichiers" "gestionnaire_fichiers5.py" "gestionnaire_fichiers5.ico"
$arch = "archiveur5.py"
foreach ($cand in "archiveur5.py","archiveur4.py","archiveur3.py","archiveur2.py","archiveur1.py") { if (Test-Path (Join-Path $Root $cand)) { $arch = $cand; break } }
New-AppShortcut "Archiveur" $arch "archiveur.ico"
New-AppShortcut "Arsenal" "arsenal1.py" "arsenal1.ico"
New-AppShortcut "Grimoire" "grimoire1.py" "grimoire1.ico"
New-AppShortcut "Facteur" "facteur1.py" "facteur1.ico"
$msg = "messager2.py"; $msgIco = "messager2.ico"
if (-not (Test-Path (Join-Path $Root $msg))) { $msg = "messager1.py"; $msgIco = "messager1.ico" }
New-AppShortcut "Messager" $msg $msgIco
New-AppShortcut "Chantier" "chantier1.py" "chantier1.ico"
New-AppShortcut "Retro" "retro1.py" "retro1.ico"
New-AppShortcut "Tableau de bord Padawan" "tableau_bord.py" "padawan_tray.ico"
New-AppShortcut "Premiers pas Padawan" "premiers_pas.py" "padawan_tray.ico"
New-AppShortcut "Coffre Padawan" "coffre_padawan.py" "padawan_tray.ico"
New-AppShortcut "Recherche Padawan" "recherche_padawan.py" "padawan_tray.ico"
# Ctrl+Alt+R : raccourci clavier Windows sur le raccourci du Bureau seulement (pas de doublon)
$rl = Join-Path $desktop "Recherche Padawan.lnk"
if (Test-Path $rl) { $s = $ws.CreateShortcut($rl); $s.Hotkey = "CTRL+ALT+R"; $s.Save(); Write-Host "  Ctrl+Alt+R -> Recherche Padawan" }

