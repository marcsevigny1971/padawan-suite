@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%~dp0"
echo ========================================
echo   SETUP PADAWAN (kit complet)
echo   Padawan + tray + Gestionnaire + Archiveur 5 + Arsenal + Grimoire + Facteur + Messager + Chantier + Retro
echo ========================================
echo Repertoire: %ROOT%
echo.

rem --- Options (variables posees par INSTALLER / Padawan-Setup) ---
rem   PADAWAN_PYTHON=chemin python.exe  PADAWAN_NOSYS=1 (test : ni PATH, ni raccourcis, ni cle Run, ni winget)
rem   PADAWAN_AUTO=1 (aucune question, pas de pause)  PADAWAN_NOOLLAMA=1  PADAWAN_STARTMENU=1
if /i "%~1"=="/test" (set "PADAWAN_NOSYS=1" & set "PADAWAN_AUTO=1" & set "PADAWAN_NOOLLAMA=1")
if /i "%~1"=="/auto" set "PADAWAN_AUTO=1"
set "UPG=--upgrade"
if defined PADAWAN_NOSYS set "UPG="
if defined PADAWAN_NOSYS echo MODE TEST : PATH, raccourcis, cle Run et winget ne sont PAS touches.

rem --- Detecter python / pythonw ---
set "PYTHON="
set "PYTHONW="
if defined PADAWAN_PYTHON if exist "%PADAWAN_PYTHON%" set "PYTHON=%PADAWAN_PYTHON%"
for /f "delims=" %%I in ('where python 2^>nul') do (
  echo %%I | findstr /i "WindowsApps" >nul
  if errorlevel 1 if not defined PYTHON set "PYTHON=%%I"
)
for /f "delims=" %%I in ('where pythonw 2^>nul') do (
  echo %%I | findstr /i "WindowsApps" >nul
  if errorlevel 1 if not defined PYTHONW set "PYTHONW=%%I"
)
if not defined PYTHONW if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe" set "PYTHONW=%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe"
if not defined PYTHON if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHONW if defined PYTHON for %%I in ("%PYTHON%") do if exist "%%~dpIpythonw.exe" set "PYTHONW=%%~dpIpythonw.exe"
if not defined PYTHONW set "PYTHONW=%PYTHON%"
if not defined PYTHON (
  echo ERREUR: Python introuvable. Installez Python 3 puis relancez.
  if not defined PADAWAN_AUTO pause
  exit /b 1
)
echo Python : %PYTHON%
echo Pythonw: %PYTHONW%
echo.

for %%I in ("%PYTHON%") do set "PY_DIR=%%~dpI"
set "PY_DIR=%PY_DIR:~0,-1%"
set "PY_SCRIPTS=%PY_DIR%\Scripts"
set "OLLAMA_DIR="
if exist "%LOCALAPPDATA%\Programs\Ollama" set "OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama"
if not defined OLLAMA_DIR if exist "%ProgramFiles%\Ollama" set "OLLAMA_DIR=%ProgramFiles%\Ollama"

echo [1/8] PATH utilisateur (HKCU Environment)...
if defined PADAWAN_NOSYS (echo   saute ^(mode test^)) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%_setup_path.ps1" -PythonDir "%PY_DIR%" -ScriptsDir "%PY_SCRIPTS%" -OllamaDir "%OLLAMA_DIR%" -RefreshFfmpeg
  call :refresh_path
)
echo.

echo [2/8] Dependances pip (Pillow, plyer, pystray, requests, bs4, ddgs, yt-dlp, tkinterdnd2)...
"%PYTHON%" -m pip install %UPG% pip
"%PYTHON%" -m pip install %UPG% -r "%ROOT%requirements-padawan.txt"
if errorlevel 1 (echo   Petit pepin reseau, nouvel essai dans 5 s... & timeout /t 5 /nobreak >nul & "%PYTHON%" -m pip install %UPG% --retries 8 --timeout 60 -r "%ROOT%requirements-padawan.txt")
if errorlevel 1 (echo   Essai en mode utilisateur... & "%PYTHON%" -m pip install %UPG% --user --retries 8 -r "%ROOT%requirements-padawan.txt")
if errorlevel 1 (echo Attention: pip a signale une erreur.) else (echo pip OK.)
echo yt-dlp : mise a jour (YouTube change souvent)...
"%PYTHON%" -m pip install %UPG% yt-dlp
echo yt-dlp : impersonation X/Facebook (curl_cffi, optionnel)...
"%PYTHON%" -m pip install %UPG% curl_cffi >nul 2>&1
if errorlevel 1 (echo   curl_cffi non installe - optionnel, on continue.) else (echo   curl_cffi OK.)
echo Archiveur 5 : glisser-deposer (tkinterdnd2) + pages web (beautifulsoup4)...
"%PYTHON%" -m pip install %UPG% tkinterdnd2 beautifulsoup4 >nul 2>&1
if errorlevel 1 (echo   tkinterdnd2/bs4 : erreur pip - glisser-deposer indisponible, le reste fonctionne.) else (echo   tkinterdnd2 + beautifulsoup4 OK.)
echo Grimoire : texte des PDF (pypdf) + memos vocaux (sounddevice, soundfile, numpy)...
"%PYTHON%" -m pip install %UPG% pypdf sounddevice soundfile numpy >nul 2>&1
if errorlevel 1 (echo   pypdf/sounddevice/soundfile : erreur pip - le Grimoire fonctionne sans, ces fonctions seront grisees.) else (echo   pypdf + sounddevice + soundfile OK.)
echo Facteur : surveillance evenementielle (watchdog) + pywin32 (DPAPI optionnel)...
"%PYTHON%" -m pip install %UPG% watchdog >nul 2>&1
if errorlevel 1 (echo   watchdog : erreur pip - Facteur utilisera le sondage.) else (echo   watchdog OK.)
"%PYTHON%" -m pip install %UPG% pywin32 >nul 2>&1
if errorlevel 1 (echo   pywin32 : erreur pip - Facteur utilisera DPAPI via ctypes.) else (echo   pywin32 OK.)
"%PYTHON%" -m pip install %UPG% pymysql >nul 2>&1
if errorlevel 1 (echo   pymysql : erreur pip - Boite SQL via pont PHP seulement.) else (echo   pymysql OK.)

"%PYTHON%" -c "import faster_whisper" >nul 2>&1
if not errorlevel 1 (
  echo faster-whisper deja installe - transcription locale disponible.
  goto :whisper_done
)
if defined PADAWAN_AUTO goto :whisper_done
echo Transcription locale (faster-whisper, optionnel) : transcrit les videos SANS sous-titres,
echo   100%% sur ce PC (rien n est envoye en ligne). Gros telechargement (environ 300 Mo + modele).
choice /C ON /N /D N /T 20 /M "Installer faster-whisper ? [O/N, defaut N dans 20 s] : "
if errorlevel 2 goto :whisper_done
"%PYTHON%" -m pip install %UPG% faster-whisper
if errorlevel 1 (echo   faster-whisper : echec pip ^(peut-etre pas encore disponible pour cette version de Python^) - optionnel.) else (echo   faster-whisper OK.)
:whisper_done
echo.

echo [3/8] ffmpeg + ffprobe + ffplay (Archiveur : fusion, storyboard, MP4 H.264, lecteur integre)...
set "FF_OK=1"
where ffmpeg >nul 2>&1
if errorlevel 1 set "FF_OK="
where ffprobe >nul 2>&1
if errorlevel 1 set "FF_OK="
if not defined FF_OK (
  echo ffmpeg/ffprobe absent - installation...
  where winget >nul 2>&1
  if not errorlevel 1 if not defined PADAWAN_NOSYS winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
  "%PYTHON%" "%ROOT%_setup_ffmpeg.py"
) else (
  for /f "delims=" %%I in ('where ffmpeg') do (echo ffmpeg : %%I & goto :ff_ok)
)
:ff_ok
if not defined PADAWAN_NOSYS (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%_setup_path.ps1" -PythonDir "%PY_DIR%" -ScriptsDir "%PY_SCRIPTS%" -OllamaDir "%OLLAMA_DIR%" -RefreshFfmpeg
  call :refresh_path
)
rem ffmpeg tout juste installe par winget : l'ajouter au PATH de cette session
where ffprobe >nul 2>&1 || for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*") do for /d %%E in ("%%D\*") do if exist "%%E\bin\ffprobe.exe" set "PATH=%%E\bin;%PATH%"
where ffprobe >nul 2>&1 && for /f "delims=" %%I in ('where ffprobe') do (echo ffprobe: %%I & goto :fp_ok)
echo ffprobe: installe, actif au prochain demarrage (l Archiveur se debrouille d ici la).
:fp_ok
where ffplay >nul 2>&1 && for /f "delims=" %%I in ('where ffplay') do (echo ffplay : %%I & goto :fy_ok)
echo ffplay : pas encore visible, actif au prochain demarrage (optionnel).
:fy_ok
echo.

echo [4/8] Lecteur video externe optionnel (VLC / mpv ; l Archiveur 5 a deja son lecteur integre)...
set "PLAYER="
if exist "%ProgramFiles%\VideoLAN\VLC\vlc.exe" set "PLAYER=VLC (%ProgramFiles%\VideoLAN\VLC\vlc.exe)"
if not defined PLAYER if exist "%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe" set "PLAYER=VLC (%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe)"
if not defined PLAYER for /f "delims=" %%I in ('where mpv 2^>nul') do if not defined PLAYER set "PLAYER=mpv (%%I)"
if defined PLAYER (
  echo Lecteur detecte : !PLAYER! - choisissable dans Archiveur ^> Lecteur.
) else (
  echo Aucun VLC/mpv. L Archiveur lit les videos dans son lecteur integre ^(ffmpeg + ffplay^) et en MP4 H.264 lisible par le lecteur Windows.
  if defined PADAWAN_AUTO goto :vlc_done
  choice /C ON /N /D N /T 20 /M "Installer VLC (lit tous les formats) via winget ? [O/N, defaut N dans 20 s] : "
  if not errorlevel 2 (
    where winget >nul 2>&1
    if not errorlevel 1 (winget install -e --id VideoLAN.VLC --silent --accept-package-agreements --accept-source-agreements) else echo winget absent - VLC non installe.
  )
)
echo.

:vlc_done
echo.
echo [5/8] Ollama...
if defined PADAWAN_NOOLLAMA (echo   saute ^(non demande^) & goto :skip_pull)
where ollama >nul 2>&1
if errorlevel 1 (
  where winget >nul 2>&1
  if not errorlevel 1 (
    echo Installation Ollama via winget...
    winget install -e --id Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
  ) else echo winget absent - Ollama non installe.
) else echo Ollama deja present.
if exist "%LOCALAPPDATA%\Programs\Ollama" set "OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%_setup_path.ps1" -PythonDir "%PY_DIR%" -ScriptsDir "%PY_SCRIPTS%" -OllamaDir "%OLLAMA_DIR%" -RefreshFfmpeg
call :refresh_path
if defined PADAWAN_AUTO goto :skip_pull
choice /C ON /N /M "Telecharger le modele dolphin3:8b maintenant ? [O/N] : "
if errorlevel 2 goto :skip_pull
where ollama >nul 2>&1 && ollama pull dolphin3:8b
:skip_pull
echo.

echo [6/8] Raccourcis Bureau (toujours) : Padawan, Gestionnaire, Archiveur (archiveur5.py), Arsenal, Grimoire, Facteur...
if exist "%ROOT%arsenal1.py" if not exist "%ROOT%arsenal1.ico" "%PYTHON%" "%ROOT%arsenal1.py" --make-icons >nul 2>&1
if exist "%ROOT%grimoire1.py" if not exist "%ROOT%grimoire1.ico" "%PYTHON%" "%ROOT%grimoire1.py" --make-icons >nul 2>&1
if exist "%ROOT%facteur1.py" if not exist "%ROOT%facteur1.ico" "%PYTHON%" "%ROOT%facteur1.py" --make-icons >nul 2>&1
if exist "%ROOT%messager2.py" if not exist "%ROOT%messager2.ico" "%PYTHON%" "%ROOT%messager2.py" --make-icons >nul 2>&1
if exist "%ROOT%chantier1.py" if not exist "%ROOT%chantier1.ico" "%PYTHON%" "%ROOT%chantier1.py" --make-icons >nul 2>&1
if exist "%ROOT%retro1.py" if not exist "%ROOT%retro1.ico" "%PYTHON%" "%ROOT%retro1.py" --make-icons >nul 2>&1
if exist "%ROOT%journal_bord.py" if not exist "%ROOT%journal_bord.ico" "%PYTHON%" "%ROOT%journal_bord.py" --make-icons >nul 2>&1
set "SM_ARG="
if defined PADAWAN_STARTMENU set "SM_ARG=-StartMenu"
if defined PADAWAN_NOSYS (echo   saute ^(mode test^)) else powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%ROOT%_setup_shortcuts.ps1" -Root "%ROOT%." -PythonW "%PYTHONW%" %SM_ARG%
echo.

echo [7/8] Demarrage Windows (HKCU Run - toujours)...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if defined PADAWAN_NOSYS (echo   saute ^(mode test^) & goto :run_done)
if exist "%STARTUP%\Padawan.bat" del /f /q "%STARTUP%\Padawan.bat" & echo Legacy Startup\Padawan.bat supprime.
if exist "%STARTUP%\Padawan.lnk" del /f /q "%STARTUP%\Padawan.lnk"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%_setup_run.ps1" -PythonW "%PYTHONW%" -App "%ROOT%padawan39.py"
:run_done
echo.


echo [7b/8] Dossier donnees Facteur + scripts (sans secrets, sans cle)...
set "FACTEUR_DATA="
if exist "C:\web\FTP_HOME" set "FACTEUR_DATA=C:\web\FTP_HOME\FACTEUR"
if not defined FACTEUR_DATA if defined PADAWAN_DATA set "FACTEUR_DATA=%PADAWAN_DATA%\Facteur"
if not defined FACTEUR_DATA set "FACTEUR_DATA=%USERPROFILE%\Documents\Padawan\Facteur"
if not exist "%FACTEUR_DATA%" mkdir "%FACTEUR_DATA%" 2>nul
if not exist "%FACTEUR_DATA%\scripts" mkdir "%FACTEUR_DATA%\scripts" 2>nul
if not exist "%FACTEUR_DATA%\_Traites" mkdir "%FACTEUR_DATA%\_Traites" 2>nul
if not exist "%FACTEUR_DATA%\_Quarantaine" mkdir "%FACTEUR_DATA%\_Quarantaine" 2>nul
if exist "%ROOT%scripts\restart_xampp.cmd" copy /Y "%ROOT%scripts\restart_xampp.cmd" "%FACTEUR_DATA%\scripts\" >nul
if exist "%ROOT%scripts\backup_web.exemple.cmd" copy /Y "%ROOT%scripts\backup_web.exemple.cmd" "%FACTEUR_DATA%\scripts\" >nul
rem Ne JAMAIS copier facteur_config.json / facteur_cle* : Facteur cree sa propre cle DPAPI au 1er lancement.
rem boites_sql reste vide tant que l'utilisateur n'ajoute pas son pont.
echo   Donnees Facteur : %FACTEUR_DATA%
echo.
echo [8/8] Verification...
echo -------- RECAP --------
call :check_python
call :check_pip
call :check where ffmpeg
call :check where ffprobe
call :check where ffplay
call :check where ollama
call :check_ytdlp
call :check_mod PIL Pillow
call :check_mod plyer plyer
call :check_mod pystray pystray
call :check_mod requests requests
call :check_mod curl_cffi "curl_cffi [optionnel]"
call :check_mod bs4 "beautifulsoup4 (pages web)"
call :check_mod tkinterdnd2 "tkinterdnd2 (glisser-deposer)"
call :check_mod pypdf "pypdf (Grimoire : texte des PDF)"
call :check_mod sounddevice "sounddevice (Grimoire : memos vocaux)"
call :check_mod soundfile "soundfile (Grimoire : memos vocaux)"
call :check_mod watchdog "watchdog (Facteur : evenementiel)"
"%PYTHON%" -c "import faster_whisper" >nul 2>&1
if errorlevel 1 (echo   -- faster-whisper : non installe ^(optionnel, transcription locale^)) else (echo   OK faster-whisper ^(transcription locale^))
if defined PLAYER (echo   OK lecteur = !PLAYER!) else (
  if exist "%ProgramFiles%\VideoLAN\VLC\vlc.exe" (echo   OK lecteur = VLC) else (echo   -- lecteur VLC/mpv : aucun ^(optionnel, lecteur Windows utilise^))
)
echo.
echo Cle HKCU Run Padawan:
powershell.exe -NoProfile -Command "$v=(Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name Padawan -EA SilentlyContinue).Padawan; if($v){Write-Host ('  OK '+$v)}else{Write-Host '  MANQUANT'}"
if exist "%STARTUP%\Padawan.bat" (echo Startup\Padawan.bat: ENCORE PRESENT) else (echo Startup\Padawan.bat: OK absent)
echo Raccourci Bureau Archiveur:
powershell.exe -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Archiveur.lnk'; if(Test-Path $l){$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); Write-Host ('  OK '+$s.Arguments)}else{Write-Host '  MANQUANT'}"
echo Raccourci Bureau Arsenal:
powershell.exe -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Arsenal.lnk'; if(Test-Path $l){$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); Write-Host ('  OK '+$s.Arguments)}else{Write-Host '  MANQUANT'}"
echo Raccourci Bureau Grimoire:
powershell.exe -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Grimoire.lnk'; if(Test-Path $l){$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); Write-Host ('  OK '+$s.Arguments)}else{Write-Host '  MANQUANT'}"
echo Cle HKCU Run Facteur:
powershell.exe -NoProfile -Command "$v=(Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name Facteur -EA SilentlyContinue).Facteur; if($v){Write-Host ('  OK '+$v)}else{Write-Host '  absente (desactivee ou mode test)'}"
echo Raccourci Bureau Facteur:
powershell.exe -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Facteur.lnk'; if(Test-Path $l){$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); Write-Host ('  OK '+$s.Arguments)}else{Write-Host '  MANQUANT'}"
echo.
for %%F in (padawan39.py padawan_tray.py systemtray.py gestionnaire_fichiers5.py archiveur5.py arsenal1.py grimoire1.py facteur1.py messager2.py chantier1.py retro1.py journal_bord.py) do (
  if exist "%ROOT%%%F" (echo   OK %%F) else (echo   MANQUANT %%F)
)
echo ========================
echo.
echo Termine. Padawan n a pas ete lance par le setup.
if not defined PADAWAN_AUTO pause
exit /b 0

:refresh_path
for /f "usebackq delims=" %%P in (`powershell.exe -NoProfile -Command "$u=(Get-ItemProperty HKCU:\Environment -Name Path -EA SilentlyContinue).Path; $m=(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment' -Name Path -EA SilentlyContinue).Path; @($m,$u | Where-Object {$_}) -join ';'"`) do set "PATH=%%P"
goto :eof

:check
%* >nul 2>&1
if errorlevel 1 (
  echo   MANQUANT %2
  goto :eof
)
for /f "delims=" %%I in ('%* 2^>nul') do (
  echo   OK %2 = %%I
  goto :eof
)
goto :eof

:check_python
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (echo   MANQUANT python & goto :eof)
for /f "delims=" %%I in ('"%PYTHON%" --version') do echo   OK python = %PYTHON% [%%I]
goto :eof

:check_pip
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (echo   MANQUANT pip) else for /f "delims=" %%I in ('"%PYTHON%" -m pip --version') do echo   OK pip = %%I
goto :eof

:check_ytdlp
"%PYTHON%" -m yt_dlp --version >nul 2>&1
if errorlevel 1 (echo   MANQUANT yt-dlp & goto :eof)
for /f "delims=" %%I in ('"%PYTHON%" -m yt_dlp --version') do echo   OK yt-dlp = %%I
goto :eof

:check_mod
"%PYTHON%" -c "import %1" >nul 2>&1
set "LBL=%~2"
if errorlevel 1 (echo   MANQUANT !LBL!) else (echo   OK !LBL!)
goto :eof
