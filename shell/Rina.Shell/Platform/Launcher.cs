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
    /// <param name="Subject">
    /// What the consent is about: the file that runs — for a shortcut, its
    /// target rather than the shortcut (audit 2026-10-07, M-3).
    /// </param>
    /// <param name="Arguments">What a shortcut hands its target.</param>
    public sealed record Outcome(bool Ok, string Reason = "",
                                 bool NeedsTrust = false,
                                 string Subject = "", string Arguments = "");

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

        // A folder is opened, not run: Explorer shows it. Nothing executes,
        // so neither the forbidden directories nor consent apply — opening
        // Downloads to look at it is fine; running a file from it is not.
        if (kind == "folder")
        {
            var there = path.Length > 0 && Directory.Exists(path);
            var opened = there && Shell(path);
            Journal.Launch(path.Length > 0 ? path : launch, "folder",
                           trusted: true, ok: opened,
                           note: there ? "" : "no folder");
            return opened ? new Outcome(true)
                : new Outcome(false, there ? "did not start" : "the folder is gone");
        }

        if (path.Length == 0 || !File.Exists(path))
        {
            Journal.Launch(launch, "file", trusted, ok: false, note: "no file");
            return new Outcome(false, "the file is gone");
        }

        var vetted = Vet(path, trusted);
        if (!vetted.Ok)
        {
            Journal.Launch(vetted.Subject, "file", trusted, ok: false,
                           note: vetted.Reason);
            return vetted;
        }

        // The shortcut itself is started, as Explorer starts it: its
        // arguments, working folder and window state are part of what the
        // person installed. What it points at is what was just checked.
        var subject = vetted.Subject;
        var ran = Shell(path);
        Journal.Launch(subject, "file",
                       trusted || Trust.Allowed(subject, vetted.Arguments),
                       ran, note: subject == path ? "" : "via shortcut");
        return ran ? new Outcome(true) : new Outcome(false, "did not start");
    }

    /// <summary>
    /// May this file be started: the checks of <see cref="Start"/>, without
    /// starting anything. <c>Ok</c> means cleared; <c>Subject</c> is what
    /// was checked.
    /// </summary>
    /// <remarks>
    /// <b>A shortcut is checked by what it starts</b> (audit 2026-10-07,
    /// M-3). The checks used to look at the shortcut file: it has no
    /// signature, so every Start-menu program was "unsigned", and it lies
    /// in the Start menu, so one pointing into Downloads passed. A shortcut
    /// whose target cannot be read — an installer's "advertised" one — is
    /// still checked as itself, and so asked about.
    /// </remarks>
    public static Outcome Vet(string path, bool trusted)
    {
        var subject = path;
        var arguments = "";
        if (path.EndsWith(".lnk", StringComparison.OrdinalIgnoreCase)
            && Shortcut.Read(path) is { } target)
        {
            var resolved = AppIndex.Canonical(target.Path);
            if (resolved.Length > 0)
            {
                subject = resolved;
                arguments = target.Arguments;
            }
        }

        // A prohibition outweighs consent: Downloads does not run, even if
        // the person once said "always trust" to something from there.
        if (AppIndex.Forbidden(path) || AppIndex.Forbidden(subject))
            return new Outcome(false, "forbidden directory", Subject: subject,
                               Arguments: arguments);

        // Unsigned runs only with consent, and only the first time.
        if (!trusted && !Trust.Allowed(subject, arguments))
            return new Outcome(false, "consent required", NeedsTrust: true,
                               Subject: subject, Arguments: arguments);

        return new Outcome(true, Subject: subject, Arguments: arguments);
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
