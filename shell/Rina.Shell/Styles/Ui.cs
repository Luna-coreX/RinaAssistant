using System.Windows;

namespace Rina.Shell.Styles;

/// <summary>
/// Мелкие свойства, которых нет у стандартных контролов.
/// </summary>
/// <remarks>
/// <para>
/// Пока здесь одно — подсказка внутри поля. Заведено вложенным свойством, а
/// не тринадцатью самодельными накладками поверх тринадцати полей:
/// накладки разъезжаются, а свойство работает всюду, где поле нарисовано
/// нашим стилем.
/// </para>
/// <para>
/// <b>Подсказка — не значение.</b> Она гаснет, как только в поле появляется
/// текст, и не участвует ни в сохранении, ни в проверке. Поле, в котором
/// подсказка притворяется значением, — способ однажды сохранить слова
/// «например, C:\Program Files» как путь.
/// </para>
/// </remarks>
public static class Ui
{
    /// <summary>Что показать в пустом поле.</summary>
    public static readonly DependencyProperty HintProperty =
        DependencyProperty.RegisterAttached(
            "Hint", typeof(string), typeof(Ui),
            new PropertyMetadata(""));

    public static string GetHint(DependencyObject element)
        => (string)element.GetValue(HintProperty);

    public static void SetHint(DependencyObject element, string value)
        => element.SetValue(HintProperty, value);
}
