#define MyAppName "ECOQUILLA"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "ECOQUILLA SAS"
#define MyAppExeName "ECOQUILLA.exe"
#define MyAppIconName "ecoquilla.ico"
#define MyAppInstallerName "ECOQUILLA_Setup"
#define MyAppId "ECOQUILLA_APP"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Instalador de ECOQUILLA
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename={#MyAppInstallerName}
SetupIconFile=ecoquilla.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
#ifdef ENABLE_INNO_SIGNING
SignTool=enterprise
SignedUninstaller=yes
SignedUninstallerDir=installer
SignToolRunMinimized=yes
#endif

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\ECOQUILLA.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ecoquilla.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ECOQUILLA"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"
Name: "{group}\Desinstalar ECOQUILLA"; Filename: "{uninstallexe}"
Name: "{commondesktop}\ECOQUILLA"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIconName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir ECOQUILLA"; Flags: nowait postinstall skipifsilent
