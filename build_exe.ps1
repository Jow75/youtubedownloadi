# ============================================================================
#  build_exe.ps1  -  Freeze Universal Media Downloader into a Windows app.
#
#  Output:  dist\UMD\UMD.exe   (a folder you can zip or wrap with Inno Setup)
#
#  Prereqs (installed once):
#    pip install -r requirements.txt pyinstaller
#    winget install Gyan.FFmpeg aria2.aria2 OpenJS.NodeJS.LTS
#    python license_tool.py --init        # creates secret.key (kept private)
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

# 1) Make sure the bundled binaries exist (ffmpeg/ffprobe/aria2c/node).
#    A binary already pinned in bin\ is KEPT as-is (so a smaller "essentials"
#    ffmpeg you've dropped in there isn't overwritten by a bigger system build);
#    only missing ones are pulled from PATH.
$bin = Join-Path $PSScriptRoot "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null
foreach ($exe in @("ffmpeg","ffprobe","aria2c","node")) {
    $dst = Join-Path $bin "$exe.exe"
    if (Test-Path $dst) { continue }
    $src = (Get-Command $exe -ErrorAction SilentlyContinue).Source
    if ($src) { Copy-Item $src $dst -Force }
    else { throw "Missing required binary: $exe (install it, then re-run)." }
}

if (-not (Test-Path (Join-Path $PSScriptRoot "secret.key"))) {
    throw "secret.key not found. Run: python license_tool.py --init"
}

# 2) Freeze with PyInstaller.
Write-Host "Building (this takes a few minutes)..." -ForegroundColor Cyan
Remove-Item dist, build -Recurse -Force -ErrorAction SilentlyContinue
# --exclude-module drops heavy libs that are pulled in transitively but never
# imported at startup or used by this app (no charts/dataframes): numba/llvmlite
# (~100 MB), scipy (~70 MB), tensorflow, matplotlib. ~170 MB saved.
# IMPORTANT: do NOT exclude pyarrow/pandas/numpy/altair — Streamlit imports
# pandas (which imports pyarrow) on startup, and a half-removed pyarrow makes it
# crash with "module 'pyarrow' has no attribute '__version__'". Those stay.
# pywebview (native window) + pythonnet/clr (its Windows WebView2 backend) must
# be fully collected, or the frozen app can't open the window and falls back to
# a browser. The WebView2 runtime itself ships with Windows 10/11.
python -m PyInstaller desktop.py --name UMD --noconfirm --windowed `
    --collect-all streamlit `
    --collect-all yt_dlp `
    --collect-all yt_dlp_ejs `
    --collect-all altair `
    --collect-all webview `
    --collect-all clr_loader `
    --copy-metadata pywebview `
    --copy-metadata pythonnet `
    --hidden-import clr `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import webview.platforms.winforms `
    --copy-metadata streamlit `
    --exclude-module numba `
    --exclude-module llvmlite `
    --exclude-module scipy `
    --exclude-module tensorflow `
    --exclude-module matplotlib `
    --add-data "app.py;." `
    --add-data "downloader.py;." `
    --add-data "downloads.py;." `
    --add-data "licensing.py;." `
    --add-data "history.py;." `
    --add-data "secret.key;."

# 3) Drop the media binaries next to the exe (loaded onto PATH at runtime).
if (Test-Path "dist\UMD\UMD.exe") {
    Copy-Item $bin "dist\UMD\bin" -Recurse -Force
    Write-Host "`nBUILD OK -> dist\UMD\UMD.exe" -ForegroundColor Green
    Write-Host "Next: compile installer.iss with Inno Setup, or zip dist\UMD."
} else {
    throw "Build failed - UMD.exe was not produced."
}
