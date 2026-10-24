@echo off
rem Desinstalle le Projet Padawan (vos donnees sont gardees, sauf si vous le demandez)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstaller_padawan.ps1" %*
