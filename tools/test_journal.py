# -*- coding: utf-8 -*-
"""
The journals keep what happened, not what was said.

`core/logging_setup.py` promises it in words: "the journal can be
attached to a bug report without disclosing the correspondence", with
one exception — DEBUG plus `log_texts` switched on deliberately. Until
this file nothing held it to that, and it was not being kept: the tool
runner wrote the validated arguments of every call verbatim, at DEBUG
into the general journal and **unconditionally** into the security one,
which is not level-gated at all. `core/audit.py` had derived the right
rule for the database beside it, and nobody applied it here.

So the promise is measured rather than restated: a tool is called with a
phrase nobody could write by accident, and the phrase is looked for in
every file the journalling produced.

To run:
    python tools/test_journal.py
"""
import io
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

# **Before the core is imported.** The folder for the application's data
# is read on the way in, and a check that wrote its journals into a
# person's real profile would be both wrong and rude.
_HOME = tempfile.mkdtemp(prefix="rina-journal-")
os.environ["APPDATA"] = _HOME
os.environ["XDG_CONFIG_HOME"] = _HOME

from console import use_utf8                            # noqa: E402
from core import logging_setup                          # noqa: E402
from core.settings_api import MemorySettings            # noqa: E402
from core.tools import Param, Tool                      # noqa: E402
from core.toolrunner import ToolContext, ToolRunner     # noqa: E402

use_utf8()

fails = 0


def check(label, ok, detail=""):
    global fails
    if not ok:
        fails += 1
    print(("OK   " if ok else "FAIL "), label, detail)


#: A phrase that cannot turn up by accident and is obviously somebody's
#: own business if it does.
SECRET = "пароль-от-сейфа-жирафа-78123"


def journals():
    """Everything both journals have written, by file."""
    folder = logging_setup.logs_dir()
    out = []
    for name in sorted(os.listdir(folder)):
        with io.open(os.path.join(folder, name), encoding="utf-8",
                     errors="replace") as source:
            out.append((name, source.read()))
    return out


def call_with_secret(texts_allowed):
    """
    Drive a real tool call with a secret in its arguments.

    Through the real runner and the real journalling: a check that built
    a logger of its own would be checking its own logger.
    """
    settings = MemorySettings({"log_level": "DEBUG",
                               "log_texts": bool(texts_allowed)})
    # `logging_setup` asks the settings module, not whoever calls it.
    import core.settings_store as settings_store
    settings_store.settings = settings

    logging_setup.setup(force=True)
    logging_setup.apply_settings()

    runner = ToolRunner(ToolContext(settings=settings,
                                    emit=lambda name, **data: None))
    ran = {"n": 0}

    def run_it(context, args):
        ran["n"] += 1
        from core.toolrunner import ToolResult
        return ToolResult.done("готово")

    # A tool of the shape that matters: one free-text argument, so the
    # rule «no list of values — no verbatim» has something to bite on.
    runner.add_tool(
        Tool(name="проба_журнала",
             summary="Проверочный инструмент",
             params=(Param("query", "string", "Свободный текст",
                           required=True),)),
        run_it)
    runner.call("проба_журнала", {"query": SECRET}, source="typed")

    for name in (logging_setup.LOGGER_NAME,
                 logging_setup.SECURITY_LOGGER_NAME):
        for handler in logging.getLogger(name).handlers:
            handler.flush()
    return ran["n"]


#: The question asked of the model, in the same unmistakable shape.
QUESTION = "вопрос-про-жирафа-в-сейфе-99417"


def model_failed():
    """A model that refuses, driven through the real tool and journal."""
    settings = MemorySettings({"log_level": "DEBUG", "log_texts": False})
    import core.settings_store as settings_store
    settings_store.settings = settings

    logging_setup.setup(force=True)
    logging_setup.apply_settings()

    from core import llm, toolrunner

    was = llm.ask

    def refuse(question, history=None):
        raise llm.LLMError("Ollama не отвечает: соединение отклонено")

    llm.ask = refuse
    try:
        result = toolrunner._ask_model(
            ToolContext(settings=settings, emit=lambda name, **data: None),
            {"question": QUESTION})
    finally:
        llm.ask = was

    for name in (logging_setup.LOGGER_NAME,
                 logging_setup.SECURITY_LOGGER_NAME):
        for handler in logging.getLogger(name).handlers:
            handler.flush()
    return result


def main():
    print("=== журналы: что в них попадает ===")
    print(f"      (пишем в {_HOME})")

    ran = call_with_secret(texts_allowed=False)
    check("инструмент действительно вызвался", ran == 1, f"| {ran}")

    written = journals()
    check("журналы вообще появились", len(written) > 0,
          f"| {[name for name, _ in written]}")

    leaking = [name for name, text in written if SECRET in text]
    check("при выключенном log_texts текста реплики в журналах нет",
          not leaking, f"| нашлось в: {leaking}")

    # And the shape of the thing is still there: a check that passed by
    # writing nothing at all would be worth nothing.
    named = [name for name, text in written if "проба_журнала" in text]
    check("но сам вызов записан", named, f"| {named}")
    lengths = [name for name, text in written if "симв." in text]
    check("и вместо текста — его длина", lengths, f"| {lengths}")

    # The exception has to work too: somebody who switched the setting on
    # did it in order to see the texts.
    call_with_secret(texts_allowed=True)
    verbatim = [name for name, text in journals() if SECRET in text]
    check("а с включённым log_texts текст записан", verbatim,
          f"| {verbatim}")

    print()
    print("=== почему модель не ответила — записано ===")
    # **Silence is the thing being fixed.** The caller turns a refusal
    # into "the model did not answer" and drops the text, so the journal
    # held twenty-one seconds of nothing between «Какая погода в
    # Хабаровске?» and «Извини, я не поняла команду», and why it failed
    # had to be reproduced instead of read.
    #
    # The reason is about the server; the question is the person's. Both
    # halves are measured, because a fix that started writing the
    # question would trade one fault for a worse one.
    result = model_failed()
    check("инструмент сообщил о неудаче",
          not result.ok and result.error_code == "llm.unavailable",
          f"| {result.error_code}")
    told = [name for name, text in journals() if "соединение отклонено" in text]
    check("причина в журнале есть", told, f"| {told}")
    leaked = [name for name, text in journals() if QUESTION in text]
    check("а вопроса в нём нет", not leaked, f"| {leaked}")

    print()
    print("ИТОГО ошибок:", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
