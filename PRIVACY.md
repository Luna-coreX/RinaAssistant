# Rina Assistant Privacy Policy

Version 1.1 · effective 11 October 2026

Russian version: [PRIVACY.ru.md](PRIVACY.ru.md). Licence agreement: [EULA.md](EULA.md). If the versions differ, the Russian version prevails.

## In short

- Rina Assistant runs on your computer. Your conversations, commands, history and settings stay there unless you yourself send something out, for example to a web search or an online voice.
- The rights holder receives nothing from the program except beta telemetry reports. Telemetry is off by default and is switched on only by you.
- The program sends the rights holder nothing that identifies you: no name, no e-mail, no account.
- The website sets no cookies, runs no analytics and loads nothing from third-party servers.

## 1. General provisions

1.1. This Policy describes what information is processed when you use the Rina Assistant program (the Program) and the website www.rina-assistant.com (the Website): who processes it, why, on what basis and for how long, and what rights you have.

1.2. The Policy is published under Part 2 of Article 18.1 of Russian Federal Law No. 152-FZ of 27 July 2006 "On Personal Data", and takes into account Articles 13 and 14 of Regulation (EU) 2016/679 (GDPR).

1.3. The Policy applies to all versions of the Program from 4.0.0-beta onwards and to the Website. It does not apply to third-party services the Program contacts at your choice (section 6) or to plugins by third-party authors.

1.4. By installing and using the Program you confirm that you have read this Policy. Separate consent is needed only for beta telemetry, and it is given in the Program itself (section 5).

## 2. Definitions

2.1. **Rights holder**: the author of the Program, who works under the name Luna-coreX. The rights holder also operates the Website and the telemetry collector. The installer names NeuroSync Foundry as the publisher; this is the name of the project under which the Program is distributed.

2.2. **User**: a person who has installed the Program or opened the Website.

2.3. **Device**: the User's computer on which the Program is installed.

2.4. **Telemetry report**: a set of anonymised counters the Program sends to the rights holder if the User has switched telemetry on (section 5).

2.5. **Installation number**: a random string of 32 hexadecimal characters that the Program creates when telemetry is switched on and deletes when it is switched off.

2.6. **Third-party service**: a service run by another organisation that the Program contacts at the User's choice: a search engine, an online voice, a language model, a model source, a weather source and others (section 6).

2.7. "Personal data", "processing", "operator" and "cross-border transfer" have the meanings given to them in Law No. 152-FZ.

## 3. Principles

3.1. **Local first.** Everything the Program knows about the User is stored on the Device. The rights holder has no access to it.

3.2. **Minimisation.** The rights holder receives only telemetry reports, and only if telemetry is on. A report contains nothing that identifies a person.

3.3. **The User's choice.** Whatever leaves the Device leaves because the User switched the corresponding feature on. Each such feature is off by default and labelled in settings.

3.4. **Transparency.** The Program shows what it stores and what it has sent on the page "What Rina knows about me", and its source code is open.

## 4. Information processed by the rights holder

4.1. The rights holder processes only the information listed below and collects nothing else about the User.

| Information | Source | Purpose | Basis | Retention |
|---|---|---|---|---|
| Telemetry report and installation number | The Program, if telemetry is on | To learn which beta features are used and where they fail | The User's consent, given by switching telemetry on | 180 days from receipt |
| Network (IP) address of a request to the collector | The Vercel platform, automatically | Platform operation; the rights holder does not record it | Technically necessary to deliver the request | About an hour, in the platform log |
| Network (IP) address of a Website visitor | The Vercel platform, automatically | Delivering the Website's pages | Technically necessary to deliver the pages | About an hour, in the platform log |
| Information in requests on GitHub | The User, if they wrote one | Answering the question or request | The User's own action | Under GitHub's rules; issues are public |

4.2. The rights holder does not process special categories of personal data or biometric personal data. Microphone audio is recognised on the Device and is not sent to the rights holder.

4.3. The rights holder makes no decisions with legal effects for the User based solely on automated processing.

## 5. Beta telemetry

5.1. **Switching it on.** Telemetry is off by default. The User switches it on in the first-run setup or in settings. Before it is switched on, the Program shows a window listing in full what is sent and what is not. Switching it on counts as consent.

5.2. **Contents of a report.** Exactly these fields and nothing else:

- the Program's and Windows' versions;
- the interface language;
- how many days counting has run;
- the chosen recognition and speech engines;
- whether model answers and always-on listening are on;
- whether Rina has a personality chosen by the User;
- counters: which intents and tools ran and how often, error codes and short reasons for refusal from the Program's vocabulary;
- timings of recognition and of the first sound;
- the installation number.

5.3. **Never sent.** What the User said or typed; sound; paths and file names; the names of the User's programs and plugins; addresses; passwords and keys.

5.4. **Frequency.** No more than once a day.

5.5. **The installation number** is not linked to the User's account, e-mail or name. It only connects one installation's reports from day to day while telemetry is on.

5.6. **Retention.** The collector records the day of receipt and the report itself, at most one report per installation per day. It records neither the network address nor the time of day. Records older than 180 days are deleted automatically every night.

5.7. **Platform log.** The collector runs on the Vercel platform, which keeps its own log of function calls; it cannot be switched off. That log contains the request's network address. On the plan in use (Hobby) the log is kept for about an hour.

5.8. **Viewing.** Every report that was sent is shown in full on the page "What Rina knows about me".

5.9. **Withdrawing consent.** The User switches telemetry off in settings. The Program immediately deletes what has been gathered on the Device and the installation number. Reports already received by the collector are deleted on request (section 9).

5.10. **End of telemetry.** In 4.0.0 Stable telemetry is removed from the Program, and the collector is shut down together with its database.

## 6. What leaves the Device at the User's choice

6.1. The Program makes the requests below only when the User has switched the corresponding feature on. The information goes to the third-party service, not to the rights holder, and that service's processing is governed by its own terms and policy.

| Feature | When | What is sent | To whom |
|---|---|---|---|
| Web search for an unrecognised phrase | If on | The phrase itself | The search engine in settings: DuckDuckGo (default), Brave Search, Startpage, Mojeek or Qwant |
| Edge online voice | If chosen | The text of the reply | Microsoft |
| gTTS online voice | If chosen | The text of the reply | Google |
| Language model on the Device (Ollama, LM Studio, llama.cpp) | By default | Nothing | — |
| Language model at another address | If the address in settings is not local | The question and the last few lines of conversation | The owner of that address |
| Ollama cloud model | If chosen | The question and the lines | ollama.com |
| OpenRouter | If chosen and a key is entered | The question and the lines, with the User's key | openrouter.ai |
| Downloading models | When the User starts it | The file request; the server sees the IP address | alphacephei.com (Vosk), huggingface.co (Whisper, Piper) |
| Update check | Once a day, if switched on; or on the "Check" button | The Program's version; the server sees the IP address | GitHub (api.github.com) |
| Weather (plugin) | If the plugin is on and the User asks | The city name and its coordinates | Open-Meteo (open-meteo.com) |
| Exchange rates (plugin) | If the plugin is on and the User asks | The rate request, with nothing about the User | The Central Bank of the Russian Federation (cbr.ru) |
| Music and video | If the User asks | A search page opens in the browser | YouTube |
| Third-party plugins | If the User installed them | The requests the plugin declares in its `sends` field | As stated in the plugin's description |
| Diagnostic package | Only if the User creates it and sends it themselves | What is visible in the package before sending | Whoever the User sends it to |

6.2. The rights holder does not review third-party plugins. By installing a plugin, the User accepts its author's terms.

## 7. Information on the Device

7.1. The Program's data folder on the Device (`%APPDATA%\RinaAssistant`) holds: settings; conversation history, only if the User keeps it; commands and the statistics of their runs; reminders, to-dos, sessions; learned words and corrections; the security journal and the call journal; backups the Program makes before updating its storage format; the list of programs the User allowed to run; the list of found programs; model files.

7.2. Language-model keys and plugin secrets are kept in the Windows Credential Manager, not in files.

7.3. The journals do not record what was said unless the User has switched on recording of texts. The security journal records every program launched, with its path and time.

7.4. This information is not sent to the rights holder or processed by them. The User can view it, export it to a file and delete it, item by item, by group or all at once, on the page "What Rina knows about me".

7.5. Uninstalling the Program keeps the data folder, so that reinstalling does not erase what has accumulated. It can be deleted with the "Forget everything" button before uninstalling, or by hand.

## 8. Transfers to third parties and cross-border transfers

8.1. The rights holder does not sell information, does not pass it to advertising networks and does not use it for targeting.

8.2. To run the Website and the collector, the rights holder uses the services of:

- **Vercel Inc.** (USA): hosting of the Website and the telemetry collector; the collector's functions run in the Frankfurt region (Germany);
- **Neon Inc.** (USA): the telemetry report database, hosted in Frankfurt (Germany);
- **GitHub, Inc.** (USA): source code, Program releases and requests.

8.3. Telemetry reports are stored on servers in Germany. Information these companies process as independent operators, such as platform logs, is governed by their own policies.

## 9. The User's rights and how to exercise them

9.1. The User has the right to:

- learn which data about them is processed, for what purpose and for how long;
- demand that data be corrected, blocked or deleted;
- withdraw consent to telemetry;
- object to processing;
- lodge a complaint with Roskomnadzor (for Users in the Russian Federation) or with the supervisory authority of their country (for Users in the EU).

9.2. The User views, exports and deletes the information on the Device themselves, in the Program, without contacting the rights holder.

9.3. To delete telemetry reports already received by the collector, the User sends their installation number through a [private GitHub advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new). The number is shown on the page "What Rina knows about me". Without it the reports cannot be found, because nothing links them to the User.

9.4. The rights holder answers a request within 10 working days. The period may be extended by another 5 working days, with a reasoned notice to the User.

## 10. The Website

10.1. The Website is static and hosted on Vercel. The platform sees visitors' network addresses in its call log (section 4).

10.2. The Website sets no cookies, does not write to localStorage and loads nothing from third-party servers: there are no external fonts, scripts, analytics, advertising networks or counters. This is enforced by a Content-Security-Policy header that forbids the browser to load anything from outside the Website.

10.3. Links to GitHub and other sites are governed by those sites' policies once followed.

## 11. Security

11.1. Language-model keys are kept in the Windows Credential Manager. They are sent only over `https` or to the Device itself, and requests carrying a key do not follow a redirect to another address.

11.2. Telemetry reports are sent only over `https`. The collector accepts a report only in a known shape and rejects anything extra outright.

11.3. For more on security measures, see [SECURITY.md](SECURITY.md) and the [threat model](https://www.rina-assistant.com/security/).

## 12. Children

12.1. The Program is not intended for children. The rights holder collects no information that identifies a person, whether a child or an adult.

## 13. Changes to the Policy

13.1. The Policy changes together with the Program. The version number and effective date are at the top of the document; the history of changes is in the Program's repository.

13.2. The rights holder announces significant changes, such as a new recipient of information, in [CHANGELOG.md](CHANGELOG.md) and in the Program itself before they take effect.

## 14. Contacts

14.1. Questions about the Policy: [GitHub Issues](https://github.com/Luna-coreX/RinaAssistant/issues). Issues are public: do not put information about yourself in them.

14.2. Requests about information and vulnerability reports: [private GitHub advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new).
