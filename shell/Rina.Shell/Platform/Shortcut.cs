using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// What a shell shortcut (<c>.lnk</c>) starts: its target and arguments.
/// </summary>
/// <remarks>
/// <para>
/// Audit 2026-10-07, M-3. The trust checks looked at the shortcut file
/// itself. A shortcut carries no signature of its own, so every Start-menu
/// program — a signed Chrome included — was "unsigned" on its first launch,
/// which teaches a person to press «Всегда доверять» without reading. And a
/// shortcut pointing into Downloads passed the forbidden-folder check,
/// because the shortcut itself lies in the Start menu.
/// </para>
/// <para>
/// <b>Read, never resolved.</b> <c>IShellLink::Resolve</c> goes looking
/// for a moved target — across the disk and the network — and may rewrite
/// the shortcut; the question here is only what it says now. The shortcut
/// is opened read-only.
/// </para>
/// </remarks>
public static class Shortcut
{
    /// <summary>A shortcut's target and the arguments it passes.</summary>
    public sealed record Target(string Path, string Arguments);

    /// <summary>
    /// The target of a shortcut to a file, or <c>null</c> when there is none
    /// to check — a broken shortcut, an installer's "advertised" one, or a
    /// shortcut to something that is not a file.
    /// </summary>
    public static Target? Read(string lnk)
    {
        if (string.IsNullOrWhiteSpace(lnk) || !File.Exists(lnk)) return null;
        object? link = null;
        try
        {
            link = new ShellLinkCoClass();
            ((IPersistFile)link).Load(lnk, 0 /* STGM_READ */);
            var shell = (IShellLinkW)link;

            var path = new StringBuilder(32768);
            shell.GetPath(path, path.Capacity, IntPtr.Zero, 0);
            var args = new StringBuilder(32768);
            shell.GetArguments(args, args.Capacity);

            var target = Environment.ExpandEnvironmentVariables(path.ToString());
            if (target.Length == 0 || !File.Exists(target)) return null;
            // An installer's "advertised" shortcut names an icon kept by
            // Windows Installer rather than the program; what it really
            // starts is decided by the installer at launch time.
            var installer = System.IO.Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.Windows),
                "Installer") + System.IO.Path.DirectorySeparatorChar;
            if (target.StartsWith(installer, StringComparison.OrdinalIgnoreCase))
                return null;
            return new Target(target, args.ToString().Trim());
        }
        catch
        {
            return null;
        }
        finally
        {
            if (link is not null) Marshal.FinalReleaseComObject(link);
        }
    }

    /// <summary>Make a shortcut — for the checks, which need ones to read.</summary>
    public static void Write(string lnk, string target, string arguments = "")
    {
        object? link = null;
        try
        {
            link = new ShellLinkCoClass();
            var shell = (IShellLinkW)link;
            shell.SetPath(target);
            shell.SetArguments(arguments);
            ((IPersistFile)link).Save(lnk, true);
        }
        finally
        {
            if (link is not null) Marshal.FinalReleaseComObject(link);
        }
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    private class ShellLinkCoClass { }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("000214F9-0000-0000-C000-000000000046")]
    private interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile,
                     int cch, IntPtr pfd, uint fFlags);
        void GetIDList(out IntPtr ppidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName,
                            int cch);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir,
                                 int cch);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs,
                          int cch);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
        void GetHotkey(out short pwHotkey);
        void SetHotkey(short wHotkey);
        void GetShowCmd(out int piShowCmd);
        void SetShowCmd(int iShowCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath,
                             int cch, out int piIcon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath,
                             int iIcon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel,
                             uint dwReserved);
        void Resolve(IntPtr hwnd, uint fFlags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown),
     Guid("0000010B-0000-0000-C000-000000000046")]
    private interface IPersistFile
    {
        void GetClassID(out Guid pClassID);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName,
                  uint dwMode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName,
                  [MarshalAs(UnmanagedType.Bool)] bool fRemember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
        void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
    }
}
