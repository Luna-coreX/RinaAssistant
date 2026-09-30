"""
"Why?" — an explanation of what Rina did, or would not do (`4.0b-B04`).

Every sentence here is built out of one record of the call journal
(`4.0-C06`) and the tool catalogue. Nothing is inferred and nothing is
remembered on the side: an explanation that came from somewhere other than
the record could disagree with the record, and then two accounts of the same
event would exist with nothing to say which is true.

**What the journal deliberately does not keep, the explanation does not
invent.** The arguments are redacted unless `log_texts` is on, so "why did
you open Chrome" is answered with the *reason* — a word you taught me, the
Start menu, a folder you pointed at — and not by reciting what was said. The
reason is the question anyway; the text was only ever the way of asking it.

**A refusal explains itself better than a success.** "I did not do it" is
the case a person actually comes asking about, and the journal keeps
refusals on a par with successes precisely so that this can be answered.
"""
import time

from core.i18n import t as tr


#: Tools that answer questions instead of doing anything. Asking "why" is
#: itself a call, and without this the answer to a second "why" would be
#: "because you asked why" — an explanation of the explaining.
QUIET = frozenset({
    "explain_last", "list_apps", "list_reminders", "list_todo",
})


def _where_from(reason):
    """Where a program's path came from — the sources of the index."""
    return {
        "learned": tr("это соответствие вы задали сами"),
        "start_menu": tr("нашла её в меню «Пуск»"),
        "desktop": tr("нашла ярлык на рабочем столе"),
        "folder": tr("нашла в папке, которую вы указали"),
        "uwp": tr("это приложение из магазина"),
        "path": tr("нашла её в системных путях"),
        "not_indexed": tr("такой программы у меня в списке нет"),
    }.get(reason, "")


def _asked_by(source):
    return {
        "voice": tr("вы попросили голосом"),
        "typed": tr("вы напечатали это"),
        "shell": tr("вы нажали кнопку"),
        "reminder": tr("сработало напоминание"),
        "plugin": tr("попросил плагин"),
        "hotkey": tr("вы нажали сочетание клавиш"),
    }.get(source, "")


def _refused(code):
    """Why it did not happen, by the code the gate returned."""
    return {
        "confirmation.required": tr(
            "это необратимое действие, а подтверждения не было"),
        "confirmation.expired": tr("подтверждение успело истечь"),
        "confirmation.invalid": tr("подтверждение не подошло к этому действию"),
        "permission.denied": tr("вы отказали в разрешении"),
        "permission.required": tr("на это не было разрешения"),
        "tool.unknown": tr("такого действия у меня нет"),
        "tool.invalid_arguments": tr("не хватило данных для действия"),
        "app.not_found": tr("не нашла такой программы"),
        "app.launch_failed": tr("не получилось её запустить"),
        "llm.unavailable": tr("языковая модель не отвечала"),
        "llm.remote_address": tr("адрес модели оказался не локальным"),
        "stt.unavailable": tr("распознавание было недоступно"),
        "tts.unavailable": tr("синтез речи был недоступен"),
        "internal": tr("внутри что-то сломалось"),
    }.get(code, "")


def explain(record, registry=None, now=None):
    """
    One journal record, said in words.

    Returns an empty string for no record: "I do not remember doing
    anything" is the caller's sentence to write, not this module's, because
    the caller knows whether nothing was found or nothing was asked.
    """
    if not record:
        return ""

    name = record.get("tool", "")
    tool = None
    if registry is not None:
        try:
            tool = registry.get(name)
        except Exception:
            tool = None

    # What was done, in the words the catalogue already uses. A second set
    # of names for the same tools would drift from the first.
    what = getattr(tool, "summary", "") or name
    what = what.rstrip(".")

    when = _ago(record.get("ts", 0), now)
    asked = _asked_by(record.get("source", ""))
    where = _where_from(record.get("reason", ""))

    # The summary is quoted as the **name** of the action rather than
    # bent into the sentence. The catalogue writes them as infinitives —
    # "Записать дело — то, что ждёт, а не срабатывает" — and a line like
    # that dropped into the middle of a spoken sentence comes out as
    # nonsense. In quotes it stays what it is: the name of the thing that
    # happened, said in the words the catalogue already uses.
    if record.get("ok"):
        parts = [tr("{when} — действие «{what}».", what=what, when=when)]
        if asked:
            parts.append(tr("Сделала, потому что {asked}.", asked=asked))
        if where:
            parts.append(tr("Путь взяла так: {where}.", where=where))
        if record.get("confirmation_id"):
            parts.append(tr("Действие необратимое, и вы его подтвердили."))
        return " ".join(parts)

    why = _refused(record.get("error_code", "")) or tr("не получилось")
    parts = [tr("{when} — действие «{what}» не выполнено.",
                what=what, when=when),
             tr("Причина: {why}.", why=why)]
    if asked:
        parts.append(tr("Просили так: {asked}.", asked=asked))
    if where:
        parts.append(tr("Про путь: {where}.", where=where))
    return " ".join(parts)


def _ago(stamp, now=None):
    """How long ago, roughly. Nobody asks "why" about last month."""
    try:
        seconds = max(0.0, (now if now is not None else time.time())
                      - float(stamp or 0))
    except (TypeError, ValueError):
        return tr("когда-то")
    if seconds < 90:
        return tr("только что")
    minutes = int(seconds // 60)
    if minutes < 60:
        return tr("{n} мин. назад", n=minutes)
    hours = int(minutes // 60)
    if hours < 24:
        return tr("{n} ч. назад", n=hours)
    return tr("{n} дн. назад", n=int(hours // 24))


def last_doing(journal, limit=40):
    """
    The most recent record that is worth explaining.

    Questions are skipped. Asking "why" is itself a call and lands in the
    journal, so without this the second "why" in a row would be answered
    with "because you asked why" — and the person would have been told
    about the asking rather than about the doing.
    """
    if journal is None:
        return None
    for record in journal.recent(limit=limit):
        if record.get("tool") in QUIET:
            continue
        return record
    return None
