# Rina Assistant

<p align="center">
  <img src="assets/logo.png" alt="Rina Assistant Logo" width="180">
</p>

<h3 align="center">
A modular desktop assistant for automation, voice interaction and personal workflows.
</h3>

<p align="center">
  <b>Version: 2.0.0 Stable</b>
</p>

---

## ✨ About

**Rina Assistant** is a customizable desktop assistant designed to simplify everyday workflows through voice commands, automation and extensible plugin support.

The project focuses on creating a flexible assistant that can interact with your system, launch applications, manage workflows and provide voice-based interaction.

Rina Assistant is developed as part of the **NeuroSync Foundry** ecosystem.

---

# 🚀 Features

## 🎙️ Voice Interaction

Rina Assistant supports multiple Text-to-Speech and Speech-to-Text engines.

### Text-to-Speech (TTS)

Supported engines:

* **pyttsx3** — offline system voice synthesis
* **Edge Neural TTS** — high-quality neural voices
* **gTTS** — Google Text-to-Speech
* **Piper TTS** — local neural voice synthesis

### Speech-to-Text (STT)

Supported engines:

* **Google Speech Recognition**
* **Vosk**
* **Whisper**
* **PocketSphinx** *(currently unavailable)*

---

# ⚙️ Automation

Rina can help automate your workflow through customizable commands.

Supported actions:

* Launch applications
* Open folders
* Open websites
* Execute custom commands
* Control Rina Assistant settings
* Create command sequences

Example:

> "Launch workspace"

Possible sequence:

```
Open Discord
↓
Launch Visual Studio
↓
Open YouTube Lo-Fi stream
↓
Open project folder
```

---

# 🧩 Plugin System

Rina Assistant includes an extensible plugin architecture.

Plugins can add:

* New application features
* Additional pages
* Custom windows
* Settings panels
* New functionality

The plugin system allows extending Rina without modifying the core application.

---

# 🎨 Interface

Features:

* Modern desktop UI
* Custom themes
* Toast notifications
* Animated interface elements
* System tray integration
* Initial setup wizard
* Customizable settings

---

# ⌨️ Hotkeys

Rina supports keyboard shortcuts for interacting with the application.

Currently available:

* Program control actions
* Quick access to assistant functions

More hotkey functionality will be expanded in future versions.

---

# 📦 Project Structure

```
RinaAssistant/
│
├── animations/     # UI animations and effects
├── app/            # Application core and window management
├── assets/         # Images, icons and resources
├── components/     # Reusable UI components
├── core/           # Core logic and services
├── dialogs/        # Application dialogs
├── pages/          # Application pages
├── plugins/        # Plugin system and extensions
├── ui/             # UI configuration and helpers
│
└── main.py         # Application entry point
```

---

# 📸 Screenshots

> Screenshots will be added soon.

<!-- Add screenshots here -->

Example:

```
docs/
 ├── main_window.png
 ├── settings.png
 ├── plugins.png
 └── voice_control.png
```

---

# 🎬 Demo Video

> Demo video coming soon.

<!-- Example:

[![Rina Assistant Demo](https://img.youtube.com/vi/VIDEO_ID/0.jpg)](https://youtu.be/VIDEO_ID)

-->

---

# 🛠️ Installation

## Windows

An installer package will be available after the first repository release.

Currently, manual installation requires:

* Python 3.x
* Required dependencies

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python main.py
```

---

# 📋 Requirements

* Windows OS
* Python 3.x
* Installed dependencies from `requirements.txt`

Some voice engines may require additional models or external configuration.

---

# 🗺️ Roadmap

Future improvements:

* More voice engines
* Improved automation system
* Extended plugin API
* More integrations
* Additional customization options
* Further UI improvements

---

# 🤝 Contributing

Contributions, suggestions and bug reports are welcome.

If you found a problem or have an idea:

1. Open an Issue
2. Describe the problem or suggestion
3. Provide additional information if needed

---

# 📄 License

This project is licensed under the **MIT License**.

See the `LICENSE` file for more information.

---

# 🌐 Links

**NeuroSync Foundry**

Coming soon.

**Repository**

https://github.com/

---

<p align="center">
  Made with ❤️ and Python
</p>
