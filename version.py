"""The application's version and links (with no dependency on Qt)."""

#: Four versions are independent (ADR 0004), and this one answers for
#: the core: which build of command parsing, memory and speech this is.
#: It stood at "3.1.0" for the whole port — naming a build this core
#: has long ceased to be: it has a protocol, streaming recognition,
#: synthesis by sentences and barge-in, and 3.1.0 had none of that.
#: "About" honestly showed "core 3.1.0" beside a 4.0.0 shell.
APP_VERSION = "4.0.0-beta"
BUILD = "2026.09"

LINKS = {
    "site": "https://neurosync-foundry-portal.pages.dev/",
    "source": "https://github.com/Luna-coreX/RinaAssistant",
    "docs": "",
    "issues": "https://github.com/Luna-coreX/RinaAssistant/issues",
}
