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

    public TrustWindow(string path, string source = "")
    {
        InitializeComponent();

        AppName.Text = Path.GetFileName(path);
        AppPath.Text = path;
        AppSource.Text = source.Length > 0
            ? S("Источник: {0}", source)
            : S("Источник неизвестен");
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
