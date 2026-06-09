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
$bin = Join-Path $PSScriptRoot "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null
foreach ($exe in @("ffmpeg","ffprobe","aria2c","node")) {
    $src = (Get-Command $exe -ErrorAction SilentlyContinue).Source
    if ($src) { Copy-Item $src $bin -Force }
    elseif (-not (Test-Path (Join-Path $bin "$exe.exe"))) {
        throw "Missing required binary: $exe (install it, then re-run)."
    }
}

if (-not (Test-Path (Join-Path $PSScriptRoot "secret.key"))) {
    throw "secret.key not found. Run: python license_tool.py --init"
}

# 2) Freeze with PyInstaller.
Write-Host "Building (this takes a few minutes)..." -ForegroundColor Cyan
Remove-Item dist, build -Recurse -Force -ErrorAction SilentlyContinue
# --exclude-module drops a heavy scientific stack (numba/llvmlite/scipy/pyarrow/
# tensorflow/matplotlib) that Streamlit's data tooling pulls in transitively but
# this app never uses (no charts/dataframes) — together ~250 MB. If a future
# feature uses st.dataframe / st.*_chart, remove the matching excludes.
python -m PyInstaller desktop.py --name UMD --noconfirm --windowed `
    --collect-all streamlit `
    --collect-all yt_dlp `
    --collect-all yt_dlp_ejs `
    --copy-metadata streamlit `
    --exclude-module numba `
    --exclude-module llvmlite `
    --exclude-module scipy `
    --exclude-module pyarrow `
    --exclude-module tensorflow `
    --exclude-module matplotlib `
    --exclude-module altair `
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
