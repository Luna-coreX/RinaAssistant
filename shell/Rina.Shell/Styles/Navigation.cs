using System.ComponentModel;
using System.Windows;
using System.Windows.Input;

namespace Rina.Shell.Styles;

/// <summary>
/// Whether the person is getting about by keyboard right now.
/// </summary>
/// <remarks>
/// <para>
/// <b>The focus ring is for somebody who cannot see the pointer.</b> It
/// exists so a keyboard user knows where they are — and it was drawn
/// after a mouse click too, because in WPF clicking a button gives it
/// keyboard focus as well. So a person who clicked the menu got a
/// bright rectangle round it and no idea why. Reported as "this outline
/// looks out of place, better remove it", and removing it would have
/// taken the ring away from the one person who needs it.
/// </para>
/// <para>
/// So it is shown by what was last used. Tab and the arrows say
/// "keyboard"; a press of the mouse says "pointer". Nothing is
/// remembered between runs and nothing is stored: this is the state of
/// one moment.
/// </para>
/// </remarks>
public sealed class Navigation : INotifyPropertyChanged
{
    public static Navigation Current { get; } = new();

    private bool _byKeyboard;

    public bool ByKeyboard
    {
        get => _byKeyboard;
        private set
        {
            if (_byKeyboard == value) return;
            _byKeyboard = value;
            PropertyChanged?.Invoke(this,
                new PropertyChangedEventArgs(nameof(ByKeyboard)));
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>Listen once, for the whole application.</summary>
    /// <remarks>
    /// Class handlers rather than a subscription per window: a window
    /// opened later — the wizard, a settings sheet — would otherwise
    /// have to remember to join in, and one of them never would.
    /// </remarks>
    public static void Watch()
    {
        EventManager.RegisterClassHandler(
            typeof(UIElement), UIElement.PreviewKeyDownEvent,
            new KeyEventHandler((_, e) =>
            {
                // Only the keys that move focus. Typing into a field is
                // not getting about: the ring would appear round the
                // field somebody is already looking at.
                if (e.Key is Key.Tab or Key.Left or Key.Right or Key.Up
                    or Key.Down or Key.Home or Key.End)
                    Current.ByKeyboard = true;
            }), true);

        EventManager.RegisterClassHandler(
            typeof(UIElement), UIElement.PreviewMouseDownEvent,
            new MouseButtonEventHandler((_, _) => Current.ByKeyboard = false),
            true);
    }
}
