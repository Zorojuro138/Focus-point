#define AppName "FocusPilot"
#define AppVersion "0.1.0"

[Setup]
AppId={{AAFD3228-4A34-4F88-9D87-1A5111C5C6A0}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\FocusPilot
DefaultGroupName=FocusPilot
OutputDir=..\dist\installer
OutputBaseFilename=FocusPilot-Setup
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\FocusPilot.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "autostart"; Description: "Start FocusPilot when I sign in to Windows"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\FocusPilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FocusPilot"; Filename: "{app}\FocusPilot.exe"
Name: "{autodesktop}\FocusPilot"; Filename: "{app}\FocusPilot.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "FocusPilot"; ValueData: """{app}\FocusPilot.exe"" --autostart"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\FocusPilot.exe"; Description: "Launch FocusPilot"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    if MsgBox('Would you also like to permanently delete FocusPilot data stored on this PC?',
      mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\FocusPilot'), True, True, True);
end;
