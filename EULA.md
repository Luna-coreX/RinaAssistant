# Rina Assistant Licence Agreement

Version 1.0 · effective 11 October 2026

Russian version: [EULA.ru.md](EULA.ru.md). Privacy policy: [PRIVACY.md](PRIVACY.md). This is a translation; if the versions differ, the Russian version prevails.

## In short

- The Program is free. You may install it on any number of computers and use it for any purpose, including at work, in any country and without a time limit.
- The source code is open under the Apache License 2.0. This Agreement does not narrow that licence: everything Apache 2.0 permits stays permitted.
- The name and logo are not licensed as marks: you may not use them to name your own program.
- The Program is provided "as is". The User is responsible for the commands they have set up and run.

## 1. General provisions

1.1. This Agreement is a licence agreement concluded in the simplified procedure under paragraph 5 of Article 1286 of the Civil Code of the Russian Federation. It is a contract of adhesion: the User accepts its terms as a whole, without changes.

1.2. The Agreement is concluded between the rights holder (section 2) and the User in respect of the computer program Rina Assistant.

1.3. Beginning to use the Program means the User agrees to the Agreement. Use begins with whichever of these happens first: running the Program's installer and continuing the installation, the first launch of the Program, or launching the Program built from source code. From that moment the contract is concluded and its written form is deemed observed.

1.4. The Agreement is free of charge: no fee is charged for the licence.

1.5. A User who does not agree with the Agreement does not install the Program, and uninstalls it if it is installed.

## 2. Definitions

2.1. **Program**: the computer program Rina Assistant, version 4.0.0-beta and later: the executable files, installer, libraries, resources, built-in plugins and documentation distributed by the rights holder.

2.2. **Rights holder**: the author of the Program, who works under the pseudonym Luna-coreX. The installer names NeuroSync Foundry as the publisher; this is the name of the project under which the Program is distributed.

2.3. **User**: an individual or legal entity using the Program.

2.4. **Source code**: the Program's source texts, published in the repository [github.com/Luna-coreX/RinaAssistant](https://github.com/Luna-coreX/RinaAssistant).

2.5. **Third-party components**: libraries, runtimes and other programs of other rights holders included in the Program (section 6).

2.6. **Plugin**: an add-on that extends the Program. A plugin is built-in if it ships with the Program, and third-party if someone else wrote it.

## 3. Subject of the Agreement

3.1. The rights holder grants the User a simple (non-exclusive) licence to use the Program in the following ways:

- reproduction: installing it on any number of devices, running it and storing it in a device's memory;
- use for its intended purpose in accordance with the documentation;
- making backup copies.

3.2. The Program may be used for any purpose, including commercial purposes and within organisations.

3.3. Rights not expressly granted to the User remain with the rights holder. This does not affect the rights the User has under the Apache License 2.0 (section 4).

## 4. Territory, term and relation to Apache 2.0

4.1. **Territory**: the whole world.

4.2. **Term**: the entire term of the exclusive right to the Program.

4.3. The source code and the Program are also distributed under the [Apache License, Version 2.0](LICENSE). The Apache License 2.0 is an open licence within the meaning of Article 1286.1 of the Civil Code of the Russian Federation. Modifying the Program, distributing it, including in modified form, and using its parts in other programs are governed by the Apache License 2.0.

4.4. The Agreement does not restrict or revoke rights granted by the Apache License 2.0. Where a term of the Agreement restricts such a right, the Apache License 2.0 applies.

4.5. Releases of the Program up to and including version 3.1.0 were distributed under the MIT licence. The Agreement does not affect the User's rights to copies of those releases obtained on its terms.

## 5. Name and logo

5.1. The licence gives no right to use the name "Rina Assistant", the name "Rina", the name NeuroSync Foundry or the Program's logo as marks of one's own product or service. Examples of prohibited use: naming one's own program that way, or distributing a modified version as if it were the original.

5.2. Stating the origin of a program or its parts, for example "based on Rina Assistant", is permitted. This follows section 6 of the Apache License 2.0.

## 6. Third-party components

6.1. Third-party components are distributed as part of the Program. Each is used on the terms of its own licence, and the Agreement does not apply to them.

| Component | Licence | Purpose |
|---|---|---|
| Python | Python Software Foundation License | Core runtime |
| edge-tts | GNU LGPL v3 | Edge online voice |
| PyAV and the FFmpeg libraries it includes | BSD-3-Clause; FFmpeg under GNU LGPL | Audio decoding |
| certifi | Mozilla Public License 2.0 | Root certificates for `https` |
| tqdm | Mozilla Public License 2.0 and MIT | Model download progress |
| .NET | MIT | Shell runtime |
| NAudio | MIT | Audio in the shell |
| H.NotifyIcon | MIT | Notification-area icon |
| Other libraries | MIT, BSD or Apache 2.0 | — |

6.2. The Agreement does not prohibit replacing components licensed under the GNU LGPL with modified versions, nor reverse engineering to the extent needed for such replacement.

6.3. Speech recognition and synthesis models (Vosk, Whisper, Piper) and language models are not part of the Program. The User downloads them, and they are used on the terms of their authors' licences.

## 7. Plugins and external services

7.1. Third-party plugins are distributed by their authors on their own terms. The rights holder does not review them and is not responsible for how they work.

7.2. Some features of the Program contact external services: search engines, online voices, language models, sources of models, weather and exchange rates. Each such feature is off by default. The User switches it on and thereby accepts the terms of the service concerned. The list of services and the information sent to them is in the [Privacy Policy](PRIVACY.md).

7.3. The availability of external services does not depend on the rights holder. If a service changes its terms or shuts down, the corresponding feature may stop working.

## 8. The User's responsibility

8.1. The Program carries out the User's commands on their computer: it launches programs, opens files and addresses, and performs actions the User has set up. The User is responsible for the consequences of commands they have created, allowed or run.

8.2. The User does not use the Program to break the law or infringe the rights of third parties.

## 9. Personal data

9.1. The Program stores information about the User on their computer. Only beta telemetry reports are sent to the rights holder, and only with the User's consent. How information is processed is set out in the [Privacy Policy](PRIVACY.md), which forms an integral part of the Agreement.

## 10. Updates

10.1. If the User has switched on update checks, the Program checks once a day whether a new version is out and reports it. Checks are off by default; a manual check is available on the "About" page. The Program installs a new version only when the User decides to.

10.2. Each version of the Program ships with the edition of the Agreement in force on the day of its release. That edition applies to the installed version.

## 11. Warranties and limitation of liability

11.1. The Program is distributed free of charge and provided "as is". The rights holder does not warrant that the Program is fit for a particular purpose, will work without errors or interruptions, or is compatible with any hardware or software.

11.2. The rights holder is not liable for losses arising in connection with the use of the Program or the inability to use it, including loss of data, unless the law provides otherwise.

11.3. The limitations in this section apply to the extent permitted by applicable law. They do not limit liability for intentional breach or any other liability the law does not allow to be limited in advance, and they do not deprive a User who is a consumer of the rights the law guarantees them.

## 12. Term and termination

12.1. The Agreement is in force from the moment stated in paragraph 1.3 for the term of the licence (paragraph 4.2).

12.2. The User may withdraw from the Agreement at any time by uninstalling the Program. Uninstalling keeps the Program's data on the computer; how to delete it is described in the Privacy Policy.

12.3. Use of the Program in breach of the Agreement is not covered by the licence under the Agreement. This does not affect the User's rights under the Apache License 2.0.

## 13. Governing law and disputes

13.1. The Agreement is governed by the law of the Russian Federation. A User who is a consumer living in another country keeps the rights guaranteed by the mandatory rules of that country's law.

13.2. Disputes are settled by negotiation. Failing agreement, a dispute is heard by a court under the jurisdiction rules established by the legislation of the Russian Federation.

## 14. Final provisions

14.1. If any term of the Agreement is held invalid, the remaining terms stay in force.

14.2. The Agreement is drawn up in Russian. The English version is a translation; if they differ, the Russian version prevails.

14.3. Questions about the Agreement: [GitHub Issues](https://github.com/Luna-coreX/RinaAssistant/issues). Requests that must not be public: through a [private GitHub advisory](https://github.com/Luna-coreX/RinaAssistant/security/advisories/new).
