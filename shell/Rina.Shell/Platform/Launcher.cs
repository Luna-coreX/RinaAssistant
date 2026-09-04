using System.IO;
using System.Diagnostics;

namespace Rina.Shell.Platform;

/// <summary>
/// Launching programs, and keeping a record of what was launched.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-G05</c>, <c>G10</c>, <c>G11</c>, <c>G12</c>.
/// </para>
/// <para>
/// <b>This check stands between "Rina decided" and "the process is
/// running".</b> The path is resolved to its canonical form, forbidden
/// directories are cut off, and an unsigned file needs the person's
/// consent the first time. The core decides <i>what</i> to launch;
/// answering <i>whether it may</i> is the shell's job
/// ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// <para>
/// <b>Every launch is recorded</b> (<c>4.0-G12</c>): what, from where,
/// whether consent was asked, how it ended. The command text is not in
/// the journal — it never is, not even under the `log_texts` setting:
/// "what was launched" and "what the person said" are different facts,
/// and there is no reason to mix them in one file.
/// </para>
/// </remarks>
public static class Launcher
{
    /// <summary>How the launch ended.</summary>
    /// <param name="Ok">The process started.</param>
    /// <param name="Reason">Why it did not — for the core, not for the person.</param>
    /// <param name="NeedsTrust">Consent for something unsigned is needed.</param>
    public sealed record Outcome(bool Ok, string Reason = "",
                                 bool NeedsTrust = false);

    /// <summary>
    /// Launch what the core named.
    /// </summary>
    /// <param name="launch">A file path or a package AppID.</param>
    /// <param name="kind">"file" or "uwp".</param>
    /// <param name="trusted">
    /// The person has already consented to this unsigned file.
    /// </param>
    public static Outcome Start(string launch, string kind, bool trusted)
    {
        if (string.IsNullOrWhiteSpace(launch))
            return new Outcome(false, "empty");

        if (kind == "uwp")
        {
            // A package has no path: it launches through a shell protocol.
            var started = Shell($"shell:AppsFolder\\{launch}");
            Journal.Launch(launch, "uwp", trusted: true, ok: started);
            return started ? new Outcome(true)
                : new Outcome(false, "the package did not start");
        }

        var path = AppIndex.Canonical(launch);
        if (path.Length == 0 || !File.Exists(path))
        {
            Journal.Launch(launch, "file", trusted, ok: false, note: "no file");
            return new Outcome(false, "the file is gone");
        }

        // A prohibition outweighs consent: Downloads does not run, even if
        // the person once said "always trust" to something from there.
        if (AppIndex.Forbidden(path))
        {
            Journal.Launch(path, "file", trusted, ok: false,
                           note: "forbidden directory");
            return new Outcome(false, "forbidden directory");
        }

        // Unsigned runs only with consent, and only the first time.
        if (!trusted && !Trust.Allowed(path))
        {
            Journal.Launch(path, "file", trusted: false, ok: false,
                           note: "consent required");
            return new Outcome(false, "consent required", NeedsTrust: true);
        }

        var ran = Shell(path);
        Journal.Launch(path, "file", trusted || Trust.Allowed(path), ran);
        return ran ? new Outcome(true) : new Outcome(false, "did not start");
    }

    /// <summary>
    /// Launching by way of the system shell.
    /// </summary>
    /// <remarks>
    /// <c>UseShellExecute</c> is mandatory: it is how shortcuts, packages
    /// and files with an association all launch — the same way Explorer
    /// does it. We do not write our own shortcut parser.
    /// </remarks>
    private static bool Shell(string what)
    {
        try
        {
            var started = Process.Start(new ProcessStartInfo
            {
                FileName = what,
                UseShellExecute = true,
                WorkingDirectory = SafeFolder(what),
            });
            return started is not null || File.Exists(what);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// The working directory is the program's own folder.
    /// </summary>
    /// <remarks>
    /// Otherwise it becomes Rina's folder, and a program looking for files
    /// next to itself will not find them. Packages and protocols have no
    /// folder — empty then.
    /// </remarks>
    private static string SafeFolder(string what)
    {
        try
        {
            return File.Exists(what) ? Path.GetDirectoryName(what) ?? "" : "";
        }
        catch
        {
            return "";
        }
    }
}
