using System.Windows;
using System.Windows.Controls;

namespace Rina.Shell.Pages;

/// <summary>
/// Заглушка раздела: заголовок и честное признание, что содержимого нет.
/// </summary>
/// <remarks>
/// Настоящие страницы — <c>4.0-F04</c>. Заглушка нужна не «чтобы что-то
/// было»: она проверяет то, ради чего писался <c>F03</c>, — что окно
/// маршрутизирует, а раздел рисует себя сам. Пустая панель этого не
/// показала бы.
/// </remarks>
public static class Placeholder
{
    public static UIElement For(string title)
    {
        var stack = new StackPanel();
        stack.Children.Add(new TextBlock
        {
            Text = title,
            Style = (Style)Application.Current.FindResource("Text.Title"),
        });
        stack.Children.Add(new TextBlock
        {
            Text = "Раздел появится в 4.0-F04.",
            Style = (Style)Application.Current.FindResource("Text.Body"),
            Margin = new Thickness(0, 16, 0, 0),
        });
        return stack;
    }
}
