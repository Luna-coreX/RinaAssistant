// Порождено tools/gen_shell_strings.py. Руками не править.
//
// Источник: shell/Rina.Shell/Strings/interface.json
//
// Ключ — русская строка (4.0-F08, ADR 0007): непереведённое место
// показывает осмысленный оригинал, а не имя ключа и не пустоту.

namespace Rina.Shell.Strings;

public static partial class Loc
{
    /// <summary>Переводы: строка оригинала — язык — перевод.</summary>
    public static readonly IReadOnlyDictionary<string,
        IReadOnlyDictionary<string, string>> Table =
        new Dictionary<string, IReadOnlyDictionary<string, string>>
        {
            [" — необратимо"] =
                new Dictionary<string, string>
                {
                    ["English"] = " — irreversible",
                },
            ["19:30"] =
                new Dictionary<string, string>
                {
                    ["English"] = "19:30",
                },
            ["[слишком глубокая вложенность]"] =
                new Dictionary<string, string>
                {
                    ["English"] = "[nesting too deep]",
                },
            ["Enter — отправить, Esc — скрыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Enter — send, Esc — hide",
                },
            ["http://localhost:11434"] =
                new Dictionary<string, string>
                {
                    ["English"] = "http://localhost:11434",
                },
            ["Portable-программы ищутся здесь"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Portable apps are looked for here",
                },
            ["{0} — сейчас недоступно"] =
                new Dictionary<string, string>
                {
                    ["English"] = "{0} — unavailable right now",
                },
            ["«{0}» включён."] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}” is on.",
                },
            ["«{0}» выключен."] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}” is off.",
                },
            ["«{0}» занято другой программой"] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}” is taken by another program",
                },
            ["«{0}» не включился: {1}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}” didn’t start: {1}",
                },
            ["«{0}» сохранено."] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}” saved.",
                },
            ["«{0}»: не понял значение."] =
                new Dictionary<string, string>
                {
                    ["English"] = "“{0}”: didn’t understand the value.",
                },
            ["Адрес модели"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Model address",
                },
            ["Адрес модели. Не локальный означает, что разговоры уйдут наружу"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Model address. Non-local means conversations leave this machine",
                },
            ["Акцент"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Accent",
                },
            ["без имени"] =
                new Dictionary<string, string>
                {
                    ["English"] = "unnamed",
                },
            ["Будильник"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Wecker",
                    ["English"] = "Alarm",
                    ["Español"] = "Alarma",
                    ["Українська"] = "Будильник",
                },
            ["Быстрее ста — торопится, медленнее — растягивает"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Above 100 she hurries, below she drawls",
                },
            ["В файле не список команд."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The file isn’t a list of commands.",
                },
            ["версия {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "version {0}",
                },
            ["вид"] =
                new Dictionary<string, string>
                {
                    ["English"] = "look",
                },
            ["Внешний вид"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Darstellung",
                    ["English"] = "Appearance",
                    ["Español"] = "Apariencia",
                    ["Українська"] = "Зовнішній вигляд",
                },
            ["Время пишется как 19:30."] =
                new Dictionary<string, string>
                {
                    ["English"] = "Time is written like 19:30.",
                },
            ["Всегда доверять"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Always trust",
                },
            ["Всегда слушать"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Immer zuhören",
                    ["English"] = "Always listen",
                    ["Español"] = "Escuchar siempre",
                    ["Українська"] = "Завжди слухати",
                },
            ["Вся поверхность целиком: цвета проверены парами"] =
                new Dictionary<string, string>
                {
                    ["English"] = "The whole surface: colours verified in pairs",
                },
            ["Выберите файл модели"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Choose the model file",
                },
            ["выбирать не из чего"] =
                new Dictionary<string, string>
                {
                    ["English"] = "nothing to choose from",
                },
            ["Выгружено: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Exported: {0}",
                },
            ["Выйти"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Quit",
                },
            ["Выполнить"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Ausführen",
                    ["English"] = "Run",
                    ["Español"] = "Ejecutar",
                    ["Українська"] = "Виконати",
                },
            ["Выполняю…"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Working…",
                },
            ["Выученные соответствия"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Learned matches",
                },
            ["Где искать, когда Рина не поняла команду"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Where to search when Rina didn’t understand",
                },
            ["Где лежит модель"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Where the model lives",
                },
            ["Голос"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Stimme",
                    ["English"] = "Voice",
                    ["Español"] = "Voz",
                    ["Українська"] = "Голос",
                },
            ["Голоса зависят от выбранной системы синтеза"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Voices depend on the chosen synthesis engine",
                },
            ["Готово"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Done",
                },
            ["Громкость"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Lautstärke",
                    ["English"] = "Volume",
                    ["Español"] = "Volumen",
                    ["Українська"] = "Гучність",
                },
            ["Диалог"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Dialogue",
                },
            ["Динамик"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Lautsprecher",
                    ["English"] = "Speaker",
                    ["Español"] = "Altavoz",
                    ["Українська"] = "Динамік",
                },
            ["Длительность записи"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Aufnahmedauer",
                    ["English"] = "Recording length",
                    ["Español"] = "Duración de la grabación",
                    ["Українська"] = "Тривалість запису",
                },
            ["Добавить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Add",
                },
            ["Добавить папку…"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Ordner hinzufügen…",
                    ["English"] = "Add folder…",
                    ["Español"] = "Añadir carpeta…",
                    ["Українська"] = "Додати теку…",
                },
            ["Добавить фразу"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Add a phrase",
                },
            ["Добавить шаг"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Schritt hinzufügen",
                    ["English"] = "Add step",
                    ["Español"] = "Añadir paso",
                    ["Українська"] = "Додати крок",
                },
            ["Добавленные папки"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Added folders",
                },
            ["Добавлено {0}, пропущено как уже известные {1}."] =
                new Dictionary<string, string>
                {
                    ["English"] = "Added {0}, skipped {1} already known.",
                },
            ["Если не ответить, действие не выполнится."] =
                new Dictionary<string, string>
                {
                    ["English"] = "If you don’t answer, nothing happens.",
                },
            ["Жду"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Waiting",
                },
            ["Забыть"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Vergessen",
                    ["English"] = "Forget",
                    ["Español"] = "Olvidar",
                    ["Українська"] = "Забути",
                },
            ["Забыть все"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Alle vergessen",
                    ["English"] = "Forget all",
                    ["Español"] = "Olvidar todo",
                    ["Українська"] = "Забути все",
                },
            ["завтра в это же время"] =
                new Dictionary<string, string>
                {
                    ["English"] = "tomorrow at this time",
                },
            ["Закрыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Close",
                },
            ["Записать"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Record",
                },
            ["записей: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "entries: {0}",
                },
            ["Записывать тексты реплик"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Nachrichtentexte protokollieren",
                    ["English"] = "Log message texts",
                    ["Español"] = "Registrar el texto de los mensajes",
                    ["Українська"] = "Записувати тексти реплік",
                },
            ["Записывать тексты реплик в журнал. По умолчанию выключено"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Write reply texts to the log. Off by default",
                },
            ["ЗАПЛАНИРОВАНО"] =
                new Dictionary<string, string>
                {
                    ["English"] = "SCHEDULED",
                },
            ["ЗАПЛАНИРОВАНО · {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "SCHEDULED · {0}",
                },
            ["Запуск без подписи"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Launching without a signature",
                },
            ["Запускать при входе в систему"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Start when you sign in",
                },
            ["Запускаться сразу в трее, без окна"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Start in the tray, without a window",
                },
            ["Запустить один раз"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Run once",
                },
            ["Звук"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Audio",
                },
            ["Звуковые эффекты"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Soundeffekte",
                    ["English"] = "Sound effects",
                    ["Español"] = "Efectos de sonido",
                    ["Українська"] = "Звукові ефекти",
                },
            ["ИИ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "AI",
                },
            ["или ко времени"] =
                new Dictionary<string, string>
                {
                    ["English"] = "or at a time",
                },
            ["Импорт"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Importieren",
                    ["English"] = "Import",
                    ["Español"] = "Importar",
                    ["Українська"] = "Імпорт",
                },
            ["Имя модели на этом сервере"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Model name on that server",
                },
            ["Искать нераспознанное"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Search unrecognized commands",
                },
            ["Источник неизвестен"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Source unknown",
                },
            ["Источник: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Source: {0}",
                },
            ["Каким характером модель отвечает"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What character the model answers with",
                },
            ["Какое действие"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Which action",
                },
            ["Какой адрес открыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Which address to open",
                },
            ["Какой микрофон слушать"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Which microphone to listen to",
                },
            ["Какую папку открыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Which folder to open",
                },
            ["Какую программу открыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Which program to open",
                },
            ["ключ {0} оболочке незнаком"] =
                new Dictionary<string, string>
                {
                    ["English"] = "key {0} is unknown to the shell",
                },
            ["Команда сохранена."] =
                new Dictionary<string, string>
                {
                    ["English"] = "Command saved.",
                },
            ["Команды"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Befehle",
                    ["English"] = "Commands",
                    ["Español"] = "Comandos",
                    ["Українська"] = "Команди",
                },
            ["Команды Рины (*.json)|*.json"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Rina commands (*.json)|*.json",
                },
            ["Комбинации действий"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Action shortcuts",
                },
            ["Короткий сигнал, когда Рина услышала и когда ответила"] =
                new Dictionary<string, string>
                {
                    ["English"] = "A short sound when Rina hears you and when she answers",
                },
            ["Крестик прячет окно, а не выходит из программы"] =
                new Dictionary<string, string>
                {
                    ["English"] = "The close button hides the window instead of quitting",
                },
            ["Крупнее — точнее и медленнее"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Larger is more accurate and slower",
                },
            ["Куда говорить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Where to speak",
                },
            ["Микрофон"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Mikrofon",
                    ["English"] = "Microphone",
                    ["Español"] = "Micrófono",
                    ["Українська"] = "Мікрофон",
                },
            ["Модели"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Models",
                },
            ["Модели (*.onnx;*.bin;*.pt)|*.onnx;*.bin;*.pt|Все файлы|*.*"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Models (*.onnx;*.bin;*.pt)|*.onnx;*.bin;*.pt|All files|*.*",
                },
            ["Модель Piper"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Piper model",
                },
            ["Модель Vosk"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Vosk model",
                },
            ["Модель Whisper"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Whisper model",
                },
            ["МОИ КОМАНДЫ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "MY COMMANDS",
                },
            ["МОИ КОМАНДЫ · {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "MY COMMANDS · {0}",
                },
            ["нажмите сочетание…"] =
                new Dictionary<string, string>
                {
                    ["English"] = "press a combination…",
                },
            ["Название модели"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Model name",
                },
            ["Напоминание"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Erinnerung",
                    ["English"] = "Reminder",
                    ["Español"] = "Recordatorio",
                    ["Українська"] = "Нагадування",
                },
            ["Напоминания"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Erinnerungen",
                    ["English"] = "Reminders",
                    ["Español"] = "Recordatorios",
                    ["Українська"] = "Нагадування",
                },
            ["Напомнить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Remind me",
                },
            ["Напомню {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "I’ll remind you {0}",
                },
            ["например, C:\\Program Files\\App\\app.exe"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, C:\\Program Files\\App\\app.exe",
                },
            ["например, D:\\Проекты"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, D:\\Projects",
                },
            ["например, github.com"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, github.com",
                },
            ["например, llama3"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, llama3",
                },
            ["например, «открой почту»"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, “open mail”",
                },
            ["например, отвечай коротко и по делу"] =
                new Dictionary<string, string>
                {
                    ["English"] = "for example, answer briefly and to the point",
                },
            ["Насколько громко Рина говорит"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How loudly Rina speaks",
                },
            ["Насколько подробен журнал"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How detailed the log is",
                },
            ["Настройки"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Einstellungen",
                    ["English"] = "Settings",
                    ["Español"] = "Ajustes",
                    ["Українська"] = "Налаштування",
                },
            ["Начинать свёрнутой"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Start minimised",
                },
            ["не назначено"] =
                new Dictionary<string, string>
                {
                    ["English"] = "not set",
                },
            ["Не прочиталось: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Couldn’t read it: {0}",
                },
            ["не разобрал сочетание «{0}»"] =
                new Dictionary<string, string>
                {
                    ["English"] = "couldn’t parse the shortcut “{0}”",
                },
            ["Непонятое уходит в поиск, а не остаётся без ответа"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What isn’t understood goes to search instead of nowhere",
                },
            ["Ниже — откликается чаще, но и на чужое тоже"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Lower means she responds more often — to other things too",
                },
            ["Никто не подтвердил, кто её выпустил и что её не подменяли."] =
                new Dictionary<string, string>
                {
                    ["English"] = "Nobody has confirmed who released it or that it wasn’t tampered with.",
                },
            ["Ничего не запланировано."] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Es ist nichts geplant.",
                    ["English"] = "Nothing is scheduled.",
                    ["Español"] = "No hay nada programado.",
                    ["Українська"] = "Нічого не заплановано.",
                },
            ["НОВАЯ КОМАНДА"] =
                new Dictionary<string, string>
                {
                    ["English"] = "NEW COMMAND",
                },
            ["Новая команда"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Neuer Befehl",
                    ["English"] = "New command",
                    ["Español"] = "Nuevo comando",
                    ["Українська"] = "Нова команда",
                },
            ["НОВОЕ НАПОМИНАНИЕ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "NEW REMINDER",
                },
            ["новое слово"] =
                new Dictionary<string, string>
                {
                    ["English"] = "new word",
                },
            ["Новый шаг"] =
                new Dictionary<string, string>
                {
                    ["English"] = "New step",
                },
            ["нужен Ctrl, Alt, Shift или Win"] =
                new Dictionary<string, string>
                {
                    ["English"] = "needs Ctrl, Alt, Shift or Win",
                },
            ["Нужен хотя бы один шаг."] =
                new Dictionary<string, string>
                {
                    ["English"] = "At least one step is needed.",
                },
            ["Нужна хотя бы одна фраза."] =
                new Dictionary<string, string>
                {
                    ["English"] = "At least one phrase is needed.",
                },
            ["Нужно указать, что делать."] =
                new Dictionary<string, string>
                {
                    ["English"] = "You need to say what to do.",
                },
            ["о программе"] =
                new Dictionary<string, string>
                {
                    ["English"] = "about",
                },
            ["о чём напомнить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "what to remind about",
                },
            ["О чём напомнить?"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What should I remind you about?",
                },
            ["Обзор…"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Durchsuchen…",
                    ["English"] = "Browse…",
                    ["Español"] = "Examinar…",
                    ["Українська"] = "Огляд…",
                },
            ["Обновления"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Updates",
                },
            ["оболочка не знает такого элемента страницы"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the shell doesn’t know this page element",
                },
            ["Основная комбинация"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Main shortcut",
                },
            ["Отвечать голосом"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Mit Stimme antworten",
                    ["English"] = "Reply with voice",
                    ["Español"] = "Responder con voz",
                    ["Українська"] = "Відповідати голосом",
                },
            ["Отвечать моделью"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Answer with a model",
                },
            ["Отвечать языковой моделью, когда команда не распознана"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Answer with a language model when a command isn’t recognised",
                },
            ["Отделка"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Finish",
                },
            ["Открыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Open",
                },
            ["Откуда взять команды"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Where to take commands from",
                },
            ["Отмена"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Abbrechen",
                    ["English"] = "Cancel",
                    ["Español"] = "Cancelar",
                    ["Українська"] = "Скасувати",
                },
            ["Отменить"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Abbrechen",
                    ["English"] = "Cancel",
                    ["Español"] = "Cancelar",
                    ["Українська"] = "Скасувати",
                },
            ["Отправить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Send",
                },
            ["Отправлено"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Sent",
                },
            ["Очистить"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Clear",
                },
            ["папка с моделью"] =
                new Dictionary<string, string>
                {
                    ["English"] = "folder with the model",
                },
            ["Папка с распакованной моделью Vosk"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Folder with the unpacked Vosk model",
                },
            ["Плавающая строка команд"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Schwebende Befehlszeile",
                    ["English"] = "Floating command bar",
                    ["Español"] = "Barra de comandos flotante",
                    ["Українська"] = "Плаваючий рядок команд",
                },
            ["плагин не загрузился"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the plugin didn’t load",
                },
            ["Плагинов пока нет."] =
                new Dictionary<string, string>
                {
                    ["English"] = "No plugins yet.",
                },
            ["Плагины"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Plug-ins",
                    ["English"] = "Plugins",
                    ["Español"] = "Complementos",
                    ["Українська"] = "Плагіни",
                },
            ["Поведение"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Verhalten",
                    ["English"] = "Behavior",
                    ["Español"] = "Comportamiento",
                    ["Українська"] = "Поведінка",
                },
            ["Поверх окон; вызывается сочетанием клавиш"] =
                new Dictionary<string, string>
                {
                    ["English"] = "On top of other windows; opened by a shortcut",
                },
            ["Подробность журнала"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Protokolldetails",
                    ["English"] = "Log detail",
                    ["Español"] = "Detalle del registro",
                    ["Українська"] = "Докладність журналу",
                },
            ["Подтверждение"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Confirmation",
                },
            ["Поиск"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Search",
                },
            ["Поисковая система"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Search engine",
                },
            ["Пока ни одного шага. Добавьте первый — он выполнится первым."] =
                new Dictionary<string, string>
                {
                    ["English"] = "No steps yet. Add the first one — it runs first.",
                },
            ["Показать"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Show",
                },
            ["Показать окно и начать слушать"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Show the window and start listening",
                },
            ["Показывать ответы, когда окно скрыто"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Show answers when the window is hidden",
                },
            ["Последовательность · шагов {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Sequence · {0} steps",
                },
            ["Появится вместе с обновлениями"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Arrives together with updates",
                },
            ["Править"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Edit",
                },
            ["ПРАВКА КОМАНДЫ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "EDITING A COMMAND",
                },
            ["Приватность"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Datenschutz",
                    ["English"] = "Privacy",
                    ["Español"] = "Privacidad",
                    ["Українська"] = "Приватність",
                },
            ["применится после перезапуска"] =
                new Dictionary<string, string>
                {
                    ["English"] = "applies after a restart",
                },
            ["Проверять обновления"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Nach Updates suchen",
                    ["English"] = "Check for updates",
                    ["Español"] = "Buscar actualizaciones",
                    ["Українська"] = "Перевіряти оновлення",
                },
            ["Программы"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Programme",
                    ["English"] = "Programs",
                    ["Español"] = "Programas",
                    ["Українська"] = "Програми",
                },
            ["Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Programs (*.exe;*.lnk)|*.exe;*.lnk|All files|*.*",
                },
            ["Прочее"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Other",
                },
            ["Развернуть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Maximise",
                },
            ["Разговор выгружен: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Conversation exported: {0}",
                },
            ["Раздел появится в 4.0-F04."] =
                new Dictionary<string, string>
                {
                    ["English"] = "This section arrives in 4.0-F04.",
                },
            ["Распознавание"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Recognition",
                },
            ["Рина"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Rina",
                    ["English"] = "Rina",
                    ["Español"] = "Rina",
                    ["Українська"] = "Ріна",
                },
            ["Рина будет запускаться сама при входе в систему"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Rina will start by herself when you sign in",
                },
            ["Рина скажет это вместо «Готово»"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Rina will say this instead of “Done”",
                },
            ["С этих слов начинается обращение к Рине"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Words that start an address to Rina",
                },
            ["Сбросить все"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Reset all",
                },
            ["Свернуть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Minimise",
                },
            ["Своих команд пока нет."] =
                new Dictionary<string, string>
                {
                    ["English"] = "No commands of your own yet.",
                },
            ["Сворачивать в трей"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "In den Infobereich minimieren",
                    ["English"] = "Minimize to tray",
                    ["Español"] = "Minimizar a la bandeja",
                    ["Українська"] = "Згортати в трей",
                },
            ["связь потеряна, поднимаем"] =
                new Dictionary<string, string>
                {
                    ["English"] = "connection lost, bringing it back",
                },
            ["сейчас"] =
                new Dictionary<string, string>
                {
                    ["English"] = "now",
                },
            ["Серебро или чёрное"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Silver or black",
                },
            ["Система синтеза"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Synthesis engine",
                },
            ["Скажите или напишите: «запусти браузер»"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Say or type: “open the browser”",
                },
            ["Сколько ждать ответа, прежде чем сдаться"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How long to wait for an answer before giving up",
                },
            ["Сколько ждать ответа, секунд"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How long to wait for an answer, seconds",
                },
            ["Сколько ждать фразу после обращения"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How long to wait for the phrase after being addressed",
                },
            ["Скорость речи"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Sprechgeschwindigkeit",
                    ["English"] = "Speech rate",
                    ["Español"] = "Velocidad del habla",
                    ["Українська"] = "Швидкість мовлення",
                },
            ["Скрыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Hide",
                },
            ["Слова активации"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Aktivierungswörter",
                    ["English"] = "Wake words",
                    ["Español"] = "Palabras de activación",
                    ["Українська"] = "Слова активації",
                },
            ["Сохранить"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Speichern",
                    ["English"] = "Save",
                    ["Español"] = "Guardar",
                    ["Українська"] = "Зберегти",
                },
            ["Сохранять историю"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Verlauf speichern",
                    ["English"] = "Save history",
                    ["Español"] = "Guardar historial",
                    ["Українська"] = "Зберігати історію",
                },
            ["Сочетания, назначенные отдельным действиям"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Combinations assigned to individual actions",
                },
            ["Таймер"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Timer",
                    ["English"] = "Timer",
                    ["Español"] = "Temporizador",
                    ["Українська"] = "Таймер",
                },
            ["такое сочетание не подойдёт"] =
                new Dictionary<string, string>
                {
                    ["English"] = "that combination won’t work",
                },
            ["Точно выполнить?"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Run it — are you sure?",
                },
            ["Убрать"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Entfernen",
                    ["English"] = "Remove",
                    ["Español"] = "Quitar",
                    ["Українська"] = "Прибрати",
                },
            ["Уведомления"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Benachrichtigungen",
                    ["English"] = "Notifications",
                    ["Español"] = "Notificaciones",
                    ["Українська"] = "Сповіщення",
                },
            ["Удалить"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Löschen",
                    ["English"] = "Delete",
                    ["Español"] = "Eliminar",
                    ["Українська"] = "Видалити",
                },
            ["УМЕЕТ СРАЗУ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "WORKS OUT OF THE BOX",
                },
            ["УМЕЕТ СРАЗУ · программ найдено: {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "WORKS OUT OF THE BOX · programs found: {0}",
                },
            ["УСТАНОВЛЕННЫЕ"] =
                new Dictionary<string, string>
                {
                    ["English"] = "INSTALLED",
                },
            ["УСТАНОВЛЕННЫЕ · {0}"] =
                new Dictionary<string, string>
                {
                    ["English"] = "INSTALLED · {0}",
                },
            ["Устройство по умолчанию"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Default device",
                },
            ["файл .onnx"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the .onnx file",
                },
            ["Файл модели .onnx"] =
                new Dictionary<string, string>
                {
                    ["English"] = "The .onnx model file",
                },
            ["Фразы, по которым сработает"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Phrases that trigger it",
                },
            ["Характер"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Persona",
                },
            ["Хранить переписку между запусками"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Keep the conversation between runs",
                },
            ["Цвет, которым Рина выделяет важное"] =
                new Dictionary<string, string>
                {
                    ["English"] = "The colour Rina highlights with",
                },
            ["Чем Рина говорит. Офлайновые работают без интернета"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How Rina speaks. Offline engines work without the internet",
                },
            ["Чем Рина слышит. Без него команды только с клавиатуры"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How Rina hears. Without it, commands are typed only",
                },
            ["через 15 минут"] =
                new Dictionary<string, string>
                {
                    ["English"] = "in 15 minutes",
                },
            ["через 3 часа"] =
                new Dictionary<string, string>
                {
                    ["English"] = "in 3 hours",
                },
            ["через 30 минут"] =
                new Dictionary<string, string>
                {
                    ["English"] = "in 30 minutes",
                },
            ["через 5 минут"] =
                new Dictionary<string, string>
                {
                    ["English"] = "in 5 minutes",
                },
            ["через час"] =
                new Dictionary<string, string>
                {
                    ["English"] = "in an hour",
                },
            ["Что ответить (необязательно)"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What to answer (optional)",
                },
            ["Что открыть"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What to open",
                },
            ["что открыть или произнести"] =
                new Dictionary<string, string>
                {
                    ["English"] = "what to open or say",
                },
            ["Что произнести"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What to say out loud",
                },
            ["что произнести"] =
                new Dictionary<string, string>
                {
                    ["English"] = "what to say",
                },
            ["Что Рина запомнила: какое слово какую программу означает"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What Rina learned: which word means which program",
                },
            ["Что сделать"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What to do",
                },
            ["Чувствительность активации"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Aktivierungsempfindlichkeit",
                    ["English"] = "Wake word sensitivity",
                    ["Español"] = "Sensibilidad de activación",
                    ["Українська"] = "Чутливість активації",
                },
            ["Шаги по порядку"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Steps in order",
                },
            ["Шагу нужно указать, что делать."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The step needs something to do.",
                },
            ["Экспорт"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Exportieren",
                    ["English"] = "Export",
                    ["Español"] = "Exportar",
                    ["Українська"] = "Експорт",
                },
            ["Эта программа не подписана"] =
                new Dictionary<string, string>
                {
                    ["English"] = "This program isn’t signed",
                },
            ["Это действие необратимо — Рина спросит подтверждение."] =
                new Dictionary<string, string>
                {
                    ["English"] = "This action is irreversible — Rina will ask for confirmation.",
                },
            ["ядро запускается"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the core is starting",
                },
            ["ядро на связи"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the core is online",
                },
            ["ядро не запускалось"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the core hasn’t been started",
                },
            ["Ядро не на связи — команды недоступны."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core is offline — commands are unavailable.",
                },
            ["Ядро не на связи — настройки недоступны."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core is offline — settings are unavailable.",
                },
            ["Ядро не на связи — плагины недоступны."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core is offline — plugins are unavailable.",
                },
            ["Ядро не на связи — разговор недоступен."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core is offline — the conversation is unavailable.",
                },
            ["Ядро не на связи — список недоступен."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core is offline — the list is unavailable.",
                },
            ["Ядро не объявило возможность «плагины»."] =
                new Dictionary<string, string>
                {
                    ["English"] = "The core didn’t declare the “plugins” capability.",
                },
            ["ядро не отвечает"] =
                new Dictionary<string, string>
                {
                    ["English"] = "the core isn’t responding",
                },
            ["Язык интерфейса"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Interface language",
                },
            ["Язык подписей в окне"] =
                new Dictionary<string, string>
                {
                    ["English"] = "Language of the labels in the window",
                },
        };
}
