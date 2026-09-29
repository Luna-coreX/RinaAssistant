using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace Rina.Shell.Platform;

/// <summary>
/// One Rina per profile.
/// </summary>
/// <remarks>
/// <para>
/// Nothing stopped a second copy: autostart and a click on the shortcut
/// gave two shells, two cores, two microphones and two sets of hotkeys over
/// one profile. The cores each write <c>settings.json</c> whole, so a
/// change made in one was silently undone by the other's next write; both
/// append to <c>rina.log</c>, and on Windows a file another process holds
/// cannot be renamed — rotation failed half-way, which is how the journal
/// came to have a <c>.1</c> and a <c>.3</c> and no <c>.2</c>.
/// </para>
/// <para>
/// <b>Keyed by the data folder, not by the program.</b> What must not be
/// shared is the profile: two builds over one profile are the same fault,
/// while a check running in a folder of its own is no conflict at all and
/// must not be turned away by a Rina the person has open.
/// </para>
/// <para>
/// The second copy does not simply vanish: it asks the first to show
/// itself, which is what a person starting the program again wants.
/// </para>
/// </remarks>
public sealed class SingleInstance : IDisposable
{
    private readonly Mutex _mutex;
    private readonly EventWaitHandle _show;
    private RegisteredWaitHandle? _waiting;

    private SingleInstance(Mutex mutex, EventWaitHandle show, bool first)
    {
        _mutex = mutex;
        _show = show;
        IsFirst = first;
    }

    /// <summary>Whether this process owns the profile.</summary>
    public bool IsFirst { get; }

    /// <summary>Claim the profile in this folder, or learn that it is taken.</summary>
    /// <remarks>
    /// A copy that crashed leaves no claim behind: the mutex belongs to the
    /// kernel only while some process holds it, and a dead one holds
    /// nothing.
    /// </remarks>
    public static SingleInstance Claim(string dataFolder)
    {
        var key = Key(dataFolder);
        var mutex = new Mutex(true, $@"Local\RinaAssistant.{key}", out var created);
        var show = new EventWaitHandle(false, EventResetMode.AutoReset,
                                       $@"Local\RinaAssistant.{key}.show");
        return new SingleInstance(mutex, show, created);
    }

    /// <summary>The second copy: ask the first one to come forward.</summary>
    public void AskFirstToShow() => _show.Set();

    /// <summary>The first copy: what to do when another one asks.</summary>
    /// <remarks>Called on a pool thread; the caller moves it to the UI.</remarks>
    public void OnAsked(Action show) =>
        _waiting = ThreadPool.RegisterWaitForSingleObject(
            _show, (_, _) => show(), null, Timeout.Infinite,
            executeOnlyOnce: false);

    public void Dispose()
    {
        _waiting?.Unregister(null);
        if (IsFirst)
        {
            try { _mutex.ReleaseMutex(); }
            catch (ApplicationException) { /* released on another thread's exit */ }
        }
        _mutex.Dispose();
        _show.Dispose();
    }

    /// <summary>
    /// A name for the folder that fits a kernel object's name.
    /// </summary>
    /// <remarks>
    /// Hashed rather than used as it is: a path has backslashes, which a
    /// mutex name reads as a namespace, and case, which Windows paths do
    /// not care about.
    /// </remarks>
    private static string Key(string folder)
    {
        var full = Path.GetFullPath(folder).TrimEnd('\\').ToUpperInvariant();
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(full));
        return Convert.ToHexString(hash, 0, 8);
    }
}
