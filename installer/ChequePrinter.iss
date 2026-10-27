; Inno Setup script — ChequePrinterSetup.exe
; Build (after PyInstaller):  iscc /DMyAppVersion=1.1.2 installer\ChequePrinter.iss
; - installs to Program Files\ChequePrinter, Start-menu and desktop shortcuts
; - creates the shared data folder %ProgramData%\ChequePrinter writable by every user of the PC
; - an update installs over the old version; the data (database, templates, backups, licence) is never touched,
;   also not on uninstall
#ifndef MyAppVersion
  #define MyAppVersion "1.1.2"
#endif
#define MyAppName "ChequePrinter"
#define MyAppPublisher "AcsVe"
#define MyAppExe "ChequePrinter.exe"

[Setup]
AppId={{6C1B2E52-8F4D-4C8E-9C1A-3D7A5E2B9F10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ChequePrinterSetup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Arabic.isl")
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Dirs]
Name: "{commonappdata}\ChequePrinter"; Permissions: users-modify
Name: "{commonappdata}\ChequePrinter\backups"; Permissions: users-modify

[Files]
Source: "..\dist\ChequePrinter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
