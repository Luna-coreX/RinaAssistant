# Contributing

Thanks for looking. This is a personal project maintained by one person, so response times vary — but issues and pull requests are read and taken seriously.

## Licensing of contributions

The project is licensed under the **Apache License 2.0** (see [`LICENSE`](LICENSE)).

Anything you submit for inclusion is licensed under those same terms, unless you say otherwise when you submit it. That is section 5 of the licence itself, so **there is no separate agreement to sign** — no CLA, no paperwork. Opening a pull request is enough.

Please only submit work you have the right to submit. Do not paste code from a project under an incompatible licence, and if a change is substantially derived from something else, say where it came from.

## Before you write code

**Open an issue first for anything non-trivial.** The project follows a written plan ([`docs/ROADMAP.md`](docs/ROADMAP.md)), and some things that look like obvious improvements are deliberately scheduled for later or deliberately excluded. A short conversation beforehand saves you from work that cannot be merged.

Small, self-evident fixes — a crash, a typo, a wrong translation — need no ceremony. Just send them.

## What the code looks like

Read a neighbouring file before writing a new one. A few things are consistent throughout and worth matching:

- **Comments explain why, not what.** The code already says what it does. Comments carry the reason a thing is done a particular way — usually the problem that made the obvious approach wrong.
- **`core/` must not import Qt.** The core is headless on purpose: it is being prepared to run as a separate process. If your change needs the core to reach the interface, it should emit an event instead (`core/protocol.py` lists them).
- **Text from outside is not markup.** Anything originating from a model, a plugin, a file, or speech recognition is rendered as plain text. There is a reason: see [`SECURITY.md`](SECURITY.md).
- **User-visible strings go through `t()`** and need an English entry in `core/i18n.py`. The other four languages live in `core/i18n_langs.py`; adding them is welcome but not required.
- **Dangerous actions ask first.** Anything that shuts down, deletes, or acts on the user's behalf goes through the confirmation path rather than around it.

## Testing your change

There is no test framework in the repository yet — checks are written as standalone scripts. At minimum, before opening a pull request:

- Launch the application and exercise the path you changed.
- If you touched the command pipeline, try a handful of awkward phrasings, not just the happy one.
- If you touched anything that reads stored data, try it with that data missing and with it corrupted.

Say in the pull request what you actually ran. "I tested it" is less useful than "I launched it, set a timer, and restarted to check it survived".

## Reporting bugs

Include the version, your Windows version, what you said or typed, and what happened instead. A log helps: `%APPDATA%/RinaAssistant/logs/`. **Message texts are not written to it** unless you switched that on in Settings → Diagnostics, so it is normally safe to attach — but skim it first if you are unsure.

## Security

Do not report vulnerabilities in public issues. [`SECURITY.md`](SECURITY.md) explains where they go and describes the trust boundaries — worth reading before you conclude that something is a vulnerability, since a few sharp edges are documented and deliberate.

## Translations

Five languages are supported. Russian is the source; English is complete; Ukrainian, Spanish and German are partial. Filling gaps is genuinely useful and needs no discussion beforehand — the untranslated strings are the ones missing from `core/i18n_langs.py`.
