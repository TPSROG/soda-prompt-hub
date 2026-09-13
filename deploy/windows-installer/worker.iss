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

[Setup]
AppId={{05E960F7-13CC-4383-8A57-06559F3CC409}
AppName=Soda Compute Worker
AppVersion={#ProductVersion}
AppPublisher=Soda
DefaultDirName={localappdata}\Programs\Soda Compute Worker
DefaultGroupName=Soda Compute Worker
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
OutputBaseFilename=Soda-Compute-Worker-{#ProductVersion}-Setup
UninstallDisplayIcon={app}\Soda Compute Worker.exe
VersionInfoVersion={#ProductVersion}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "{#PayloadRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebView2Bootstrapper}"; DestDir: "{tmp}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: deleteafterinstall

[Icons]
Name: "{group}\Soda Compute Worker"; Filename: "{app}\Soda Compute Worker.exe"
Name: "{autodesktop}\Soda Compute Worker"; Filename: "{app}\Soda Compute Worker.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "正在确认 WebView2 Runtime…"; Flags: waituntilterminated
Filename: "{app}\Soda Compute Worker.exe"; Description: "启动 Soda Compute Worker"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if not UninstallSilent then
      MsgBox('Soda Compute Worker 已卸载。你的 Worker 配置、日志和任务目录仍保留在用户数据目录。', mbInformation, MB_OK);
  end;
end;
