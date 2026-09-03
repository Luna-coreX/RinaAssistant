using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>Как настройка называется и в какой секции живёт.</summary>
public sealed record Labelled(string Key, string Title, string Hint = "");

/// <summary>Секция экрана настроек: заголовок и то, что в ней.</summary>
public sealed record Section(string Title, Labelled[] Keys);

/// <summary>
/// Раскладка экрана настроек — целиком забота оболочки.
/// </summary>
/// <remarks>
/// <para>
/// Это и есть [ADR 0006](../../../docs/adr/0006-settings-ownership.md) в
/// коде. Ядро отдаёт <b>смысл</b>: тип, умолчание, допустимые значения,
/// зависимости, предупреждения. Здесь лежит <b>вид</b>: подписи, порядок,
/// десять секций из <c>4.0-R04</c>.
/// </para>
/// <para>
/// Подписи не могут жить в ядре, потому что <c>4.0-F08</c> уже решил:
/// строки интерфейса — в оболочке, реплики Рины — в ядре. «Слова активации» —
/// строка интерфейса.
/// </para>
/// <para>
/// <b>Незнакомый ключ показывается, а не прячется.</b> Это правило с зубами
/// из того же решения: ядро заводит настройку, оболочку не обновляют, и
/// спрятанный ключ становится недостижимым, а заметить это нечем. Показанный
/// в общей секции — всего лишь некрасив, а некрасивое чинят.
/// </para>
/// </remarks>
public static class SettingsLayout
{
    /// <summary>Куда девать то, чего оболочка не знает.</summary>
    public static string Other => S("Прочее");

    public static readonly Section[] Sections =
    [
        new(S("Голос"),
        [
            new("tts_engine", S("Система синтеза")),
            new("stt_engine", S("Распознавание")),
            new("voice", S("Голос")),
            new("wake_words", S("Слова активации")),
            new("volume", S("Громкость")),
            new("speed", S("Скорость речи")),
        ]),
        new(S("Модели"),
        [
            new("whisper_model", S("Модель Whisper")),
            new("vosk_model", S("Модель Vosk")),
            new("piper_model", S("Модель Piper")),
            new("wake_sensitivity", S("Чувствительность активации")),
            new("listen_seconds", S("Длительность записи")),
        ]),
        new(S("Звук"),
        [
            new("input_device", S("Микрофон")),
            new("output_device", S("Динамик")),
            new("sound_effects", S("Звуковые эффекты")),
        ]),
        new(S("Программы"),
        [
            new("program_folders", S("Добавленные папки"),
                S("Portable-программы ищутся здесь")),
            new("app_aliases", S("Выученные соответствия")),
        ]),
        new(S("Поведение"),
        [
            new("autostart", S("Запускать при входе в систему")),
            new("minimize_to_tray", S("Сворачивать в трей")),
            new("start_minimized", S("Начинать свёрнутой")),
            new("floating_command_bar", S("Плавающая строка команд"),
                S("Поверх окон; вызывается сочетанием клавиш")),
            new("notifications", S("Уведомления"),
                S("Показывать ответы, когда окно скрыто")),
            new("hotkey", S("Основная комбинация")),
            new("action_hotkeys", S("Комбинации действий")),
        ]),
        new(S("Обновления"),
        [
            // Настройка есть, а обновлений ещё нет: подсказка говорит об
            // этом прямо. Переключатель без подсказки обещал бы поведение,
            // которого не будет до блока U.
            new("check_updates", S("Проверять обновления"),
                S("Появится вместе с обновлениями")),
        ]),
        new(S("ИИ"),
        [
            new("llm_enabled", S("Отвечать моделью")),
            new("llm_url", S("Адрес модели")),
            new("llm_model", S("Название модели")),
            new("llm_persona", S("Характер")),
            new("llm_timeout", S("Сколько ждать ответа, секунд")),
        ]),
        new(S("Поиск"),
        [
            new("search_engine", S("Поисковая система")),
            new("web_search_fallback", S("Искать нераспознанное")),
        ]),
        new(S("Внешний вид"),
        [
            new("finish", S("Отделка")),
            new("ui_language", S("Язык интерфейса")),
        ]),
        new(S("Приватность"),
        [
            new("save_history", S("Сохранять историю")),
            new("log_texts", S("Записывать тексты реплик")),
            new("log_level", S("Подробность журнала")),
        ]),
    ];

    /// <summary>
    /// Настройки, которые оболочка показывает не здесь.
    /// </summary>
    /// <remarks>
    /// «Отвечать голосом» и «всегда слушать» стоят у строки ввода
    /// (<c>4.0-R04</c>): это не настройка, а режим работы прибора, и
    /// переключают его в процессе разговора. Они не «неизвестные» — они
    /// известны и показаны в другом месте, и правило про незнакомый ключ к
    /// ним не относится.
    /// </remarks>
    public static readonly HashSet<string> Elsewhere =
    [
        "voice_reply",
        "always_listen",
    ];

    /// <summary>
    /// Ключи, чей список значений знает оболочка, а не ядро.
    /// </summary>
    /// <remarks>
    /// Устройства ввода и вывода — свойство звуковой подсистемы, а она в 4.0
    /// принадлежит оболочке (<c>4.0-F09</c>). Ядро их не видит вовсе и
    /// перечислить не может; оно лишь хранит выбранное имя. Это не исключение
    /// из [ADR 0006](../../../docs/adr/0006-settings-ownership.md), а его
    /// прямое следствие: смысл у того, кто знает.
    /// </remarks>
    public static readonly HashSet<string> ShellKnows =
    [
        "input_device",
        "output_device",
    ];

    /// <summary>
    /// Как называется «стереть всё» для конкретного ключа.
    /// </summary>
    /// <remarks>
    /// Выученные соответствия <b>забывают</b>, назначенные сочетания
    /// <b>сбрасывают</b>. Одно слово на оба случая было бы неправдой в
    /// одном из них: забытое Рина выучит заново сама, сброшенное придётся
    /// назначать руками.
    /// </remarks>
    public static string ClearWordOf(string key) => key switch
    {
        "app_aliases" => S("Забыть все"),
        "action_hotkeys" => S("Сбросить все"),
        _ => S("Очистить"),
    };

    /// <summary>Все ключи, которые оболочка знает по имени.</summary>
    public static readonly HashSet<string> Known =
        Sections.SelectMany(s => s.Keys).Select(k => k.Key).ToHashSet();

    public static string TitleOf(string key) =>
        Sections.SelectMany(s => s.Keys).FirstOrDefault(k => k.Key == key)?.Title
        ?? key;

    public static string HintOf(string key) =>
        Sections.SelectMany(s => s.Keys).FirstOrDefault(k => k.Key == key)?.Hint
        ?? "";
}
