; Inno Setup script for Shani Pharmacy Management System.
; Builds a single Setup.exe that installs the app, adds a Start Menu entry
; (searchable via Windows Search) and an optional Desktop shortcut, and
; registers a proper uninstaller in "Add or Remove Programs".
;
; Installs per-machine under Program Files (standard Windows convention --
; the target path resolution here is the most consistent/predictable across
; different PCs). Requires a one-time admin/UAC confirmation at install time,
; which is normal for desktop software and typical shop PCs are run as local
; admin anyway.

#define MyAppName "Shani Pharmacy Management System"
#define MyAppVersion "1.0"
#define MyAppPublisher "Shani Pharmacy Management System"
#define MyAppExeName "PharmacyManagementSystem.exe"

; The real install password is never committed to source control -- it's
; passed in at build time with /DInstallerPassword="..." (see README). If
; nobody supplies one, this placeholder is used, so a build straight from
; a fresh checkout is intentionally NOT the real protected installer.
#ifndef InstallerPassword
  #define InstallerPassword "CHANGE_ME_AT_BUILD_TIME"
#endif

[Setup]
; Setup.exe won't proceed past the password prompt without this. Anyone
; who wants to install needs the password from the developer -- that's the
; point: distribute the same Setup.exe to every shop, but each install
; still requires contacting you first.
Password={#InstallerPassword}
Encryption=yes
AppId={{B9C1E7B4-2F3E-4C2A-9B3E-6D9B0B7A2F10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PharmacyManagementSystem
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=installer_output
OutputBaseFilename=PharmacyManagementSystem_Setup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\PharmacyManagementSystem.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
