using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
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
        // Страницы строятся отложенно и получают связь, а не окно: раздел,
        // дотянувшийся до родителя, — первый шаг к god-object'у, ради
        // избавления от которого затевался блок B.
        _pages = new Dictionary<string, Func<UIElement>>
        {
            ["dialog"] = () => new Pages.DialoguePage(Link),
            ["commands"] = () => Pages.Placeholder.For("Команды"),
            ["reminders"] = () => new Pages.RemindersPage(Link),
            ["plugins"] = () => Pages.Placeholder.For("Плагины"),
            ["settings"] = () => Pages.Placeholder.For("Настройки"),
        };

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
        _section = section;
        Pane.Content = build();

        foreach (var child in Sections.Children.OfType<RadioButton>())
            if ((string?)child.Tag == section && child.IsChecked != true)
                child.IsChecked = true;
    }

    /// <summary>Связь с ядром; ставится при запуске (<c>4.0-F07</c>, <c>F12</c>).</summary>
    public CoreLink? Link
    {
        get => _link;
        set
        {
            _link = value;
            // Раздел, показанный до появления связи, надо построить заново:
            // он уже сообщил человеку, что ядра нет.
            ShowSection(_section);
        }
    }

    private CoreLink? _link;
    private string _section = "dialog";

    private string _finish = "black";

    /// <summary>Что окно показывает про связь — для самопроверки.</summary>
    public string CoreStateTextValue => CoreStateText.Text;

    /// <summary>Какая отделка сейчас показана — для самопроверки.</summary>
    public string FinishValue => _finish;

    /// <summary>Состояние сменилось. Слушает самопроверка.</summary>
    public event Action<CoreState>? CoreStateShown;

    /// <summary>
    /// Показать состояние связи с ядром (<c>4.0-F12</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Состояние видно всегда, а не по запросу: §13 требует, чтобы окно не
    /// выглядело зависшим, и человек должен понимать, что происходит, не
    /// нажимая ничего.
    /// </para>
    /// <para>
    /// Неполадка окрашивается акцентом, а не красным. Красного в палитре нет
    /// вовсе (§2 дизайн-системы): цвет опасности размывается от повторения,
    /// и там, где им красят каждую неприятность, он перестаёт значить
    /// «осторожно». «Ядро не отвечает» — это ошибка, а не опасность.
    /// </para>
    /// </remarks>
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
        CoreStateText.SetResourceReference(
            ForegroundProperty,
            state is CoreState.Ready or CoreState.Stopped ? "C.InkFaint"
                                                          : "C.Signal");
        CoreStateShown?.Invoke(state);
    }

    /// <summary>Событие ядра. Пока — только полоса уровня.</summary>
    public void OnCoreEvent(Envelope message)
    {
        // Разбор событий по разделам — 4.0-F04. Здесь остаётся то, что
        // принадлежит прибору целиком, а не разделу: полоса уровня.
        if (message.Method is "listening.capturing")
            Level.Width = message.Payload["active"]?.GetValue<bool>() == true
                ? ActualWidth * 0.4 : 0;
    }

    /// <summary>Отделка, которую показывает окно.</summary>
    public void ShowFinish(string finish) => _finish = finish;

    private async void OnSwitchFinish(object sender, RoutedEventArgs e)
    {
        // Две отделки равноправны (4.0-R08), поэтому переключатель, а не
        // список: выбирать не из чего, кроме как между ними.
        _finish = _finish == "black" ? "silver" : "black";
        if (Link is not null) await Link.SetFinishAsync(_finish);
        else App.ApplyFinish(_finish);
    }

    private void OnMinimise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void OnMaximise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized
            ? WindowState.Normal : WindowState.Maximized;

    private void OnClose(object sender, RoutedEventArgs e) => System.Windows.Application.Current.Shutdown();
}
