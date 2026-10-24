# Installateur du Projet Padawan (Padawan, tray, Gestionnaire, Archiveur, Arsenal, Grimoire)
# Sans droits admin. Usage : INSTALLER.bat  ou  Padawan-Setup.exe
#   -InstallDir <dossier>   -Silent (aucune question)   -Test (aucun changement systeme : ni PATH, ni raccourcis,
#   ni cle Run, ni desinstalleur inscrit, ni Ollama, ni lancement)   -DataDir <dossier> (donnees, sinon Documents\Padawan)
param(
  [string]$InstallDir = "",
  [string]$DataDir = "",
  [switch]$Silent,
  [switch]$Test,
  [switch]$NoLaunch,
  [switch]$Ollama,
  [switch]$NoCopy,
  [switch]$Inno
)
if ($NoCopy) { $env:PADAWAN_NOCOPY = "1" }
if ($Inno) { $env:PADAWAN_INNO = "1" }
$ErrorActionPreference = "Continue"
# Padawan-Setup.exe ne transmet pas d'arguments : variables PADAWAN_TEST=1 et PADAWAN_INSTALLDIR possibles
if ($env:PADAWAN_TEST -eq "1") { $Test = $true }
if (-not $InstallDir -and $env:PADAWAN_INSTALLDIR) { $InstallDir = $env:PADAWAN_INSTALLDIR }
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = "Padawan Suite - installation en cours (ne ferme pas cette fenetre)" } catch {}
if (-not $Test) { try { $lg = Join-Path $env:LOCALAPPDATA "Padawan"; New-Item -ItemType Directory -Force $lg | Out-Null; Start-Transcript -Path (Join-Path $lg "install.log") -Force | Out-Null } catch {} }
if ($Inno) { $env:PIP_QUIET = "1"; $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"; $env:PIP_NO_WARN_SCRIPT_LOCATION = "1" }
$Src = Join-Path $PSScriptRoot "app"
if (-not (Test-Path (Join-Path $Src "padawan39.py"))) { $Src = $PSScriptRoot }
Write-Host "==============================================="
Write-Host "   Bienvenue ! Installation de la Padawan Suite"
Write-Host "   Padawan + tray + Gestionnaire + Archiveur + Arsenal + Grimoire + Facteur + Messager + Chantier + Retro"
Write-Host "==============================================="
if ($Test) { Write-Host "MODE TEST : rien n'est change sur le systeme (PATH, raccourcis, demarrage, desinstalleur)."; $Silent = $true; $NoLaunch = $true }

function Ask($q, $def) {
  if ($Silent) { return $def }
  $a = Read-Host "$q [defaut : $def]"
  if ([string]::IsNullOrWhiteSpace($a)) { return $def }
  return $a.Trim().Trim('"')
}
function AskYes($q, $defYes) {
  if ($Silent) { return $defYes }
  $d = "N"; if ($defYes) { $d = "O" }
  $a = Read-Host "$q (O/N) [defaut : $d]"
  if ([string]::IsNullOrWhiteSpace($a)) { return $defYes }
  return ($a.Trim().ToUpper().StartsWith("O") -or $a.Trim().ToUpper().StartsWith("Y"))
}

# 1) Dossier d'installation
if (-not $InstallDir) { $InstallDir = Ask "Dossier d'installation" (Join-Path $env:LOCALAPPDATA "Padawan") }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
New-Item -ItemType Directory -Force $InstallDir | Out-Null
Write-Host ""
Write-Host "[1/6] Copie des programmes vers $InstallDir ..."
# ne jamais ecraser les donnees de l'utilisateur deja presentes
$keep = @("arsenal.json","config.json","memory.json","archiveur_config.json","tasks.json","search_cache.json")
if ($env:PADAWAN_NOCOPY -eq "1") { Write-Host "  (fichiers deja places par Padawan-Setup.exe)" } else {
Get-ChildItem -LiteralPath $Src -Force | ForEach-Object {
  $dst = Join-Path $InstallDir $_.Name
  if ($keep -contains $_.Name -and (Test-Path $dst)) { Write-Host "  garde $($_.Name) (deja present)"; return }
  Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force
}
}
Write-Host "  OK"

# 2) Python
Write-Host ""
Write-Host "[2/6] Python 3..."
function Find-Python {
  $c = @()
  foreach ($n in "python.exe") {
    $w = (Get-Command $n -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1)
    if ($w) { $c += $w.Source }
  }
  $c += (Get-ChildItem (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3*\python.exe") -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName)
  $c += (Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python\Python3*\python.exe") -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | ForEach-Object FullName)
  $c += (Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue | ForEach-Object FullName)
  foreach ($p in $c) {
    if ($p -and (Test-Path $p)) {
      & $p -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
      if ($LASTEXITCODE -eq 0) { return $p }
    }
  }
  return $null
}
$py = Find-Python
if (-not $py -and -not $Test) {
  Write-Host "  Python absent : installation pour cet utilisateur (sans admin). Ca peut prendre 1-2 min, c'est normal..."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    $py = Find-Python
  }
  if (-not $py) {
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    $tmp = Join-Path $env:TEMP "python-3.12.10-amd64.exe"
    Write-Host "  Telechargement $url (environ 27 Mo)..."
    try {
      [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
      Start-Process -FilePath $tmp -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_tcltk=1 Include_pip=1 Include_launcher=0" -Wait
    } catch { Write-Host "  ERREUR telechargement Python : $_" }
    $py = Find-Python
  }
}
if (-not $py) {
  Write-Host "  Pas de panique : verifie ta connexion Internet puis relance Padawan-Setup.exe (ou menu Demarrer > Padawan > Reparer l'installation)."
  if (-not $Test) { try { Start-Process "https://www.python.org/downloads/windows/" } catch {} }
  Write-Host "ERREUR : Python 3 introuvable. Installez-le depuis https://www.python.org/downloads/ (cocher « Add to PATH ») puis relancez."
  if (-not $Silent) { Read-Host "Entree pour fermer" }
  exit 1
}
Write-Host "  OK $py"
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
try { Set-Content -LiteralPath (Join-Path $InstallDir "python_path.txt") -Value $pyw -Encoding ASCII } catch {}

# 3) Ollama (option)
$wantOllama = $false
if (-not $Test) {
  Write-Host ""
  Write-Host "[3/6] Ollama = l'IA locale de Padawan (optionnel)."
  Write-Host "      Ollama : environ 1 Go. Modele dolphin3:8b : environ 4,9 Go de plus (8 Go de RAM conseilles)."
  Write-Host "      Sans Ollama, les autres programmes fonctionnent ; Padawan n'aura pas son IA."
  $wantOllama = $Ollama -or (AskYes "Installer Ollama + le modele maintenant ?" $false)
}

# 4) Dependances, ffmpeg, raccourcis, demarrage : setup_padawan.bat
Write-Host ""
Write-Host "[4/6] Dependances (pip), ffmpeg, raccourcis Bureau + Menu Demarrer, demarrage auto..."
$env:PADAWAN_PYTHON = $py
$env:PADAWAN_AUTO = "1"
$env:PADAWAN_NOOLLAMA = "1"
$env:PADAWAN_STARTMENU = "1"
if ($Test) { $env:PADAWAN_NOSYS = "1" } else { Remove-Item Env:PADAWAN_NOSYS -ErrorAction SilentlyContinue }
& cmd.exe /c "`"$(Join-Path $InstallDir 'setup_padawan.bat')`""
$setupCode = $LASTEXITCODE

if ($wantOllama) {
  Write-Host ""
  Write-Host "Ollama..."
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
      winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
    } else { Write-Host "  winget absent : installez Ollama depuis https://ollama.com/download" }
  }
  $ol = (Get-Command ollama -ErrorAction SilentlyContinue | Select-Object -First 1).Source
  if (-not $ol) { $c = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"; if (Test-Path $c) { $ol = $c } }
  if ($ol) { & $ol pull dolphin3:8b } else { Write-Host "  Ollama introuvable apres installation (redemarrez puis : ollama pull dolphin3:8b)" }
}

# 5) Desinstalleur
Write-Host ""
Write-Host "[5/6] Desinstalleur..."
if ($env:PADAWAN_INNO -eq "1") { Write-Host "  OK (gere par Padawan-Setup.exe : Parametres > Applications > Projet Padawan)" }
elseif (-not $Test) {
  $un = Join-Path $InstallDir "Desinstaller.bat"
  $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ProjetPadawan"
  New-Item -Path $key -Force | Out-Null
  Set-ItemProperty $key -Name DisplayName -Value "Projet Padawan"
  Set-ItemProperty $key -Name Publisher -Value "Marc Sevigny"
  Set-ItemProperty $key -Name InstallLocation -Value $InstallDir
  Set-ItemProperty $key -Name UninstallString -Value ('"' + $un + '"')
  Set-ItemProperty $key -Name DisplayIcon -Value (Join-Path $InstallDir "padawan_tray.ico")
  Set-ItemProperty $key -Name NoModify -Value 1 -Type DWord
  Set-ItemProperty $key -Name NoRepair -Value 1 -Type DWord
  Write-Host "  OK (Parametres > Applications > Projet Padawan, ou $un)"
} else { Write-Host "  saute (mode test)" }

# 6) Fin
Write-Host ""
Write-Host "[6/6] Termine ! La Padawan Suite est prete."
Write-Host "  Programmes : $InstallDir"
if (Test-Path "C:\web\FTP_HOME") { $dd = "C:\web\FTP_HOME (GRIMOIRE, ARCHIVEUR)" } elseif ($env:PADAWAN_DATA) { $dd = $env:PADAWAN_DATA } else { $dd = "$env:USERPROFILE\Documents\Padawan\" }
Write-Host "  Donnees    : $dd - gardees a la desinstallation"
if ($setupCode -ne 0) { Write-Host "  Attention : setup_padawan.bat a retourne le code $setupCode (voir ci-dessus)." }
if (-not $NoLaunch) {
  Write-Host "  Lancement de Padawan (icone dans la zone de notification)..."
  Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $InstallDir "padawan39.py") + '"') -WorkingDirectory $InstallDir
}
if (-not $Silent) { Read-Host "Entree pour fermer" }
exit 0


