using System.Runtime.InteropServices;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// Secrets — a plugin's token, a key to a model's service — kept in the
/// Windows Credential Manager (<c>4.0-H11</c>).
/// </summary>
/// <remarks>
/// <para>
/// <b>Why here and not in the settings.</b> The settings are a file of
/// plain text that goes into the export on the privacy page and is meant
/// to be readable. A password to a mailbox cannot live there. The
/// Credential Manager keeps it encrypted with the person's own Windows
/// account, and the shell owns the machine (ADR 0009); the core asks.
/// </para>
/// <para>
/// <b>Named, not listed by value.</b> An entry is
/// <c>RinaAssistant/&lt;owner&gt;/&lt;name&gt;</c>: the owner is <c>core</c>
/// or <c>plugin:&lt;id&gt;</c>, set by the core, never by a plugin, so one
/// plugin cannot reach another's. What is enumerated is the names — for the
/// privacy page's "a sign-in is kept" — and a value leaves only to the one
/// that asked for it by name.
/// </para>
/// <para>
/// <b>This machine only.</b> Kept as <c>CRED_PERSIST_LOCAL_MACHINE</c>: it
/// survives a restart and does not travel with a roaming profile.
/// </para>
/// </remarks>
public static class Secrets
{
    /// <summary>What every entry's name begins with.</summary>
    public const string Prefix = "RinaAssistant/";

    /// <summary>The largest secret the Credential Manager keeps: 5 × 512 bytes.</summary>
    public const int MaxBytes = 2560;

    private const int CredTypeGeneric = 1;
    private const int CredPersistLocalMachine = 2;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct Credential
    {
        public int Flags;
        public int Type;
        public string TargetName;
        public string? Comment;
        public long LastWritten;
        public int CredentialBlobSize;
        public IntPtr CredentialBlob;
        public int Persist;
        public int AttributeCount;
        public IntPtr Attributes;
        public string? TargetAlias;
        public string? UserName;
    }

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredWrite(ref Credential credential, int flags);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredRead(string target, int type, int flags, out IntPtr credential);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredDelete(string target, int type, int flags);

    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredEnumerate(string filter, int flags, out int count,
                                             out IntPtr credentials);

    [DllImport("advapi32.dll")]
    private static extern void CredFree(IntPtr buffer);

    /// <summary>Is this a name the core may give: no slash, nothing empty.</summary>
    private static bool Named(string owner, string name) =>
        owner.Length is > 0 and <= 80 && name.Length is > 0 and <= 80
        && !owner.Contains('/') && !name.Contains('/');

    private static string Target(string owner, string name) => $"{Prefix}{owner}/{name}";

    /// <summary>Keep a secret. (ok, reason) — the reason a code, not prose.</summary>
    public static (bool Ok, string Reason) Set(string owner, string name, string value)
    {
        if (!Named(owner, name)) return (false, "bad_name");
        var bytes = Encoding.UTF8.GetBytes(value);
        if (bytes.Length > MaxBytes) return (false, "too_long");
        var blob = Marshal.AllocHGlobal(Math.Max(bytes.Length, 1));
        try
        {
            Marshal.Copy(bytes, 0, blob, bytes.Length);
            var credential = new Credential
            {
                Type = CredTypeGeneric,
                TargetName = Target(owner, name),
                Comment = "Rina Assistant",
                CredentialBlobSize = bytes.Length,
                CredentialBlob = blob,
                Persist = CredPersistLocalMachine,
                UserName = owner,
            };
            return CredWrite(ref credential, 0)
                ? (true, "")
                : (false, $"error_{Marshal.GetLastWin32Error()}");
        }
        finally
        {
            // The plain value is in managed memory too; that cannot be
            // helped in .NET. The unmanaged copy at least is wiped.
            for (var i = 0; i < bytes.Length; i++) Marshal.WriteByte(blob, i, 0);
            Marshal.FreeHGlobal(blob);
        }
    }

    /// <summary>The secret, or null when there is none.</summary>
    public static string? Get(string owner, string name)
    {
        if (!Named(owner, name)) return null;
        if (!CredRead(Target(owner, name), CredTypeGeneric, 0, out var found)) return null;
        try
        {
            var credential = Marshal.PtrToStructure<Credential>(found);
            if (credential.CredentialBlobSize == 0) return "";
            var bytes = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, bytes, 0, bytes.Length);
            return Encoding.UTF8.GetString(bytes);
        }
        finally
        {
            CredFree(found);
        }
    }

    /// <summary>
    /// Forget one secret, or all of an owner's when <paramref name="name"/>
    /// is empty. Returns how many went.
    /// </summary>
    public static int Delete(string owner, string name = "")
    {
        if (name.Length > 0)
        {
            if (!Named(owner, name)) return 0;
            return CredDelete(Target(owner, name), CredTypeGeneric, 0) ? 1 : 0;
        }
        var gone = 0;
        foreach (var (who, what) in List())
        {
            if (who == owner && CredDelete(Target(who, what), CredTypeGeneric, 0)) gone++;
        }
        return gone;
    }

    /// <summary>The names kept — owner and name, never a value.</summary>
    public static List<(string Owner, string Name)> List()
    {
        var found = new List<(string, string)>();
        if (!CredEnumerate(Prefix + "*", 0, out var count, out var list))
            return found;   // ERROR_NOT_FOUND when there is nothing yet
        try
        {
            for (var i = 0; i < count; i++)
            {
                var item = Marshal.ReadIntPtr(list, i * IntPtr.Size);
                var credential = Marshal.PtrToStructure<Credential>(item);
                var rest = credential.TargetName[Prefix.Length..];
                var slash = rest.IndexOf('/');
                if (slash <= 0 || slash == rest.Length - 1) continue;
                found.Add((rest[..slash], rest[(slash + 1)..]));
            }
        }
        finally
        {
            CredFree(list);
        }
        return found;
    }
}
