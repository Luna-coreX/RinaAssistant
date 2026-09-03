using System.Windows;
using System.Windows.Input;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// Плавающая строка команд: сказать Рине, не открывая окна.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F04</c> — настройка `floating_command_bar`
/// существовала с 3.1.0 и в 4.0 не делала ничего. Переключатель, который
/// ничего не переключает, хуже отсутствующего: человек считает, что
/// включил, и ждёт поведения.
/// </para>
/// <para>
/// <b>Строка живёт поверх окон и не занимает панель задач.</b> В этом весь
/// смысл: набрать команду посреди чужой работы, не переключаясь. Поэтому
/// же у неё нет рамки и заголовка — перетаскивается за себя саму.
/// </para>
/// <para>
/// <b>Esc прячет, а не закрывает.</b> Закрытая строка потребовала бы снова
/// идти в настройки; спрятанная возвращается тем же сочетанием, которым
/// вызвана.
/// </para>
/// </remarks>
public partial class FloatingBar : Window
{
    private readonly CoreLink? _link;

    public FloatingBar(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        // Снизу по центру основного экрана: там, где её ждут глаза, и там,
        // где она не накрывает то, с чем человек работает.
        var screen = SystemParameters.WorkArea;
        Left = screen.Left + (screen.Width - Width) / 2;
        Top = screen.Bottom - 96;
    }

    /// <summary>Показать и отдать ей ввод.</summary>
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

        // Ответ придёт событием и покажется в окне разговора или
        // уведомлением: строка — это способ сказать, а не место для беседы.
        State.Text = S("Отправлено");
        await (_link?.HandleAsync(text) ?? Task.CompletedTask);
        State.Text = S("Enter — отправить, Esc — скрыть");
    }
}
