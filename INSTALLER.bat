@echo off
rem Installe le Projet Padawan (Padawan, tray, Gestionnaire, Archiveur, Arsenal, Grimoire, Facteur, Messager)
rem Options : /test (aucun changement systeme)  ou n importe quelle option de installer_padawan.ps1
cd /d "%~dp0"
if /i "%~1"=="/test" (powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer_padawan.ps1" -Test -InstallDir "%~2" & exit /b)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer_padawan.ps1" %*
