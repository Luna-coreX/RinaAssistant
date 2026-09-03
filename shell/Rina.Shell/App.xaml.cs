using System.Windows;

namespace Rina.Shell;

public partial class App : Application
{
    /// <summary>
    /// Отделка, выбранная на старте.
    /// </summary>
    /// <remarks>
    /// Две отделки равноправны (<c>4.0-R08</c>): ни одна не «основная» и ни
    /// одна не инверсия другой. Поэтому подменяется целый словарь ресурсов, а
    /// не пересчитываются цвета от одного базового.
    /// </remarks>
    /// <summary>
    /// Сменить акцент, не трогая остальную отделку.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Замечание человека, `4.0-R08` уточнён. Пять палитр 3.1.0 уступили
    /// двум отделкам, и это решение остаётся: отделка — вся поверхность, её
    /// цвета проверены парами, и менять их поштучно нельзя. Но **акцент —
    /// не палитра**: это один цвет с двумя обязанностями, читаться на
    /// панели и на приподнятом. Его можно выбирать, если каждый вариант
    /// проверен там же, где проверялся исходный, — и каждый проверен
    /// (`tools/check_contrast.py`).
    /// </para>
    /// <para>
    /// Подменяются и кисть, и цвет: их два представления одного и того же,
    /// и подменить одно, забыв другое, — вопрос времени. Незнакомое имя
    /// оставляет всё как есть: акцент, которого нет, не повод обесцветить
    /// программу.
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

    /// <summary>Акцент по умолчанию — тот, что был до выбора.</summary>
    public static string DefaultAccent =>
        Current?.TryFindResource("Accent.Default") as string ?? "amber";

    /// <summary>Какие акценты есть у этой отделки, с именами.</summary>
    /// <remarks>
    /// Набор свой у каждой отделки: одна и та же краска на светлом и на
    /// тёмном читается по-разному, и общий список был бы списком,
    /// половина которого не проходит проверку.
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
