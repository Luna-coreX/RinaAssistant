using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace Rina.Shell.Overlays;

/// <summary>
/// Ответ Рины поверх экрана — своим окном, а не уведомлением системы.
/// </summary>
/// <remarks>
/// <para>
/// Замечание человека: в 3.1.0 ответ показывался своим окном, после
/// переезда — системным уведомлением. Разница не косметическая.
/// </para>
/// <para>
/// <b>Системное уведомление — это почта, а не разговор.</b> Оно ложится в
/// центр уведомлений, ждёт там, показывается по правилам Windows (включая
/// «не беспокоить», при котором его не увидят вовсе) и выглядит как
/// сообщение от программы. Ответ на «который час» — не сообщение от
/// программы, а реплика в разговоре: он нужен сейчас, две секунды, и
/// хранить его незачем.
/// </para>
/// <para>
/// <b>Окно не забирает фокус.</b> <c>ShowActivated=false</c> обязателен:
/// человек говорит с Риной, не отрываясь от своей работы, и окно, которое
/// перехватывает набор текста в чужом редакторе, хуже молчания.
/// </para>
/// <para>
/// <b>Одно окно, а не по одному на реплику.</b> Вторая реплика подменяет
/// текст в том же окне и продлевает срок: стопка карточек в углу — это
/// шум, а не разговор.
/// </para>
/// </remarks>
public partial class Toast : Window
{
    private readonly DispatcherTimer _hide = new();

    /// <summary>Сколько живёт обычная реплика.</summary>
    public static readonly TimeSpan Normal = TimeSpan.FromSeconds(6);

    /// <summary>Короткая — для «слушаю», «готово» и прочего мимолётного.</summary>
    public static readonly TimeSpan Short = TimeSpan.FromSeconds(2.6);

    public Toast()
    {
        InitializeComponent();
        _hide.Tick += (_, _) => FadeOut();
        // Клик прячет: реплика прочитана, и ждать её ухода незачем.
        MouseLeftButtonDown += (_, _) => FadeOut();
    }

    /// <summary>Что показано сейчас — для сквозной проверки.</summary>
    public string Shown => Body.Text;

    /// <summary>
    /// Показать реплику. Повторный вызов подменяет текст, а не плодит окна.
    /// </summary>
    public void Say(string text, TimeSpan? life = null)
    {
        if (string.IsNullOrWhiteSpace(text)) return;

        Body.Text = text;
        Place();
        if (!IsVisible) Show();

        Card.BeginAnimation(OpacityProperty, new DoubleAnimation(
            Card.Opacity, 1, TimeSpan.FromMilliseconds(140)));
        Slide.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(
            Slide.Y, 0, TimeSpan.FromMilliseconds(140)));

        _hide.Stop();
        _hide.Interval = life ?? Normal;
        _hide.Start();
    }

    /// <summary>Убрать немедленно: разговор продолжился в окне.</summary>
    public void Dismiss()
    {
        _hide.Stop();
        FadeOut();
    }

    private void FadeOut()
    {
        _hide.Stop();
        var fade = new DoubleAnimation(Card.Opacity, 0,
                                       TimeSpan.FromMilliseconds(180));
        fade.Completed += (_, _) => { if (Card.Opacity <= 0.01) Hide(); };
        Card.BeginAnimation(OpacityProperty, fade);
        Slide.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(
            Slide.Y, 12, TimeSpan.FromMilliseconds(180)));
    }

    /// <summary>
    /// Правый нижний угол рабочей области.
    /// </summary>
    /// <remarks>
    /// Рабочей, а не экрана: иначе окно ляжет под панель задач. Отступ
    /// такой же, как у системных уведомлений, — человек уже знает, куда
    /// смотреть.
    /// </remarks>
    private void Place()
    {
        var area = SystemParameters.WorkArea;
        UpdateLayout();
        var height = Card.ActualHeight > 0 ? Card.ActualHeight : 80;
        Left = area.Right - Width - 24;
        Top = area.Bottom - height - 24;
    }
}
