# Security Policy

## Reporting a vulnerability

Report privately through **[GitHub Security Advisories](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new)** — not through public issues, so the problem is not disclosed before it is fixed.

Please include the version, your operating system, and the smallest set of steps that reproduces the problem. A proof of concept helps, but a clear description is enough.

Expect an acknowledgement within a few days. This is a personal project, not a company: there is no bounty programme and no guaranteed response time, but reports are taken seriously and credited in the changelog unless you prefer otherwise.

For anything that is not a vulnerability — a crash, a wrong answer, a mistranslation — the normal [issue tracker](https://github.com/Luna-coreX/RinaAssistant/issues) is the right place.

## Supported versions

Only the latest release receives fixes. There are no long-term support branches.

## What Rina trusts, and what she does not

Knowing where the boundaries are makes it easier to tell a vulnerability from intended behaviour.

### Plugins are arbitrary code

**A plugin is ordinary Python running inside the application, with the same rights as the application itself.** It can read and write your files, reach the network, and start programs. There is no sandbox.

Installing a plugin is therefore exactly as consequential as running a downloaded program: install only what you have reason to trust. The application does what it can at the edges — plugin identifiers are validated, a plugin can only be written into its own folder inside `plugins/`, a replaced plugin is forced back to disabled rather than silently taking over the old one's place, and the folder name — not the manifest — decides a plugin's identity. None of that constrains what the code inside does once you enable it.

A tighter boundary is planned; until it exists, this is the honest description.

### Imported commands arrive disabled

A command file can name any program to launch, so importing one is treated as untrusted input. Imported entries are stripped to known fields, checked against the known command and system-action types, capped in size and number, and **always imported disabled**. You have to look at a command and enable it before it can run.

### Destructive actions always ask

Shutdown, restart and sleep are never performed on a single recognised phrase. Speech recognition mishears; a confirmation step means a misheard word cannot power off the machine.

### Text from outside is never markup

Model replies, recognised speech, plugin output and plugin manifests are rendered as plain text. Otherwise a crafted string could make the interface fetch a remote resource — on Windows, an SMB path is enough to leak an authentication attempt.

### The language model is local by default

Requests go only to the address in settings, `http://localhost:11434` unless you change it. If you point it somewhere else, the settings page says so, because at that moment your questions start leaving the machine.

### System programs are launched by absolute path

Windows searches the current directory when a program is named without a path. Every system utility the application invokes is resolved through `%SystemRoot%` first, so a file dropped next to the application cannot take its place.

## Out of scope

- Anything a plugin you installed does. See above — that is the trust model, not a defect in it.
- Physical or administrator access to the machine. Someone who can write into the application folder can already replace the application.
- Configuration you set yourself, such as pointing the model at a remote server after being warned.

## Diagnostics and privacy

The application writes a log to `%APPDATA%/RinaAssistant/logs/`. **Message texts are not written to it** — only their length — unless you explicitly enable "Log message texts" in Settings → Diagnostics. This is so the log can be attached to a report without disclosing your conversations. Check the setting before attaching a log, and skim the file if in doubt.
