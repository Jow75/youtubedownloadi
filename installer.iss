; ============================================================================
;  installer.iss  —  Inno Setup script for Universal Media Downloader
;
;  Produces a single Setup.exe your customers double-click to install.
;  1) Install Inno Setup:  winget install JRSoftware.InnoSetup
;  2) Build the app first:  powershell -ExecutionPolicy Bypass -File build_exe.ps1
;  3) Compile this:         iscc installer.iss   (or open it in Inno Setup)
;  Output: Output\UniversalMediaDownloader-Setup.exe
; ============================================================================

[Setup]
AppName=Universal Media Downloader
AppVersion=4.2
AppPublisher=George (Jowgei)
AppPublisherURL=https://baziqhue.co.ke/
AppSupportURL=https://baziqhue.co.ke/
AppContact=phantomtyper.review@gmail.com
AppComments=Publisher: George (Jowgei), Kenya. Email phantomtyper.review@gmail.com / WhatsApp +254799553292
AppCopyright=Copyright (c) 2026 George (Jowgei)
DefaultDirName={autopf}\UniversalMediaDownloader
DefaultGroupName=Universal Media Downloader
DisableProgramGroupPage=yes
OutputBaseFilename=UniversalMediaDownloader-Setup
SetupIconFile=assets\umd.ico
UninstallDisplayIcon={app}\UMD.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Install per-user so no admin rights are required (easy to share).
PrivilegesRequired=lowest
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; The entire frozen app folder produced by build_exe.ps1 (includes bin\).
Source: "dist\UMD\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Universal Media Downloader"; Filename: "{app}\UMD.exe"
Name: "{autodesktop}\Universal Media Downloader"; Filename: "{app}\UMD.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\UMD.exe"; Description: "Launch Universal Media Downloader"; Flags: nowait postinstall skipifsilent
