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

### Plugins run in a process of their own — which is not a sandbox

A plugin used to be ordinary Python inside the application. It now runs in a
process of its own, one per plugin, and **declares** what it can do instead of
doing it. Both halves of that need saying plainly, because the second is
easily mistaken for the first.

**What the separation gives you.** A plugin's tools go into the same registry
as the built-in ones and get the same gates: the permission check, the
confirmation for anything irreversible, and an entry in the call journal.
Certain permissions are never issued to a plugin at all — powering the machine
off, writing files, and the ones reserved for a later version — and a tool
asking for one of those is not registered, so it cannot be offered to you and
then refuse. A plugin can reach the application for exactly two things: saying
a line, and reading its own setting. Every call has a deadline; a plugin that
does not answer is treated as broken and stopped, and its neighbours keep
working. On installation the identifier is checked, the folder it unpacks into
must land directly inside `plugins/`, names Windows reserves for devices are
refused, and a replacement is forced back to disabled instead of inheriting
the old plugin's "enabled".

**What it does not give you, and this is the part that matters.** A separate
process is not a sandbox. The plugin runs under the same interpreter with the
same rights as you have, and `subprocess` inside it still works. What was
taken away is its access to *the application*, not its access to *the
machine*. A plugin's permissions are honest about our tools and promise
nothing whatsoever about Python.

So installing a plugin remains exactly as consequential as running a
downloaded program, and should be treated that way. The real boundary is
restricted process rights; that is planned and does not exist yet. Until it
does, this is the honest description rather than a smaller claim dressed up as
a bigger one.

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

### You can see everything that is kept about you

A page in the application — Privacy → *What Rina knows about me* — lists every
kind of thing stored locally: the words you taught her, the conversation, your
reminders, things to do, your own commands, how often each has run, plugins,
the folders you pointed at, and which settings you changed. Every entry can be
removed one at a time, a group at a time, a day at a time, or all at once; and
all of it can be written out to a file, either as data or as text you can
read.

The list is assembled by walking the store rather than from a list somebody
maintains, so a kind of data added later appears on that page without anybody
having to remember to add it. If you find something stored that the page does
not show, that is a defect and worth reporting.

### She can tell you why she did something

Ask "почему?" — or "why?" — and the answer comes out of the call journal: what
was done, who asked for it, whether it was confirmed, and, for a program that
was launched, where the path came from. Refusals are explained the same way,
which is usually the question people actually have.

## Out of scope

- Anything a plugin you installed does. See above — that is the trust model, not a defect in it.
- Physical or administrator access to the machine. Someone who can write into the application folder can already replace the application.
- Configuration you set yourself, such as pointing the model at a remote server after being warned.

## Diagnostics and privacy

The application writes a log to `%APPDATA%/RinaAssistant/logs/`, and keeps a
journal of tool calls next to it. **Neither records what you said** — only how
long it was — unless you explicitly enable "Log message texts" in
Settings → Privacy.

The rule for the call journal is not a list of exceptions but a property of
each argument: a value chosen from a fixed set is written down as it stands,
because "shutdown" came from a list of three and says nothing about you; free
text is replaced by its length. That way the journal can answer *what she did*
without answering *what you asked about*.

This is so a log can be attached to a report without disclosing your
conversations. Check the setting before attaching one, and skim the file if in
doubt.
