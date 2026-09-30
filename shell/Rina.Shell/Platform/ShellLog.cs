using System.IO;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// The shell's own journal: <c>logs/shell.log</c>.
/// </summary>
/// <remarks>
/// <para>
/// There was none. The core writes <c>rina.log</c> and both layers write
/// <c>security.log</c>, but the shell's own failures went nowhere: no
/// handler for an unhandled exception, so a fault in the window closed it
/// without a line anywhere Rina keeps; a core that died was restarted and
/// shown as "reconnecting", and its exit code and last words were gone
/// with the process. The diagnostic package collects <c>logs/</c> whole,
/// so this file reaches it without a change there.
/// </para>
/// <para>
/// <b>No conversation here, ever.</b> What the shell writes is its own
/// state: exceptions, the core's exits, a wizard that would not open. The
/// core's last lines come from its error stream, which carries the same
/// journal lines as <c>rina.log</c> — already made safe there.
/// </para>
/// <para>
/// Small and rotated once: a megabyte, and one previous file. This is for
/// the last failure, like the core's journal, not for history.
/// </para>
/// </remarks>
public static class ShellLog
{
    private const long MaxBytes = 1024 * 1024;
    private static readonly object Lock = new();

    /// <summary>Where it is written — so checks look in the same place.</summary>
    public static string Where =>
        Path.Combine(DataFolder.Roaming, "logs", "shell.log");

    public static void Info(string what) => Write("INFO", what);

    public static void Warn(string what) => Write("WARNING", what);

    /// <summary>An exception, with where it was caught.</summary>
    public static void Error(string where, Exception error) =>
        Write("ERROR", $"{where}: {error}");

    private static void Write(string level, string what)
    {
        try
        {
            lock (Lock)
            {
                var path = Where;
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                var info = new FileInfo(path);
                if (info.Exists && info.Length > MaxBytes)
                    File.Move(path, path + ".1", overwrite: true);
                File.AppendAllText(
                    path,
                    $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {level,-7} {what}{Environment.NewLine}",
                    Encoding.UTF8);
            }
        }
        catch
        {
            // A journal is evidence, not permission: failing to write it
            // is not a reason to fail what is being written about.
        }
    }
}
