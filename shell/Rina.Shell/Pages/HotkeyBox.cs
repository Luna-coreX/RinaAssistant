using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Поле сочетания клавиш: его нажимают, а не набирают.
/// </summary>
/// <remarks>
/// <para>
/// Замечание человека. Сочетание, набранное строкой, — это просьба к
/// человеку знать, как мы его пишем: «Ctrl» или «Control», «Win» или
/// «Super», в каком порядке. Он ошибётся, сочетание не займётся, и
/// причину он узнает только по тому, что клавиши не работают.
/// </para>
/// <para>
/// <b>Записывается то, что нажали.</b> Поле переходит в режим ожидания,
/// ловит следующую комбинацию и показывает её так, как её понимает
/// <see cref="Hotkeys.TryParse"/> — то есть ровно в том виде, в каком она
/// потом займётся.
/// </para>
/// <para>
/// <b>Модификатор обязателен, и об этом говорят сразу.</b> Сочетание без
/// модификатора заняло бы клавишу во всей системе: человек нажал бы «R» в
/// чужом редакторе и вызвал Рину. Раньше это выяснялось при попытке
/// занять; теперь — в тот момент, когда он отпустил клавиши.
/// </para>
/// </remarks>
public sealed class HotkeyBox : StackPanel
{
    private readonly TextBox _shown;
    private readonly Button _record;
    private bool _listening;

    /// <summary>Человек записал новое сочетание.</summary>
    public event Action<string>? Changed;

    /// <summary>Что записано сейчас.</summary>
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

        // Ловим до того, как клавишу увидит поле: иначе Tab уйдёт на
        // переход по фокусу, а Alt — в меню окна, и записать их будет
        // нельзя ровно потому, что они полезные.
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

        // Одни модификаторы — ещё не сочетание: человек держит Ctrl и
        // думает, какую букву нажать.
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

        // Проверяем разбором тем же кодом, который потом займёт сочетание:
        // показать человеку то, что мы сами не сумеем прочитать, — способ
        // соврать ему в лицо.
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
