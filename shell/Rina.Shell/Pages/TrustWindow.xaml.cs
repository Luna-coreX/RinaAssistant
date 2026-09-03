using System.IO;
using System.Windows;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// «Эта программа не подписана» — спросить перед первым запуском.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-G10</c>.
/// </para>
/// <para>
/// <b>Показывается всё, чем можно решать</b>: имя, полный путь, источник
/// индекса. Вопрос «доверяете ли вы этой программе» без пути — это вопрос
/// без ответа: половина неподписанного лежит в папках, куда человек её сам
/// и положил, а вторая половина — там, куда её положил кто-то другой.
/// </para>
/// <para>
/// <b>Три ответа, а не два.</b> «Один раз» существует потому, что «нет» и
/// «навсегда да» — плохая пара: человек, которому нужно запустить это
/// сейчас, выберет «навсегда» просто чтобы продолжить.
/// </para>
/// <para>
/// <b>Рамка акцентом, а не красным.</b> Красного в палитре нет вовсе
/// (<c>4.0-R07</c>): цвет опасности размывается от повторения. Здесь он и
/// не нужен — вопрос задан словами.
/// </para>
/// </remarks>
public partial class TrustWindow : Window
{
    /// <summary>Что ответил человек.</summary>
    public enum Reply
    {
        /// <summary>Не запускать.</summary>
        Never,

        /// <summary>Запустить сейчас, но не запоминать.</summary>
        Once,

        /// <summary>Запускать всегда без вопросов.</summary>
        Always,
    }

    /// <summary>
    /// Ответ. По умолчанию — отказ.
    /// </summary>
    /// <remarks>
    /// Закрытое окно значит «нет», а не «да»: молчание не согласие, тем
    /// более на запуск неподписанного.
    /// </remarks>
    public Reply Answer { get; private set; } = Reply.Never;

    public TrustWindow(string path, string source = "")
    {
        InitializeComponent();

        AppName.Text = Path.GetFileName(path);
        AppPath.Text = path;
        AppSource.Text = source.Length > 0
            ? S("Источник: {0}", source)
            : S("Источник неизвестен");
    }

    private void OnOnce(object sender, RoutedEventArgs e) => Decide(Reply.Once);

    private void OnAlways(object sender, RoutedEventArgs e)
        => Decide(Reply.Always);

    private void OnNever(object sender, RoutedEventArgs e) => Decide(Reply.Never);

    private void Decide(Reply reply)
    {
        Answer = reply;
        Close();
    }
}
