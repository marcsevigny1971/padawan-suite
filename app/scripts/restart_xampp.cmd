@echo off
REM Redemarrage Apache + MySQL XAMPP (appele uniquement via Facteur admin)
cd /D C:\xampp
call apache_stop.bat
call mysql_stop.bat
ping -n 3 127.0.0.1 >nul
cscript //nologo "C:\xampp\start_apache_mysql_hidden.vbs"
exit /b 0
