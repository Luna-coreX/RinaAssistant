using System.Windows;

namespace Rina.Shell;

public partial class App : Application
{
    /// <summary>
    /// Change the accent without touching the rest of the finish.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Raised by the person; `4.0-R08` was refined. The five palettes of
    /// 3.1.0 gave way to two finishes, and that decision stands: a finish is
    /// the whole surface, its colours were verified in pairs, and they must
    /// not be changed one at a time. But <b>an accent is not a palette</b>:
    /// it is one colour with two duties, to read on the panel and on the
    /// raised surface. It may be chosen, provided every option was verified
    /// where the original was — and every one is
    /// (`tools/check_contrast.py`).
    /// </para>
    /// <para>
    /// Both the brush and the colour are replaced: they are two
    /// representations of the same thing, and replacing one while forgetting
    /// the other is a matter of time. An unknown name leaves everything as
    /// it is: an accent that does not exist is no reason to drain the colour
    /// out of the program.
    /// </para>
    /// </remarks>
    public static void ApplyAccent(string finish, string accent)
    {
        if (Current is null) return;
        var wanted = string.IsNullOrWhiteSpace(accent)
            ? DefaultAccent : accent.Trim();

        var signal = Current.TryFindResource($"Accent.{finish}.{wanted}.Signal");
        var sunk = Current.TryFindResource($"Accent.{finish}.{wanted}.SignalSunk");
        if (signal is not System.Windows.Media.Color tone
            || sunk is not System.Windows.Media.Color deep)
            return;

        Current.Resources["Color.Signal"] = tone;
        Current.Resources["Color.SignalSunk"] = deep;
        Current.Resources["C.Signal"] =
            new System.Windows.Media.SolidColorBrush(tone);
        Current.Resources["C.SignalSunk"] =
            new System.Windows.Media.SolidColorBrush(deep);
    }

    /// <summary>The default accent — the one that was there before any choice.</summary>
    public static string DefaultAccent =>
        Current?.TryFindResource("Accent.Default") as string ?? "amber";

    /// <summary>Which accents this finish has, with their names.</summary>
    /// <remarks>
    /// Each finish has its own set: the same paint reads differently on
    /// light and on dark, and a shared list would be a list half of which
    /// fails the check.
    /// </remarks>
    public static IEnumerable<(string Value, string Title)> Accents(
        string finish)
    {
        if (Current is null) yield break;
        foreach (var key in Current.Resources.MergedDictionaries
                     .SelectMany(d => d.Keys.OfType<string>())
                     .Where(k => k.StartsWith($"Accent.{finish}.")
                                 && k.EndsWith(".Signal"))
                     .OrderBy(k => k, StringComparer.Ordinal))
        {
            var name = key.Split('.')[2];
            yield return (name,
                Current.TryFindResource($"Accent.Title.{name}") as string
                ?? name);
        }
    }

    /// <summary>
    /// The finish chosen at startup.
    /// </summary>
    /// <remarks>
    /// The two finishes are equals (<c>4.0-R08</c>): neither is the "main"
    /// one and neither is an inversion of the other. That is why a whole
    /// resource dictionary is swapped rather than colours being derived from
    /// one base.
    ///
    /// This block used to sit above <c>ApplyAccent</c>, orphaned by an
    /// earlier edit, while the method it describes had no documentation at
    /// all.
    /// </remarks>
    public static void ApplyFinish(string finish)
    {
        var name = finish is "black" ? "Black" : "Silver";
        var wanted = new Uri($"Generated/Finish.{name}.g.xaml", UriKind.Relative);

        var dictionaries = Current.Resources.MergedDictionaries;
        for (var i = 0; i < dictionaries.Count; i++)
        {
            if (dictionaries[i].Source?.OriginalString.Contains("Finish.") == true)
            {
                dictionaries[i] = new ResourceDictionary { Source = wanted };
                return;
            }
        }
    }
}
