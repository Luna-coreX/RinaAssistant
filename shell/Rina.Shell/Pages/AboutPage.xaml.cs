using System.Text.Json.Nodes;
using Rina.Protocol;
using System.Diagnostics;
using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// About: what it is built from and where to go.
/// </summary>
/// <remarks>
/// <para>
/// Noted by a person: "about" in the footer was text that could not be
/// clicked.
/// </para>
/// <para>
/// <b>There are four versions, and all four are shown.</b> This follows
/// directly from
/// [ADR 0004](../../../docs/adr/0004-versioning-and-compatibility.md): the
/// shell, the core, the protocol and the data schema are updated
/// separately, and the question "what version do I have" without saying
/// "of what" no longer has a single answer. Someone who came here because
/// of a fault needs all four — otherwise they will name one and be asked
/// about another.
/// </para>
/// <para>
/// <b>A link opens in the browser, not inside the window.</b> Rina has no
/// browser of her own and never will: a page opened inside an assistant is
/// somebody else's code that we handed our own window to.
/// </para>
/// </remarks>
public partial class AboutPage : UserControl
{
    private readonly CoreLink? _link;

    /// <summary>How many "built from" rows — for the end-to-end check.</summary>
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

    /// <summary>What the last check said — for the end-to-end check.</summary>
    public string UpdateSaid => UpdateState.Text;

    /// <summary>
    /// Ask whether there is anything newer.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Plan item <c>4.0-U03</c>. The client lives in the shell
    /// ([ADR 0009](../../../docs/adr/0009-system-layer.md)): downloading a
    /// file and putting it on disk is the system layer's work, and only
    /// whoever stops the core may replace the core's files.
    /// </para>
    /// <para>
    /// <b>The button is always there, even when the automatic check is
    /// off.</b> The `check_updates` setting governs whether we ask on our
    /// own; a person who came to ask by hand has already answered that
    /// question.
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
    /// The core's version: it is named in the handshake.
    /// </summary>
    /// <remarks>
    /// Zero means "the core is not connected". Checking for updates is
    /// still allowed then: the shell updates separately from the core, and
    /// that is the whole point of separate versions (ADR 0004).
    /// </remarks>
    private string CoreVersion
        => _link?.Connection is { Ready: true, CoreVersion.Length: > 0 } live
            ? live.CoreVersion : "0.0.0";

    /// <summary>
    /// The version of the data schema on disk.
    /// </summary>
    /// <remarks>
    /// Asked of the core, because the core is what writes to disk. Zero
    /// means "we do not know" — and then a rollback is not forbidden by
    /// schema, and not forbidden in silence either: an unknown number is no
    /// reason to refuse, but no reason to allow either, so the schema check
    /// simply does not fire.
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
    /// What to put in place of an unknown version.
    /// </summary>
    /// <remarks>
    /// Not through `S(...)`: a dash is a mark, not a word, and there is no
    /// point translating it. A string that ends up in the translation table
    /// for nothing demands attention in every language afterwards.
    /// </remarks>
    private const string Unknown = "—";

    /// <summary>The shell's version — from the assembly, not from a string in the code.</summary>
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

        // The data schema comes from the handshake: the file on disk
        // belongs to the core, and it is not handed out as a setting.
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
    /// Where the data, the logs and the plugins live.
    /// </summary>
    /// <remarks>
    /// This is the first thing asked when a fault is being sorted out, and
    /// the last thing a person can find on their own: the application
    /// directory is hidden away in `AppData`, and the path to it can
    /// neither be guessed nor dictated over the phone.
    ///
    /// The folder is opened by the file manager — the same way a person
    /// would open it if they knew the road.
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

    /// <summary>A shorter path: the home directory is replaced by "~".</summary>
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
    /// Open a link in the person's browser.
    /// </summary>
    /// <remarks>
    /// <c>UseShellExecute</c> is the same as double-clicking a link in the
    /// file manager: it opens the browser the person chose themselves. If
    /// it did not work, we say so instead of keeping quiet: a button that
    /// does nothing looks like a broken program rather than a missing
    /// browser.
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
