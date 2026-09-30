using System.IO;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// A screenshot.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-G03</c>.
/// </para>
/// <para>
/// <b>Captures every monitor at once.</b> Someone asking for a screenshot
/// means what they see, and what they see is two screens. Capturing only
/// the primary one cuts half of it away without warning.
/// </para>
/// <para>
/// <b>The bounds come from the system in physical pixels</b>
/// (<c>GetSystemMetrics</c>), not from WPF: WPF reports them in
/// device-independent units, and on a display scaled to 150% the capture
/// would come out short by exactly a third. We do not take a dependency
/// on WinForms for the sake of one rectangle either.
/// </para>
/// <para>
/// <b>Into Pictures, not into a hidden folder.</b> A screenshot exists to
/// be sent somewhere; one that cannot be found is useless. The path is
/// returned outward — the core will tell the person where it is.
/// </para>
/// <para>
/// In 3.1.0 this was done by Qt and only from the interface thread. There
/// is no such restriction here: <c>CopyFromScreen</c> works from any
/// thread, and a screenshot stopped being something one has to ask the
/// window for.
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

    /// <summary>Capture the screen to a file. Empty string — it did not work.</summary>
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
