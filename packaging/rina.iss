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
; к системным папкам.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

LicenseFile=..\LICENSE
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

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
; Рантайм обзаводится __pycache__ и поставленными потом пакетами — того,
; чего в установке не было. Без этой строки после удаления остаётся папка
; с чужим мусором, и человек находит её через полгода.
; Одной этой строки не хватило, и выяснилось это только когда установщик
; впервые собрали и прогнали от установки до удаления: ядро лежит в
; {app}\core, {app}\voice, {app}\plugins, и Python пишет __pycache__
; рядом с ними, а не в runtime. После удаления оставалось 58 файлов.
;
; Поэтому не список папок, а вся {app}: точный список устаревает в тот
; день, когда в раскладке появляется новый пакет, и устаревает молча —
; ровно так, как устарел этот.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}"

; Настройки, история и команды НЕ удаляются намеренно: они в %APPDATA%, и
; переустановка не должна стирать годами накопленное. Удалить их — отдельное
; осознанное действие, как и «сбросить настройки» внутри программы.
