using System.Text.Json.Nodes;
using Rina.Protocol;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// О программе: из чего собрана и куда идти.
/// </summary>
/// <remarks>
/// <para>
/// Замечание человека: «о программе» в подвале было текстом, по которому
/// нельзя нажать.
/// </para>
/// <para>
/// <b>Версий четыре, и показаны все четыре.</b> Это прямое следствие
/// [ADR 0004](../../../docs/adr/0004-versioning-and-compatibility.md):
/// оболочка, ядро, протокол и схема данных обновляются порознь, и вопрос
/// «какая у меня версия» без уточнения «чего» больше не имеет одного
/// ответа. Человеку, который пришёл сюда из-за неполадки, нужны все
/// четыре — иначе он назовёт одну, а спросят другую.
/// </para>
/// <para>
/// <b>Ссылка открывается в браузере, а не внутри окна.</b> Своего браузера
/// у Рины нет и не будет: страница, открытая внутри помощника, — это чужой
/// код, которому мы дали своё окно.
/// </para>
/// </remarks>
public partial class AboutPage : UserControl
{
    private readonly CoreLink? _link;

    /// <summary>Сколько строк «из чего собрана» — для сквозной проверки.</summary>
    public int PartCount => Parts.Children.Count;

    public AboutPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        Version.Text = ShellVersion;
        BuildLinks();
        BuildPlaces();
        Loaded += async (_, _) => await ShowPartsAsync();
    }

    /// <summary>Что сказала последняя проверка — для сквозной проверки.</summary>
    public string UpdateSaid => UpdateState.Text;

    /// <summary>
    /// Спросить, есть ли новее.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Задача плана <c>4.0-U03</c>. Клиент живёт в оболочке
    /// ([ADR 0009](../../../docs/adr/0009-system-layer.md)): скачать файл и
    /// положить на диск — работа системного слоя, а заменять файлы ядра
    /// может только тот, кто ядро останавливает.
    /// </para>
    /// <para>
    /// <b>Кнопка есть всегда, даже когда автопроверка выключена.</b>
    /// Настройка `check_updates` управляет тем, спрашиваем ли мы сами;
    /// человек, пришедший спросить руками, уже ответил на этот вопрос.
    /// </para>
    /// </remarks>
    private async void OnCheckUpdates(object sender, RoutedEventArgs e)
    {
        CheckNow.IsEnabled = false;
        UpdateState.Text = S("Спрашиваю…");
        UpdateNote.Text = "";
        try
        {
            var found = await new Update.Updater([ProtocolVersion.Current])
                .CheckAsync(ShellVersion, CoreVersion,
                            await DataSchemaAsync());

            UpdateState.Text = found.Explanation;
            UpdateNote.Text = found.Verdict switch
            {
                Update.Verdict.UpToDate => "",
                Update.Verdict.Unknown => S("Проверить не вышло — попробуйте позже."),
                Update.Verdict.Incompatible => S("Установить эту пару нельзя."),
                _ => S("Установка появится вместе с установщиком."),
            };
            UpdateState.SetResourceReference(ForegroundProperty,
                found.Verdict is Update.Verdict.Unknown
                                 or Update.Verdict.Incompatible
                    ? "C.Signal" : "C.Ink");
        }
        finally
        {
            CheckNow.IsEnabled = true;
        }
    }

    /// <summary>
    /// Версия ядра: она названа в рукопожатии.
    /// </summary>
    /// <remarks>
    /// Ноль значит «ядра нет на связи». Проверять обновления при этом
    /// можно: оболочка обновляется отдельно от ядра, в этом и смысл
    /// раздельных версий (ADR 0004).
    /// </remarks>
    private string CoreVersion
        => _link?.Connection is { Ready: true, CoreVersion.Length: > 0 } live
            ? live.CoreVersion : "0.0.0";

    /// <summary>
    /// Версия схемы данных на диске.
    /// </summary>
    /// <remarks>
    /// Спрашивается у ядра, потому что на диск пишет оно. Ноль значит «не
    /// знаем» — и тогда откат по схеме не запрещается, а не запрещается
    /// молча: неизвестное число не повод отказать, но и не повод
    /// разрешить, поэтому проверка схемы просто не срабатывает.
    /// </remarks>
    private async Task<int> DataSchemaAsync()
    {
        if (_link?.Connection is not { Ready: true } connection) return 0;
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsGet,
                new JsonObject
                {
                    ["keys"] = new JsonArray("config_version"),
                }, TimeSpan.FromSeconds(10));
            return answer.Payload["values"]?["config_version"]
                   ?.GetValue<int>() ?? 0;
        }
        catch
        {
            return 0;
        }
    }

    /// <summary>
    /// Чем заменить неизвестную версию.
    /// </summary>
    /// <remarks>
    /// Не через `S(...)`: тире — это знак, а не слово, и переводить его
    /// незачем. Строка, попавшая в таблицу переводов зря, требует потом
    /// внимания на каждом языке.
    /// </remarks>
    private const string Unknown = "—";

    /// <summary>Версия оболочки — из сборки, а не из строки в коде.</summary>
    private static string ShellVersion =>
        typeof(AboutPage).Assembly.GetName().Version is { } v
            ? $"{v.Major}.{v.Minor}.{v.Build}" : "4.0.0";

    private async Task ShowPartsAsync()
    {
        Parts.Children.Clear();
        Add(S("Оболочка"), ShellVersion, S("окно, звук, системный слой"));

        var connection = _link?.Connection;
        Add(S("Ядро"),
            connection?.CoreVersion is { Length: > 0 } core ? core : S("нет связи"),
            S("разбор команд, память, речь"));
        Add(S("Протокол"),
            connection is { Ready: true } ready
                ? ready.NegotiatedVersion.ToString() : Unknown,
            S("на чём они разговаривают"));

        // Схема данных — из рукопожатия: файл на диске принадлежит ядру,
        // и как настройка наружу не отдаётся.
        Add(S("Данные на диске"),
            connection is { Ready: true, DataVersion: > 0 } data
                ? data.DataVersion.ToString() : Unknown,
            S("формат настроек и истории"));
        await Task.CompletedTask;
    }

    private void Add(string what, string version, string why)
    {
        var line = new Border { Style = (Style)FindResource("Rows.Item") };
        var row = new Grid();
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(160),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });

        var name = new StackPanel();
        name.Children.Add(new TextBlock
        {
            Text = what,
            Style = (Style)FindResource("Text.Body"),
        });
        name.Children.Add(new TextBlock
        {
            Text = why,
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
        });
        Grid.SetColumn(name, 0);
        row.Children.Add(name);

        var shown = new TextBlock
        {
            Text = version,
            Style = (Style)FindResource("Text.Figure"),
            VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(shown, 1);
        row.Children.Add(shown);

        line.Child = row;
        Parts.Children.Add(line);

        if (Parts.Children[^1] is Border last)
        {
            foreach (var one in Parts.Children.OfType<Border>())
                one.BorderThickness = new Thickness(0, 0, 0, 1);
            last.BorderThickness = new Thickness(0);
        }
    }

    /// <summary>
    /// Где лежат данные, журналы и плагины.
    /// </summary>
    /// <remarks>
    /// Это первое, что спрашивают при разборе неполадки, и последнее, что
    /// человек может найти сам: каталог приложения спрятан в `AppData`, и
    /// путь к нему нельзя ни угадать, ни продиктовать по телефону.
    ///
    /// Папка открывается проводником — тем же способом, каким её открыл бы
    /// человек, если бы знал дорогу.
    /// </remarks>
    private void BuildPlaces()
    {
        var data = System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "RinaAssistant");

        foreach (var (what, path) in new[]
        {
            (S("Настройки, история, команды"), data),
            (S("Журналы"), System.IO.Path.Combine(data, "logs")),
            (S("Плагины"), System.IO.Path.Combine(
                AppContext.BaseDirectory, "..", "..", "..", "..", "plugins")),
        })
        {
            var row = new Border
            {
                Style = (Style)FindResource("Rows.Item"),
            };
            var grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = new GridLength(1, GridUnitType.Star),
            });
            grid.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = GridLength.Auto,
            });

            var about = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            about.Children.Add(new TextBlock
            {
                Text = what,
                Style = (Style)FindResource("Text.Body"),
            });
            about.Children.Add(new TextBlock
            {
                Text = Short(path),
                Style = (Style)FindResource("Text.Meta"),
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = path,
            });
            Grid.SetColumn(about, 0);
            grid.Children.Add(about);

            var open = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Открыть"),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var target = path;
            open.Click += (_, _) => Open(target);
            Grid.SetColumn(open, 1);
            grid.Children.Add(open);

            row.Child = grid;
            Places.Children.Add(row);
        }

        if (Places.Children[^1] is Border tail)
            tail.BorderThickness = new Thickness(0);
    }

    /// <summary>Путь покороче: домашний каталог заменяется на «~».</summary>
    private static string Short(string path)
    {
        try
        {
            var full = System.IO.Path.GetFullPath(path);
            var home = Environment.GetFolderPath(
                Environment.SpecialFolder.UserProfile);
            return home.Length > 0 && full.StartsWith(home)
                ? "~" + full[home.Length..] : full;
        }
        catch
        {
            return path;
        }
    }

    private void BuildLinks()
    {
        foreach (var (title, url) in new[]
        {
            (S("Сайт"), "https://neurosync-foundry-portal.pages.dev/"),
            (S("Исходники"), "https://github.com/Luna-coreX/RinaAssistant"),
            (S("Сообщить о неполадке"),
             "https://github.com/Luna-coreX/RinaAssistant/issues"),
        })
        {
            var button = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = title,
                Margin = new Thickness(0, 0, 8, 0),
                ToolTip = url,
            };
            var target = url;
            button.Click += (_, _) => Open(target);
            Links.Children.Add(button);
        }
    }

    /// <summary>
    /// Открыть ссылку браузером человека.
    /// </summary>
    /// <remarks>
    /// <c>UseShellExecute</c> — то же, что двойной щелчок по ссылке в
    /// проводнике: открывает браузер, который человек выбрал сам. Не
    /// вышло — говорим об этом, а не молчим: неработающая кнопка выглядит
    /// как поломка программы, а не как отсутствие браузера.
    /// </remarks>
    private void Open(string url)
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true,
            });
        }
        catch (Exception error)
        {
            Note.Text = S("Не вышло открыть ссылку: {0}", error.Message);
        }
    }
}
