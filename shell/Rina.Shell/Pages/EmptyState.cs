using System.Windows;
using System.Windows.Controls;

namespace Rina.Shell.Pages;

/// <summary>
/// Пустое место, которое объясняет себя.
/// </summary>
/// <remarks>
/// <para>
/// Замечание человека: «выглядит хорошо, но пустовато». Разбор показал, что
/// дело не в количестве украшений, а в том, что раздел без записей
/// заканчивался одной серой строкой и тремястами точками пустоты под ней.
/// Панель прибора так не выглядит: у неё нет незаполненного низа.
/// </para>
/// <para>
/// <b>Пустое состояние — это показание, а не отсутствие показания.</b> Оно
/// отвечает на три вопроса разом: что здесь бывает, почему сейчас пусто и
/// что сделать, чтобы не было. «Ничего не запланировано» отвечает на
/// половину первого.
/// </para>
/// <para>
/// <b>Занимает весь остаток и центрируется в нём.</b> Прижатое к верху
/// пустое состояние читается как обрезанная страница; в середине пустого
/// места оно читается как состояние прибора.
/// </para>
/// <para>
/// Значка нет. Направление запрещает значок без подписи, а значок с
/// подписью здесь — это подпись, которая уже есть.
/// </para>
/// </remarks>
public static class EmptyState
{
    /// <summary>
    /// Собрать пустое состояние.
    /// </summary>
    /// <param name="what">Чего пока нет — одной строкой.</param>
    /// <param name="why">Что здесь появляется и откуда.</param>
    /// <param name="how">Что сказать или нажать. Необязательно.</param>
    /// <param name="onGlass">
    /// Пустое состояние лежит на стеклянном поле, а не на панели.
    /// </param>
    /// <remarks>
    /// Цвета на стекле свои — `GLASS_TEXT` и `GLASS_DIM`. Не украшение:
    /// пара «чернила на стекле» в проверке контраста не значится, потому
    /// что стекло и панель — разные поверхности, и краска панели на стекле
    /// не проверена никем.
    /// </remarks>
    public static FrameworkElement For(string what, string why,
                                       string how = "", bool onGlass = false)
    {
        var stack = new StackPanel
        {
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            MaxWidth = 420,
        };

        var bright = onGlass ? Brush("C.GlassText") : Brush("C.Ink");
        var faint = onGlass ? Brush("C.GlassDim") : Brush("C.InkSoft");

        stack.Children.Add(new TextBlock
        {
            Text = what,
            Style = Find("Text.Body"),
            Foreground = bright,
            HorizontalAlignment = HorizontalAlignment.Center,
            TextAlignment = TextAlignment.Center,
        });

        stack.Children.Add(new TextBlock
        {
            Text = why,
            Style = Find("Text.Meta"),
            Foreground = faint,
            TextWrapping = TextWrapping.Wrap,
            TextAlignment = TextAlignment.Center,
            Margin = new Thickness(0, 8, 0, 0),
        });

        if (how.Length > 0)
        {
            // Пример набран моноширинным: это то, что говорят или пишут
            // дословно, а дословное в системе набирается цифровым шрифтом.
            stack.Children.Add(new TextBlock
            {
                Text = how,
                Style = Find("Text.Figure"),
                Foreground = faint,
                TextWrapping = TextWrapping.Wrap,
                TextAlignment = TextAlignment.Center,
                Margin = new Thickness(0, 16, 0, 0),
            });
        }

        return stack;
    }

    private static Style Find(string key)
        => (Style)Application.Current.FindResource(key);

    private static System.Windows.Media.Brush Brush(string key)
        => (System.Windows.Media.Brush)Application.Current.FindResource(key);
}
