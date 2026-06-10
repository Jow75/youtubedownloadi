# ============================================================================
#  build_admin_exe.ps1  -  Freeze the License Console into ONE clean exe.
#
#  Output:  dist\LicenseConsole.exe   (one-click, NO console window)
#
#  Prereqs:
#    pip install pyinstaller
#    python license_tool.py --init        # creates secret.key (kept PRIVATE)
#
#  SECURITY: the exe embeds secret.key so it can sign licenses. Keep it PRIVATE.
#  ASCII-only on purpose - Windows PowerShell 5.1 mis-parses non-ASCII .ps1.
# ============================================================================
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path (Join-Path $PSScriptRoot "secret.key"))) {
    throw "secret.key not found. Run: python license_tool.py --init"
}

Write-Host "Building License Console (about a minute)..." -ForegroundColor Cyan
Remove-Item dist\LicenseConsole, build\LicenseConsole -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item dist\LicenseConsole.exe -Force -ErrorAction SilentlyContinue

# admin_server / licensing / records are followed as imports automatically.
# pywebview + pythonnet/clr give it a native window (Windows WebView2).
python -m PyInstaller admin_app.py --name LicenseConsole --noconfirm --windowed --onefile `
    --icon "assets\umd.ico" `
    --version-file "version_admin.txt" `
    --collect-all webview `
    --collect-all clr_loader `
    --copy-metadata pywebview `
    --copy-metadata pythonnet `
    --hidden-import clr `
    --hidden-import webview.platforms.edgechromium `
    --hidden-import webview.platforms.winforms `
    --add-data "admin_ui.html;." `
    --add-data "secret.key;."

if (Test-Path "dist\LicenseConsole.exe") {
    $mb = [math]::Round((Get-Item "dist\LicenseConsole.exe").Length / 1MB, 1)
    Write-Host "`nBUILD OK -> dist\LicenseConsole.exe ($mb MB)" -ForegroundColor Green
    Write-Host "Double-click it to open the License Console. Keep it PRIVATE."
} else {
    throw "Build failed - LicenseConsole.exe was not produced."
}
