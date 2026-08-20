#define MyAppVersion "0.1.0"

[Setup]
AppId={{C2BCB7D4-4B6D-4D10-AE44-9F2C6E3C9E1C}
AppName=NanoSense
AppVersion={#MyAppVersion}
AppPublisher=NanoSense
DefaultDirName={autopf}\NanoSense
DefaultGroupName=NanoSense
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=NanoSense-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\NanoSense.exe

[Files]
Source: "..\dist\NanoSense\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\NanoSense"; Filename: "{app}\NanoSense.exe"
Name: "{group}\NanoSense"; Filename: "{app}\NanoSense.exe"

[Run]
Filename: "{app}\NanoSense.exe"; Description: "Launch NanoSense"; Flags: nowait postinstall skipifsilent
