using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>What a setting is called and which section it lives in.</summary>
public sealed record Labelled(string Key, string Title, string Hint = "");

/// <summary>A section of the settings screen: a heading and what is in it.</summary>
public sealed record Section(string Title, Labelled[] Keys);

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
        new(Word("Голос"),
        [
            new("tts_engine", Word("Система синтеза"),
                Word("Чем Рина говорит. Офлайновые работают без интернета")),
            new("stt_engine", Word("Распознавание"),
                Word("Чем Рина слышит. Без него команды только с клавиатуры")),
            new("voice", Word("Голос"),
                Word("Голоса зависят от выбранной системы синтеза")),
            new("wake_words", Word("Слова активации"),
                Word("С этих слов начинается обращение к Рине")),
            new("volume", Word("Громкость"),
                Word("Насколько громко Рина говорит")),
            new("speed", Word("Скорость речи"),
                Word("Быстрее ста — торопится, медленнее — растягивает")),
        ]),
        new(Word("Модели"),
        [
            new("whisper_model", Word("Модель Whisper"),
                Word("Крупнее — точнее и медленнее")),
            new("vosk_model", Word("Модель Vosk"),
                Word("Папка с распакованной моделью Vosk")),
            new("piper_model", Word("Модель Piper"),
                Word("Файл модели .onnx")),
            new("wake_sensitivity", Word("Чувствительность активации"),
                Word("Ниже — откликается чаще, но и на чужое тоже")),
            new("listen_seconds", Word("Длительность записи"),
                Word("Сколько ждать фразу после обращения")),
        ]),
        new(Word("Звук"),
        [
            new("input_device", Word("Микрофон"),
                Word("Какой микрофон слушать")),
            new("output_device", Word("Динамик"),
                Word("Куда говорить")),
            new("sound_effects", Word("Звуковые эффекты"),
                Word("Короткий сигнал, когда Рина услышала и когда ответила")),
        ]),
        new(Word("Программы"),
        [
            new("program_folders", Word("Добавленные папки"),
                Word("Portable-программы ищутся здесь")),
            new("app_aliases", Word("Выученные соответствия"),
                Word("Что Рина запомнила: какое слово какую программу означает")),
        ]),
        new(Word("Поведение"),
        [
            new("autostart", Word("Запускать при входе в систему"),
                Word("Рина будет запускаться сама при входе в систему")),
            new("minimize_to_tray", Word("Сворачивать в трей"),
                Word("Крестик прячет окно, а не выходит из программы")),
            new("start_minimized", Word("Начинать свёрнутой"),
                Word("Запускаться сразу в трее, без окна")),
            new("floating_command_bar", Word("Плавающая строка команд"),
                Word("Поверх окон; вызывается сочетанием клавиш")),
            new("notifications", Word("Уведомления"),
                Word("Показывать ответы, когда окно скрыто")),
            new("hotkey", Word("Основная комбинация"),
                Word("Показать окно и начать слушать")),
            new("action_hotkeys", Word("Комбинации действий"),
                Word("Сочетания, назначенные отдельным действиям")),
        ]),
        new(Word("Обновления"),
        [
            // The setting is there, and updates are not yet: the hint
            // says so outright. A toggle without a hint would promise
            // behaviour that will not exist until block U.
            new("check_updates", Word("Проверять обновления"),
                Word("Появится вместе с обновлениями")),
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
                Word("Сколько ждать ответа, прежде чем сдаться")),
        ]),
        new(Word("Поиск"),
        [
            new("search_engine", Word("Поисковая система"),
                Word("Где искать, когда Рина не поняла команду")),
            new("web_search_fallback", Word("Искать нераспознанное"),
                Word("Непонятое уходит в поиск, а не остаётся без ответа")),
        ]),
        new(Word("Внешний вид"),
        [
            new("finish", Word("Отделка"),
                Word("Вся поверхность целиком: цвета проверены парами")),
            new("accent", Word("Акцент"),
                Word("Цвет, которым Рина выделяет важное")),
            new("ui_language", Word("Язык интерфейса"),
                Word("Язык подписей в окне")),
        ]),
        new(Word("Приватность"),
        [
            new("save_history", Word("Сохранять историю"),
                Word("Хранить переписку между запусками")),
            new("log_texts", Word("Записывать тексты реплик"),
                Word("Записывать тексты реплик в журнал. По умолчанию выключено")),
            new("log_level", Word("Подробность журнала"),
                Word("Насколько подробен журнал")),
        ]),
    ];

    /// <summary>
    /// Settings the shell shows somewhere other than here.
    /// </summary>
    /// <remarks>
    /// "Answer by voice" and "always listen" stand by the input line
    /// (<c>4.0-R04</c>): these are not settings but the instrument's mode
    /// of work, and they are switched in the middle of a conversation. They
    /// are not "unknown" — they are known and shown elsewhere, and the rule
    /// about unfamiliar keys does not apply to them.
    /// </remarks>
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
        "wake_word" => S("Рина"),
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
    public static readonly HashSet<string> Known =
        Sections.SelectMany(s => s.Keys).Select(k => k.Key).ToHashSet();

    public static string TitleOf(string key) => S(
        Sections.SelectMany(s => s.Keys).FirstOrDefault(k => k.Key == key)?.Title
        ?? key);

    public static string HintOf(string key)
    {
        var hint = Sections.SelectMany(s => s.Keys)
            .FirstOrDefault(k => k.Key == key)?.Hint ?? "";
        return hint.Length > 0 ? S(hint) : "";
    }
}
