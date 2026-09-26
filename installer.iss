[Setup]
AppName=Rave Mode
AppVersion=2.1
DefaultDirName={autopf}\RaveMode
DefaultGroupName=Rave Mode
OutputDir=dist
OutputBaseFilename=RaveMode_Installer
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
SetupIconFile=ui\icon.ico

[Files]
Source: "dist\RaveMode.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ui\icon.ico"; DestDir: "{app}\ui"; Flags: ignoreversion

[Icons]
Name: "{group}\Rave Mode"; Filename: "{app}\RaveMode.exe"; IconFilename: "{app}\ui\icon.ico"
Name: "{autodesktop}\Rave Mode"; Filename: "{app}\RaveMode.exe"; Tasks: desktopicon; IconFilename: "{app}\ui\icon.ico"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
