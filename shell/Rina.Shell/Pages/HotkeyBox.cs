using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// A hotkey field: it is pressed, not typed.
/// </summary>
/// <remarks>
/// <para>
/// Noted by a person. A combination typed as text is a request that the
/// person know how we spell it: "Ctrl" or "Control", "Win" or "Super", in
/// what order. They will get it wrong, the combination will not be
/// registered, and they will learn the reason only from the keys not
/// working.
/// </para>
/// <para>
/// <b>What gets recorded is what was pressed.</b> The field goes into a
/// waiting state, catches the next combination and shows it the way
/// <see cref="Hotkeys.TryParse"/> understands it — that is, exactly as it
/// will be registered afterwards.
/// </para>
/// <para>
/// <b>A modifier is required, and that is said right away.</b> A
/// combination without a modifier would take the key over the whole
/// system: a person would press "R" in someone else's editor and summon
/// Rina. Before, this came out at registration time; now it comes out the
/// moment they let go of the keys.
/// </para>
/// </remarks>
public sealed class HotkeyBox : StackPanel
{
    private readonly TextBox _shown;
    private readonly Button _record;
    private bool _listening;

    /// <summary>A person recorded a new combination.</summary>
    public event Action<string>? Changed;

    /// <summary>What is recorded right now.</summary>
    public string Combination { get; private set; }

    public HotkeyBox(string current)
    {
        Orientation = Orientation.Horizontal;
        Combination = current ?? "";

        _shown = new TextBox
        {
            Style = (Style)Application.Current.FindResource("Field"),
            Width = 200,
            IsReadOnly = true,
            Text = Combination.Length > 0 ? Combination : S("не назначено"),
            Focusable = true,
        };

        _record = new Button
        {
            Style = (Style)Application.Current.FindResource("Btn"),
            Content = S("Записать"),
            Margin = new Thickness(8, 0, 0, 0),
        };
        _record.Click += (_, _) => Listen();

        var clear = new Button
        {
            Style = (Style)Application.Current.FindResource("Btn"),
            Content = S("Убрать"),
            Margin = new Thickness(8, 0, 0, 0),
        };
        clear.Click += (_, _) => Accept("");

        Children.Add(_shown);
        Children.Add(_record);
        Children.Add(clear);

        // Catch it before the field sees the key: otherwise Tab would go to
        // focus navigation and Alt into the window menu, and recording them
        // would be impossible for exactly the reason they are useful.
        _shown.PreviewKeyDown += OnKey;
        _shown.LostKeyboardFocus += (_, _) => Stop();
    }

    private void Listen()
    {
        _listening = true;
        _shown.Text = S("нажмите сочетание…");
        _record.Content = S("Жду");
        _shown.Focus();
        Keyboard.Focus(_shown);
    }

    private void Stop()
    {
        if (!_listening) return;
        _listening = false;
        _record.Content = S("Записать");
        _shown.Text = Combination.Length > 0 ? Combination : S("не назначено");
    }

    private void OnKey(object sender, KeyEventArgs e)
    {
        if (!_listening) return;
        e.Handled = true;

        var key = e.Key == Key.System ? e.SystemKey : e.Key;
        if (key == Key.Escape) { Stop(); return; }

        // Modifiers alone are not a combination yet: the person is holding
        // Ctrl and thinking about which letter to press.
        if (key is Key.LeftCtrl or Key.RightCtrl or Key.LeftShift
                or Key.RightShift or Key.LeftAlt or Key.RightAlt
                or Key.LWin or Key.RWin)
            return;

        var parts = new List<string>();
        var modifiers = Keyboard.Modifiers;
        if (modifiers.HasFlag(ModifierKeys.Control)) parts.Add("Ctrl");
        if (modifiers.HasFlag(ModifierKeys.Shift)) parts.Add("Shift");
        if (modifiers.HasFlag(ModifierKeys.Alt)) parts.Add("Alt");
        if (modifiers.HasFlag(ModifierKeys.Windows)) parts.Add("Win");

        if (parts.Count == 0)
        {
            _shown.Text = S("нужен Ctrl, Alt, Shift или Win");
            return;
        }

        parts.Add(key.ToString());
        var combination = string.Join("+", parts);

        // Check by parsing with the same code that will register the
        // combination later: showing a person something we cannot read
        // ourselves is a way of lying to their face.
        if (!Hotkeys.TryParse(combination, out _, out _))
        {
            _shown.Text = S("такое сочетание не подойдёт");
            return;
        }

        Accept(combination);
    }

    private void Accept(string combination)
    {
        Combination = combination;
        _listening = false;
        _record.Content = S("Записать");
        _shown.Text = combination.Length > 0 ? combination : S("не назначено");
        Changed?.Invoke(combination);
    }
}
