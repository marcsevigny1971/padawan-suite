# Lance un programme Padawan sans console avec le Python trouve par l'installation (python_path.txt)
param([Parameter(Mandatory=$true)][string]$Script, [string]$Arg = "")
$dir = $PSScriptRoot
$pyw = ""
$f = Join-Path $dir "python_path.txt"
if (Test-Path $f) { $pyw = (Get-Content $f -TotalCount 1).Trim() }
if (-not $pyw -or -not (Test-Path $pyw)) { $c = Get-Command pythonw.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1; if ($c) { $pyw = $c.Source } }
if (-not $pyw) { exit 1 }
$a = @('"' + (Join-Path $dir $Script) + '"'); if ($Arg) { $a += $Arg }
Start-Process -FilePath $pyw -ArgumentList $a -WorkingDirectory $dir
