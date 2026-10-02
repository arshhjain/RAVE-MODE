[Setup]
AppName=Rave Mode Dev Tools
AppVersion=2.2.0
DefaultDirName={autopf}\RaveModeDev
DefaultGroupName=Rave Mode Dev Tools
OutputDir=dist
OutputBaseFilename=RaveMode_Dev_Installer
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
SetupIconFile=ui\icon.ico

[Files]
Source: "dist\RaveModeDev.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ui\icon.ico"; DestDir: "{app}\ui"; Flags: ignoreversion

[Icons]
Name: "{group}\Rave Mode Dev Tools"; Filename: "{app}\RaveModeDev.exe"; IconFilename: "{app}\ui\icon.ico"
Name: "{autodesktop}\Rave Mode Dev Tools"; Filename: "{app}\RaveModeDev.exe"; Tasks: desktopicon; IconFilename: "{app}\ui\icon.ico"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
