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
        Loaded += async (_, _) => await ShowPartsAsync();
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
        var row = new Grid { Margin = new Thickness(0, 0, 0, 8) };
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

        Parts.Children.Add(row);
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
