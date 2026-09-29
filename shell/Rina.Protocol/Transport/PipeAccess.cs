using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;

namespace Rina.Protocol.Transport;

/// <summary>
/// Who may open the pipes between the shell and the core.
/// </summary>
/// <remarks>
/// <para>
/// <b>This user, and nobody else.</b> Created with defaults, a named pipe
/// lets every account on the machine read it and a few more write to it;
/// the core's channel carries what a person says and the orders to launch
/// programs. <c>PipeOptions.CurrentUserOnly</c> makes .NET build the pipe
/// with an ACL naming the current user alone — the promise ADR 0002 made
/// when it chose a named pipe for having a security descriptor.
/// </para>
/// <para>
/// The core is not affected: it runs as the same user, started by this
/// shell, and opens the pipe as an ordinary file.
/// </para>
/// </remarks>
public static class PipeAccess
{
    /// <summary>The options every channel is created with.</summary>
    public const PipeOptions Options =
        PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly;

    /// <summary>The accounts the pipe's ACL lets in — for the check.</summary>
    public static IReadOnlyList<string> Grantees(NamedPipeServerStream pipe)
    {
        var rules = pipe.GetAccessControl()
                        .GetAccessRules(true, true, typeof(SecurityIdentifier));
        return rules.OfType<PipeAccessRule>()
                    .Where(rule => rule.AccessControlType == AccessControlType.Allow)
                    .Select(rule => rule.IdentityReference.Value)
                    .Distinct()
                    .ToList();
    }
}
