using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

namespace Rina.Shell;

/// <summary>
/// Главное окно: рама, колонка разделов, место для раздела.
/// </summary>
/// <remarks>
/// <para>
/// <b>Окно только маршрутизирует.</b> Оно знает, какие есть разделы и куда их
/// показывать, и ничего — про их содержимое. Страницы независимы; иначе окно
/// станет god-object'ом, ради избавления от которого затевался блок B, только
/// теперь на другом языке.
/// </para>
/// <para>
/// Пять разделов — решение <c>4.0-R04</c>, а не восемь вкладок 3.1.0.
/// «История» поглощена «Диалогом», «Горячие клавиши» ушли в «Настройки»,
/// «О программе» — в подвал колонки.
/// </para>
/// </remarks>
public partial class MainWindow : Window
{
    /// <summary>Разделы в том порядке, в каком они стоят в колонке.</summary>
    private static readonly (string Name, string Title)[] SectionList =
    [
        ("dialog", "Диалог"),
        ("commands", "Команды"),
        ("reminders", "Напоминания"),
        ("plugins", "Плагины"),
        ("settings", "Настройки"),
    ];

    private readonly Dictionary<string, Func<UIElement>> _pages;

    public MainWindow()
    {
        InitializeComponent();

        // Страницы заводятся отложенно: раздел, на который не заходили, не
        // должен ничего строить. Это же и место, куда F04 подставит
        // настоящие страницы, не трогая окно.
        _pages = SectionList.ToDictionary(
            s => s.Name,
            s => (Func<UIElement>)(() => Pages.Placeholder.For(s.Title)));

        BuildSections();
        ShowSection("dialog");
    }

    private void BuildSections()
    {
        foreach (var (name, title) in SectionList)
        {
            var item = new RadioButton
            {
                Content = title,
                Tag = name,
                GroupName = "sections",
                Style = (Style)FindResource("Nav.Item"),
            };
            item.Checked += (_, _) => ShowSection(name);
            Sections.Children.Add(item);
        }
    }

    private void ShowSection(string section)
    {
        if (!_pages.TryGetValue(section, out var build)) return;
        Pane.Content = build();

        foreach (var child in Sections.Children.OfType<RadioButton>())
            if ((string?)child.Tag == section && child.IsChecked != true)
                child.IsChecked = true;
    }

    /// <summary>Показать состояние связи с ядром (заготовка <c>4.0-F12</c>).</summary>
    public void ShowCoreState(CoreState state, string reason)
    {
        var text = state switch
        {
            CoreState.Ready => "ядро на связи",
            CoreState.Starting => "ядро запускается",
            CoreState.Reconnecting => "связь потеряна, поднимаем",
            CoreState.Failed => "ядро не отвечает",
            _ => "ядро не запускалось",
        };
        CoreStateText.Text = reason.Length > 0 ? $"{text} · {reason}" : text;
    }

    private void OnMinimise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void OnMaximise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized
            ? WindowState.Normal : WindowState.Maximized;

    private void OnClose(object sender, RoutedEventArgs e) => System.Windows.Application.Current.Shutdown();
}
