using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// Снимок экрана.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-G03</c>.
/// </para>
/// <para>
/// <b>Снимает все мониторы разом.</b> Человек, просящий снимок, имеет в
/// виду то, что видит, а видит он два экрана. Снять только основной значит
/// отрезать половину без предупреждения.
/// </para>
/// <para>
/// <b>Границы берутся у системы в физических точках</b>
/// (<c>GetSystemMetrics</c>), а не у WPF: у WPF они в независимых от
/// плотности единицах, и на экране с масштабом 150% снимок вышел бы
/// обрезанным ровно на треть. Своей зависимости от WinForms ради одного
/// прямоугольника мы при этом не заводим.
/// </para>
/// <para>
/// <b>В «Изображения», а не в скрытую папку.</b> Снимок нужен, чтобы его
/// куда-то отправить; лежащий там, где его не найти, бесполезен. Путь
/// возвращается наружу — ядро скажет его человеку.
/// </para>
/// <para>
/// В 3.1.0 это делал Qt и только из потока интерфейса. Здесь ограничения
/// нет: <c>CopyFromScreen</c> работает из любого потока, и снимок перестал
/// быть операцией, которую надо просить у окна.
/// </para>
/// </remarks>
public static class Screen
{
    private const int VirtualLeft = 76;
    private const int VirtualTop = 77;
    private const int VirtualWidth = 78;
    private const int VirtualHeight = 79;

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int index);

    /// <summary>Снять экран в файл. Пустая строка — не вышло.</summary>
    public static string Grab()
    {
        try
        {
            var left = GetSystemMetrics(VirtualLeft);
            var top = GetSystemMetrics(VirtualTop);
            var width = GetSystemMetrics(VirtualWidth);
            var height = GetSystemMetrics(VirtualHeight);
            if (width <= 0 || height <= 0) return "";

            using var shot = new Bitmap(width, height);
            using (var canvas = Graphics.FromImage(shot))
                canvas.CopyFromScreen(left, top, 0, 0, new Size(width, height));

            var folder = Environment.GetFolderPath(
                Environment.SpecialFolder.MyPictures);
            if (!Directory.Exists(folder))
                folder = Environment.GetFolderPath(
                    Environment.SpecialFolder.UserProfile);

            var path = Path.Combine(
                folder, $"rina_{DateTime.Now:yyyy-MM-dd_HH-mm-ss}.png");
            shot.Save(path, ImageFormat.Png);
            return path;
        }
        catch
        {
            return "";
        }
    }
}
