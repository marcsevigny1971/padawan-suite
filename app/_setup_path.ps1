param(
  [string]$PythonDir = "",
  [string]$ScriptsDir = "",
  [string]$OllamaDir = "",
  [switch]$RefreshFfmpeg
)
$ErrorActionPreference = "Stop"

function Get-UserPath {
  $p = (Get-ItemProperty -Path "HKCU:\Environment" -Name Path -ErrorAction SilentlyContinue).Path
  if ($null -eq $p) { return "" }
  return [string]$p
}

function Find-FfmpegBin {
  $cands = @()
  $which = Get-Command ffmpeg -ErrorAction SilentlyContinue
  if ($which) { $cands += (Split-Path -Parent $which.Source) }
  $links = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"
  if (Test-Path (Join-Path $links "ffmpeg.exe")) { $cands += $links }
  $pkg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path $pkg) {
    Get-ChildItem $pkg -Directory -Filter "Gyan.FFmpeg*" -ErrorAction SilentlyContinue | ForEach-Object {
      Get-ChildItem $_.FullName -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object {
        $cands += $_.DirectoryName
      }
    }
  }
  $zipBin = Join-Path $env:LOCALAPPDATA "Archiveur\ffmpeg"
  if (Test-Path $zipBin) {
    Get-ChildItem $zipBin -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object {
      $cands += $_.DirectoryName
    }
  }
  foreach ($d in @("C:\ffmpeg\bin", "${env:ProgramFiles}\ffmpeg\bin")) {
    if (Test-Path (Join-Path $d "ffmpeg.exe")) { $cands += $d }
  }
  foreach ($d in $cands) {
    if ($d -and (Test-Path (Join-Path $d "ffmpeg.exe"))) { return $d }
  }
  return ""
}

function Add-ToUserPath([string[]]$Dirs) {
  $current = Get-UserPath
  $parts = @()
  if ($current) { $parts = @($current.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
  $changed = $false
  foreach ($d in $Dirs) {
    if (-not $d) { continue }
    if (-not (Test-Path $d)) { continue }
    $norm = [System.IO.Path]::GetFullPath($d).TrimEnd("\")
    $exists = $false
    foreach ($p in $parts) {
      if ([string]::Equals($p.TrimEnd("\"), $norm, [System.StringComparison]::OrdinalIgnoreCase)) { $exists = $true; break }
    }
    if (-not $exists) {
      $parts += $norm
      $changed = $true
      Write-Host "  + PATH: $norm"
    }
  }
  if ($changed) {
    $newPath = [string]::Join(";", $parts)
    Set-ItemProperty -Path "HKCU:\Environment" -Name Path -Value $newPath -Type ExpandString
  } else {
    Write-Host "  PATH deja a jour."
  }
  # Diffuser aux apps
  try {
    Add-Type -Namespace Win32 -Name Native -MemberDefinition @"
[DllImport("user32.dll", SetLastError=true, CharSet=CharSet.Auto)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
"@
    $HWND_BROADCAST = [IntPtr]0xffff
    $WM_SETTINGCHANGE = 0x1A
    $result = [UIntPtr]::Zero
    [Win32.Native]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [UIntPtr]::Zero, "Environment", 2, 5000, [ref]$result) | Out-Null
  } catch {}
}

$toAdd = @($PythonDir, $ScriptsDir, $OllamaDir)
if ($RefreshFfmpeg) {
  $ff = Find-FfmpegBin
  if ($ff) { $toAdd += $ff; Write-Host "  ffmpeg bin: $ff" }
}
Add-ToUserPath $toAdd
