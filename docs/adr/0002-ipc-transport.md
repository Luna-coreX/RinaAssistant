# ADR 0002 — Transport between shell and core

- **Status:** accepted
- **Date:** 2026-09-01
- **Plan item:** `4.0-D01`
- **Enables:** `4.0-D02` (protocol specification), `4.0-E01`, `4.0-F02`

## Context

Version 4.0 splits the application into a Python core and a C# shell running as separate processes. They need a channel. It carries two very different kinds of traffic: small JSON control messages where latency is what matters, and continuous binary streams — microphone audio now, screen frames in 5.0 — where throughput is what matters and where a stall must not delay the control traffic.

The realistic candidates on Windows are a named pipe and a TCP socket on loopback. They were compared on latency, binary support, access control, debuggability, and behaviour when one side dies.

Latency and binary support are close enough not to decide anything: both carry bytes at local speed, and both need explicit framing if used in byte mode. Failure detection is clean on both — a broken pipe and a reset connection are equally detectable. Three things separated them.

**Access control.** A loopback port is reachable by every process of every user on the machine. Nothing in TCP itself prevents an unrelated program from connecting and driving the core: launching applications, changing system settings, and — by 5.0 — controlling the computer. Making that safe means building authentication: a secret generated at startup, passed to the shell out of band, verified on every connection, with all the ways that can be got wrong. A named pipe carries a security descriptor, so the same guarantee is a property of the object rather than code we have to write and keep correct.

**Dependencies, and which side hosts the channel.** The obvious arrangement — core as server, shell as client — costs Python either `pywin32` or an asyncio Proactor loop, since plain Python cannot host a named pipe. Inverting it removes that cost entirely: the **shell hosts the pipe and the core connects as a client**, which in C# is `System.IO.Pipes` from the base library and in Python is `open(r'\\.\pipe\...', 'r+b')` with nothing installed. The inversion also matches `4.0-E07`, where the shell already starts the core, watches it, and restarts it after a crash — the supervisor owning the endpoint is the arrangement that makes reconnection straightforward.

**Debuggability**, the one place TCP wins. There is no `netstat` for pipes, no packet capture, no reaching for a generic client. This is a real cost, and it is the reason the third option existed.

## Decision

**A named pipe, hosted by the shell; the core connects as a client.**

Two pipes rather than one, named per session:

- `\\.\pipe\rina.<session>.control` — JSON control messages
- `\\.\pipe\rina.<session>.data` — binary frames

They are separate so that a burst of audio cannot delay a control message behind it. One pipe with typed frames would be simpler to set up and would reintroduce exactly the head-of-line blocking that `4.0-D07` is required to prove absent.

Both are opened in byte mode with explicit framing defined by the protocol, rather than message mode. Message-mode pipes would hand us framing for free on Windows, but framing that the protocol defines itself is framing that survives being carried over something else.

The pipe's security descriptor restricts access to the user who owns the session. No application-level authentication is implemented, because the operating system already answers that question.

## Alternatives considered

**TCP on loopback.** Rejected on access control. Everything else about it is pleasant — familiar, observable with ordinary tools, trivially portable — but an unauthenticated local port that can drive the assistant is a hole in a product whose entire position is that the user controls their machine, and closing it means writing an authentication layer whose only purpose is to recover a property the alternative has for free.

**Named pipe as primary, TCP behind a debug flag.** Tempting: it removes the single real drawback. Rejected because it doubles the transport implementation and, more importantly, because a debug mode that opens an unauthenticated port is a debug mode that will eventually be left switched on — by a user following a stale forum post, or by us in a build. The protocol is nevertheless specified so that it does not depend on the transport, so this can be revisited cheaply if debugging proves genuinely painful.

## Consequences

**Gained.** Access control by construction rather than by code. No new dependency on either side. Reconnection has an obvious owner. Audio and control traffic cannot block each other.

**Paid.** Debugging needs tools we write. A test client for the control pipe is therefore not optional — it is required by `4.0-D16` (conformance tests) in any case, and it must exist early rather than late.

**Constrained.** The core cannot be reached without a shell hosting the pipe. For tests and headless use this is handled by an in-process transport implementing the same message interface, which the protocol permits precisely because it does not assume the pipe.

**Deferred.** If cross-platform support is ever revisited — it was rejected in `4.0-F01` — .NET maps `NamedPipeClientStream` onto Unix domain sockets, so the shape survives; the Python client side would need the equivalent change.
