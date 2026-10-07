using System.Diagnostics;

namespace Rina.Shell.Platform;

/// <summary>
/// Opens a web address in the default browser, for the core.
/// </summary>
/// <remarks>
/// <para>
/// The core decided what to open; the machine is the shell's (ADR 0009).
/// Until this existed the core opened the browser itself — a search, music,
/// and every "website" step of a person's own command — past anything the
/// shell checks and records (audit 2026-10-07, H-2).
/// </para>
/// <para>
/// <b>Only <c>http</c> and <c>https</c>, absolute, without a login in the
/// address.</b> Shell execution opens whatever has a handler — <c>file:</c>,
/// <c>ms-settings:</c>, a registered protocol of any installed program — and
/// a card imported from somebody else's file must not reach those by being
/// called a website. A <c>user:password@</c> part is refused as well: it is
/// how an address is dressed up as another one.
/// </para>
/// <para>
/// The journal gets the fact and the host, never the address: a search's
/// words travel in it.
/// </para>
/// </remarks>
public static class Browser
{
    /// <summary>Whether an address may be opened, and if so which.</summary>
    public static Uri? Allowed(string url)
    {
        if (!Uri.TryCreate((url ?? "").Trim(), UriKind.Absolute, out var uri))
            return null;
        if (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            return null;
        if (uri.UserInfo.Length > 0 || uri.Host.Length == 0)
            return null;
        return uri;
    }

    /// <summary>Open it. (opened, why not — for the core).</summary>
    public static (bool Ok, string Reason) Open(string url)
    {
        var uri = Allowed(url);
        if (uri is null)
        {
            Journal.Action("browser.open.refused", false);
            return (false, "not a web address");
        }
        try
        {
            _ = Process.Start(new ProcessStartInfo
            {
                FileName = uri.AbsoluteUri,
                UseShellExecute = true,
            });
            // A browser that is already running takes the address and the
            // process handed back is null; that is an opened page, not a
            // failure.
            Journal.Action($"browser.open {uri.Host}", true);
            return (true, "");
        }
        catch (Exception error)
        {
            Journal.Action($"browser.open {uri.Host}", false);
            return (false, error.Message);
        }
    }
}
