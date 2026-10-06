# -*- coding: utf-8 -*-
"""
4.0-H11: secrets — a plugin's token, a key to a model's service.

The shell's Credential Manager is substituted by a dictionary that answers
`secrets.*` the way the shell does; the real store is checked by the
shell's `--check-secrets`. Checked here:

- a secret is kept and read back by name, refused without a shell, and a
  bad name is refused before anything is asked;
- a plugin reaches its own secrets and nobody else's: the owner is set by
  the core from the plugin that asks;
- no value reaches the settings, the privacy page or the export — only the
  names, and the privacy page can forget them one by one, a plugin's with
  the plugin, and all of them;
- nothing about a value is written to the journal.

To run:
    python tools/test_secrets.py
"""
import json
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from console import use_utf8
from sandbox import neutralise

use_utf8()
neutralise()

from core import privacy
from core.plugin_host import HostedPlugins
from core.secrets import CORE, SecretStore, SecretsUnavailable, plugin_owner
from core.settings_api import MemorySettings

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


class Shell:
    """The shell's Credential Manager, as `secrets.*` answers it."""

    def __init__(self):
        self.kept = {}

    def __call__(self, method, payload):
        owner, name = payload.get("owner", ""), payload.get("name", "")
        if method == "secrets.get":
            value = self.kept.get((owner, name))
            return {"found": value is not None, "value": value or ""}
        if method == "secrets.set":
            self.kept[(owner, name)] = payload["value"]
            return {"ok": True, "reason": ""}
        if method == "secrets.delete":
            gone = [key for key in self.kept
                    if key[0] == owner and (not name or key[1] == name)]
            for key in gone:
                del self.kept[key]
            return {"deleted": len(gone)}
        return {"items": [{"owner": o, "name": n} for o, n in self.kept]}


SECRET = "ghp_ЭтоНеДолжноНигдеПоявиться"

# ---------------------------------------------------------------------------
print("=== хранилище ===")
shell = Shell()
store = SecretStore(ask=shell)
store.set(CORE, "openrouter", SECRET)
check("секрет сохранён и читается", store.get(CORE, "openrouter") == SECRET)
check("неизвестный — None", store.get(CORE, "nothing") is None)
for bad in ("", "a/b", "x" * 65, "с пробелом"):
    try:
        store.get(CORE, bad)
        check(f"имя {bad!r} отклонено", False)
    except ValueError:
        check(f"имя {bad!r} отклонено до вопроса оболочке", True)
try:
    store.get("чужой", "token")
    check("владелец не из словаря отклонён", False)
except ValueError:
    check("владелец не из словаря отклонён", True)
try:
    SecretStore().get(CORE, "openrouter")
    check("без оболочки — отказ, а не файл открытым текстом", False)
except SecretsUnavailable:
    check("без оболочки — отказ, а не файл открытым текстом", True)

# ---------------------------------------------------------------------------
print()
print("=== плагин видит только свои ===")
settings = MemorySettings({"plugin_settings": {}, "enabled_plugins": ["mail"]})
hosted = HostedPlugins(settings=settings)
hosted.secrets = store
kept = hosted._secret("mail", "plugin.secret.set", {"name": "token", "value": SECRET})
check("плагин сохранил свой", kept.get("ok") and
      shell.kept.get((plugin_owner("mail"), "token")) == SECRET, f"| {kept}")
mine = hosted._secret("mail", "plugin.secret.get", {"name": "token"})
check("и читает его", mine.get("found") and mine.get("value") == SECRET)
other = hosted._secret("weather", "plugin.secret.get", {"name": "token"})
check("а другой плагин под тем же именем не видит ничего",
      other.get("ok") and not other.get("found"), f"| {other}")
core_key = hosted._secret("weather", "plugin.secret.get", {"name": "openrouter"})
check("и секрет ядра плагину недоступен", not core_key.get("found"))
check("плохое имя — отказ словом, без падения",
      hosted._secret("mail", "plugin.secret.get", {"name": "../core"}).get("error")
      == "bad_name")
check("в настройках плагина — ничего", settings.get("plugin_settings") == {})
nowhere = HostedPlugins(settings=settings)
check("без хранилища — «недоступно»",
      nowhere._secret("mail", "plugin.secret.get", {"name": "token"}).get("error")
      == "unavailable")

# ---------------------------------------------------------------------------
print()
print("=== страница приватности: что есть, но не что именно ===")
groups = {g["id"]: g for g in privacy.inventory(settings, store)}
secrets = groups.get("secrets", {})
check("группа «Сохранённые входы» есть, обоих", secrets.get("count") == 2,
      f"| {secrets}")
check("значений в описи нет", SECRET not in json.dumps(groups, ensure_ascii=False))
check("без оболочки группы нет — «ничего не сохранено» было бы неправдой",
      "secrets" not in {g["id"] for g in privacy.inventory(settings, None)})
exported = json.dumps(privacy.export(settings, store), ensure_ascii=False)
check("в экспорте — имена, но не значения",
      "openrouter" in exported and SECRET not in exported)

gone = privacy.forget(settings, "secrets", [f"{CORE}/openrouter"], store)
check("забыть один вход", gone == 1 and store.get(CORE, "openrouter") is None)
store.set(CORE, "openrouter", SECRET)
privacy.forget(settings, "plugins", ["mail"], store)
check("забытый плагин забывает и свои входы, а чужие — нет",
      store.get(plugin_owner("mail"), "token") is None
      and store.get(CORE, "openrouter") == SECRET)
store.set(plugin_owner("mail"), "token", SECRET)
privacy.forget_everything(settings, store)
check("«забыть всё» — и все входы", shell.kept == {}, f"| {shell.kept}")

# ---------------------------------------------------------------------------
print()
print("=== ключ модели из настроек — в хранилище, не в файл (4.0b-E15) ===")
from core.settings_schema import DEFAULTS
from core.wire.server import ProtocolServer


class Message:
    def __init__(self, payload):
        self.payload = payload


class Session:
    @staticmethod
    def may_call(method):
        return True


box = ProtocolServer.__new__(ProtocolServer)
stored = MemorySettings(dict(DEFAULTS))
box._settings = lambda: stored
box.secrets = SecretStore(ask=Shell())
box.session = Session()
verdict = box._settings_set(Message({"values": {"llm_key": SECRET}}))["verdicts"]["llm_key"]
check("ключ принят", verdict["accepted"] and "диспетчер" in verdict["message"],
      f"| {verdict}")
check("в файле настроек его нет", stored.get("llm_key") == ""
      and SECRET not in json.dumps(stored.get("llm_key")))
check("а в хранилище — есть", box.secrets.get(CORE, "llm_key") == SECRET)
got = box._settings_get(Message({"keys": ["llm_key", "llm_provider"]}))["values"]
check("настройки отдают только «сохранён», а не ключ",
      got.get("llm_key") == "kept" and SECRET not in json.dumps(got), f"| {got}")
box._settings_set(Message({"values": {"llm_key": ""}}))
check("пустое — ключ забыт", box.secrets.get(CORE, "llm_key") is None)
check("и поле снова пустое",
      box._settings_get(Message({"keys": ["llm_key"]}))["values"]["llm_key"] == "")
box.session = None
refused = box._settings_set(Message({"values": {"llm_key": SECRET}}))["verdicts"]["llm_key"]
check("без оболочки ключ не принят и в файл не записан",
      not refused["accepted"] and stored.get("llm_key") == "", f"| {refused}")

# ---------------------------------------------------------------------------
print()
print("=== журнал не знает значений ===")
written = []


class Catch(logging.Handler):
    def emit(self, record):
        written.append(record.getMessage())


catch = Catch()
logging.getLogger().addHandler(catch)
logging.getLogger().setLevel(logging.DEBUG)
try:
    store.set(plugin_owner("mail"), "token", SECRET)
    hosted._secret("mail", "plugin.secret.get", {"name": "token"})
    store.delete(plugin_owner("mail"))
finally:
    logging.getLogger().removeHandler(catch)
check("сохранение, чтение и удаление записаны", len(written) >= 2, f"| {written}")
check("а значение — нигде", not any(SECRET in line for line in written))

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
