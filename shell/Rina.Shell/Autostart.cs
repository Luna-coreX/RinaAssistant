using Microsoft.Win32;

namespace Rina.Shell;

/// <summary>
/// Starting when the user signs in.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F05</c>.
/// </para>
/// <para>
/// <b>The current user's branch, not the machine's.</b> `HKCU` needs no
/// administrator rights and does not touch other people at this computer:
/// Rina is a personal assistant, and nobody asked to set her up for
/// everyone at once.
/// </para>
/// <para>
/// <b>Our own entry name, and we do not touch anyone else's.</b> The entry
/// is named after the program; everything else in that branch belongs to
/// other programs, and sifting through it looking for "something like us"
/// is a way to one day delete someone else's.
/// </para>
/// <para>
/// The setting lives in the core (`autostart`) and the shell carries it
/// out: the registry is the system, and the system layer in 4.0 belongs to
/// the shell. The core keeps the intent, the shell brings the system into
/// line with it.
/// </para>
/// </remarks>
public static class Autostart
{
    private const string Branch =
        @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Name = "RinaAssistant";

    /// <summary>Whether the entry is there right now.</summary>
    public static bool Enabled
    {
        get
        {
            try
            {
                using var key = Registry.CurrentUser.OpenSubKey(Branch);
                return key?.GetValue(Name) is not null;
            }
            catch
            {
                return false;
            }
        }
    }

    /// <summary>What exactly will be started.</summary>
    public static string Command
    {
        get
        {
            var exe = Environment.ProcessPath ?? "";
            // The quotes are mandatory: the path almost certainly contains
            // a space, and without them the system would launch
            // "C:\Program".
            return exe.Length > 0 ? $"\"{exe}\"" : "";
        }
    }

    /// <summary>Bring the system into line with the setting. `true` — it worked.</summary>
    public static bool Apply(bool wanted)
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(Branch, true);
            if (key is null) return false;

            if (wanted)
            {
                if (Command.Length == 0) return false;
                key.SetValue(Name, Command, RegistryValueKind.String);
            }
            else if (key.GetValue(Name) is not null)
            {
                key.DeleteValue(Name, throwOnMissingValue: false);
            }
            return true;
        }
        catch
        {
            // Group policy may forbid the write. Staying silent is not an
            // option, but there is no reason to fall over either: the caller
            // will show that it did not work.
            return false;
        }
    }
}
