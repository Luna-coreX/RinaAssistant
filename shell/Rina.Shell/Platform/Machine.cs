using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// System actions: volume, media, power, screenshot.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-G01</c>, <c>G02</c>, <c>G03</c>. The decision is
/// [ADR 0009](../../../docs/adr/0009-system-layer.md): the shell touches
/// the machine, the core decides what to do with it.
/// </para>
/// <para>
/// <b>The list is closed and named in advance.</b> An action arrives by a
/// name from this table; nothing resembling "run this string" is here or
/// ever will be. That is precisely what separates system actions from the
/// actuation channel (§12): "turn the volume up" cannot be aimed
/// somewhere else.
/// </para>
/// <para>
/// <b>The core does the talking.</b> What leaves here is a fact — it
/// worked or it did not; "Volume up" is composed by the core, because
/// that is Rina speaking
/// ([ADR 0007](../../../docs/adr/0007-localisation.md)), not a system
/// report.
/// </para>
/// <para>
/// <b>Keys, not the mixer.</b> Volume and media use the same messages a
/// multimedia keyboard sends: they reach the active application and work
/// the same with anything, from a player to a browser. Driving volume
/// through the mixer would touch only Rina's own session, and Rina has no
/// sound of her own at all.
/// </para>
/// </remarks>
public static class Machine
{
    // Virtual key codes of the multimedia keys.
    private const byte VkVolumeMute = 0xAD;
    private const byte VkVolumeDown = 0xAE;
    private const byte VkVolumeUp = 0xAF;
    private const byte VkMediaNext = 0xB0;
    private const byte VkMediaPrev = 0xB1;
    private const byte VkMediaPlayPause = 0xB3;

    private const uint KeyEventKeyUp = 0x0002;

    [DllImport("user32.dll")]
    private static extern void keybd_event(byte key, byte scan, uint flags,
                                           UIntPtr extra);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool LockWorkStation();

    /// <summary>What the shell can do to the machine.</summary>
    /// <remarks>
    /// The names are the ones from <c>voice/system_control.py</c> in 3.1.0:
    /// these are the same abilities that moved across the process border,
    /// and renaming them would cost a change in recognition for nothing.
    /// </remarks>
    public static readonly string[] Actions =
    [
        "volume_up", "volume_down", "volume_mute",
        "media_next", "media_prev", "media_play_pause",
        "lock", "sleep", "shutdown", "restart", "screenshot",
    ];

    /// <summary>
    /// Do the named thing. Returns whether it worked, and a detail.
    /// </summary>
    /// <remarks>
    /// An unknown name is not an exception but "no such action": the core
    /// may be newer than the shell, and falling over for that is not on.
    /// </remarks>
    public static (bool Ok, string Detail) Do(string action)
    {
        try
        {
            switch (action)
            {
                case "volume_up": Tap(VkVolumeUp); return (true, "");
                case "volume_down": Tap(VkVolumeDown); return (true, "");
                case "volume_mute": Tap(VkVolumeMute); return (true, "");
                case "media_next": Tap(VkMediaNext); return (true, "");
                case "media_prev": Tap(VkMediaPrev); return (true, "");
                case "media_play_pause": Tap(VkMediaPlayPause); return (true, "");

                case "lock":
                    return LockWorkStation() ? (true, "")
                        : (false, "the system refused to lock");

                // Power goes through the standard Windows tools rather
                // than ExitWindowsEx: the same rights, the same behaviour
                // with open documents, and no detour of our own.
                case "sleep":
                    return Run("rundll32.exe", "powrprof.dll,SetSuspendState 0,1,0");
                case "shutdown":
                    return Run("shutdown.exe", "/s /t 0");
                case "restart":
                    return Run("shutdown.exe", "/r /t 0");

                case "screenshot":
                    var path = Screen.Grab();
                    return path.Length > 0 ? (true, path)
                        : (false, "could not capture the screen");

                default:
                    return (false, "no such action");
            }
        }
        catch (Exception error)
        {
            return (false, error.Message);
        }
    }

    /// <summary>Whether confirmation is needed — in the shell's opinion.</summary>
    /// <remarks>
    /// The core asks all the same (§11): confirmation is part of the
    /// conversation, not of a system call. The list is here so the shell
    /// can refuse an irreversible action that arrived without
    /// confirmation — a second lock in case the first is ever left off.
    /// </remarks>
    public static readonly HashSet<string> Irreversible =
        ["sleep", "shutdown", "restart"];

    private static void Tap(byte key)
    {
        keybd_event(key, 0, 0, UIntPtr.Zero);
        keybd_event(key, 0, KeyEventKeyUp, UIntPtr.Zero);
    }

    private static (bool Ok, string Detail) Run(string file, string arguments)
    {
        var started = Process.Start(new ProcessStartInfo
        {
            FileName = file,
            Arguments = arguments,
            UseShellExecute = false,
            CreateNoWindow = true,
        });
        return started is null ? (false, "the process did not start") : (true, "");
    }
}
