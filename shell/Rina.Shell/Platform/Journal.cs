using System.IO;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// The security journal, shell side.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-G12</c>: the journal must show what was launched and
/// where it came from — <b>without any of the conversation</b>. Command
/// text never reaches it, not even when `log_texts` is on: "what was
/// launched" and "what the person said" are different facts, and there is
/// no reason to keep them in one file.
/// </para>
/// <para>
/// <b>Written to the same file the core uses</b>
/// (<c>%APPDATA%\RinaAssistant\logs\security.log</c>). Two files for one
/// chronology would have to be stitched together by hand when an incident
/// is examined, and the first clock discrepancy would make that
/// impossible.
/// </para>
/// <para>
/// <b>Failing to write does not cancel the action.</b> A journal is
/// evidence, not permission; a program that refused to launch something
/// because its log file was busy would be worse, not safer.
/// </para>
/// </remarks>
public static class Journal
{
    private static readonly object Lock = new();

    /// <summary>Where the journal is written — so checks look in the same place.</summary>
    public static string Where => Path;

    private static string Path => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "logs", "security.log");

    /// <summary>A launch: what, from where, with consent or not, how it ended.</summary>
    public static void Launch(string what, string kind, bool trusted, bool ok,
                              string note = "")
    {
        var source = kind == "uwp" ? "uwp" : SourceOf(what);
        Write($"launch app={Name(what)} path={what} source={source} "
              + $"trusted={(trusted ? "yes" : "no")} "
              + $"result={(ok ? "ok" : "fail")}"
              + (note.Length > 0 ? $" note={note}" : ""));
    }

    /// <summary>The person allowed this unsigned file to run from now on.</summary>
    public static void Trusted(string path)
        => Write($"trust path={path} scope=always");

    /// <summary>
    /// Updates: the check, the download, integrity, installation.
    /// </summary>
    /// <remarks>
    /// Plan item <c>4.0-U05</c>. Written where launches are written: the
    /// question "which update did this start after" cannot be answered if
    /// updates live in one file and launches in another.
    /// </remarks>
    public static void Update(string stage, string detail)
        => Write($"update stage={stage} {detail}");

    /// <summary>A system action: volume, power, screenshot.</summary>
    public static void Action(string action, bool ok)
        => Write($"system action={action} result={(ok ? "ok" : "fail")}");

    private static string Name(string what)
    {
        try
        {
            return System.IO.Path.GetFileName(what);
        }
        catch
        {
            return what;
        }
    }

    /// <summary>
    /// Where the entry came from — by its place in the index.
    /// </summary>
    /// <remarks>
    /// The index is asked, not the path: "where we learned of it" and
    /// "where it sits" are different things, and the journal wants the first.
    /// </remarks>
    private static string SourceOf(string path)
    {
        try
        {
            return AppIndex.Get().FirstOrDefault(
                e => string.Equals(e.Launch, path,
                                   StringComparison.OrdinalIgnoreCase))
                ?.Source ?? "unknown";
        }
        catch
        {
            return "unknown";
        }
    }

    private static void Write(string line)
    {
        try
        {
            var stamped = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} | SECURITY | "
                          + $"shell | {line}{Environment.NewLine}";
            lock (Lock)
            {
                Directory.CreateDirectory(
                    System.IO.Path.GetDirectoryName(Path)!);

                // Opened so others may write too. The core holds the same
                // file as its own journal, and `File.AppendAllText` opens it
                // without granting write access to anyone else — meaning it
                // could **never** append while the core was alive. The
                // shell's entries never appeared at all, and the exception
                // was swallowed: a journal has no right to bring down what
                // it records.
                using var file = new FileStream(
                    Path, FileMode.Append, FileAccess.Write,
                    FileShare.ReadWrite | FileShare.Delete);
                var bytes = Encoding.UTF8.GetBytes(stamped);
                file.Write(bytes, 0, bytes.Length);
            }
        }
        catch
        {
            // A journal is evidence, not permission: if it did not write,
            // the action still happened, and staying quiet about it is more
            // honest than dropping a launch. That silence is exactly what
            // cost us months of missing entries — hence the check that now
            // reads the file back.
        }
    }
}
