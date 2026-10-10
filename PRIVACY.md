# Privacy Policy — Rina Assistant

Version 1.0 · 11 October 2026

Russian version: [PRIVACY.ru.md](PRIVACY.ru.md).

## In short

- Rina Assistant runs on your computer. Your conversations, commands, history and settings stay there, unless you yourself send something out — for example, to a web search or an online voice.
- The program sends nothing to the developer except beta telemetry. Telemetry is off by default and is switched on only by you.
- The website sets no cookies and collects no analytics.

## 1. Who is responsible for your data

Rina Assistant is an open-source project under the Apache-2.0 licence, maintained by Luna-coreX. The installer names NeuroSync Foundry as the publisher.

The operator of the services the project runs itself — the website and the telemetry collector — is the project's developer, Luna-coreX. The legal entity and its details will be stated here if and when there is one.

You can reach us through [GitHub Issues](https://github.com/Luna-coreX/RinaAssistant/issues) for questions, and through a [private GitHub security advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new) for requests about your data and for vulnerabilities.

## 2. What is stored on your computer

Everything the program knows about you is kept in its data folder on your computer (`%APPDATA%\RinaAssistant`):

- settings;
- conversation history — only if you keep it;
- your commands and the statistics of their runs;
- reminders, to-dos, sessions;
- words learned and corrections made;
- the security journal and the call journal;
- backups the program makes before updating its storage format;
- the list of programs you allowed to run, and the list of installed programs;
- recognition and speech model files.

Model keys and plugin secrets are kept in the Windows Credential Manager, not in files.

The journals do not record what was said, unless you have switched on recording of texts yourself. The security journal does record every program launched, with its path and time.

All of this can be viewed, exported and deleted on the page "What Rina knows about me". None of it is sent to us.

## 3. What leaves your computer — only by your choice

| What | When | What is sent | To whom |
|---|---|---|---|
| Beta telemetry | Only if you switched it on | A report no more than once a day; contents in section 4 | Our collector on Vercel (Frankfurt region); database on Neon (Frankfurt) |
| Web search for an unrecognised phrase | Only if switched on | The phrase itself | The search engine in settings: DuckDuckGo (default), Brave Search, Startpage, Mojeek or Qwant |
| Edge online voice | Only if chosen | The text of the reply | Microsoft |
| gTTS online voice | Only if chosen | The text of the reply | Google |
| Language model on your computer (Ollama, LM Studio, llama.cpp) | By default | Nothing leaves | — |
| Language model at another address | If the address in settings is not local | The question and the last few lines of conversation | That address |
| Ollama cloud model | If chosen | The question and the lines | ollama.com |
| OpenRouter | If chosen and you entered your own key | The question and the lines, with your key | openrouter.ai |
| Downloading models | When you start it | The file request; the server sees your IP address | alphacephei.com (Vosk), huggingface.co (Whisper, Piper) |
| Update check | Once a day or on the button | The program's version; the server sees your IP address | GitHub (api.github.com) |
| Weather (plugin) | If the plugin is on and you ask | The city name and its coordinates | Open-Meteo (open-meteo.com) |
| Exchange rates (plugin) | If the plugin is on and you ask | The rate request; nothing about you | The Central Bank of the Russian Federation (cbr.ru) |
| Music and video | If you ask for them | A search page opens in your browser | YouTube — then under the browser's and the site's policies |
| Third-party plugins | If you installed them | The requests the plugin declares in its `sends` field | As described by the plugin |
| Diagnostic package | Only if you create it and send it | What you see in the package before sending it | Whoever you send it to |

We do not review third-party plugins. By installing one you accept its terms and policy.

## 4. Beta telemetry

- **Switching it on.** Telemetry is off by default. You switch it on in the first-run setup or in settings, and before it is switched on the program shows what is sent and what is not.
- **What is sent.** Exactly these, and nothing else: the program's and Windows' versions; the interface language; how many days counting has run; the chosen recognition and speech engines; whether model answers and always-on listening are switched on; whether Rina has a personality of your own; counters — which intents and tools ran and how often, error codes and short reasons for refusal from the program's vocabulary; timings of recognition and of the first sound; a random installation number.
- **What is never sent.** What you said or typed; sound; paths and file names; the names of your programs and plugins; addresses; passwords and keys.
- **Installation number.** It is random and is not linked to your user account, e-mail or name. It exists so that reports from one installation can be connected from day to day, while telemetry is on.
- **Retention.** The collector records the day a report arrived and the report itself, one report per installation per day. It records neither the address nor the time of day. Records older than 180 days are deleted every night.
- **Platform log.** Vercel keeps its own log of function calls, which cannot be switched off. The request address is in it. On the Hobby plan that log is kept for about an hour. It is the platform's log rather than ours, but we say so plainly.
- **Switching it off.** Switching telemetry off deletes what has been gathered on your computer and the random installation number. Reports that have already reached the server are deleted on request — see section 7.
- **Viewing.** Every report that was sent is shown in full on the page "What Rina knows about me".
- **Leaving with Stable.** In 4.0.0 Stable telemetry is removed from the program, and the collector is switched off together with its database.

## 5. The website

The website is static and hosted on Vercel. The host sees visitors' addresses in its call log, as described in section 4.

The website sets no cookies, does not use localStorage, and makes no requests to third-party services: there are no external fonts, scripts, analytics, advertising networks or counters. Links to GitHub or other sites are governed by those sites' policies once you follow them.

## 6. Who else sees data

- **Vercel** — hosts the website and the telemetry collector.
- **Neon** — the database of telemetry reports.
- **GitHub** — source code, releases and requests. Issues are public: do not put personal data in them.

We do not sell data, do not pass it to advertising networks and do not use it for targeting.

## 7. Retention and deletion

- Data on your computer is kept until you delete it, in the program.
- Telemetry reports are kept for up to 180 days.
- To delete reports that have already reached the server, send your installation number through a [private GitHub security advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new). The number is shown on the page "What Rina knows about me". We will delete the records with that number. Without the number your reports cannot be found, because they are not linked to you.
- Vercel's logs are kept for the platform's periods, which we do not control.

## 8. Your rights

You have the right to learn which data about you is processed, to ask for its deletion, to object to its processing and to withdraw consent by switching telemetry off. For data on your own computer you do all of this yourself, in the program.

If you are in the EU, the GDPR applies; if you are in the Russian Federation, Federal Law No. 152-FZ applies. We try to follow the principles of data minimisation and transparency, but this is not a legal assessment of your situation.

## 9. Children

The program is not intended for children and does not collect data that is linked to a particular person. Telemetry contains no such data.

## 10. Security

Model keys are kept in the Windows Credential Manager. They are sent only over `https` or to this computer, and requests carrying a key are not followed to another address. For more, see [SECURITY.md](SECURITY.md) and the [threat model](https://www.rina-assistant.com/security/).

## 11. Changes

This document changes together with the program. The version and date are at the top. Significant changes, such as new recipients of data, are recorded in [CHANGELOG.md](CHANGELOG.md) and shown in the program before they take effect.

## 12. Contacts

- Questions and suggestions: [GitHub Issues](https://github.com/Luna-coreX/RinaAssistant/issues).
- Requests about your data and vulnerabilities: [private GitHub security advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new).
