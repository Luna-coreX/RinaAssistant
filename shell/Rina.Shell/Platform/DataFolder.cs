using System.IO;

namespace Rina.Shell.Platform;

/// <summary>
/// Where the shell keeps its own files: beside the core's, in the person's
/// data folder — or, for a check, in a folder of the check's own.
/// </summary>
/// <remarks>
/// <para>
/// One place for a path that was written out by hand in six. It had to
/// become one when the checks turned out to write into it: the shell finds
/// this folder through <see cref="System.Environment.GetFolderPath(System.Environment.SpecialFolder)"/>,
/// which does not read <c>APPDATA</c>, so no stand-in profile given from
/// outside ever reached it. Measured: the platform check left its test
/// launches in the person's security journal and rewrote their index cache,
/// and the update check wrote to the journal too.
/// </para>
/// <para>
/// <b>The override is set by code, never by the environment.</b> Only the
/// start of a check sets it (<c>--check-*</c>, <c>--shot</c>). A variable
/// read here would be a switch in working code that could one day be on at
/// somebody's machine — and their Rina would quietly keep nothing.
/// </para>
/// </remarks>
public static class DataFolder
{
    private static string? _check;

    /// <summary>Send the shell's files into a check's own folder.</summary>
    public static void UseForCheck(string root) => _check = root;

    /// <summary>Roaming data: the shell's own store, the journal, the trust list.</summary>
    public static string Roaming => _check is { } root
        ? Path.Combine(root, "RinaAssistant")
        : Path.Combine(System.Environment.GetFolderPath(
              System.Environment.SpecialFolder.ApplicationData), "RinaAssistant");

    /// <summary>Local data: what is large and belongs to this machine — update downloads.</summary>
    public static string Local => _check is { } root
        ? Path.Combine(root, "Local", "RinaAssistant")
        : Path.Combine(System.Environment.GetFolderPath(
              System.Environment.SpecialFolder.LocalApplicationData), "RinaAssistant");
}
