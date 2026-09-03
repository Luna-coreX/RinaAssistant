using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

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
        ("dialog", Word("Диалог")),
        ("commands", Word("Команды")),
        ("reminders", Word("Напоминания")),
        ("plugins", Word("Плагины")),
        ("settings", Word("Настройки")),
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
            ["commands"] = () => new Pages.CommandsPage(Link),
            ["reminders"] = () => new Pages.RemindersPage(Link),
            ["plugins"] = () => new Pages.PluginsPage(Link),
            ["settings"] = () => new Pages.SettingsPage(Link),
        };

        BuildSections();
        ShowSection("dialog");

        Strings.Loc.Changed += OnLanguageChanged;
        Closed += (_, _) => Strings.Loc.Changed -= OnLanguageChanged;
    }

    /// <summary>
    /// Пересобрать интерфейс на новом языке.
    /// </summary>
    /// <remarks>
    /// Страницы строятся заново, а не правятся по строчке: подписи живут в
    /// разметке, в коде страниц и в раскладке настроек, и обойти их все
    /// значило бы завести четвёртый список тех же строк. Открытый раздел
    /// при этом остаётся открытым — человек менял язык, а не место, где
    /// стоял.
    /// </remarks>
    private void OnLanguageChanged()
    {
        var open = _section;
        BuildSections();
        _section = "";
        ShowSection(open);
    }

    private void BuildSections()
    {
        Sections.Children.Clear();
        foreach (var (name, title) in SectionList)
        {
            var item = new RadioButton
            {
                Content = S(title),
                Tag = name,
                GroupName = "sections",
                Style = (Style)FindResource("Nav.Item"),
            };
            item.Checked += (_, _) => ShowSection(name);
            Sections.Children.Add(item);
        }
    }

    /// <summary>Что сейчас показано — для проверок.</summary>
    public object? CurrentPage => Pane.Content;

    /// <summary>Открыть раздел снаружи — для снимков и проверок.</summary>
    public void ShowSectionFor(string section) => ShowSection(section);

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
            CoreState.Ready => S("ядро на связи"),
            CoreState.Starting => S("ядро запускается"),
            CoreState.Reconnecting => S("связь потеряна, поднимаем"),
            CoreState.Failed => S("ядро не отвечает"),
            _ => S("ядро не запускалось"),
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
        // принадлежит прибору целиком, а не разделу: полоса уровня и то,
        // что видно поверх экрана.
        if (message.Method is "listening.capturing")
            Level.Width = message.Payload["active"]?.GetValue<bool>() == true
                ? ActualWidth * 0.4 : 0;

        Overlay(message);
    }

    /// <summary>Что видно поверх экрана: реплика и плашка «слушаю».</summary>
    public Overlays.Toast? Toast { get; set; }

    /// <summary>Плашка слушания.</summary>
    public Overlays.Listening? Plaque { get; set; }

    /// <summary>Показывать ли реплики поверх экрана (настройка).</summary>
    public bool ShowToasts { get; set; } = true;

    /// <summary>
    /// Событие ядра — в окна поверх экрана.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>Реплика показывается, когда окна не видно.</b> Если человек
    /// смотрит на диалог, ответ уже перед ним, и дублировать его карточкой
    /// в углу — значит показывать одно и то же дважды.
    /// </para>
    /// <para>
    /// <b>Плашка «слушаю» показывается всегда.</b> Здесь наоборот: право
    /// знать, что микрофон работает, не зависит от того, открыто ли окно, —
    /// именно при закрытом окне это и важно.
    /// </para>
    /// </remarks>
    private void Overlay(Envelope message)
    {
        switch (message.Method)
        {
            case "listening.started":
                Plaque?.Appear(always: false);
                break;

            case "listening.stopped":
                if (Plaque is { } stopping && !stopping.Always)
                    stopping.Vanish();
                break;

            case "listening.always":
                var on = message.Payload["enabled"]?.GetValue<bool>() == true;
                if (on) Plaque?.Appear(always: true);
                else Plaque?.Vanish();
                break;

            case "assistant.response":
                if (ShowToasts && !IsVisible)
                    Toast?.Say(message.Payload["text"]?.GetValue<string>() ?? "");
                break;

            case "assistant.error":
                if (ShowToasts && !IsVisible)
                    Toast?.Say(message.Payload["text"]?.GetValue<string>() ?? "",
                               Overlays.Toast.Short);
                break;
        }
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

    /// <summary>Значок в трее; ставится при запуске (<c>4.0-F05</c>).</summary>
    public Tray? Tray { get; set; }

    /// <summary>Сворачивать в трей вместо выхода. Решает человек.</summary>
    public bool MinimiseToTray { get; set; } = true;

    /// <summary>
    /// Крестик: свернуть или выйти.
    /// </summary>
    /// <remarks>
    /// Программа, не закрывающаяся по крестику вопреки ожиданию,
    /// воспринимается как сломанная, — поэтому поведение выбирает человек, а
    /// не мы за него. Из трея выйти можно всегда.
    /// </remarks>
    private void OnClose(object sender, RoutedEventArgs e) => OnCloseButton();

    /// <summary>То же, что нажать крестик. Отдельно — ради проверки.</summary>
    /// <remarks>
    /// Прятать окно можно только если значок в трее действительно заведён:
    /// иначе вернуть окно будет нечем и программа останется работать
    /// невидимой и недостижимой. Поэтому спрашивается не «есть ли объект
    /// трея», а «получилось ли завести значок» — объект есть всегда.
    /// </remarks>
    public void OnCloseButton()
    {
        if (MinimiseToTray && Tray is { Created: true }) Tray.Hide();
        else System.Windows.Application.Current.Shutdown();
    }

    /// <summary>Нажато основное сочетание (<c>4.0-F06</c>).</summary>
    public void OnMainHotkey()
    {
        Tray?.Show();
        ShowSection("dialog");
        // Слушать по нажатию — то, ради чего сочетание и нужно: помощника
        // вызывают, когда есть что сказать.
        _ = Link?.ListenOnceAsync();
    }

    /// <summary>Короткое сообщение человеку в подвале колонки.</summary>
    public void ShowNote(string text)
    {
        CoreStateText.Text = text;
        CoreStateText.SetResourceReference(ForegroundProperty, "C.Signal");
    }
}
