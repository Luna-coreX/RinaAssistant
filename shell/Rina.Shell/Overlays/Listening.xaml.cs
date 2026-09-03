using System.Windows;
using System.Windows.Media.Animation;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Overlays;

/// <summary>
/// Плашка «слушаю» поверх экрана.
/// </summary>
/// <remarks>
/// <para>
/// Замечание человека: в 3.1.0 включённое «всегда слушать» и вызов
/// сочетанием были видны на экране, после переезда — нет.
/// </para>
/// <para>
/// <b>Микрофон, работающий незаметно, — это не мелочь интерфейса.</b>
/// Человек имеет право видеть, что его слушают, не открывая окна и не
/// вспоминая, нажимал ли он что-то полчаса назад. Поэтому плашка
/// появляется на всё время слушания, а не мигает на секунду.
/// </para>
/// <para>
/// <b>Два состояния, а не одно.</b> «Слушаю» разовое — по сочетанию, на
/// несколько секунд; «всегда слушаю» — режим, включённый до отмены. Они
/// выглядят по-разному, потому что значат разное: первое кончится само,
/// второе — нет.
/// </para>
/// <para>
/// Сверху по центру, а не в углу: там её видно, не отводя глаз от того,
/// чем человек занят, и она не спорит с уведомлениями внизу справа.
/// </para>
/// </remarks>
public partial class Listening : Window
{
    private bool _always;

    public Listening()
    {
        InitializeComponent();
    }

    /// <summary>
    /// Режим «всегда слушаю».
    /// </summary>
    /// <remarks>
    /// Нужен снаружи: разовое слушание кончается событием
    /// `listening.stopped`, и по нему плашку надо убрать — но не тогда,
    /// когда включён режим. Иначе первая же распознанная фраза погасила бы
    /// признак того, что микрофон продолжает работать.
    /// </remarks>
    public bool Always => _always && IsVisible;

    /// <summary>Видна ли плашка — для сквозной проверки.</summary>
    public bool Visible => IsVisible && Card.Opacity > 0.5;

    /// <summary>Что на ней написано — для сквозной проверки.</summary>
    public string Caption => Label.Text;

    /// <summary>
    /// Показать. <paramref name="always"/> — режим, а не разовое слушание.
    /// </summary>
    public void Appear(bool always)
    {
        _always = always;
        Label.Text = always ? S("Всегда слушаю") : S("Слушаю…");
        Place();
        if (!IsVisible) Show();

        Card.BeginAnimation(OpacityProperty, new DoubleAnimation(
            Card.Opacity, 1, TimeSpan.FromMilliseconds(140)));
        Pulse();
    }

    /// <summary>Спрятать. Режим «всегда» так не гасится — только отменой.</summary>
    public void Vanish()
    {
        _always = false;
        Dot.BeginAnimation(OpacityProperty, null);
        var fade = new DoubleAnimation(Card.Opacity, 0,
                                       TimeSpan.FromMilliseconds(180));
        fade.Completed += (_, _) => { if (Card.Opacity <= 0.01) Hide(); };
        Card.BeginAnimation(OpacityProperty, fade);
    }

    /// <summary>
    /// Точка дышит, пока слушают.
    /// </summary>
    /// <remarks>
    /// В режиме «всегда» медленнее: быстрое мигание час подряд —
    /// раздражитель, а не сообщение.
    /// </remarks>
    private void Pulse()
    {
        var beat = new DoubleAnimation(1.0, 0.35, new Duration(
            TimeSpan.FromMilliseconds(_always ? 1600 : 900)))
        {
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever,
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
        };
        Dot.BeginAnimation(OpacityProperty, beat);
    }

    private void Place()
    {
        var area = SystemParameters.WorkArea;
        UpdateLayout();
        Left = area.Left + (area.Width - ActualWidth) / 2;
        Top = area.Top + 24;
    }
}
