using System.Windows;

namespace Rina.Shell.Pages;

/// <summary>
/// A group of settings shown in a window of its own (<c>4.0b-A10</c>).
/// </summary>
/// <remarks>
/// It knows nothing about settings. The page builds the editors — the same
/// ones it would have put on itself — and hands them over; this only holds
/// them, gives them a heading and a way out. A window that also knew how to
/// build a settings editor would be a second place where that is decided,
/// and the two would answer differently within a month.
/// </remarks>
public partial class SheetWindow : Window
{
    public SheetWindow(string title, string note,
                       IEnumerable<UIElement> content)
    {
        InitializeComponent();
        // It arrives rather than being simply there (`4.0b-E04`).
        Arrival.Animate(this);
        Heading.Text = title;
        Note.Text = note;
        Note.Visibility = note.Length > 0
            ? Visibility.Visible : Visibility.Collapsed;
        foreach (var element in content) Body.Children.Add(element);
    }

    /// <summary>How many things are in it — for the check.</summary>
    public int Rows => Body.Children.Count;

    private void OnClose(object sender, RoutedEventArgs e) => Close();
}
