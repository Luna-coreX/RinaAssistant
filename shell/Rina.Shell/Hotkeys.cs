using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// Глобальные сочетания клавиш.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F06</c>.
/// </para>
/// <para>
/// <b>Обработка идёт максимально рано, и это архитектурное требование, а не
/// придирка к скорости.</b> В 5.0 сюда встанет kill-switch — сочетание,
/// мгновенно снимающее все разрешения и обрывающее управление компьютером
/// (<c>5.0-D08</c>). Ему нельзя ждать очереди: если он окажется за
/// обработкой сообщений окна, за занятым ядром или за чем угодно ещё, он
/// сработает тогда, когда уже поздно.
/// </para>
/// <para>
/// Поэтому сообщение перехватывается в самом начале оконной процедуры, до
/// всякой логики, и обработчик зовётся прямо оттуда. Всё, что он делает,
/// обязано быть быстрым; долгое уходит в другой поток самим обработчиком.
/// </para>
/// <para>
/// <b>Регистрация в системе, а не перехват клавиатуры.</b> `RegisterHotKey`
/// просит систему прислать сообщение и не видит остальных нажатий. Глобальный
/// перехватчик клавиатуры видел бы всё, что человек печатает, — для
/// программы, у которой в настройках есть «не записывать тексты реплик»,
/// это было бы противоречием самой себе.
/// </para>
/// </remarks>
public sealed class Hotkeys : IDisposable
{
    private const int WmHotkey = 0x0312;

    /// <summary>Модификаторы в том виде, в каком их ждёт система.</summary>
    [Flags]
    public enum Mod
    {
        Alt = 0x0001,
        Control = 0x0002,
        Shift = 0x0004,
        Win = 0x0008,
        NoRepeat = 0x4000,
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr window, int id,
                                              uint modifiers, uint key);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr window, int id);

    private readonly Dictionary<int, Action> _bound = [];
    private readonly Dictionary<string, int> _byName = [];
    private HwndSource? _source;
    private IntPtr _handle;
    private int _next = 1;

    /// <summary>Сочетание не удалось занять: его держит другая программа.</summary>
    public event Action<string, string>? Refused;

    public void Attach(Window window)
    {
        _handle = new WindowInteropHelper(window).EnsureHandle();
        _source = HwndSource.FromHwnd(_handle);
        _source?.AddHook(OnMessage);
    }

    private IntPtr OnMessage(IntPtr hwnd, int message, IntPtr wParam,
                             IntPtr lParam, ref bool handled)
    {
        // Раньше всего остального. Ни разбора, ни поиска по словарю сверх
        // одного обращения: здесь начинается путь kill-switch'а.
        if (message != WmHotkey) return IntPtr.Zero;
        if (_bound.TryGetValue(wParam.ToInt32(), out var act))
        {
            handled = true;
            act();
        }
        return IntPtr.Zero;
    }

    /// <summary>
    /// Занять сочетание. `false` — не вышло, и это не исключение.
    /// </summary>
    /// <remarks>
    /// Сочетание, занятое другой программой, — обычное дело, а не сбой: у
    /// человека может стоять что угодно. Он должен об этом узнать и выбрать
    /// другое, а не гадать, почему не работает.
    /// </remarks>
    public bool Bind(string name, string combination, Action action)
    {
        Unbind(name);
        if (!TryParse(combination, out var modifiers, out var key))
        {
            Refused?.Invoke(name, S("не разобрал сочетание «{0}»", combination));
            return false;
        }

        var id = _next++;
        if (!RegisterHotKey(_handle, id, (uint)(modifiers | Mod.NoRepeat), key))
        {
            Refused?.Invoke(name, S("«{0}» занято другой программой", combination));
            return false;
        }
        _bound[id] = action;
        _byName[name] = id;
        return true;
    }

    public void Unbind(string name)
    {
        if (!_byName.TryGetValue(name, out var id)) return;
        UnregisterHotKey(_handle, id);
        _bound.Remove(id);
        _byName.Remove(name);
    }

    /// <summary>Сколько сочетаний занято сейчас.</summary>
    public int Count => _bound.Count;

    /// <summary>
    /// «Ctrl+Shift+R» → модификаторы и код клавиши.
    /// </summary>
    /// <remarks>
    /// Запись та же, что в 3.1.0: настройки переносятся как есть, и
    /// заставлять человека перенабирать семь сочетаний ради нового формата
    /// было бы потерей без выигрыша.
    /// </remarks>
    public static bool TryParse(string combination, out Mod modifiers,
                                out uint key)
    {
        modifiers = 0;
        key = 0;
        if (string.IsNullOrWhiteSpace(combination)) return false;

        foreach (var part in combination.Split('+',
                     StringSplitOptions.RemoveEmptyEntries
                     | StringSplitOptions.TrimEntries))
        {
            switch (part.ToLowerInvariant())
            {
                case "ctrl" or "control": modifiers |= Mod.Control; break;
                case "shift": modifiers |= Mod.Shift; break;
                case "alt": modifiers |= Mod.Alt; break;
                case "win": modifiers |= Mod.Win; break;
                default:
                    if (!Enum.TryParse<Key>(part, true, out var parsed))
                        return false;
                    key = (uint)KeyInterop.VirtualKeyFromKey(parsed);
                    break;
            }
        }
        // Сочетание без модификатора заняло бы клавишу во всей системе:
        // человек нажал бы «R» в чужом редакторе и вызвал Рину.
        return key != 0 && modifiers != 0;
    }

    public void Dispose()
    {
        foreach (var id in _bound.Keys.ToArray()) UnregisterHotKey(_handle, id);
        _bound.Clear();
        _byName.Clear();
        _source?.RemoveHook(OnMessage);
        _source = null;
    }
}
