using System.IO;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// One entry in the program index.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-G09</c>. An entry has to show <b>where it came from
/// and when it was last checked</b>: without that you can neither warn
/// about something unsigned nor clear out what has gone stale. In 3.1.0
/// an entry held a name, a path, a kind and a source — and that was all;
/// "where from" was there, "how much to trust it" was not.
/// </para>
/// <para>
/// <b>The shell gathers the aliases, the core matches them.</b> Only the
/// names the system gave are kept here: the shortcut's name, the file
/// name, the name from the resources. Spoken ones ("telegram",
/// "photoshop") are the core's business
/// ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// </remarks>
public sealed record AppEntry
{
    /// <summary>What the program is called for a person.</summary>
    public required string Name { get; init; }

    /// <summary>What to launch: a file path or a package AppID.</summary>
    public required string Launch { get; init; }

    /// <summary>"file" or "uwp".</summary>
    public string Kind { get; init; } = "file";

    /// <summary>Where we learned of it: start_menu, app_paths, uwp, path, folder.</summary>
    public required string Source { get; init; }

    /// <summary>Names from the system: shortcut, file, resources.</summary>
    public string[] Aliases { get; init; } = [];

    /// <summary>The file's signature was checked by the system and is valid.</summary>
    public bool Signed { get; init; }

    /// <summary>When the entry was last checked (UTC).</summary>
    public DateTime CheckedAt { get; init; } = DateTime.UtcNow;

    // --- signature verification ---------------------------------------------

    private static readonly Guid VerifyAction =
        new("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");

    private const uint UiNone = 2;
    private const uint RevokeWholeChain = 1;
    private const uint ChoiceFile = 1;
    private const uint StateActionVerify = 1;
    private const uint StateActionClose = 2;
    private const uint SafeLifetimeSigning = 0x00000800;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileInfoBlock
    {
        public uint Size;
        [MarshalAs(UnmanagedType.LPWStr)] public string FilePath;
        public IntPtr FileHandle;
        public IntPtr KnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TrustData
    {
        public uint Size;
        public IntPtr PolicyCallbackData;
        public IntPtr SipClientData;
        public uint UiChoice;
        public uint RevocationChecks;
        public uint UnionChoice;
        public IntPtr FileInfoPointer;
        public uint StateAction;
        public IntPtr StateData;
        [MarshalAs(UnmanagedType.LPWStr)] public string? UrlReference;
        public uint ProviderFlags;
        public uint UiContext;
        public IntPtr SignatureSettings;
    }

    [DllImport("wintrust.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int WinVerifyTrust(IntPtr window, ref Guid action,
                                             ref TrustData data);

    // --- signature by catalogue ---------------------------------------------

    private const uint ChoiceCatalog = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct CatalogInfoBlock
    {
        public uint Size;
        public uint CatalogVersion;
        [MarshalAs(UnmanagedType.LPWStr)] public string CatalogFilePath;
        [MarshalAs(UnmanagedType.LPWStr)] public string MemberTag;
        [MarshalAs(UnmanagedType.LPWStr)] public string MemberFilePath;
        public IntPtr MemberFile;
        public IntPtr CalculatedFileHash;
        public uint HashLength;
        public IntPtr CatalogContext;
        public IntPtr CatAdmin;
    }

    // CharSet is mandatory: `wszCatalogFile` is a wide string, and without
    // it `ByValTStr` reads it as single-byte. The catalogue path came back
    // as the string "C" — the first letter, followed by a zero byte.
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct CatalogInfo
    {
        public uint Size;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)]
        public string CatalogFile;
    }

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminAcquireContext2(
        out IntPtr admin, IntPtr subsystem,
        [MarshalAs(UnmanagedType.LPWStr)] string? algorithm,
        IntPtr policy, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminCalcHashFromFileHandle2(
        IntPtr admin, IntPtr file, ref uint size, byte[]? hash, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern IntPtr CryptCATAdminEnumCatalogFromHash(
        IntPtr admin, byte[] hash, uint hashLength, uint flags,
        IntPtr previous);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATCatalogInfoFromContext(
        IntPtr context, ref CatalogInfo info, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminReleaseCatalogContext(
        IntPtr admin, IntPtr context, uint flags);

    [DllImport("wintrust.dll", SetLastError = true)]
    private static extern bool CryptCATAdminReleaseContext(IntPtr admin,
                                                           uint flags);

    /// <summary>
    /// Whether the file is signed by a catalogue.
    /// </summary>
    /// <remarks>
    /// Windows system files do not carry a signature inside themselves:
    /// their hashes are listed in a catalogue, and the catalogue is what
    /// is signed. A check that knows only about embedded signatures would
    /// declare half the system unsigned — and teach the person to click
    /// "always trust" without reading.
    ///
    /// Here the catalogue is found by the file's hash and <b>it</b> is
    /// verified — by the same `WinVerifyTrust`, only told whose member
    /// this is.
    /// </remarks>
    /// <summary>Where exactly the catalogue check stumbled — for diagnosis.</summary>
    public static string CatalogTrace(string path)
    {
        if (!CryptCATAdminAcquireContext2(out var admin, IntPtr.Zero,
                                          "SHA256", IntPtr.Zero, 0))
            return $"acquire=fail err={Marshal.GetLastWin32Error()}";
        try
        {
            using var file = File.OpenRead(path);
            var handle = file.SafeFileHandle.DangerousGetHandle();
            uint size = 0;
            CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size, null, 0);
            if (size == 0)
                return $"hashsize=0 err={Marshal.GetLastWin32Error()}";
            var hash = new byte[size];
            if (!CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size, hash, 0))
                return $"hash=fail err={Marshal.GetLastWin32Error()}";
            var catalog = CryptCATAdminEnumCatalogFromHash(admin, hash, size, 0, IntPtr.Zero);
            if (catalog == IntPtr.Zero)
                return $"catalog=none err={Marshal.GetLastWin32Error()}";
            var info = new CatalogInfo { Size = (uint)Marshal.SizeOf<CatalogInfo>(), CatalogFile = "" };
            if (!CryptCATCatalogInfoFromContext(catalog, ref info, 0))
                return $"info=fail err={Marshal.GetLastWin32Error()}";
            CryptCATAdminReleaseCatalogContext(admin, catalog, 0);
            return $"catalog={info.CatalogFile} verify={SignedByCatalog(path)}";
        }
        finally { CryptCATAdminReleaseContext(admin, 0); }
    }

    private static bool SignedByCatalog(string path)
    {
        if (!CryptCATAdminAcquireContext2(out var admin, IntPtr.Zero,
                                          "SHA256", IntPtr.Zero, 0))
            return false;

        var catalog = IntPtr.Zero;
        try
        {
            using var file = File.OpenRead(path);
            var handle = file.SafeFileHandle.DangerousGetHandle();

            uint size = 0;
            CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size,
                                                 null, 0);
            if (size == 0) return false;

            var hash = new byte[size];
            if (!CryptCATAdminCalcHashFromFileHandle2(admin, handle, ref size,
                                                      hash, 0))
                return false;

            catalog = CryptCATAdminEnumCatalogFromHash(admin, hash, size, 0,
                                                       IntPtr.Zero);
            if (catalog == IntPtr.Zero) return false;

            var info = new CatalogInfo
            {
                Size = (uint)Marshal.SizeOf<CatalogInfo>(),
                CatalogFile = "",
            };
            if (!CryptCATCatalogInfoFromContext(catalog, ref info, 0))
                return false;

            var tag = BitConverter.ToString(hash).Replace("-", "");
            var member = new CatalogInfoBlock
            {
                Size = (uint)Marshal.SizeOf<CatalogInfoBlock>(),
                CatalogVersion = 0,
                CatalogFilePath = info.CatalogFile,
                MemberTag = tag,
                MemberFilePath = path,
                MemberFile = handle,
                CalculatedFileHash = IntPtr.Zero,
                HashLength = 0,
                CatalogContext = IntPtr.Zero,
                CatAdmin = admin,
            };

            var block = Marshal.AllocHGlobal((int)member.Size);
            try
            {
                Marshal.StructureToPtr(member, block, false);
                var data = new TrustData
                {
                    Size = (uint)Marshal.SizeOf<TrustData>(),
                    UiChoice = UiNone,
                    RevocationChecks = RevokeWholeChain,
                    UnionChoice = ChoiceCatalog,
                    FileInfoPointer = block,
                    StateAction = StateActionVerify,
                    ProviderFlags = SafeLifetimeSigning,
                };
                var action = VerifyAction;
                var verdict = WinVerifyTrust(IntPtr.Zero, ref action, ref data);

                data.StateAction = StateActionClose;
                WinVerifyTrust(IntPtr.Zero, ref action, ref data);
                return verdict == 0;
            }
            finally
            {
                Marshal.FreeHGlobal(block);
            }
        }
        catch
        {
            return false;
        }
        finally
        {
            if (catalog != IntPtr.Zero)
                CryptCATAdminReleaseCatalogContext(admin, catalog, 0);
            CryptCATAdminReleaseContext(admin, 0);
        }
    }
    /// <summary>
    /// Whether the file's Authenticode signature is valid.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The system is asked (<c>WinVerifyTrust</c>) rather than the file
    /// being taken apart by hand: verifying a signature means walking the
    /// trust chain, checking revocation and honouring machine policy — and
    /// doing that ourselves means doing it worse than it is already done.
    /// </para>
    /// <para>
    /// The "signature stays valid past certificate expiry" flag is on
    /// deliberately: the certificate a program was signed with three years
    /// ago has long expired, and the program did not become unsigned
    /// because of it.
    /// </para>
    /// </remarks>
    public static bool HasSignature(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return false;

        var file = new FileInfoBlock
        {
            Size = (uint)Marshal.SizeOf<FileInfoBlock>(),
            FilePath = path,
        };
        var pointer = Marshal.AllocHGlobal((int)file.Size);
        try
        {
            Marshal.StructureToPtr(file, pointer, false);
            var data = new TrustData
            {
                Size = (uint)Marshal.SizeOf<TrustData>(),
                UiChoice = UiNone,
                RevocationChecks = RevokeWholeChain,
                UnionChoice = ChoiceFile,
                FileInfoPointer = pointer,
                StateAction = StateActionVerify,
                ProviderFlags = SafeLifetimeSigning,
            };

            var action = VerifyAction;
            var verdict = WinVerifyTrust(IntPtr.Zero, ref action, ref data);

            // Closing the state is mandatory: otherwise the provider keeps
            // memory and an open file for every check, and there are
            // hundreds of those in a single reindex.
            data.StateAction = StateActionClose;
            WinVerifyTrust(IntPtr.Zero, ref action, ref data);

            // No embedded signature — the file may be signed by a
            // catalogue. This order deliberately: embedded is the cheaper
            // check, and most third-party programs have exactly that.
            return verdict == 0 || SignedByCatalog(path);
        }
        catch
        {
            // No wintrust, a provider refusal, a busy file — all of it is
            // one and the same answer: the signature could not be confirmed.
            return false;
        }
        finally
        {
            Marshal.FreeHGlobal(pointer);
        }
    }
}
