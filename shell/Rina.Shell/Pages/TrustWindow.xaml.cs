using System.IO;
using System.Windows;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// "This program is not signed" — ask before the first launch.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-G10</c>.
/// </para>
/// <para>
/// <b>Everything one can decide by is shown</b>: the name, the full path,
/// the source of the index. The question "do you trust this program"
/// without a path is a question with no answer: half of the unsigned
/// software lives in folders the person put it in themselves, and the
/// other half is where somebody else put it.
/// </para>
/// <para>
/// <b>Three answers, not two.</b> "Once" exists because "no" and "yes,
/// forever" are a bad pair: a person who needs to run this now will pick
/// "forever" simply to get on with it.
/// </para>
/// <para>
/// <b>An accent border, not a red one.</b> There is no red in the palette
/// at all (<c>4.0-R07</c>): the colour of danger wears out through
/// repetition. It is not needed here either — the question is asked in
/// words.
/// </para>
/// </remarks>
public partial class TrustWindow : Window
{
    /// <summary>What the person answered.</summary>
    public enum Reply
    {
        /// <summary>Do not launch.</summary>
        Never,

        /// <summary>Launch now, but do not remember it.</summary>
        Once,

        /// <summary>Always launch without asking.</summary>
        Always,
    }

    /// <summary>
    /// The answer. Refusal by default.
    /// </summary>
    /// <remarks>
    /// A closed window means "no", not "yes": silence is not consent, all
    /// the less so for launching something unsigned.
    /// </remarks>
    public Reply Answer { get; private set; } = Reply.Never;

    /// <param name="path">What runs: for a shortcut, its target.</param>
    /// <param name="source">Where the index found it.</param>
    /// <param name="arguments">What a shortcut hands its target.</param>
    /// <param name="via">The shortcut, when what runs is reached through one.</param>
    public TrustWindow(string path, string source = "", string arguments = "",
                       string via = "")
    {
        InitializeComponent();
        // It arrives rather than being simply there (`4.0b-E04`).
        Arrival.Animate(this);

        // A signed host given a command is not "an unsigned program": what
        // is unvouched for is the command (audit 2026-10-07, M-3). Said as
        // it is, so the question reads as the one being asked.
        if (Platform.Trust.RunsCommand(path, arguments))
        {
            Headline.Text = S("Ярлык запускает команду");
            Why.Text = S("Программа, которая выполняет любые команды, получит вот эту. Подпись программы ничего не говорит о самой команде.");
        }

        AppName.Text = Path.GetFileName(path);
        AppPath.Text = arguments.Length > 0 ? $"{path} {arguments}" : path;
        var where = source.Length > 0
            ? S("Источник: {0}", source)
            : S("Источник неизвестен");
        AppSource.Text = via.Length > 0
            ? where + "\n" + S("Через ярлык: {0}", via)
            : where;
    }

    private void OnOnce(object sender, RoutedEventArgs e) => Decide(Reply.Once);

    private void OnAlways(object sender, RoutedEventArgs e)
        => Decide(Reply.Always);

    private void OnNever(object sender, RoutedEventArgs e) => Decide(Reply.Never);

    private void Decide(Reply reply)
    {
        Answer = reply;
        Close();
    }
}
