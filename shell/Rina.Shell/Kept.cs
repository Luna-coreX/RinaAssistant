using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;

namespace Rina.Shell;

/// <summary>
/// The little the shell keeps for itself.
/// </summary>
/// <remarks>
/// <para>
/// <b>Why not in the settings.</b>
/// [ADR 0006](../../docs/adr/0006-settings-ownership.md) divides it: the
/// core owns meaning, the shell owns appearance. How large the window was
/// when it was last closed is not a setting — nobody goes looking for it,
/// nobody sets it on purpose, and it means nothing to the core. Putting it
/// in the core's store would be a line sneaked into somebody else's data,
/// and it would then show up on the settings page, because the rule with
/// teeth there is that a key with nowhere to go is shown rather than
/// hidden.
/// </para>
/// <para>
/// So the shell has a store of its own. One small file, beside the core's
/// — the same person's data folder, because it is the same program — and
/// deliberately nothing but presentation in it.
/// </para>
/// <para>
/// <b>It is allowed to be missing, empty or nonsense.</b> A first run has
/// no file; a half-written one is a file that was being saved when the
/// machine went off. Neither is an error worth a word to anybody: the
/// defaults are perfectly good, and this is a convenience, not a record.
/// </para>
/// </remarks>
public static class Kept
{
    /// <summary>Where it lives.</summary>
    /// <remarks>
    /// Beside the core's settings rather than in a folder of the shell's
    /// own: a person looking for "where Rina keeps her things" should
    /// find one place, and «о программе» already points them at it.
    /// </remarks>
    private static string Where => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "shell.json");

    /// <summary>How big the window should open.</summary>
    /// <param name="Width">Points across.</param>
    /// <param name="Height">Points down.</param>
    /// <param name="Full">It was maximised.</param>
    public sealed record Size(double Width, double Height, bool Full);

    /// <summary>The size a first run opens at.</summary>
    /// <remarks>
    /// Larger than it was: 940 by 620 was chosen when the window held a
    /// figure and a list, and a settings page with three columns in it
    /// is cramped at that. Still small enough to fit a laptop — and
    /// clamped to the screen below in any case.
    /// </remarks>
    public static readonly Size Default = new(1180, 780, Full: false);

    /// <summary>What was kept, or the default.</summary>
    public static Size Window()
    {
        try
        {
            if (!File.Exists(Where)) return Default;
            var read = JsonNode.Parse(File.ReadAllText(Where))?["window"];
            if (read is null) return Default;
            var width = read["width"]?.GetValue<double>() ?? Default.Width;
            var height = read["height"]?.GetValue<double>() ?? Default.Height;
            var full = read["full"]?.GetValue<bool>() ?? false;
            // A size out of all reason is not a size. It comes of a
            // screen that has been unplugged, of a file half written,
            // and of nobody having checked.
            if (width < 640 || height < 480
                || width > 20000 || height > 20000) return Default;
            return new Size(width, height, full);
        }
        catch (Exception exc)                            // noqa
        {
            Journal($"shell store unreadable: {exc.GetType().Name}");
            return Default;
        }
    }

    /// <summary>Keep this size for next time.</summary>
    public static void Window(Size size)
    {
        try
        {
            var folder = Path.GetDirectoryName(Where);
            if (folder is not null) Directory.CreateDirectory(folder);

            // Read what is there first: this file is the shell's, not
            // this property's, and whatever else comes to live in it
            // must not be wiped by a window being closed.
            var all = File.Exists(Where)
                ? JsonNode.Parse(File.ReadAllText(Where)) as JsonObject
                  ?? []
                : [];
            all["window"] = new JsonObject
            {
                ["width"] = size.Width,
                ["height"] = size.Height,
                ["full"] = size.Full,
            };
            File.WriteAllText(Where, all.ToJsonString(
                new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception exc)                            // noqa
        {
            // Losing the size of a window is not worth telling anybody
            // about, and certainly not worth taking the program down on
            // the way out.
            Journal($"shell store unwritable: {exc.GetType().Name}");
        }
    }

    /// <summary>
    /// Fit a size to the screen it will open on.
    /// </summary>
    /// <remarks>
    /// A window remembered from a large monitor opens off the edge of a
    /// small one, and a person who unplugs a screen finds the program
    /// gone. The working area, not the whole screen: the taskbar is
    /// part of what is in the way.
    /// </remarks>
    public static Size OnScreen(Size wanted)
    {
        var room = SystemParameters.WorkArea;
        return new Size(Math.Min(wanted.Width, room.Width),
                        Math.Min(wanted.Height, room.Height),
                        wanted.Full);
    }

    private static void Journal(string said)
    {
        try { Console.Error.WriteLine(said); } catch { /* nowhere to say it */ }
    }
}
