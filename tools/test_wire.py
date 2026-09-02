"""
D03, D04: рукопожатие и конверт сообщения.

Проверяется без транспорта и без приложения. Так и задумано: ADR 0002
требует, чтобы спецификация не зависела от канала, и conformance-тесты
(`4.0-D16`) могли гонять её через транспорт внутри процесса. Если бы этому
файлу понадобился именованный канал, требование было бы нарушено.
"""
import os
import sys

ROOT = r"C:\DevStation\PCDev\DesktopApps\RinaAssistant"
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import re

from core.wire import (CATALOGUE, CONTROL_FRAME_LIMIT, CORE_CAPABILITIES,
                       EVENTS, Envelope, FrameDecoder, IdGenerator,
                       MessageType, NO_TRACE, ProtocolFault, Router,
                       SHELL_CAPABILITIES, STREAM_DONE, STREAM_FAILED, Session,
                       SessionState, Side, StreamReceiver, StreamSender,
                       TraceFilter, current_trace, decode, encode,
                       encode_frame, event, make, negotiate, new_trace_id,
                       trace_scope, validate_event)
from core.wire.errors import (CATEGORIES, ERROR_FRAME_TOO_LARGE,
                              ERROR_INCOMPATIBLE, ERROR_INVALID_ENVELOPE,
                              ERROR_INVALID_PAYLOAD, ERROR_INVALID_STATE,
                              ERROR_NOT_READY, ERROR_UNKNOWN_METHOD,
                              ProtocolError)
from core.wire.tasks import FINAL, Registry, STATUS_UNKNOWN, TaskState, run

fails = 0


def check(label, cond, detail=""):
    global fails
    if not cond:
        fails += 1
    print(("OK   " if cond else "FAIL "), label, detail)


def fault(fn, code):
    """Вызов обязан упасть протокольной ошибкой ровно с этим кодом."""
    try:
        fn()
    except ProtocolFault as exc:
        if exc.error.code == code:
            return exc.error
        print(f"       (ожидался {code}, получен {exc.error.code})")
        return None
    return None


print("=== чистота ===")
check("Qt не загружен", "PySide6" not in sys.modules)


# ---------------------------------------------------------------------------
print()
print("=== D04: конверт ===")

trace = new_trace_id()
ids = IdGenerator("s-")
req = Envelope.request("command.handle",
                       {"text": "запусти телеграм", "source": "typed"},
                       id=ids.next(), trace_id=trace)

check("тип запроса", req.type == MessageType.REQUEST)
check("версия по умолчанию 1", req.v == 1)
check("идентификатор с префиксом стороны", req.id == "s-0001", f"| {req.id}")

back = decode(encode(req))
check("круговой оборот сохраняет метод", back.method == "command.handle")
check("круговой оборот сохраняет полезную нагрузку",
      back.payload == req.payload)
check("круговой оборот сохраняет trace_id", back.trace_id == trace)

check("необязательные поля не пишутся пустыми",
      "correlation_id" not in req.to_dict() and "stream_id" not in req.to_dict())

# обязательные поля по типу сообщения
check("запрос без метода отклонён",
      fault(lambda: Envelope(type="request", id="s-1", timestamp=1.0,
                             trace_id="t-1"), ERROR_INVALID_ENVELOPE)
      is not None)
check("ответ без correlation_id отклонён",
      fault(lambda: Envelope(type="response", id="s-1", timestamp=1.0,
                             trace_id="t-1"), ERROR_INVALID_ENVELOPE)
      is not None)
check("событие без метода отклонено",
      fault(lambda: Envelope(type="event", id="s-1", timestamp=1.0,
                             trace_id="t-1"), ERROR_INVALID_ENVELOPE)
      is not None)
check("неизвестный тип сообщения отклонён",
      fault(lambda: Envelope(type="жалоба", id="s-1", timestamp=1.0,
                             trace_id="t-1"), ERROR_INVALID_ENVELOPE)
      is not None)
check("пустой trace_id отклонён",
      fault(lambda: Envelope(type="event", id="s-1", method="ping",
                             timestamp=1.0, trace_id=""),
            ERROR_INVALID_ENVELOPE) is not None)
check("истина вместо номера версии отклонена",
      fault(lambda: Envelope(type="event", id="s-1", method="ping",
                             timestamp=1.0, trace_id="t-1", v=True),
            ERROR_INVALID_ENVELOPE) is not None)
check("payload не объект — отклонено",
      fault(lambda: Envelope(type="event", id="s-1", method="ping",
                             timestamp=1.0, trace_id="t-1", payload=[1, 2]),
            ERROR_INVALID_ENVELOPE) is not None)

# совместимость вперёд: незнакомое поле не мешает
raw = encode(req).replace(b'{"v":1', b'{"v":1,"weather":"rain"', 1)
survived = decode(raw)
check("незнакомое поле конверта пропускается молча",
      survived.method == "command.handle")

err = fault(lambda: decode(b"{not json"), ERROR_INVALID_ENVELOPE)
check("неразбираемый JSON отклонён", err is not None)
err = fault(lambda: decode(b'{"type":"event"}'), ERROR_INVALID_ENVELOPE)
check("отсутствие обязательных полей названо поимённо",
      err is not None and set(err.details.get("fields", [])) >=
      {"v", "id", "timestamp", "trace_id", "payload"},
      f"| {err.details if err else ''}")

# наследование трассировки
resp = req.reply({"accepted": True}, id="c-0001")
check("ответ ссылается на запрос", resp.correlation_id == req.id)
check("ответ наследует trace_id", resp.trace_id == trace)
check("ответ наследует версию", resp.v == req.v)

failure = req.fail(ProtocolError("app.not_found", "user", False,
                                 "Не нашла программу «фотошоп».",
                                 {"query": "фотошоп"}), id="c-0002")
check("ошибка несёт код и текст раздельно",
      failure.payload["code"] == "app.not_found"
      and failure.payload["message"].startswith("Не нашла"))
check("ошибка наследует trace_id", failure.trace_id == trace)


# ---------------------------------------------------------------------------
print()
print("=== D04: кадрирование ===")

frame = encode_frame(req)
check("кадр начинается с длины",
      int.from_bytes(frame[:4], "big") == len(frame) - 4)

dec = FrameDecoder()
check("половина кадра не даёт сообщения",
      list(dec.feed(frame[:7])) == [] and dec.pending == 7)
got = list(dec.feed(frame[7:]))
check("кадр, пришедший по кускам, собран",
      len(got) == 1 and got[0].method == "command.handle")
check("остатка не осталось", dec.pending == 0)

two = encode_frame(req) + encode_frame(resp)
got = list(FrameDecoder().feed(two))
check("два кадра в одном куске разобраны",
      [m.type for m in got] == ["request", "response"])

# Предел проверяется по заявленной длине, до выделения памяти: декодеру
# скармливается только заголовок, тела нет и не будет.
header_only = (CONTROL_FRAME_LIMIT + 1).to_bytes(4, "big")
err = fault(lambda: list(FrameDecoder().feed(header_only)),
            ERROR_FRAME_TOO_LARGE)
check("огромный кадр отвергнут по заголовку, до тела",
      err is not None and err.details.get("size") == CONTROL_FRAME_LIMIT + 1)

big = Envelope.event("assistant.response", {"text": "я" * CONTROL_FRAME_LIMIT},
                     id="c-9", trace_id="t-9")
check("собственное сообщение сверх предела не отправляется",
      fault(lambda: encode_frame(big), ERROR_FRAME_TOO_LARGE) is not None)

check("идентификаторы идут подряд",
      [ids.next(), ids.next()] == ["s-0002", "s-0003"])
check("trace_id уникальны", new_trace_id() != new_trace_id())


# ---------------------------------------------------------------------------
print()
print("=== D03: согласование версий ===")

check("наибольшая общая", negotiate([1, 2], [2, 3]) == 2)
check("оболочка [1,2] с ядром [1] работает по 1 (§15.3a)",
      negotiate([1, 2], [1]) == 1)
check("одинаковые наборы", negotiate([1], [1]) == 1)

err = fault(lambda: negotiate([2], [1]), ERROR_INCOMPATIBLE)
check("несовместимость названа внятно, с обеими сторонами",
      err is not None and "2" in err.message and "1" in err.message,
      f"| {err.message if err else ''}")
check("несовместимость не предлагает повторить",
      err is not None and err.retryable is False)
check("пустой набор версий отклонён",
      fault(lambda: negotiate([], [1]), ERROR_INCOMPATIBLE) is not None)


# ---------------------------------------------------------------------------
print()
print("=== D03: рукопожатие целиком ===")

shell = Session(side=Side.SHELL, versions=[1, 2], app_version="4.0.0")
core = Session(side=Side.CORE, versions=[1], app_version="4.0.0")

check("до рукопожатия обе стороны не готовы",
      shell.state == SessionState.NOT_READY
      and core.state == SessionState.NOT_READY)
check("до рукопожатия метод звать нельзя",
      fault(lambda: shell.check_outgoing("command.handle"), ERROR_NOT_READY)
      is not None)
check("до рукопожатия принимается только hello",
      fault(lambda: core.check_incoming("command.handle"), ERROR_NOT_READY)
      is not None)
core.check_incoming("hello")
check("hello до рукопожатия принимается", True)

# сообщения ходят кадрами через два декодера — заготовка транспорта D16
shell_ids, core_ids = IdGenerator("s-"), IdGenerator("c-")
t = new_trace_id()
hello = Envelope.request("hello", shell.hello_payload(),
                         id=shell_ids.next(), trace_id=t)
to_core = FrameDecoder()
received = list(to_core.feed(encode_frame(hello)))[0]
core.check_incoming(received.method)
answer = received.reply(core.handle_hello(received.payload),
                        id=core_ids.next())
to_shell = FrameDecoder()
back = list(to_shell.feed(encode_frame(answer)))[0]
chosen = shell.accept_hello_result(back.payload)

check("выбрана наибольшая общая версия", chosen == 1)
check("обе стороны готовы", shell.ready and core.ready)
check("ядро назвало идентификатор сессии", len(core.session_id) == 32)
check("оболочка запомнила тот же идентификатор",
      shell.session_id == core.session_id)
check("ядро узнало возможности оболочки",
      set(core.peer_capabilities) == set(SHELL_CAPABILITIES))
check("оболочка узнала возможности ядра",
      set(shell.peer_capabilities) == set(CORE_CAPABILITIES))
check("trace_id прошёл всю цепочку", back.trace_id == t)

err = fault(lambda: shell.accept_hello_result({"protocol_version": 7}),
            ERROR_INCOMPATIBLE)
check("выбранная версия, которой мы не объявляли, отклонена", err is not None)


# ---------------------------------------------------------------------------
print()
print("=== D03: возможности отпирают методы ===")

shell = Session(side=Side.SHELL)
core = Session(side=Side.CORE)
core.handle_hello(shell.hello_payload())
shell.accept_hello_result({"protocol_version": 1,
                           "capabilities": list(core.capabilities),
                           "core_version": "4.0.0",
                           "session_id": core.session_id})

check("базовый метод доступен всегда", shell.may_call("command.handle"))
check("speech.say доступен: ядро объявило tts", shell.may_call("speech.say"))
check("apps.launch доступен ядру: оболочка объявила apps",
      core.may_call("apps.launch"))
check("permission.request доступен ядру", core.may_call("permission.request"))

check("метод актуации звать нельзя", not core.may_call("window.focus"))
check("метод актуации отвечает «неизвестный», а не «нет права»",
      fault(lambda: core.check_incoming("actuation.input.click"),
            ERROR_UNKNOWN_METHOD) is not None)
check("выдуманный метод отклонён",
      fault(lambda: shell.check_outgoing("cook.dinner"),
            ERROR_UNKNOWN_METHOD) is not None)

# ядро без распознавания: оболочка обязана не звать
deaf = Session(side=Side.CORE, capabilities=("tts", "reminders"))
shell2 = Session(side=Side.SHELL)
deaf.handle_hello(shell2.hello_payload())
shell2.accept_hello_result({"protocol_version": 1,
                            "capabilities": list(deaf.capabilities),
                            "core_version": "4.0.0", "session_id": "x"})
check("необъявленная возможность закрывает метод",
      not shell2.may_call("speech.listen_once"))
err = fault(lambda: shell2.check_outgoing("speech.listen_once"),
            ERROR_UNKNOWN_METHOD)
check("отказ называет возможность, а не только метод",
      err is not None and err.details.get("capability") == "stt")
check("ядро без stt само не принимает speech.listen_once",
      fault(lambda: deaf.check_incoming("speech.listen_once"),
            ERROR_UNKNOWN_METHOD) is not None)
check("но tts у него работает", shell2.may_call("speech.say"))

try:
    Session(side=Side.CORE, capabilities=("apps",))
    check("возможность чужой стороны отклонена", False)
except ValueError:
    check("возможность чужой стороны отклонена", True)
try:
    Session(side=Side.CORE, capabilities=("телепатия",))
    check("неизвестная возможность отклонена", False)
except ValueError:
    check("неизвестная возможность отклонена", True)

check("закрытая сессия перестаёт пускать",
      (core.close() or True) and not core.may_call("command.handle"))


# ---------------------------------------------------------------------------
print()
print("=== D05: каталог ошибок ===")

check("категории только объявленные",
      all(spec.category in CATEGORIES for spec in CATALOGUE.values()))
check("код в записи совпадает с ключом",
      all(code == spec.code for code, spec in CATALOGUE.items()))

e = make("app.not_found", "Не нашла программу «фотошоп».", query="фотошоп")
check("категория берётся из каталога, а не от вызывающего",
      e.category == "user" and e.retryable is False)
check("подробности сохранены", e.details == {"query": "фотошоп"})
check("полезная нагрузка ошибки — по §5",
      set(e.to_payload()) == {"code", "category", "retryable", "message",
                              "details"})

try:
    make("выдуманный.код", "…")
    check("незнакомый код отклонён", False)
except ValueError:
    check("незнакомый код отклонён", True)

check("not_ready повторяем, incompatible нет",
      CATALOGUE["protocol.not_ready"].retryable is True
      and CATALOGUE["protocol.incompatible"].retryable is False)
check("просроченное подтверждение не повторяемо тем же вызовом",
      CATALOGUE["confirmation.expired"].retryable is False)

# Сверка с тем, что ядро действительно умеет отправлять. Список, который
# пишут руками и не сверяют, расходится с кодом на первом же инструменте.
from core.toolbox import ALL_TOOLS
from core.tools import (ERROR_INVALID_ARGUMENTS, ERROR_PERMISSION_DENIED,
                        ERROR_UNKNOWN_TOOL)

declared = {code for tool in ALL_TOOLS for code in tool.errors}
declared |= {ERROR_UNKNOWN_TOOL, ERROR_INVALID_ARGUMENTS,
             ERROR_PERMISSION_DENIED}
missing = sorted(declared - set(CATALOGUE))
check("каждый код инструментов есть в каталоге", not missing,
      f"| нет: {missing}")
print(f"     кодов у инструментов: {len(declared)}, "
      f"в каталоге: {len(CATALOGUE)}")

# Сверка с документом: код и спецификация не должны разъезжаться.
spec_text = open("docs/protocol/PROTOCOL-v1.md", encoding="utf-8").read()
section = spec_text[spec_text.index("Начальный каталог:"):]
# Резать по "---" нельзя: разделитель шапки таблицы «|---|---|---|» тоже
# содержит эти символы, и срез пришёлся бы до первой строки данных.
section = section[:section.index(chr(10) + "---" + chr(10))]
spec_codes = set(re.findall(r"^\| `([a-z_.]+)` \|", section, re.M))
check("каталог документа непуст", len(spec_codes) >= 15, f"| {len(spec_codes)}")
check("код документа = код программы",
      spec_codes == set(CATALOGUE),
      f"| только в документе: {sorted(spec_codes - set(CATALOGUE))}, "
      f"только в программе: {sorted(set(CATALOGUE) - spec_codes)}")


# ---------------------------------------------------------------------------
print()
print("=== D15: сквозная трассировка ===")

check("вне действия трассировки нет", current_trace() is None)
with trace_scope("t-outer") as outer:
    check("область задаёт трассировку", current_trace() == "t-outer")
    check("область возвращает её же", outer == "t-outer")
    with trace_scope("t-inner"):
        check("вложенная область перекрывает", current_trace() == "t-inner")
    check("выход возвращает прежнюю", current_trace() == "t-outer")
check("после выхода трассировки снова нет", current_trace() is None)

with trace_scope() as born:
    check("вход без аргумента начинает цепочку",
          born.startswith("t-") and current_trace() == born)

# Событие рождается глубоко и трассировку не получает параметром.
def deep_event():
    """Как если бы его поднял реестр инструментов изнутри исполнения."""
    return Envelope.event("assistant.response", {"text": "готово"}, id="c-77")

with trace_scope("t-deep"):
    ev = deep_event()
check("событие подхватило трассировку из контекста", ev.trace_id == "t-deep")
check("вне контекста событие всё равно с трассировкой",
      deep_event().trace_id.startswith("t-"))

# Требование §15.12: trace_id во всей цепочке от запроса до финального события.
with trace_scope() as chain:
    ask = Envelope.request("command.handle", {"text": "выключи компьютер"},
                           id="s-100")
    ok = ask.reply({"accepted": True}, id="c-100")
    note = Envelope.event("assistant.thinking", {"active": True}, id="c-101")
    bad = ask.fail(make("permission.denied", "Не разрешено."), id="c-102")
same = {ask.trace_id, ok.trace_id, note.trace_id, bad.trace_id}
check("вся цепочка несёт одну трассировку (§15.12)", same == {chain},
      f"| {sorted(same)}")

# Через канал: трассировка переживает сериализацию и продолжается на той
# стороне — именно так её и подхватывает получатель.
wire = list(FrameDecoder().feed(encode_frame(ask)))[0]
with trace_scope(wire.trace_id):
    answer = Envelope.event("history.changed", {}, id="c-200")
check("получатель продолжает чужую цепочку", answer.trace_id == chain)


class _Record:
    pass


rec = _Record()
TraceFilter().filter(rec)
check("вне действия в журнал идёт прочерк", rec.trace == NO_TRACE)
with trace_scope("t-log"):
    rec2 = _Record()
    TraceFilter().filter(rec2)
check("внутри действия в журнал идёт идентификатор", rec2.trace == "t-log")
kept = _Record()
kept.trace = "t-своя"
TraceFilter().filter(kept)
check("готовое поле не затирается", kept.trace == "t-своя")


# ---------------------------------------------------------------------------
print()
print("=== D11: каталог событий ===")

# Сверка с перечнем 3.1.0: спецификация писалась по нему, и потерянное при
# переносе событие — это поведение, о котором ядро сообщать перестанет.
from core.protocol import ALL_EVENTS as EVENTS_310

lost = sorted(set(EVENTS_310) - set(EVENTS))
check("ни одно событие 3.1.0 не потеряно", not lost, f"| потеряно: {lost}")
print(f"     событий 3.1.0: {len(EVENTS_310)}, в каталоге провода: {len(EVENTS)}")

# Сверка с документом: таблица §6. Потоковые события живут в §7 и в этой
# таблице отсутствуют законно.
section = spec_text[spec_text.index("### Ядро → оболочка (события)"):]
section = section[:section.index("### Ядро → оболочка (запросы)")]
spec_events = set()
for line in section.split("\n"):
    if line.startswith("|") and not line.startswith("|---"):
        cell = line.split("|")[1]
        spec_events |= set(re.findall(r"`([a-z]+\.[a-z_]+)`", cell))
check("таблица событий документа прочитана", len(spec_events) >= 10,
      f"| {len(spec_events)}")
# Таблица §6 описывает ровно перенос 3.1.0: ничего не потеряно и ничего не
# придумано. Потоковые события живут в §7, события задач — в §9, и сверять
# их с этой таблицей значило бы требовать от неё того, чем она не является.
check("таблица §6 = события 3.1.0", spec_events == set(EVENTS_310),
      f"| только в документе: {sorted(spec_events - set(EVENTS_310))}, "
      f"только в 3.1.0: {sorted(set(EVENTS_310) - spec_events)}")
# Зато каждое событие каталога обязано быть описано хоть где-то: событие,
# которого контракт не упоминает, — договорённость, о которой знает одна
# сторона. Список исключений не ведётся намеренно, иначе он и станет тем
# местом, где события прячут.
undocumented = sorted(n for n in EVENTS if n not in spec_text)
check("каждое событие каталога описано в спецификации", not undocumented,
      f"| нет в документе: {undocumented}")


# ---------------------------------------------------------------------------
print()
print("=== D11: нагрузка проверяется у отправителя ===")

validate_event("history.changed", {})
check("событие без полей проходит пустым", True)
check("не хватает поля",
      fault(lambda: validate_event("speech.recognized", {}),
            ERROR_INVALID_PAYLOAD) is not None)
err = fault(lambda: validate_event("speech.recognized",
                                   {"text": "да", "мысли": "…"}),
            ERROR_INVALID_PAYLOAD)
check("лишнее поле названо поимённо",
      err is not None and err.details.get("fields") == ["мысли"])
check("не тот тип",
      fault(lambda: validate_event("assistant.thinking", {"active": "да"}),
            ERROR_INVALID_PAYLOAD) is not None)
err = fault(lambda: validate_event("window.action", {"action": "станцуй"}),
            ERROR_INVALID_PAYLOAD)
check("значение вне перечисления отклонено",
      err is not None and err.details.get("got") == "станцуй")
validate_event("window.action", {"action": "screenshot"})
check("значение из перечисления проходит", True)
check("незнакомое событие отправить нельзя",
      fault(lambda: validate_event("рина.загрустила", {}),
            ERROR_INVALID_PAYLOAD) is not None)

with trace_scope("t-ev"):
    ev = event("assistant.response", {"text": "готово"}, id="c-500")
check("событие собрано с трассировкой из контекста",
      ev.trace_id == "t-ev" and ev.method == "assistant.response")


# ---------------------------------------------------------------------------
print()
print("=== D11: приём и молчаливое игнорирование ===")

seen = []
broken = []
router = Router(on_broken=lambda name, exc: broken.append(name))
router.on("assistant.response", lambda p: seen.append(p["text"]))

check("знакомое событие доставлено", router.dispatch(ev) is True)
check("нагрузка дошла целиком", seen == ["готово"])

# Незнакомое событие приходит от более новой стороны — и это не ошибка,
# иначе правило «добавить событие можно, не меняя версию» было бы ложью.
future = Envelope.event("рина.загрустила", {"уровень": 3}, id="c-501",
                        trace_id="t-1")
check("незнакомое событие проигнорировано молча",
      router.dispatch(future) is False
      and router.ignored == ["рина.загрустила"])

# Знакомое, но испорченное, роняет только себя.
bad_ev = Envelope.event("speech.recognized", {"text": 42}, id="c-502",
                        trace_id="t-1")
check("испорченное событие не доставлено", router.dispatch(bad_ev) is False)
check("о нём сообщено наблюдателю", broken == ["speech.recognized"])
check("подписчик не пострадал", seen == ["готово"])

try:
    Router().on("нет.такого", lambda p: None)
    check("подписка на необъявленное событие отклонена", False)
except ValueError:
    check("подписка на необъявленное событие отклонена", True)


# ---------------------------------------------------------------------------
print()
print("=== D06: потоковый текст ===")

sender = StreamSender(IdGenerator("c-"))
sid = sender.begin()
check("номер потока занят", sid == 1 and sid in sender.open)

with trace_scope("t-stream"):
    parts = [sender.chunk(sid, t) for t in
             ("Столица ", "Австралии — ", "Канберра.")]
    closing = sender.end(sid, STREAM_DONE)

check("части несут номер потока",
      all(p.stream_id == sid for p in parts) and closing.stream_id == sid)
check("части несут одну трассировку",
      {p.trace_id for p in parts} == {"t-stream"})
check("поток закрыт", sid not in sender.open)
check("часть после закрытия не отправляется",
      fault(lambda: sender.chunk(sid, "ещё"), ERROR_INVALID_STATE)
      is not None)
check("часть незанятого потока не отправляется",
      fault(lambda: sender.chunk(99, "чужое"), ERROR_INVALID_STATE)
      is not None)

sid2 = sender.begin()
check("неизвестная причина закрытия отклонена",
      fault(lambda: sender.end(sid2, "надоело"), ERROR_INVALID_PAYLOAD)
      is not None)
sender.end(sid2, STREAM_FAILED)

# §7: часть потока может прийти раньше ответа, открывшего поток. Приёмник,
# отбрасывающий ранние части, терял бы начало каждого быстрого ответа —
# тем чаще, чем быстрее отвечает модель.
receiver = StreamReceiver()
wire = b"".join(encode_frame(m) for m in parts + [closing])
delivered = 0
for message in FrameDecoder().feed(wire):
    if receiver.accept(message):
        delivered += 1
check("все сообщения потока приняты", delivered == 4)
check("текст собран в исходном порядке",
      receiver.text(sid) == "Столица Австралии — Канберра.",
      f"| {receiver.text(sid)!r}")
check("поток отмечен завершённым",
      receiver.done(sid) and receiver.finished[sid] == STREAM_DONE)
check("приёмник не трогает чужие сообщения", receiver.accept(ev) is False)


# ---------------------------------------------------------------------------
print()
print("=== D09: жизненный цикл долгой задачи ===")

registry = Registry(IdGenerator("c-"))
task = registry.create()
check("ответ на запрос сообщает номер и приём",
      task.accepted_payload() == {"task_id": task.id, "status": "accepted"})
check("задача начинается принятой", task.state == TaskState.ACCEPTED)

with trace_scope("t-task"):
    task.start()
    m1 = task.progress("читаю файлы", fraction=0.25)
    m2 = task.progress("без доли")
    m3 = task.partial({"файлов": 12})
    m4 = task.done({"файлов": 40})

check("задача перешла в работу и завершилась",
      task.state == TaskState.DONE)
check("прогресс несёт номер задачи и пояснение",
      m1.payload["task_id"] == task.id and m1.payload["note"] == "читаю файлы")
check("доля попала в нагрузку", m1.payload.get("fraction") == 0.25)
check("доля необязательна", "fraction" not in m2.payload)
check("промежуточный результат отдан", m3.payload["result"] == {"файлов": 12})
check("события задачи несут трассировку контекста",
      {m.trace_id for m in (m1, m2, m3, m4)} == {"t-task"})

finals = [m.method for m in task.events if m.method in
          ("task.done", "task.failed", "task.cancelled")]
check("ровно одно финальное событие", finals == ["task.done"], f"| {finals}")

# После финала любое сообщение задачи — дефект отправителя.
for what, call in (("прогресс", lambda: task.progress("ещё")),
                   ("промежуточный", lambda: task.partial(1)),
                   ("второй done", lambda: task.done(1)),
                   ("failed после done", lambda: task.failed(
                       make("internal", "…"))),
                   ("cancelled после done", lambda: task.cancelled())):
    check(f"после завершения отклонён {what}",
          fault(call, ERROR_INVALID_STATE) is not None)

check("доля вне 0..1 отклонена",
      fault(lambda: registry.create().progress("шаг", fraction=1.5),
            ERROR_INVALID_PAYLOAD) is not None)

failing = registry.create()
failing.start()
bad = failing.failed(make("llm.unavailable", "Модель не отвечает."))
check("провал несёт ошибку по §5",
      bad.payload["error"]["code"] == "llm.unavailable"
      and bad.payload["error"]["category"] == "system"
      and bad.payload["error"]["retryable"] is True)
check("проваленная задача финальна", failing.state == TaskState.FAILED)

# §15.7: задача на шестьдесят секунд. Часы поддельные — требование про форму
# последовательности, а не про ожидание в реальном времени; держать проверку
# минуту ради этого значило бы платить минутой за ничто.
clock = [0.0]
long_task = registry.create()
events = run(long_task, steps=12, clock=lambda: clock[0],
             advance=lambda d: clock.__setitem__(0, clock[0] + d),
             seconds=60.0, partial_every=4)
kinds = [m.method for m in events]
check("часы прошли шестьдесят секунд", clock[0] == 60.0, f"| {clock[0]}")
check("прогресс отдан", kinds.count("task.progress") == 12)
check("промежуточные результаты отданы", kinds.count("task.partial") == 3)
check("ровно одно финальное событие у долгой задачи",
      len([k for k in kinds if k in ("task.done", "task.failed",
                                     "task.cancelled")]) == 1)
check("финальное — последнее", kinds[-1] == "task.done")


# ---------------------------------------------------------------------------
print()
print("=== D10: кооперативная отмена ===")

live = registry.create()
live.start()
ack = live.request_cancel()
check("подтверждение получения — не остановка",
      ack == {"accepted": True, "status": TaskState.RUNNING})
check("задача ещё не завершена", not live.finished)
check("задача видит просьбу", live.cancel_requested is True)
check("повторная просьба не ломает", live.request_cancel()["accepted"] is True)

stop = live.cancelled()
check("остановка приходит третьим шагом",
      stop.method == "task.cancelled" and live.state == TaskState.CANCELLED)
check("у отменённой задачи тоже ровно одно финальное событие",
      len([m for m in live.events if m.method in
           ("task.done", "task.failed", "task.cancelled")]) == 1)

# Отмена, доехавшая до задачи посреди работы, останавливает её на границе шага.
clock2 = [0.0]
racing = registry.create()
racing.start()
racing.progress("первый шаг")
racing.request_cancel()
racing.state = TaskState.ACCEPTED          # вернуть в исходное для run()
racing.events.clear()
stopped = run(racing, steps=10, clock=lambda: clock2[0],
              advance=lambda d: clock2.__setitem__(0, clock2[0] + d),
              seconds=60.0)
check("задача остановилась, не доработав",
      [m.method for m in stopped] == ["task.cancelled"],
      f"| {[m.method for m in stopped]}")
check("часы почти не сдвинулись", clock2[0] == 0.0, f"| {clock2[0]}")

# Гонка §9: задача успела завершиться сама.
quick = registry.create()
quick.start()
quick.done({"итог": "уже"})
late = registry.cancel(quick.id)
check("отмена завершённой задачи не принимается",
      late == {"accepted": False, "status": TaskState.DONE})
check("task.cancelled при этом не отправляется",
      [m.method for m in quick.events] == ["task.done"])

check("отмена неизвестной задачи говорит правду",
      registry.cancel("task-9999") == {"accepted": False,
                                       "status": STATUS_UNKNOWN})

# Возможность: оболочка не зовёт task.cancel у ядра, которое задач не умеет.
plain = Session(side=Side.SHELL)
old_core = Session(side=Side.CORE, capabilities=("stt", "tts"))
old_core.handle_hello(plain.hello_payload())
plain.accept_hello_result({"protocol_version": 1,
                           "capabilities": list(old_core.capabilities),
                           "core_version": "4.0.0", "session_id": "x"})
check("ядро без задач не принимает task.cancel",
      not plain.may_call("task.cancel"))
modern = Session(side=Side.SHELL)
core_now = Session(side=Side.CORE)
core_now.handle_hello(modern.hello_payload())
modern.accept_hello_result({"protocol_version": 1,
                            "capabilities": list(core_now.capabilities),
                            "core_version": "4.0.0", "session_id": "y"})
check("ядро с возможностью tasks принимает", modern.may_call("task.cancel"))

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
