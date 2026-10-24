; Установщик WhoKey для Windows (Inno Setup 6). Собирается из папки dist\WhoKey,
; которую делает build_windows.py:
;     ISCC.exe /DAppVersion=1.2 installer.iss
; Ставит программу без прав администратора — в папку пользователя
; (%LOCALAPPDATA%\Programs\WhoKey), ярлык в «Пуске», по желанию — на Рабочем столе.
; Хранилище паролей лежит отдельно (%APPDATA%\EduPasswords) и при удалении
; программы НЕ удаляется.

#ifndef AppVersion
  #define AppVersion "1.2"
#endif

[Setup]
AppId={{8F3C2A51-6E2B-4C7D-9A0E-5B1D3F7A9C42}
AppName=WhoKey
AppVersion={#AppVersion}
AppPublisher=kichike
AppPublisherURL=https://github.com/kichike/whokey
DefaultDirName={autopf}\WhoKey
DefaultGroupName=WhoKey
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename=WhoKey Installer
SetupIconFile=gui\assets\WhoKey.ico
UninstallDisplayIcon={app}\WhoKey.exe
UninstallDisplayName=WhoKey
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\WhoKey\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\WhoKey"; Filename: "{app}\WhoKey.exe"
Name: "{autodesktop}\WhoKey"; Filename: "{app}\WhoKey.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WhoKey.exe"; Description: "{cm:LaunchProgram,WhoKey}"; Flags: nowait postinstall skipifsilent
