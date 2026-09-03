using System.Windows;
using System.Windows.Threading;

namespace Rina.Shell.Pages;

/// <summary>Что человек решил.</summary>
public enum Consent
{
    /// <summary>Согласился явно.</summary>
    Granted,
    /// <summary>Отказался явно.</summary>
    Refused,
    /// <summary>Не ответил в срок — то же, что отказ.</summary>
    Expired,
}

/// <summary>
/// Окно подтверждения: единая точка для всех опасных действий.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F11</c>; §11 спецификации.
/// </para>
/// <para>
/// <b>Показывается предпросмотр, а не название действия.</b> «Компьютер
/// будет выключен немедленно» человек успевает осознать; <c>power_action</c>
/// не значит ничего. Это прямое требование §11, и текст приходит от ядра:
/// только оно знает, что именно произойдёт.
/// </para>
/// <para>
/// <b>Отказ по умолчанию.</b> Не ответили в срок — значит «нет». Не «ждём
/// дальше» и не «раз молчит, значит согласен»: молчание может означать, что
/// окна вообще никто не увидел.
/// </para>
/// <para>
/// <b>Закрыть окно — то же, что отказаться.</b> Крестик, Escape и «Отмена»
/// делают одно и то же, потому что человек, закрывающий окно с вопросом об
/// опасном действии, совершенно точно не соглашается.
/// </para>
/// </remarks>
public partial class ConfirmWindow : Window
{
    private readonly DispatcherTimer _timer = new()
    {
        Interval = TimeSpan.FromSeconds(1),
    };
    private DateTimeOffset _deadline;

    /// <summary>Решение человека. До ответа — отказ.</summary>
    public Consent Result { get; private set; } = Consent.Expired;

    /// <summary>Есть ли у вопроса срок. Без срока окно ждёт сколько угодно.</summary>
    public bool Timed { get; }

    /// <param name="ttlSeconds">
    /// Сколько секунд ждать ответа. <b>Ноль или меньше — ждать без срока.</b>
    /// </param>
    /// <remarks>
    /// <para>
    /// Срок нужен не всякому вопросу. Он существует для того, что затеяно
    /// <b>голосом</b>: человек сказал «выключи компьютер», отошёл, и окно
    /// не должно висеть до утра — молчание тогда значит «нет».
    /// </para>
    /// <para>
    /// Вопрос, который человек открыл сам нажатием, — другое дело: он
    /// сидит перед экраном и уже смотрит на окно. Срок здесь означал бы,
    /// что окно исчезнет, пока он читает, — и это ровно то, что случилось
    /// со «Сбросить настройки»: `Math.Max(ttl, 1)` превращал переданный
    /// ноль в одну секунду, и окно пропадало раньше, чем его успевали
    /// прочесть.
    /// </para>
    /// </remarks>
    public ConfirmWindow(string preview, string reason, int ttlSeconds)
    {
        InitializeComponent();
        Preview.Text = preview;
        Reason.Text = reason;

        Timed = ttlSeconds > 0;
        if (Timed)
        {
            _deadline = DateTimeOffset.UtcNow.AddSeconds(ttlSeconds);
            _timer.Tick += OnTick;
            _timer.Start();
            Tick();
        }
        else
        {
            // Показания нет — и место под него не занимаем: пустая ячейка
            // на месте счётчика читалась бы как «сейчас что-то появится».
            Countdown.Visibility = Visibility.Collapsed;
            // Без срока «не ответили» невозможно, поэтому и отказ по
            // умолчанию другой: закрыли окно — отказались.
            Result = Consent.Refused;
        }

        // Опасное не подтверждают по инерции: фокус на отказе, а не на
        // действии. Пробел и Enter тогда отказывают, и случайное нажатие
        // ничего не ломает.
        Loaded += (_, _) => Refuse.Focus();
        Closed += (_, _) => _timer.Stop();
    }

    private void OnTick(object? sender, EventArgs e) => Tick();

    private void Tick()
    {
        var left = _deadline - DateTimeOffset.UtcNow;
        if (left <= TimeSpan.Zero)
        {
            Result = Consent.Expired;
            _timer.Stop();
            Close();
            return;
        }
        // Моноширинные цифры и постоянная ширина: показание прибора не
        // должно дёргаться раз в секунду (§3 дизайн-системы).
        Countdown.Text = $"{(int)left.TotalMinutes:00}:{left.Seconds:00}";
    }

    private void OnConfirm(object sender, RoutedEventArgs e)
    {
        Result = Consent.Granted;
        Close();
    }

    private void OnRefuse(object sender, RoutedEventArgs e)
    {
        Result = Consent.Refused;
        Close();
    }

    /// <summary>Вопрос закрылся сам: человек ответил голосом.</summary>
    public void Withdraw()
    {
        Result = Consent.Expired;
        Close();
    }
}
