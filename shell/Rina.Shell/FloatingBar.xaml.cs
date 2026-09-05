using System.Windows;
using System.Windows.Input;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// The floating command bar: say something to Rina without opening a window.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F04</c> — the `floating_command_bar` setting had
/// existed since 3.1.0 and did nothing in 4.0. A switch that switches
/// nothing is worse than a missing one: a person believes they turned it
/// on and waits for the behaviour.
/// </para>
/// <para>
/// <b>The bar lives above other windows and takes no taskbar slot.</b>
/// That is the whole point: type a command in the middle of someone
/// else's work without switching away. For the same reason it has no
/// border and no title — it is dragged by itself.
/// </para>
/// <para>
/// <b>Esc hides, it does not close.</b> A closed bar would mean going back
/// into settings; a hidden one comes back with the same hotkey that
/// summoned it.
/// </para>
/// </remarks>
public partial class FloatingBar : Window
{
    private readonly CoreLink? _link;

    public FloatingBar(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        // Bottom centre of the main screen: where the eyes expect it, and
        // where it does not cover what the person is working with.
        var screen = SystemParameters.WorkArea;
        Left = screen.Left + (screen.Width - Width) / 2;
        Top = screen.Bottom - 96;
    }

    /// <summary>Show it and give it the input.</summary>
    public void Summon()
    {
        Show();
        Activate();
        Input.Focus();
        Input.SelectAll();
    }

    private void OnDrag(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState == MouseButtonState.Pressed) DragMove();
    }

    private async void OnKey(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape) { Hide(); return; }
        if (e.Key != Key.Enter) return;

        var text = Input.Text.Trim();
        if (text.Length == 0) return;
        Input.Clear();

        // The answer comes as an event and is shown in the conversation
        // window or as a notification: the bar is a way to speak, not a
        // place to converse.
        State.Text = S("Отправлено");
        await (_link?.HandleAsync(text) ?? Task.CompletedTask);
        State.Text = S("Enter — отправить, Esc — скрыть");
    }
}
