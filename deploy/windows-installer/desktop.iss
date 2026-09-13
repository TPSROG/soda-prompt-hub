#ifndef PayloadRoot
  #error PayloadRoot is required
#endif
#ifndef OutputRoot
  #error OutputRoot is required
#endif
#ifndef ProductVersion
  #error ProductVersion is required
#endif
#ifndef WebView2Bootstrapper
  #error WebView2Bootstrapper is required
#endif
#if !FileExists(PayloadRoot + "\runtime\git\cmd\git.exe") || !FileExists(PayloadRoot + "\GIT_RUNTIME.json")
  #error Desktop payload must include the pinned private Git runtime
#endif

[Setup]
AppId={{D85005E7-FC6D-47D4-9C08-AD92C2AD32D0}
AppName=Soda Prompt Hub
AppVersion={#ProductVersion}
AppPublisher=Soda
DefaultDirName={localappdata}\Programs\Soda Prompt Hub
DefaultGroupName=Soda Prompt Hub
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\desktop-ui\app-icon.ico
DisableWelcomePage=no
CloseApplications=yes
RestartApplications=no
OutputDir={#OutputRoot}
OutputBaseFilename=Soda-Prompt-Hub-Desktop-{#ProductVersion}-Setup
UninstallDisplayIcon={app}\Soda Prompt Hub.exe
VersionInfoVersion={#ProductVersion}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebView2Bootstrapper}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Soda Prompt Hub"; Filename: "{app}\Soda Prompt Hub.exe"
Name: "{autodesktop}\Soda Prompt Hub"; Filename: "{app}\Soda Prompt Hub.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "正在确认 WebView2 Runtime…"; Flags: waituntilterminated
Filename: "{app}\Soda Prompt Hub.exe"; Description: "启动 Soda Prompt Hub"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\core\src\prompt_hub\__pycache__"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UninstallSilent then
      MsgBox('Soda Prompt Hub 已卸载。你的资料库、数据库、日志和备份仍保留在用户数据目录。', mbInformation, MB_OK);
  end;
end;
