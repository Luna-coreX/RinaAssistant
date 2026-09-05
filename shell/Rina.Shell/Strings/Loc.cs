using System.Windows;
using System.Windows.Markup;

namespace Rina.Shell.Strings;

/// <summary>
/// Interface strings in the chosen language.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F08</c>, decided by
/// [ADR 0007](../../../docs/adr/0007-localisation.md):
/// <b>the words of the interface live in the shell, Rina's lines in the
/// core.</b>
/// </para>
/// <para>
/// <b>The key is a Russian string.</b> The convention is inherited from
/// 3.1.0 and was not chosen out of laziness: an untranslated place shows a
/// meaningful Russian original rather than <c>settings.voice.title</c> or
/// nothing at all. A missing translation spoils one label instead of
/// breaking a screen.
/// </para>
/// <para>
/// <b>The language is stored in the core and applied here.</b> There is
/// one setting for the whole program (`ui_language`), and keeping a copy
/// of it in the shell would mean a second source of truth. The core holds
/// the intent, the shell brings itself into line — the same rule as for
/// autostart and the tray.
/// </para>
/// </remarks>
public static partial class Loc
{
    /// <summary>The original language: no translations are looked up for it.</summary>
    public const string Source = "Русский";

    private static string _language = Source;

    /// <summary>The chosen language. Changes with the setting from the core.</summary>
    public static string Language => _language;

    /// <summary>The language changed — whatever is already drawn has to redraw.</summary>
    public static event Action? Changed;

    /// <summary>Languages in which the shell has anything at all.</summary>
    public static IEnumerable<string> Languages =>
        new[] { Source }.Concat(Table.Values.SelectMany(row => row.Keys)
                                     .Distinct().OrderBy(name => name,
                                                         StringComparer.Ordinal));

    /// <summary>Switch language. Does nothing if it is the same one.</summary>
    public static void Use(string language)
    {
        if (string.IsNullOrWhiteSpace(language) || language == _language) return;
        _language = language;
        // Bindings first, subscribers second: a string in the markup
        // updates by itself, and whoever rebuilds pages will already see
        // the new language.
        Live.Refresh();
        Changed?.Invoke();
    }

    /// <summary>
    /// Translate a string. No translation — the string itself comes back.
    /// </summary>
    /// <remarks>
    /// Returning the original in silence is a deliberate choice: a string
    /// without a translation should look untranslated, not missing.
    /// Complaining to the log about every such string would mean making
    /// noise exactly where the behaviour is intended.
    /// </remarks>
    public static string S(string key)
    {
        if (_language == Source) return key;
        return Table.TryGetValue(key, out var row)
               && row.TryGetValue(_language, out var translated)
            ? translated : key;
    }

    /// <summary>
    /// Mark a string as translatable without translating it here.
    /// </summary>
    /// <remarks>
    /// For places where the translation must happen later: a static table
    /// would freeze on the language of the moment the type was loaded. It
    /// returns the string as it is — all the work is in being seen by the
    /// translation-table collector and by the check.
    /// </remarks>
    public static string Word(string key) => key;

    /// <summary>
    /// A translation lookup for bindings from the markup.
    /// </summary>
    /// <remarks>
    /// One for the whole application. A language change announces that
    /// **all** of its values have changed (`Item[]`), and every binding
    /// re-reads its key. Cheaper than rebuilding windows, and more reliable
    /// than remembering which of them need rebuilding.
    /// </remarks>
    public sealed class Lookup : System.ComponentModel.INotifyPropertyChanged
    {
        public event System.ComponentModel.PropertyChangedEventHandler?
            PropertyChanged;

        public string this[string key] => S(key);

        internal void Refresh() => PropertyChanged?.Invoke(
            this, new System.ComponentModel.PropertyChangedEventArgs("Item[]"));
    }

    /// <summary>The translation lookup; the source for `{loc:S …}` bindings.</summary>
    public static Lookup Live { get; } = new();

    /// <summary>Translate and substitute: <c>S("Осталось {0}", n)</c>.</summary>
    public static string S(string key, params object?[] arguments)
    {
        try
        {
            return string.Format(S(key), arguments);
        }
        catch (FormatException)
        {
            // A translation with a broken substitution is no reason to
            // show nothing: the original with the right places is better
            // than an exception.
            return string.Format(key, arguments);
        }
    }

    /// <summary>How many strings are translated into a language, out of the total.</summary>
    /// <remarks>
    /// An honest measure of coverage: a language translated by a third is
    /// better called a third than "supported".
    /// </remarks>
    public static double Coverage(string language) =>
        language == Source || Table.Count == 0 ? 1.0
        : (double)Table.Values.Count(row => row.ContainsKey(language))
          / Table.Count;
}

/// <summary>
/// Markup: <c>Text="{loc:S Настройки}"</c>.
/// </summary>
/// <remarks>
/// Needed because half the interface strings live in XAML rather than in
/// code. Leaving them as literals would mean translating the program
/// halfway — and noticing it only in another language.
/// </remarks>
[MarkupExtensionReturnType(typeof(string))]
public sealed class SExtension : MarkupExtension
{
    public SExtension() { }

    public SExtension(string key) => Key = key;

    [ConstructorArgument("key")]
    public string Key { get; set; } = "";

    /// <summary>
    /// A binding to the translation, not a one-off substitution.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Markup is parsed once. Returning a string here got us a translation
    /// that never changed afterwards: pages hid this — they are rebuilt on
    /// a language change — but the window did not, and the footer of the
    /// column stayed in the previous language.
    /// </para>
    /// <para>
    /// A binding to <see cref="Loc.Live"/> updates by itself wherever the
    /// string stands, and does not require remembering what exactly needs
    /// rebuilding.
    /// </para>
    /// </remarks>
    public override object ProvideValue(IServiceProvider provider)
    {
        var binding = new System.Windows.Data.Binding($"[{Key}]")
        {
            Source = Loc.Live,
            Mode = System.Windows.Data.BindingMode.OneWay,
        };

        // Not every target is a dependency property: `ToolTip` in an
        // attribute, for one, arrives as an object. Where a binding is
        // impossible we return a string, as before.
        if (provider?.GetService(typeof(IProvideValueTarget))
            is IProvideValueTarget target
            && target.TargetProperty is not DependencyProperty)
            return Loc.S(Key);

        return binding.ProvideValue(provider!);
    }
}
