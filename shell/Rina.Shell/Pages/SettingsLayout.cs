using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>What a setting is called and which section it lives in.</summary>
public sealed record Labelled(string Key, string Title, string Hint = "");

/// <summary>A section of the settings screen: a heading and what is in it.</summary>
public sealed record Section(string Title, Labelled[] Keys,
                            Sheet[]? Sheets = null);

/// <summary>
/// A group of settings that opens in a window of its own.
/// </summary>
/// <remarks>
/// <para>
/// For what is a **list** rather than a switch: the words Rina answers to,
/// the programs she has learned, the key combinations, the models. Such
/// things grow — a person adds a word, teaches an alias, downloads a model
/// — and a growing list on a shared page drowns everything below it. After
/// a year of use the page would be aliases with a few settings lost among
/// them.
/// </para>
/// <para>
/// A button on the page, the list in a window. The editors are the same
/// ones: what changed is where they are shown, not what they are.
/// </para>
/// </remarks>
public sealed record Sheet(string Title, string Note, string[] Keys,
                          Labelled[]? Named = null)
{
    /// <summary>
    /// What each key on this sheet is called.
    /// </summary>
    /// <remarks>
    /// A sheet of one key borrows the sheet's own title: the header
    /// already says «Слова активации», and repeating it on the row
    /// below said it twice — and said it as `wake_words`, because
    /// nothing else knew the name. A sheet of several needs one name
    /// each, and gives them in `Named`.
    /// </remarks>
    public Labelled Label(string key) =>
        Named?.FirstOrDefault(n => n.Key == key)
        ?? (Keys.Length == 1 ? new Labelled(key, Title, Note)
                             : new Labelled(key, key));
}

/// <summary>
/// The layout of the settings screen — entirely the shell's business.
/// </summary>
/// <remarks>
/// <para>
/// This is [ADR 0006](../../../docs/adr/0006-settings-ownership.md) in
/// code. The core hands over <b>meaning</b>: the type, the default, the
/// allowed values, the dependencies, the warnings. What lies here is
/// <b>appearance</b>: the labels, the order, the ten sections of
/// <c>4.0-R04</c>.
/// </para>
/// <para>
/// Labels cannot live in the core, because <c>4.0-F08</c> already decided
/// it: interface strings belong to the shell, Rina's lines to the core.
/// "Activation words" is an interface string.
/// </para>
/// <para>
/// <b>An unfamiliar key is shown, not hidden.</b> This is the rule with
/// teeth from that same decision: the core adds a setting, the shell is
/// not updated, and a hidden key becomes unreachable with nothing to
/// notice it by. Shown in the general section it is merely ugly, and what
/// is ugly gets fixed.
/// </para>
/// </remarks>
public static class SettingsLayout
{
    /// <summary>Where to put what the shell does not know.</summary>
    public static string Other => S("Прочее");

    /// <summary>
    /// The layout: keys, not translations.
    /// </summary>
    /// <remarks>
    /// <b>`Word` here, not `S`.</b> A static field is evaluated once — on
    /// the first use of the type — and remembers the language of that
    /// moment forever. Because of this, settings stayed Russian under an
    /// English interface: they were translated once and never asked again.
    /// Whoever draws is who translates: `TitleOf`, `HintOf` and the
    /// section heading.
    /// </remarks>
    public static readonly Section[] Sections =
    [
        new(Word("Голос и речь"),
        [
            new("tts_engine", Word("Система синтеза"),
                Word("Чем Рина говорит. Офлайновые работают без интернета")),
            new("voice", Word("Голос"),
                Word("Голоса зависят от выбранной системы синтеза")),
            new("volume", Word("Громкость"),
                Word("Насколько громко Рина говорит")),
            new("speed", Word("Скорость речи"),
                Word("Быстрее ста — торопится, медленнее — растягивает")),
            new("stt_engine", Word("Распознавание"),
                Word("Чем Рина слышит. Без него команды только с клавиатуры")),
            new("wake_sensitivity", Word("Чувствительность активации"),
                Word("Ниже — реже слышит имя, выше — чаще ошибается")),
            new("listen_seconds", Word("Длительность записи"),
                Word("Сколько секунд слушать после активации")),
        ],
        [
            new(Word("Слова активации"),
                Word("С этих слов начинается обращение к Рине"),
                ["wake_words"]),
            new(Word("Модели"),
                Word("Что скачано и где лежит"),
                ["whisper_model", "vosk_model", "piper_model"],
                [new("whisper_model", Word("Whisper"),
                     Word("Размер модели: чем больше, тем точнее и медленнее")),
                 new("vosk_model", Word("Vosk"),
                     Word("Папка с распакованной моделью")),
                 new("piper_model", Word("Голос Piper"),
                     Word("Файл голоса .onnx"))]),
        ]),
        new(Word("Звук"),
        [
            new("input_device", Word("Микрофон"),
                Word("Устройство, с которого Рина слышит")),
            new("output_device", Word("Динамик"),
                Word("Устройство, в которое Рина говорит")),
            new("sound_effects", Word("Звуковые эффекты"),
                Word("Короткие сигналы: услышала, ошиблась")),
        ]),
        new(Word("Программы"),
        [
            new("watch_apps", Word("Замечать, какие программы открыты"),
                Word("Нужно для напоминаний «когда открою…». Выключено по умолчанию")),
        ],
        [
            new(Word("Где искать программы"),
                Word("Папки, кроме тех, что Рина находит сама"),
                ["program_folders"]),
            new(Word("Выученные соответствия"),
                Word("Каким словом Рина зовёт какую программу"),
                ["app_aliases"]),
        ]),
        new(Word("Поведение"),
        [
            new("autostart", Word("Запускать при входе в систему"),
                Word("Рина будет готова сразу после входа")),
            new("minimize_to_tray", Word("Сворачивать в трей"),
                Word("Окно уходит в трей, а не на панель задач")),
            new("start_minimized", Word("Начинать свёрнутой"),
                Word("Запускаться без окна")),
            new("floating_command_bar", Word("Плавающая строка команд"),
                Word("Строка поверх экрана по горячей клавише")),
            new("notifications", Word("Уведомления"),
                Word("Показывать всплывающие сообщения")),
        ],
        [
            new(Word("Комбинации клавиш"),
                Word("Чем вызывать Рину и её действия"),
                ["hotkey", "action_hotkeys"],
                [new("hotkey", Word("Позвать Рину"),
                     Word("Одна комбинация на всё окно")),
                 new("action_hotkeys", Word("Отдельные действия"),
                     Word("Каждому своё сочетание"))]),
        ]),
        new(Word("ИИ"),
        [
            new("llm_enabled", Word("Отвечать моделью"),
                Word("Отвечать языковой моделью, когда команда не распознана")),
            new("llm_url", Word("Адрес модели"),
                Word("Адрес модели. Не локальный означает, что разговоры уйдут наружу")),
            new("llm_model", Word("Название модели"),
                Word("Имя модели на этом сервере")),
            new("llm_persona", Word("Характер"),
                Word("Каким характером модель отвечает")),
            new("llm_timeout", Word("Сколько ждать ответа, секунд"),
                Word("Дольше — терпеливее, но и молчание дольше")),
        ]),
        new(Word("Поиск"),
        [
            new("search_engine", Word("Поисковая система"),
                Word("Где искать по просьбе")),
            new("web_search_fallback", Word("Искать нераспознанное"),
                Word("Непонятую фразу отправлять в поиск")),
        ]),
        new(Word("Внешний вид"),
        [
            new("finish", Word("Отделка"),
                Word("Серебро, чёрный или графит — равноправные")),
            new("accent", Word("Акцент"),
                Word("Цвет, которым Рина обращает на себя внимание")),
            new("ui_language", Word("Язык интерфейса"),
                Word("Язык окна и реплик Рины")),
        ]),
        new(Word("Приватность"),
        [
            new("save_history", Word("Сохранять историю"),
                Word("Хранить, о чём был разговор")),
            new("log_texts", Word("Записывать тексты реплик"),
                Word("Записывать тексты реплик в журнал. По умолчанию выключено")),
            new("log_level", Word("Подробность журнала"),
                Word("Насколько подробен журнал")),
        ]),
        new(Word("Обновления"),
        [
            new("check_updates", Word("Проверять обновления"),
                Word("Появится вместе с обновлениями")),
        ]),
    ];

    public static readonly HashSet<string> Elsewhere =
    [
        "voice_reply",
        "always_listen",
    ];

    /// <summary>
    /// Keys whose list of values is known by the shell, not the core.
    /// </summary>
    /// <remarks>
    /// Input and output devices are a property of the audio subsystem, and
    /// in 4.0 that belongs to the shell (<c>4.0-F09</c>). The core does not
    /// see them at all and cannot enumerate them; it only stores the chosen
    /// name. This is not an exception to
    /// [ADR 0006](../../../docs/adr/0006-settings-ownership.md) but a
    /// direct consequence of it: meaning belongs to whoever knows.
    /// </remarks>
    public static readonly HashSet<string> ShellKnows =
    [
        "input_device",
        "output_device",
        // The set of accents depends on the finish, and the finish is the
        // shell's business: one and the same paint reads differently on
        // light and on dark.
        "accent",
    ];

    /// <summary>
    /// What to show in an empty settings field.
    /// </summary>
    /// <remarks>
    /// Not an explanation but an **example**: an explanation says what a
    /// setting is for, while a hint says in what form to write into it.
    /// "Model address" and "http://localhost:11434" answer different
    /// questions, and the second answer is needed at exactly the moment the
    /// field is empty.
    /// </remarks>
    public static string HintInField(string key) => key switch
    {
        "llm_url" => S("http://localhost:11434"),
        "llm_model" => S("например, llama3"),
        "llm_persona" => S("например, отвечай коротко и по делу"),
        "vosk_model" => S("папка с моделью"),
        "piper_model" => S("файл .onnx"),
        // There is deliberately no `wake_word` here. The core marks it
        // obsolete — it is 3.1.0's singular mirror of `wake_words`, kept for
        // compatibility and never shown — so a hint for it could never
        // appear. A hint nobody will see reads as a key that exists.
        _ => "",
    };

    /// <summary>
    /// What "erase everything" is called for a particular key.
    /// </summary>
    /// <remarks>
    /// Learned associations are <b>forgotten</b>, assigned hotkeys are
    /// <b>reset</b>. One word for both cases would be an untruth in one of
    /// them: what was forgotten Rina will learn again by herself, what was
    /// reset has to be assigned by hand.
    /// </remarks>
    public static string ClearWordOf(string key) => key switch
    {
        "app_aliases" => S("Забыть все"),
        "action_hotkeys" => S("Сбросить все"),
        _ => S("Очистить"),
    };

    /// <summary>Every key the shell knows by name.</summary>
    /// <summary>Every key this layout has a place for — sheets included.</summary>
    /// <remarks>
    /// **The sheets were left out, and that was visible.** A key that
    /// lives on a sheet of its own — `wake_words`, `hotkey` — counted
    /// as unknown, so its own sheet showed it as "wake_words · ключ
    /// wake_words оболочке незнаком", under a header that had just
    /// named it properly. A place on a sheet is a place.
    /// </remarks>
    private static IEnumerable<Labelled> Everything =>
        Sections.SelectMany(s => s.Keys)
                .Concat(Sections.SelectMany(s => s.Sheets ?? [])
                                .SelectMany(sheet => sheet.Keys
                                                          .Select(sheet.Label)));

    public static readonly HashSet<string> Known =
        Everything.Select(k => k.Key).ToHashSet();

    public static string TitleOf(string key) => S(
        Everything.FirstOrDefault(k => k.Key == key)?.Title ?? key);

    public static string HintOf(string key)
    {
        var hint = Everything.FirstOrDefault(k => k.Key == key)?.Hint ?? "";
        return hint.Length > 0 ? S(hint) : "";
    }
}
