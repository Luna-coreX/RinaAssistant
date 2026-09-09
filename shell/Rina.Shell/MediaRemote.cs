using System.IO;
using System.Windows.Media.Imaging;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Media.Control;
using Windows.Storage.Streams;

namespace Rina.Shell;

/// <summary>
/// A remote for whatever is already playing.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A07</c>. Not a player: Rina has no library, no
/// playlists and reads nobody's folders. Windows keeps a register of what
/// is playing — Spotify, a browser, anything that announces itself — and
/// this reads that register and presses its buttons.
/// </para>
/// <para>
/// <b>Why not a player of our own.</b> A second audio path beside speech
/// synthesis means two things fighting for the output device, a library to
/// index, formats to decode, and a person's music folder to read. The
/// person asked for a remote, and a remote is what the system already
/// offers.
/// </para>
/// <para>
/// <b>It is allowed to be absent.</b> Nothing is playing most of the time,
/// and a panel showing empty fields is worse than no panel: it says the
/// thing is broken. <see cref="Playing"/> being null means the remote shows
/// nothing at all.
/// </para>
/// <para>
/// <b>Everything is wrapped.</b> These are system calls into a component
/// that can be missing, busy or refuse — on an N edition of Windows, in a
/// session without media, on a machine where the service is off. A remote
/// that throws takes the home screen with it, and the home screen is the
/// first thing a person sees.
/// </para>
/// </remarks>
public sealed class MediaRemote
{
    /// <summary>What is playing, as far as anyone can tell.</summary>
    /// <param name="Artist">Who; may be empty — not everything says.</param>
    /// <param name="Title">What.</param>
    /// <param name="Running">Sounding right now, rather than paused.</param>
    /// <param name="Cover">The artwork, if the source gave one.</param>
    public sealed record Sounding(string Artist, string Title, bool Running,
                                  BitmapImage? Cover);

    private GlobalSystemMediaTransportControlsSessionManager? _manager;
    private GlobalSystemMediaTransportControlsSession? _session;

    /// <summary>What is playing, or null when nothing is.</summary>
    public Sounding? Playing { get; private set; }

    /// <summary>It changed — the window may want to look again.</summary>
    public event Action? Changed;

    /// <summary>Did the system let us in at all.</summary>
    public bool Available { get; private set; }

    /// <summary>Start listening to what the machine is playing.</summary>
    public async Task StartAsync()
    {
        try
        {
            _manager = await GlobalSystemMediaTransportControlsSessionManager
                .RequestAsync();
            Available = true;
            _manager.CurrentSessionChanged += (_, _) => OnUi(Follow);
            Follow();
        }
        catch (Exception exc)                            // noqa
        {
            // Not a failure of the application: a machine without the media
            // service is a machine where nothing is playing, and that is a
            // state the home screen already knows how to show.
            Available = false;
            Log($"remote unavailable: {exc.GetType().Name}");
        }
    }

    /// <summary>Back to the previous track.</summary>
    public Task Previous() => Press(s => s.TrySkipPreviousAsync());

    /// <summary>Pause, or start again.</summary>
    public Task PlayPause() => Press(s => s.TryTogglePlayPauseAsync());

    /// <summary>On to the next.</summary>
    public Task Next() => Press(s => s.TrySkipNextAsync());

    private async Task Press(
        Func<GlobalSystemMediaTransportControlsSession,
             Windows.Foundation.IAsyncOperation<bool>> what)
    {
        var session = _session;
        if (session is null) return;
        try { await what(session); }
        catch (Exception exc)                            // noqa
        {
            // A source may refuse — a browser tab that has gone away, a
            // player that closed between the press and the call. There is
            // nothing to tell the person: the buttons will simply stop
            // showing when the register loses the session.
            Log($"remote press refused: {exc.GetType().Name}");
        }
    }

    /// <summary>Follow whichever session is current now.</summary>
    private void Follow()
    {
        if (_session is not null)
        {
            _session.MediaPropertiesChanged -= OnTrack;
            _session.PlaybackInfoChanged -= OnState;
        }

        _session = null;
        try { _session = _manager?.GetCurrentSession(); }
        catch (Exception exc) { Log($"remote has no session: {exc.GetType().Name}"); }

        if (_session is not null)
        {
            _session.MediaPropertiesChanged += OnTrack;
            _session.PlaybackInfoChanged += OnState;
        }
        _ = ReadAsync();
    }

    private void OnTrack(GlobalSystemMediaTransportControlsSession s, object e)
        => OnUi(() => _ = ReadAsync());

    private void OnState(GlobalSystemMediaTransportControlsSession s, object e)
        => OnUi(() => _ = ReadAsync());

    /// <summary>Ask the current session what it is playing.</summary>
    private async Task ReadAsync()
    {
        var session = _session;
        if (session is null)
        {
            Set(null);
            return;
        }

        try
        {
            var about = await session.TryGetMediaPropertiesAsync();
            var state = session.GetPlaybackInfo();
            var running = state?.PlaybackStatus
                == GlobalSystemMediaTransportControlsSessionPlaybackStatus
                    .Playing;

            Set(new Sounding(about.Artist ?? "", about.Title ?? "", running,
                             await CoverAsync(about)));
        }
        catch (Exception exc)                            // noqa
        {
            Log($"remote unreadable: {exc.GetType().Name}");
            Set(null);
        }
    }

    /// <summary>The artwork, if there is one and it can be read.</summary>
    private static async Task<BitmapImage?> CoverAsync(
        GlobalSystemMediaTransportControlsSessionMediaProperties about)
    {
        if (about.Thumbnail is null) return null;
        try
        {
            using var stream = await about.Thumbnail.OpenReadAsync();
            using var memory = new MemoryStream();
            await stream.AsStreamForRead().CopyToAsync(memory);
            memory.Position = 0;

            var image = new BitmapImage();
            image.BeginInit();
            image.CacheOption = BitmapCacheOption.OnLoad;
            image.StreamSource = memory;
            image.EndInit();
            // Frozen: it is built off the interface thread and shown on it.
            image.Freeze();
            return image;
        }
        catch (Exception exc)                            // noqa
        {
            Log($"cover unreadable: {exc.GetType().Name}");
            return null;
        }
    }

    /// <summary>Pretend something is playing — for the check.</summary>
    /// <remarks>
    /// The two halves of this are owned by different people. Reading the
    /// register is the system's half, and what it says depends on what the
    /// person has open; laying it out on the home screen is ours, and that
    /// has to be checkable on a quiet machine. This seam is where they
    /// part: everything after it is our code, and the check exercises it
    /// without waiting for somebody to press play.
    /// </remarks>
    public void ShowForCheck(Sounding? sounding) => Set(sounding);

    private void Set(Sounding? sounding)
    {
        Playing = sounding;
        OnUi(() => Changed?.Invoke());
    }

    /// <summary>
    /// Onto the interface thread.
    /// </summary>
    /// <remarks>
    /// The system's notifications arrive on a pool thread, and everything
    /// they lead to here ends in a control being changed. Without this the
    /// window would throw at the first change of track — which is to say,
    /// not while anybody was testing it and always in use.
    /// </remarks>
    private static void OnUi(Action what)
    {
        var app = System.Windows.Application.Current;
        if (app is null) return;
        if (app.Dispatcher.CheckAccess()) what();
        else app.Dispatcher.BeginInvoke(what);
    }

    /// <summary>
    /// A line for whoever is debugging, in English like the rest of the code.
    /// </summary>
    /// <remarks>
    /// Not shown to anybody using Rina, so not a product string —
    /// `check_strings.py` cannot tell the difference and is right not to
    /// be able to: a Russian literal here looks exactly like a label that
    /// forgot to go through the translation.
    /// </remarks>
    private static void Log(string said) =>
        System.Diagnostics.Debug.WriteLine($"[media] {said}");
}
