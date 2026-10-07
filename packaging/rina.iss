; Установщик Рины 4.0 — задача плана 4.0-I01.
;
; Кладёт готовую раскладку из dist/Rina: оболочку, привезённый Python и
; ядро. Собирается так:
;
;     python tools/build_release.py
;     ISCC packaging/rina.iss
;
; Что установщик НЕ делает, и это решения, а не упущения:
;
;   * не трогает PATH и не регистрирует Python. Привезённый рантайм —
;     наш и только наш (ADR 0011); Python, попавший в PATH, начинает
;     отвечать на чужие вызовы и ломает то, что человек ставил сам;
;   * не просит прав администратора. Рина ставится в профиль
;     пользователя: ей не нужен доступ к системным папкам, а установщик,
;     просящий больше, чем ему надо, приучает соглашаться не глядя;
;   * не ставит службу и не прописывает автозапуск. Автозапуск — настройка
;     внутри программы, и включать его должен человек, а не установка.

; Версия приходит снаружи: `build_release.py` передаёт `/DAppVersion=`,
; прочитав её у ядра (`version.py`). Записанная здесь числом, она уже
; разошлась: ядро назвалось `4.0.0-beta`, а установщик остался
; `RinaAssistant-4.0.0-setup.exe` — то есть файл, который человек
; скачивает, врал о том, что внутри. Значение ниже — запасное, на
; случай сборки скрипта руками.
#define AppName "Rina Assistant"
#ifndef AppVersion
  #define AppVersion "0.0.0-неизвестно"
#endif
#define AppPublisher "NeuroSync Foundry"
#define AppURL "https://github.com/Luna-coreX/RinaAssistant"
#define AppExe "Rina.Shell.exe"
#define Payload "..\dist\Rina"

[Setup]
AppId={{8E4C1F2A-7B3D-4A9E-9C15-RINA40PORT001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\RinaAssistant
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=RinaAssistant-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; В профиль пользователя, без прав администратора: Рине не нужен доступ
; к системным папкам. И без выбора «для всех пользователей» (аудит
; 2026-10-07, M-7): в Program Files папка программы недоступна для записи,
; а Рина пишет в неё — пакеты, которые человек ставит потом в runtime,
; __pycache__ ядра. Установка там проходила, а потом это ломалось с
; непонятной ошибкой.
PrivilegesRequired=lowest

; Обновление ставится туда же, где стоит прежняя версия, не спрашивая.
UsePreviousAppDir=yes
DisableDirPage=auto
; В уже существующую папку — с предупреждением, а в непустую чужую — никак
; (см. [Code]): удаление программы убирает то, что лежит в её папке.
DirExistsWarning=auto

LicenseFile=..\LICENSE
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; Сфера Рины (4.0b-D06) — тот же файл, что у программы: скачанный
; установщик и то, что он ставит, выглядят одним и тем же.
SetupIconFile=..\assets\brand\rina.ico

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Вся раскладка целиком: оболочка, runtime\python, core, voice, plugins.
Source: "{#Payload}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Своё — то, что положила установка, — деинсталлятор убирает сам. Здесь —
; то, что появилось потом: пакеты, поставленные в runtime, и __pycache__,
; который Python пишет рядом с модулями ядра. Когда установщик впервые
; прогнали от установки до удаления, их осталось 58 файлов.
;
; Только эти папки, а не {app} целиком (аудит 2026-10-07, M-7). Вся {app}
; закрывала и новые пакеты раскладки, о которых забыли бы здесь, но
; удаляла и всё, что лежало в выбранной папке, — человек, поставивший Рину
; в D:\Tools, лишился бы при удалении всего D:\Tools. Новый пакет
; раскладки, забытый здесь, ловит `check_release.py --probe-install`:
; после удаления не должно остаться ни одного файла.
;
; {app}\plugins — не здесь, а в [Code]: до M-7 там лежали и плагины,
; которые ставил человек.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\voice"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: dirifempty; Name: "{app}"

; Настройки, история, команды и плагины человека НЕ удаляются намеренно:
; они в %APPDATA%, и переустановка не должна стирать годами накопленное.
; Удалить их — отдельное осознанное действие, как и «сбросить настройки»
; внутри программы.

[CustomMessages]
russian.ForeignFolder=В этой папке уже есть файлы, и это не Rina Assistant.%n%nПри удалении программа убирает то, что лежит в её папке, поэтому ставить её сюда нельзя. Выберите пустую или новую папку.
english.ForeignFolder=This folder already has files in it, and they are not Rina Assistant.%n%nUninstalling removes what is in the program's folder, so it cannot be installed here. Choose an empty or a new folder.

[Code]
// Rina's own folder: a previous install of it, which an update goes over.
function IsRinaFolder(const Dir: String): Boolean;
begin
  Result := FileExists(AddBackslash(Dir) + '{#AppExe}')
    or FileExists(AddBackslash(Dir) + 'unins000.exe');
end;

function IsEmptyFolder(const Dir: String): Boolean;
var
  Found: TFindRec;
begin
  Result := True;
  if FindFirst(AddBackslash(Dir) + '*', Found) then
  try
    repeat
      if (Found.Name <> '.') and (Found.Name <> '..') then
      begin
        Result := False;
        Break;
      end;
    until not FindNext(Found);
  finally
    FindClose(Found);
  end;
end;

// A folder with somebody else's files in it (M-7).
function IsForeignFolder(const Dir: String): Boolean;
begin
  Result := DirExists(Dir) and not IsEmptyFolder(Dir) and not IsRinaFolder(Dir);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and IsForeignFolder(WizardDirValue) then
  begin
    MsgBox(CustomMessage('ForeignFolder'), mbError, MB_OK);
    Result := False;
  end;
end;

// Again here, because a silent install with /DIR= never shows the page.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if IsForeignFolder(ExpandConstant('{app}')) then
    Result := CustomMessage('ForeignFolder');
end;

// Before M-7 a person's plugins were installed next to the shipped ones.
// The core moves them to the profile on start; for an update that was
// uninstalled without ever being started, it is done here. A folder that
// `shipped.json` (written by the build) does not name is the person's.
// True when nothing of theirs is left behind.
function KeepPersonsPlugins(): Boolean;
var
  Base, Target: String;
  Listed: AnsiString;
  Found: TFindRec;
begin
  Result := True;
  Base := ExpandConstant('{app}\plugins');
  if not LoadStringFromFile(Base + '\shipped.json', Listed) then
  begin
    // No list — nothing can be told apart, so nothing is deleted.
    Result := not DirExists(Base);
    Exit;
  end;
  Target := ExpandConstant('{userappdata}\RinaAssistant\plugins');
  if FindFirst(Base + '\*', Found) then
  try
    repeat
      if ((Found.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0)
        and (Found.Name <> '.') and (Found.Name <> '..')
        and FileExists(Base + '\' + Found.Name + '\plugin.json')
        and (Pos('"' + Found.Name + '"', String(Listed)) = 0) then
      begin
        ForceDirectories(Target);
        if DirExists(Target + '\' + Found.Name)
          or not RenameFile(Base + '\' + Found.Name, Target + '\' + Found.Name) then
          Result := False;
      end;
    until not FindNext(Found);
  finally
    FindClose(Found);
  end;
end;

var
  NothingOfTheirs: Boolean;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Before the files go: `shipped.json` is one of them.
  if CurUninstallStep = usUninstall then
    NothingOfTheirs := KeepPersonsPlugins();
  // The shipped plugins' __pycache__ goes only when nothing of the
  // person's is among them; otherwise the folder stays, and so does {app}.
  if (CurUninstallStep = usPostUninstall) and NothingOfTheirs then
  begin
    DelTree(ExpandConstant('{app}\plugins'), True, True, True);
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
