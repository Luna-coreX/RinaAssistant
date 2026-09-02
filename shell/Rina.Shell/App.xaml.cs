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
