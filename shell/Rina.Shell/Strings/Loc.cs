using System.Windows.Markup;

namespace Rina.Shell.Strings;

/// <summary>
/// Строки интерфейса на выбранном языке.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F08</c>, решение — [ADR 0007](../../../docs/adr/0007-localisation.md):
/// <b>слова интерфейса живут в оболочке, реплики Рины — в ядре.</b>
/// </para>
/// <para>
/// <b>Ключ — это русская строка.</b> Соглашение унаследовано от 3.1.0 и
/// выбрано не из лени: непереведённое место показывает осмысленный русский
/// оригинал, а не <c>settings.voice.title</c> и не пустоту. Пропущенный
/// перевод портит один ярлык, а не ломает экран.
/// </para>
/// <para>
/// <b>Язык хранится в ядре, а применяется здесь.</b> Настройка одна на
/// программу (`ui_language`), и держать её копию в оболочке значило бы
/// завести второй источник правды. Ядро хранит намерение, оболочка
/// приводит себя в соответствие — то же правило, что у автозапуска и трея.
/// </para>
/// </remarks>
public static partial class Loc
{
    /// <summary>Язык оригинала: для него переводов не ищут.</summary>
    public const string Source = "Русский";

    private static string _language = Source;

    /// <summary>Выбранный язык. Меняется по настройке из ядра.</summary>
    public static string Language => _language;

    /// <summary>Язык сменился — тем, кто уже нарисован, надо перерисоваться.</summary>
    public static event Action? Changed;

    /// <summary>Языки, на которых у оболочки есть хоть что-то.</summary>
    public static IEnumerable<string> Languages =>
        new[] { Source }.Concat(Table.Values.SelectMany(row => row.Keys)
                                     .Distinct().OrderBy(name => name,
                                                         StringComparer.Ordinal));

    /// <summary>Переключить язык. Ничего не делает, если он тот же.</summary>
    public static void Use(string language)
    {
        if (string.IsNullOrWhiteSpace(language) || language == _language) return;
        _language = language;
        Changed?.Invoke();
    }

    /// <summary>
    /// Перевести строку. Нет перевода — вернётся она же.
    /// </summary>
    /// <remarks>
    /// Молча вернуть оригинал — сознательный выбор: строка без перевода
    /// должна выглядеть непереведённой, а не отсутствующей. Ругаться в
    /// журнал на каждую такую строку значило бы шуметь ровно там, где
    /// поведение задумано.
    /// </remarks>
    public static string S(string key)
    {
        if (_language == Source) return key;
        return Table.TryGetValue(key, out var row)
               && row.TryGetValue(_language, out var translated)
            ? translated : key;
    }

    /// <summary>
    /// Пометить строку как переводимую, не переводя её здесь.
    /// </summary>
    /// <remarks>
    /// Для мест, где перевод обязан случиться позже: статическая таблица
    /// застыла бы на языке, который был в момент загрузки типа. Возвращает
    /// строку как есть — вся работа в том, что её видят сборщик таблицы
    /// переводов и проверка.
    /// </remarks>
    public static string Word(string key) => key;

    /// <summary>Перевести и подставить: <c>S("Осталось {0}", n)</c>.</summary>
    public static string S(string key, params object?[] arguments)
    {
        try
        {
            return string.Format(S(key), arguments);
        }
        catch (FormatException)
        {
            // Перевод с испорченной подстановкой не повод показать пустоту:
            // оригинал с правильными местами лучше, чем исключение.
            return string.Format(key, arguments);
        }
    }

    /// <summary>Сколько строк переведено на язык, от общего числа.</summary>
    /// <remarks>
    /// Честная мера покрытия: язык, переведённый на треть, лучше называть
    /// третью, чем «поддерживаемым».
    /// </remarks>
    public static double Coverage(string language) =>
        language == Source || Table.Count == 0 ? 1.0
        : (double)Table.Values.Count(row => row.ContainsKey(language))
          / Table.Count;
}

/// <summary>
/// Разметка: <c>Text="{loc:S Настройки}"</c>.
/// </summary>
/// <remarks>
/// Нужна потому, что половина строк интерфейса живёт в XAML, а не в коде.
/// Оставить их литералами значило бы перевести программу наполовину —
/// и заметить это только на чужом языке.
/// </remarks>
[MarkupExtensionReturnType(typeof(string))]
public sealed class SExtension : MarkupExtension
{
    public SExtension() { }

    public SExtension(string key) => Key = key;

    [ConstructorArgument("key")]
    public string Key { get; set; } = "";

    public override object ProvideValue(IServiceProvider provider)
        => Loc.S(Key);
}
