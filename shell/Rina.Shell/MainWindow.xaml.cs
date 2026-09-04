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

    //: Разделы включённых плагинов: `plugin:<id>` → как назвать.
    //:
    //: Замечание человека: в 3.1.0 плагин со своей вкладкой получал место
    //: в колонке, после переезда его страница жила внутри списка плагинов.
    //: Разница существенная: раздел — это «я этим пользуюсь», карточка в
    //: списке — «я это установил». Заметки открывают каждый день, список
    //: плагинов — раз в месяц.
    private readonly List<(string Name, string Title)> _pluginSections = [];

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
            ["about"] = () => new Pages.AboutPage(Link),
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

        // И подвал: он переводит при вызове, но после смены языка его никто
        // не звал заново — строка оставалась той, что написали в прошлый
        // раз. Перевод, случающийся один раз, — это не перевод.
        ShowCoreState(_coreState, _coreReason);
    }

    private void BuildSections()
    {
        Sections.Children.Clear();
        foreach (var (name, title) in SectionList.Select(
                     s => (s.Name, S(s.Title)))
                 .Concat(_pluginSections))
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

    /// <summary>Что сейчас показано — для проверок.</summary>
    public object? CurrentPage => Pane.Content;

    /// <summary>Открыть раздел снаружи — для снимков и проверок.</summary>
    public void ShowSectionFor(string section) => ShowSection(section);

    private void ShowSection(string section)
    {
        if (!_pages.TryGetValue(section, out var build)) return;
        _section = section;
        Pane.Content = build();

        // Переход между разделами — 220 мс (SYSTEM §7). Появление, а не
        // «выезд»: движение обязано отвечать на вопрос «что изменилось»,
        // и здесь изменилось содержимое, а не его положение. Панель
        // прибора не ездит.
        Pane.Opacity = 0;
        Pane.BeginAnimation(OpacityProperty,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                To = 1,
                Duration = (Duration)FindResource("Motion.Panel"),
                EasingFunction = (System.Windows.Media.Animation.IEasingFunction)
                    FindResource("Ease.In"),
            });

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
    private CoreState _coreState = CoreState.Stopped;
    private string _coreReason = "";

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
        // Запоминаем: после смены языка подвал надо переписать, а
        // состояние к тому времени уже никто не пришлёт заново.
        _coreState = state;
        _coreReason = reason;
        // Причина приходит из `Rina.Protocol` — библиотеки без переводов, и
        // это правильно: её дело провод, а не язык. Самую частую фразу окно
        // собирает само; остальное показывает как есть — техническая
        // подробность на языке журнала честнее её кривого перевода.
        var about = state == CoreState.Ready && reason.Length > 0
            ? S("ядро {0}", reason)   // причина здесь — версия ядра
            : reason;

        CoreStateText.Text = about.Length > 0 ? $"{text} · {about}" : text;
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
            ShowLevel(message.Payload["active"]?.GetValue<bool>() == true
                      ? 0.4f : 0f);

        Overlay(message);
    }

    /// <summary>
    /// Показать уровень микрофона с послесвечением.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>Подпись направления, а не украшение</b> (`DIRECTION` §4). Полоса
    /// не переключается между «выключено» и «включено»: после услышанной
    /// фразы след гаснет примерно за секунду, и по панели видно не только
    /// то, что Рина слушает <i>сейчас</i>, но и то, что она только что
    /// слышала. Мгновенное переключение — прямое «не в стиле» по
    /// двенадцати вопросам §6, и до этой правки полоса именно скакала.
    /// </para>
    /// <para>
    /// <b>Вверх — быстро, вниз — медленно.</b> Рост показывает то, что
    /// происходит сейчас, и опаздывать ему нельзя; спад показывает то, что
    /// уже прошло, и торопиться ему некуда. Одна длительность на оба
    /// направления дала бы либо вялую реакцию, либо мигание.
    /// </para>
    /// </remarks>
    public void ShowLevel(float level)
    {
        var wanted = Math.Clamp(level, 0f, 1f) * ActualWidth;
        var now = Level.ActualWidth;

        // Рост — отклик на нажатие по длительности: полоса и есть
        // микрофон, и её движение вверх это то же «сейчас», что у кнопки.
        var rising = wanted > now;
        var span = rising ? (Duration)FindResource("Motion.Press")
                          : (Duration)FindResource("Motion.Afterglow");

        var glide = new global::System.Windows.Media.Animation.DoubleAnimation
        {
            To = wanted,
            Duration = span,
            EasingFunction = (global::System.Windows.Media.Animation.IEasingFunction)
                FindResource(rising ? "Ease.In" : "Ease.Out"),
            FillBehavior = global::System.Windows.Media.Animation
                .FillBehavior.HoldEnd,
        };
        Level.BeginAnimation(WidthProperty, glide);
        LevelShown = level;
    }

    /// <summary>Какой уровень показан последним — для сквозной проверки.</summary>
    public float LevelShown { get; private set; }

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

    /// <summary>
    /// Обновить разделы плагинов.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Раздел получает только <b>включённый</b> плагин со своей страницей:
    /// выключенный не загружен, и спрашивать его страницу не у кого.
    /// </para>
    /// <para>
    /// Открытый раздел сохраняется, если он ещё существует. Иначе
    /// выключение одного плагина выбрасывало бы человека из другого.
    /// </para>
    /// </remarks>
    public void ShowPluginSections(
        IEnumerable<(string Id, string Title, string Icon)> plugins)
    {
        var wanted = plugins
            .Select(p => ($"plugin:{p.Id}",
                          p.Icon.Length > 0 ? $"{p.Icon}  {p.Title}" : p.Title))
            .ToList();

        if (wanted.Select(w => w.Item1).SequenceEqual(
                _pluginSections.Select(p => p.Name)))
            return;                                  // ничего не изменилось

        foreach (var (name, _) in _pluginSections) _pages.Remove(name);
        _pluginSections.Clear();

        foreach (var (name, title) in wanted)
        {
            var id = name["plugin:".Length..];
            _pluginSections.Add((name, title));
            _pages[name] = () => new Pages.PluginView(Link, id);
        }

        var open = _section;
        BuildSections();
        _section = "";
        ShowSection(_pages.ContainsKey(open) ? open : "dialog");
    }

    /// <summary>Какие разделы есть сейчас — для сквозной проверки.</summary>
    public string[] SectionNames() => Sections.Children
        .OfType<System.Windows.Controls.RadioButton>()
        .Select(item => (string)item.Tag)
        .ToArray();

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

    /// <summary>
    /// «О программе» — раздел, а не всплывающее окно.
    /// </summary>
    /// <remarks>
    /// В колонке его нет: туда ходят редко, и постоянное место он не
    /// заслуживает. Но и модальное окно ему не годится — там ссылки, по
    /// которым ходят, и версии, которые переписывают в сообщение о
    /// неполадке.
    /// </remarks>
    private void OnAbout(object sender, MouseButtonEventArgs e)
        => ShowSection("about");

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
