using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The second question before the beta's telemetry is switched on.
/// </summary>
/// <remarks>
/// <para>
/// Asked for by the person (2026-09-29): switching telemetry on is one
/// click — a box in the wizard, a row in settings — and what it starts is
/// a report a day to somebody else's server. So the click is answered with
/// what exactly leaves, how often, what never does and where to look, and
/// only an explicit «Включить» turns it on. Anything else — «Не включать»,
/// Escape, closing the window — leaves it off.
/// </para>
/// <para>
/// Switching it off is never asked about: it takes nothing from anybody.
/// </para>
/// </remarks>
public partial class TelemetryConsent : Window
{
    /// <summary>What is said about the telemetry, here and in the wizard.</summary>
    /// <remarks>
    /// One list for both, so that the step and the question cannot come to
    /// describe two different reports.
    /// </remarks>
    public static IReadOnlyList<(string Title, string Said)> Explained() =>
    [
        (S("Уходит"),
         S("Версия программы и Windows, какие команды и инструменты срабатывали и сколько раз, коды ошибок, время распознавания и первого звука, случайный номер установки.")),
        (S("Как часто"),
         S("Не чаще раза в сутки. Первый отчёт — через сутки после включения; если Рина в это время выключена, то вскоре после следующего запуска.")),
        (S("Не уходит никогда"),
         S("Что вы сказали или напечатали, звук, пути и имена файлов, названия ваших плагинов, адреса, пароли и ключи.")),
        (S("Где посмотреть и выключить"),
         S("Каждый ушедший отчёт виден целиком на странице «Что Рина знает обо мне». Выключается в настройках, в разделе «Приватность». В 4.0.0 Stable телеметрии не будет.")),
    ];

    /// <summary>The person pressed «Включить».</summary>
    public bool Agreed { get; private set; }

    /// <summary>For the checks: answers in place of a person.</summary>
    /// <remarks>
    /// A check that opens a modal window waits for a click nobody will
    /// make. The question itself is still counted in <see cref="Asked"/>,
    /// so a check can tell "asked and refused" from "never asked".
    /// </remarks>
    public static Func<bool>? Answer { get; set; }

    /// <summary>How many times the question was put — for the checks.</summary>
    public static int Asked { get; private set; }

    /// <summary>Ask. True only for an explicit «Включить».</summary>
    public static bool Ask(Window? owner)
    {
        Asked++;
        if (Answer is { } answer) return answer();
        var window = new TelemetryConsent();
        if (owner is { IsLoaded: true, IsVisible: true }) window.Owner = owner;
        else window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
        window.ShowDialog();
        return window.Agreed;
    }

    public TelemetryConsent()
    {
        InitializeComponent();
        // It arrives rather than being simply there (`4.0b-E04`).
        Arrival.Animate(this);
        foreach (var (title, said) in Explained())
        {
            Body.Children.Add(new TextBlock
            {
                Text = title,
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 14, 0, 2),
            });
            Body.Children.Add(new TextBlock
            {
                Text = said,
                Style = (Style)FindResource("Text.Body"),
                TextWrapping = TextWrapping.Wrap,
            });
        }
    }

    private void OnAgree(object sender, RoutedEventArgs e)
    {
        Agreed = true;
        Close();
    }

    private void OnDecline(object sender, RoutedEventArgs e) => Close();
}
