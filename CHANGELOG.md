# Changelog

All notable changes to Rina Assistant.
Releases before 3.0.0 are documented on the [releases page](https://github.com/Luna-coreX/RinaAssistant/releases).

---

## Unreleased

### Fixed

**"Убавь громкость" made it louder.** System phrases are matched in one pass, longest first, with a fuzzy fallback for misrecognition. "Убавь громкость" scores 0.875 against "прибавь громкость" — above the 0.82 threshold — and the latter is two characters longer, so it was tested first and won. Matching is now two passes: exact containment first, approximate only afterwards. An exact phrase must beat an approximate one whatever its length.

Found by the new golden-utterance set on its first run, which is precisely what that set exists for. All 53 system phrases now resolve to their own action, and the pair is kept as a regression case.

### Licence

**The project moved from MIT to the Apache License 2.0.** The reasoning is in [ADR 0001](docs/adr/0001-license-and-contributions.md); in short, Apache-2.0 gives everything MIT gave and adds two things this project needs — an explicit patent grant, and protection of the name, so a fork inherits the code but not the right to call itself Rina.

The change was made now because it could be: every commit so far is by one author, who could therefore relicense unilaterally. That stops being true the moment outside code is merged.

**This is not retroactive.** Releases up to and including 3.1.0 went out under MIT, and copies obtained under those terms keep them.

**Contributions need no agreement to sign.** Apache-2.0 section 5 licenses a submitted contribution under the same terms by default, which is the job a CLA would otherwise do. Added `CONTRIBUTING.md` describing this, `NOTICE` for attribution, and `docs/adr/` for decision records.

---

## 3.1.0 — 2026-09-01

An intermediate release between 3.0.0 and the 4.0.0 split. It adds one new behaviour — the application now keeps a log — and otherwise closes findings from two audits, mine and an external review, preparing the ground for moving the core into its own process.

### Highlights

- **Logs.** Levels, rotation, and a separate security log. Message texts are never written unless you explicitly ask for them.
- **No shell, no bare names.** The last `shell=True` is gone; programs are launched by absolute path.
- **Speech no longer overlaps itself.** One playback queue, one temporary file per answer.
- **Commands left the interface thread.** Typing a command no longer freezes the window while the model thinks.
- **Nothing gets stuck.** Test buttons, recognition failures and the command pipeline report what happened instead of going quiet.

---

### Observability

**Logging with levels.** New `core/logging_setup.py` — `DEBUG` / `INFO` / `WARNING` / `ERROR`, rotating files (1 MB × 3) under `%APPDATA%/RinaAssistant/logs/`, level selectable in **Settings → Diagnostics**. Uncaught exceptions are recorded, including those in background threads — which previously killed the thread in silence and left the user looking at an action that simply never happened.

**Message texts stay private.** Only their length is logged unless "Log message texts" is deliberately switched on, so a log can be attached to a bug report without disclosing conversations. When the setting is on, the log says so on its first line.

**A separate security log.** `security.log` records what both audits had to reconstruct by hand: plugin installs and replacements, rejected plugin names, command imports (how many accepted, how many discarded), execution of power actions, requests to a non-local model address, and refusal of a dangerous action at the confirmation prompt.

---

### Security

**The last `shell=True` is gone.** It lived in `voice/commands.py`, launching `discord`, `calc`, `notepad`, `explorer` and `start chrome` by bare name through the command interpreter. No user input reached it, so this was not command injection — but Windows searches the current directory, so a file placed next to the application would have run instead. Programs are now resolved to an absolute path (System32 → `%SystemRoot%` → PATH) and started without a shell. Verified by planting a decoy `notepad.exe` in the working directory: the real one still wins.

**The browser fallback works again.** `start chrome` could not survive removing the shell; if Chrome is not found, the default browser opens instead of nothing happening.

**Store apps report honestly.** Launching a UWP app always returned success, because `explorer.exe` says nothing about what became of `shell:AppsFolder\<id>` — and waiting for it is unsafe, since it becomes the desktop shell process when not already running. The identifier is now checked against the index before launching, and an unknown one fails without spawning anything.

**A vanished program says so.** Command targets and index entries are checked for existence before launching, and the answer names the cause — "Не нашла «foo.exe» — программу удалили или перенесли" — instead of "Не получилось выполнить команду". Bare names such as `discord` are deliberately left alone: Windows resolves them through the App Paths registry, and that is a legitimate way to write a command.

**`SECURITY.md`.** Private reporting through GitHub Security Advisories, plus an explicit description of the trust boundaries — most importantly that **a plugin is ordinary Python with the application's rights, and there is no sandbox**. Installing one is as consequential as running a downloaded program.

---

### Reliability

**Speech no longer overlaps itself.** Playback went through no queue and three fixed temporary filenames (`rina_gtts.mp3`, `rina_edge.mp3`, `rina_piper.wav`), so two answers in quick succession overwrote each other's file and played at the same time. There is now a single playback worker, one uniquely named file per synthesis, deletion after playback, and a failed file no longer kills the worker.

**The microphone no longer hears Rina.** `_speaking` was one flag for the whole core, so with two overlapping answers the first to finish cleared it and the microphone opened under speech that was still playing. It is now a counter: the flag holds until the last speaker finishes.

**Default settings are copied properly.** `dict(DEFAULTS)` is a shallow copy, and more than a dozen defaults are mutable — `plugin_settings`, `wake_words`, `action_hotkeys`, `app_aliases`, `program_folders`, `custom_commands`. Changing a plugin setting wrote into the module-level defaults, so "reset" restored the already-modified value rather than the factory one.

**Stores no longer lose writes.** History, reminders, usage statistics and user commands all used read-modify-write: two threads read the same state and the second overwrote the first. All of them now run under one store-wide lock. Under load — four threads writing at once — 160 of 160 history entries, 60 of 60 reminders, and exactly 200 of 200 counter increments survive.

**Test buttons come back.** `MicTester._worker` had no `try/finally`: an exception left the button greyed out until restart. The model's "Check connection" button had the same shape, and `http.client.HTTPException` — which does not inherit from `OSError` — escaped the request handler entirely. Both now report the cause and return to a usable state.

**Recognition failures are visible.** `_listen_worker` had a `finally` but no `except`, so a failing engine cleared the indicator and killed the thread without a word.

---

### Responsiveness

**Commands run off the interface thread.** Typed commands drove the entire pipeline in the GUI thread; with the language model enabled, that is several seconds of a frozen window. Commands now go through a single queue inside the core — the window stays live, ordering is preserved, and an exception in one command no longer strands every command behind it. Always-listen still waits for completion, because it must not listen while Rina is answering.

**Hotkeys fire once.** Holding a combination produces key auto-repeat, and every repeat was reported as a fresh activation. A 300 ms suppression window per combination fixes it.

**Theme switching is safe.** Pages were destroyed from inside the theme-change signal handler — while that signal was still being delivered to those same pages. The rebuild is now deferred to the next event-loop turn and guarded against re-entry. The tray menu is rebuilt on theme and language change instead of keeping the old palette and the old language, and its old actions are released rather than accumulated.

**Plugins load after Qt exists.** `plugin_manager.discover()` ran before `QApplication` was constructed. It only reads manifests today, but it also loads the code of enabled plugins — and a plugin touching Qt at that moment would have crashed the launch with nothing to tell the user.

---

### Parsing

**Compound durations.** "Поставь таймер на 1 час 30 минут" was read as one hour, and the user found out ninety minutes later. All number-unit pairs are now summed: 5400 seconds for that phrase, 8130 for "2 часа 15 минут 30 секунд".

**Percentages only when asked.** Percentage parsing ran before the check that the phrase was addressed to the calculator at all, so ordinary speech containing "20 процентов от 3000" was answered with arithmetic. It now follows the same admission rule as the rest of the calculator: an explicit trigger, or a phrase that is nothing but the expression.

---

### Decisions

**Plugin trust boundary (ADR).** Recorded for 4.0.0 as `4.0-H07`: a plugin gets its own process and speaks to the core over the same protocol as the shell. It lands there rather than in 5.0.0 because `H03` rewrites the Plugin API from scratch anyway, `D02` designs the protocol anyway, and `C04` builds the permission catalogue anyway — so a plugin becomes one more protocol client instead of a separate mechanism. Deferring would mean changing the Plugin API twice and migrating the bundled plugins twice. A full sandbox with resource limits was rejected as a separate research task: in-process sandboxing does not exist in Python, and OS-level limits can be layered on top of `H07` later if needed.

---

### Deliberately not done

- **Moving all storage to SQLite**, as the external review proposed. 5.0.0 introduces SQLite for memory and 4.0.0 migrates user data; doing that migration twice buys nothing. The races are fixed with a lock instead.
- **An allow-list of directories for command targets.** It would break portable programs, which is the case the mechanism was built for. Imported commands remain sanitised and disabled.
- **Schema validation of event payloads.** That is `4.0-D02` and `4.0-D04`. Wrapping every event in a version envelope is the wrong shape: the version is agreed once at handshake, and plugins do not subscribe to the event bus at all.

---

### Verification

- **Block tests:** security 26 checks, reliability 27, responsiveness 15, parsing 24, security log 12 — all passing.
- **Regression:** command pipeline, reminders, plugins, import/export, all 5 languages, all 5 themes — 0 failures.
- **Translations:** 0 untranslated strings.

### On the external review

An external audit of 3.0.0 was reviewed alongside my own. Of its twelve findings, two were confirmed and are fixed here (the speech queue and the hotkey debounce), two were real but attributed to the wrong file, three were already fixed in 3.0.0, and the rest did not match the code — including a quoted fragment of `settings_store.py` that does not exist, and a claim of `shell=True` in `voice/system_control.py`, which contains none. Checking that particular claim is what surfaced the real `shell=True` in `voice/commands.py`. Its recommendations section was considerably stronger than its findings: the logging work and `SECURITY.md` in this release come from it.

---

## 3.0.0 — 2026-08-30

The largest release so far. Rina's brain was pulled out of the interface and now runs on its own; free-form questions can be answered by a local language model; and a full security and crash audit closed a set of issues, two of which could destroy data or run someone else's code.

### Highlights

- **Headless core.** All command handling moved into `core/`, which imports no Qt at all. The window is now a thin shell subscribed to events.
- **AI answers.** Anything Rina can't parse can be answered by a local Ollama model instead of "Sorry, I didn't understand."
- **Security audit.** Two critical plugin vulnerabilities fixed, plus untrusted text no longer rendered as markup, and imported commands can no longer arrive pre-armed.
- **Crash audit.** ~600 hostile inputs, corrupted data files and concurrent access: 30 failures found, 0 remaining.

---

### Architecture: the headless core

Rina used to think inside `voice/service.py`, which was a `QObject`. Recognition, parsing, launching and speaking were all entangled with the widget tree, so none of it could run — or be tested — without a window on screen.

- **`core/engine.py`** — the whole pipeline: pending questions → plugins → user commands → reminders → system control → app launcher → built-ins → language model → web fallback. **Zero Qt imports.**
- **`core/events.py`** — a small synchronous event bus. The core announces what happened; it never touches a widget.
- **`core/protocol.py`** — every event and its payload declared in one place, with a `PROTOCOL_VERSION`. Payloads are plain JSON-serialisable values, so this contract becomes an IPC protocol unchanged when the shell moves to another process or another language.
- **`voice/service.py`** — reduced from ~700 lines of logic to a Qt adapter that forwards core events to signals. **−538 lines.**

Practical consequences today: the core can be driven headless in tests, the shell can be replaced without touching behaviour, and a background thread can no longer accidentally call into Qt.

---

### AI answers via Ollama

When no handler claims a phrase, Rina can now ask a local model.

- **Local by design.** Requests go only to the address in settings (`localhost:11434` by default). Nothing leaves the machine; if you point it elsewhere, the settings page says so plainly.
- **No new dependencies.** Ollama speaks HTTP, so `urllib` is enough.
- **Conversational.** The last 6 exchanges are sent as context, so follow-up questions work.
- **Spoken-answer persona.** The default prompt asks for one or two sentences, no lists, no markup, in the speaker's language — the answer is read aloud.
- **New `THINKING` event.** The interface shows an indicator instead of going silent for several seconds.
- **Settings → AI.** Enable, server address, model picker (populated from the server), custom persona, timeout, and a "Check connection" button.

Disabled by default. With it off, the pipeline behaves exactly as in 2.5.0.

---

### Security

Every issue below was reproduced in a sandbox before being fixed, not inferred from reading the code.

#### Critical

**Plugin installation could delete the application.** A `plugin.json` declaring `"id": ".."` escaped the plugins folder, and the overwrite step then removed the application root — `main.py`, `core/`, every plugin. Fixed in three layers: plugin ids are validated against a strict whitelist, the resulting path is re-checked **after** joining to confirm it is a direct child of the plugins folder, and nothing is removed unless the target actually contains a `plugin.json`.

**A plugin could run without being enabled.** An archive reusing the id of an already-enabled plugin replaced it, and its code executed **immediately** during the automatic re-scan — while the interface still said "Enable it below." Replacing a plugin now forces it back to disabled, and the confirmation message says a plugin was replaced.

**Folder names are now authoritative.** `discover()` used to trust the `id` inside the manifest, so a manifest could claim another plugin's identity and inherit its stored settings. The folder name wins.

#### High

**Untrusted text is no longer rendered as markup.** Qt labels interpret HTML by default and `setTextFormat` was never called, so a model reply, a recognised phrase, plugin output or a plugin manifest containing `<img src="file://some-host/x">` would make Windows reach out to that host over SMB. All externally-sourced text — history, toasts, plugin pages, plugin cards — is now explicitly plain text.

**Imported commands can no longer arrive armed.** Command files were validated only by their envelope; `type`, `target` and `enabled` were trusted verbatim, so a shared file could plant an enabled command pointing at an arbitrary executable or UNC path. Imported entries are now reduced to known fields, checked against the known command and system-action types, capped (500 commands, 20 triggers, 200 characters each, minimum 2), and **always imported disabled**.

**System binaries are launched by absolute path.** `shutdown.exe` and `rundll32.exe` were invoked by bare name, and Windows' search order includes the current directory — a file dropped there would run instead. Resolved through `%SystemRoot%\System32` now.

#### Medium

- The Ollama address was accepted as free text; it is now required to be `http`/`https` with a host, responses are capped at 4 MB, and a non-local address is flagged in settings.
- Removed a dead `dispatch_user_command` path that **skipped the confirmation prompt** for destructive actions.

---

### Reliability

**Settings could be lost, and could kill the reminder scheduler.** `save()` iterated the live dirty-key set while another thread modified it, raising `RuntimeError: Set changed size during iteration`. The store is now guarded by a lock and snapshots the set before writing.

**Vosk speech recognition never worked.** A missing `import os` made the model loader raise `NameError` on the first phrase for anyone who installed Vosk.

**Corrupted data no longer breaks a whole tab.** History and reminder stores now normalise and drop malformed records instead of propagating them into the interface.

**Absurd dates are no longer permanent.** "Remind me in 99999999999999999999 minutes" produced an entry that broke the Reminders tab on every launch and could not be deleted. Durations are now bounded, dates are clamped to ten years out, and unformattable timestamps degrade to `—`.

**Duplicate command execution.** Toggling always-listen twice left two microphone threads running, so a single phrase was handled twice. Each run now owns its own stop signal.

**Interface freezes.** The full application scan — including a PowerShell call for Store apps — ran on the interface thread when opening the command editor. It now reads the cached index and refreshes in the background.

**Screenshots crashed from the wrong thread.** Screen capture is a Qt operation and was being called from the worker; it now travels to the shell as a window action and is taken on the interface thread.

Also fixed: a failed system action reported success inside sequences; a malformed `format` field escaped the import handler as an unhandled `ValueError`; the "Refresh applications" button could stay disabled after a failed scan.

---

### Interface

- New **AI** section in Settings with a live connection check.
- History messages measure their own wrapped height, so long replies are no longer clipped.
- Plugin cards and plugin-authored pages render text safely (see above).
- Documentation strings corrected where they had drifted from the code (event contract, reminder scheduler).

---

### Housekeeping

- Removed the empty `ui/` package left over from 1.0.0; the build spec now ships `core/`.
- README rewritten from scratch for the current application, with screenshots.

---

### Verification

- **Crash test:** ~600 hostile inputs (empty, 10 000 characters, emoji, control and RTL characters, `../..`, UNC paths, division by zero, `2**2**2**2**2`, "at 99:99"), corrupted data files, answers with no question pending, and 4 concurrent threads — **30 failures → 0**.
- **Security probes:** path traversal 0 failures; plugin replacement no longer executes on discovery.
- **Regression:** command pipeline, reminders, plugins, import/export, all 5 languages, all 5 themes — **0 failures**.
- **Translations:** 0 untranslated strings.

---

### Known limitations

- Typed commands still run the pipeline on the interface thread; the worst stall (the application scan) is gone, but launching still happens there.
- Overlapping speech replies share one busy flag, and gTTS/Piper use fixed temporary filenames — two answers in quick succession can interfere.
- History, reminders and usage statistics still use read-modify-write updates.
- "1 hour 30 minutes" is parsed as one hour; only the first unit is read.
