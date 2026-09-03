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
            ["Новый шаг"] =
                new Dictionary<string, string>
                {
                    ["English"] = "New step",
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
            ["Сколько ждать ответа, секунд"] =
                new Dictionary<string, string>
                {
                    ["English"] = "How long to wait for an answer, seconds",
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
            ["Таймер"] =
                new Dictionary<string, string>
                {
                    ["Deutsch"] = "Timer",
                    ["English"] = "Timer",
                    ["Español"] = "Temporizador",
                    ["Українська"] = "Таймер",
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
            ["Цвет, которым Рина выделяет важное"] =
                new Dictionary<string, string>
                {
                    ["English"] = "The colour Rina highlights with",
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
            ["Что произнести"] =
                new Dictionary<string, string>
                {
                    ["English"] = "What to say out loud",
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
        };
}
