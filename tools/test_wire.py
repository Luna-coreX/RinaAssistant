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
from core.wire.data import (DATA_FRAME_LIMIT, DataFrame, DataFrameDecoder,
                            DataReceiver, DataSender, KINDS,
                            capability_for_kind, encode_data_frame)
from core.wire.permissions import Ask, PermissionChannel
from core.wire.liveness import MISSED_LIMIT, SILENCE, Liveness, VolatileState
from core.confirmations import ONCE, SCOPES, UNTIL, ConfirmationError

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

# То же для методов: метод, о котором документ молчит, — договорённость,
# известная одной стороне.
from core.wire.handshake import BASE_METHODS, CAPABILITIES as CAPS

all_methods = set(BASE_METHODS)
for cap in CAPS.values():
    all_methods |= set(cap.methods)
unknown_methods = sorted(m for m in all_methods if m not in spec_text)
check("каждый метод описан в спецификации", not unknown_methods,
      f"| нет в документе: {unknown_methods}")
print(f"     методов: {len(all_methods)}, событий: {len(EVENTS)}")


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


# ---------------------------------------------------------------------------
print()
print("=== D07: бинарный канал ===")

sender = DataSender()
sender.open_stream(11, "audio.input")
check("вид потока знает свою возможность",
      capability_for_kind("audio.input") == "audio.input"
      and capability_for_kind("screen.frame") == "actuation")
check("неизвестный вид потока отклонён",
      fault(lambda: sender.open_stream(12, "запах"), ERROR_INVALID_PAYLOAD)
      is not None)
check("повторное открытие того же потока отклонено",
      fault(lambda: sender.open_stream(11, "audio.input"), ERROR_INVALID_STATE)
      is not None)

sender.grant(11, 100000)
pcm = bytes(range(256)) * 4          # 1024 байта «звука»
frames = [sender.send(11, pcm) for _ in range(8)]

decoder = DataFrameDecoder()
receiver = DataReceiver()
for raw in frames:
    for frame in decoder.feed(raw):
        receiver.accept(frame)
check("звук доехал побайтно", bytes(receiver.data[11]) == pcm * 8)
check("порядковые номера подряд, пропусков нет", receiver.gaps == [])

# Кадр, пришедший по кускам, и два кадра в одном куске.
split = DataFrameDecoder()
joined = b"".join(frames[:2])
check("половина кадра данных не даёт кадра",
      list(split.feed(joined[:5])) == [] and split.pending == 5)
check("остаток собирает оба кадра", len(list(split.feed(joined[5:]))) == 2)

# Пропуск номера не обрывает приём, но записывается.
gappy = DataReceiver()
gappy.accept(DataFrame(7, 1, b"a"))
gappy.accept(DataFrame(7, 3, b"c"))
check("пропуск замечен и назван", gappy.gaps == [(7, 2, 3)], f"| {gappy.gaps}")
check("приём при этом продолжился", bytes(gappy.data[7]) == b"ac")

# Предел — по заявленной длине, до выделения памяти.
header_only = (DATA_FRAME_LIMIT + 1).to_bytes(4, "big")
check("огромный кадр данных отвергнут по заголовку",
      fault(lambda: list(DataFrameDecoder().feed(header_only)),
            ERROR_FRAME_TOO_LARGE) is not None)
check("кадр короче собственного заголовка отвергнут",
      fault(lambda: list(DataFrameDecoder().feed((4).to_bytes(4, "big")
                                                 + b"abcd")),
            ERROR_INVALID_PAYLOAD) is not None)
check("свой кадр сверх предела не отправляется",
      fault(lambda: encode_data_frame(DataFrame(1, 1,
                                                b"x" * DATA_FRAME_LIMIT)),
            ERROR_FRAME_TOO_LARGE) is not None)


# ---------------------------------------------------------------------------
print()
print("=== D07: звук не задерживает управление ===")

# Требование §15.6 — «поток PCM не ухудшает задержку управляющего канала».
# Настоящую задержку измеряют на живом канале, и это работа D16. Здесь
# измеряется то, откуда задержка берётся: сколько байт управляющему разбору
# придётся проглотить, прежде чем он дойдёт до команды. Сравниваются две
# раскладки одной и той же нагрузки — принятая и отвергнутая (§2, base64
# внутри JSON), обе собранные настоящим кодом.
import base64

BURST = 200
command = Envelope.request("command.handle", {"text": "стоп", "source": "voice"},
                           id="s-9000", trace_id="t-9000")

# Отвергнутая раскладка: звук едет управляющим каналом как base64.
rejected = b""
for i in range(BURST):
    rejected += encode_frame(Envelope.event(
        "assistant.response",
        {"text": base64.b64encode(pcm).decode("ascii")},
        id=f"c-{i}", trace_id="t-9000"))
before_rejected = len(rejected)
rejected += encode_frame(command)

# Принятая: звук в своём канале, команда в своём.
data_bytes = b""
burst_sender = DataSender()
burst_sender.open_stream(51, "audio.input")
burst_sender.grant(51, BURST * len(pcm))
for _ in range(BURST):
    data_bytes += burst_sender.send(51, pcm)
accepted = encode_frame(command)
before_accepted = 0

# Сколько байт управляющий разбор съедает до команды — в обоих случаях.
def bytes_before_command(stream):
    eaten = 0
    decoder = FrameDecoder()
    for offset in range(0, len(stream), 4096):
        piece = stream[offset:offset + 4096]
        eaten += len(piece)
        for message in decoder.feed(piece):
            if message.method == "command.handle":
                return eaten
    return None

eaten_rejected = bytes_before_command(rejected)
eaten_accepted = bytes_before_command(accepted)
check("в отвергнутой раскладке команда за всем звуком",
      eaten_rejected is not None and eaten_rejected > before_rejected,
      f"| {eaten_rejected} байт")
check("в принятой команда достаётся сразу",
      eaten_accepted is not None and eaten_accepted < 4096,
      f"| {eaten_accepted} байт")
check("звук из управляющего канала ушёл целиком",
      len(accepted) < len(pcm),
      f"| управляющий канал {len(accepted)} байт при {len(pcm)} байт звука")
print(f"     всплеск {BURST} кадров: до команды {eaten_rejected} байт против "
      f"{eaten_accepted}, звук отдельно — {len(data_bytes)} байт")

# И то, что делает разделение возможным: звук вообще не попадает в JSON.
audio_frame = encode_data_frame(DataFrame(11, 1, pcm))
check("кадр данных не является JSON",
      not audio_frame.lstrip(b"\x00").startswith(b"{"))
check("двоичный кадр компактнее base64 в JSON",
      len(audio_frame) < len(base64.b64encode(pcm)),
      f"| {len(audio_frame)} против {len(base64.b64encode(pcm))}")


# ---------------------------------------------------------------------------
print()
print("=== D08: обратное давление ===")

fresh = DataSender()
fresh.open_stream(21, "audio.output")
check("начальный кредит — ноль", fresh.available(21) == 0)
check("без кредита не отправляют",
      fault(lambda: fresh.send(21, b"rano"), ERROR_INVALID_STATE) is not None)

fresh.grant(21, 10)
fresh.send(21, b"12345")
check("кредит списывается по байтам", fresh.available(21) == 5)
check("превышение кредита отклонено",
      fault(lambda: fresh.send(21, b"123456"), ERROR_INVALID_STATE)
      is not None)
fresh.send(21, b"12345")
check("кредит исчерпан ровно", fresh.available(21) == 0)
check("нулевой кредит не выдаётся",
      fault(lambda: fresh.grant(21, 0), ERROR_INVALID_PAYLOAD) is not None)

# Кредит считается по потоку: микрофон и синтез идут одновременно и в разные
# стороны, и общий счёт связал бы их скорости без всякой причины.
two = DataSender()
two.open_stream(31, "audio.input")
two.open_stream(32, "audio.output")
two.grant(31, 100)
check("кредит одного потока не виден другому",
      two.available(31) == 100 and two.available(32) == 0)

# Кредит выдаётся по мере обработки, а не по мере получения: кредит за
# необработанное — это и есть та неограниченная очередь, ради устранения
# которой схема существует.
flow = DataSender()
flow.open_stream(41, "audio.input")
flow.grant(41, 4096)
sink = DataReceiver(window=2048)
dec = DataFrameDecoder()
for frame in dec.feed(flow.send(41, b"z" * 1500)):
    sink.accept(frame)
back = sink.take_credit(41)
check("приёмник вернул кредит на обработанное", back == 1500, f"| {back}")
check("повторно тот же кредит не выдаётся", sink.take_credit(41) == 0)
big_sink = DataReceiver(window=1000)
big_sink.consumed[41] = 5000
check("кредит не превышает окно приёмника",
      big_sink.take_credit(41) == 1000)

check("закрытый поток не принимает данные",
      (flow.close_stream(41) or True)
      and fault(lambda: flow.send(41, b"pozdno"), ERROR_INVALID_STATE)
      is not None)

# Методы управления потоком базовые: сам метод есть всегда, а вид отпирается
# возможностью собеседника.
pair_shell = Session(side=Side.SHELL)
pair_core = Session(side=Side.CORE)
pair_core.handle_hello(pair_shell.hello_payload())
pair_shell.accept_hello_result({"protocol_version": 1,
                                "capabilities": list(pair_core.capabilities),
                                "core_version": "4.0.0", "session_id": "z"})
check("stream.open доступен обеим сторонам",
      pair_shell.may_call("stream.open") and pair_core.may_call("stream.open"))
check("stream.credit доступен", pair_core.may_call("stream.credit"))
check("вид screen.frame просит возможность, которой в 4.0 нет",
      capability_for_kind("screen.frame") not in pair_core.peer_capabilities)


# ---------------------------------------------------------------------------
print()
print("=== D12: канал разрешений ===")

check("областей две, и обе означают разное", set(SCOPES) == {ONCE, UNTIL})

now = [1000.0]
channel = PermissionChannel(clock=lambda: now[0])
ask = channel.ask("power_action", {"action": "shutdown"},
                  permission="system.power",
                  reason="Пользователь сказал «выключи компьютер»",
                  preview="Компьютер будет выключен немедленно.", ttl=60)

payload = ask.to_payload()
check("просьба несёт своё имя, причину и предпросмотр",
      payload["permission"] == "system.power"
      and payload["preview"].startswith("Компьютер будет")
      and payload["reason"].startswith("Пользователь"))
check("аргументы вызова наружу не уходят",
      "args" not in payload and "shutdown" not in str(payload))
check("просьба открыта", channel.pending == 1)
check("просьба без предпросмотра не заводится",
      fault(lambda: channel.ask("power_action", permission="system.power",
                                reason="…", preview="   "),
            ERROR_INVALID_PAYLOAD) is not None)

# Идентификатор выпускает ядро: оболочка отвечает «да», а не приносит номер.
answer = channel.resolve(ask.id, True)
check("подтверждение выписано ядром", bool(answer["confirmation_id"]))
check("ответ несёт срок и область",
      answer["scope"] == ONCE and answer["expires_at"] > now[0])
check("просьба закрыта", channel.pending == 0)
check("ответить второй раз нельзя",
      fault(lambda: channel.resolve(ask.id, True), ERROR_INVALID_STATE)
      is not None)

# Подтверждение годится ровно для того вызова, под который выдано.
cid = answer["confirmation_id"]
try:
    channel.ledger.redeem(cid, "power_action", {"action": "sleep"})
    check("подтверждение не подходит к другим аргументам", False)
except ConfirmationError as exc:
    check("подтверждение не подходит к другим аргументам",
          exc.code == "confirmation.invalid")
used = channel.ledger.redeem(cid, "power_action", {"action": "shutdown"})
check("подтверждение принято для своего вызова", used.id == cid)
try:
    channel.ledger.redeem(cid, "power_action", {"action": "shutdown"})
    check("однократное сгорело", False)
except ConfirmationError:
    check("однократное сгорело", True)

# Отказ.
denied_ask = channel.ask("power_action", {"action": "reboot"},
                         permission="system.power", reason="…",
                         preview="Компьютер будет перезагружен.")
denied = channel.resolve(denied_ask.id, False)
check("отказ не выдаёт подтверждения",
      denied["granted"] is False and denied["confirmation_id"] is None)
check("отказ назван причиной", denied["reason"] == "denied")

# Отказ по умолчанию: молчание не согласие.
silent = channel.ask("power_action", {"action": "shutdown"},
                     permission="system.power", reason="…",
                     preview="Компьютер будет выключен.", ttl=60)
now[0] += 61
late = channel.resolve(silent.id, True)
check("поздний ответ «да» не разрешает",
      late["granted"] is False and late["reason"] == "expired")

forgotten = channel.ask("power_action", {"action": "shutdown"},
                        permission="system.power", reason="…",
                        preview="Компьютер будет выключен.", ttl=30)
check("незакрытая просьба висит", channel.pending == 1)
now[0] += 31
check("просроченные просьбы убираются", channel.expire() == 1)
check("после уборки не осталось", channel.pending == 0)

# Опасному действию длительная область не выдаётся.
risky = channel.ask("power_action", {"action": "shutdown"},
                    permission="system.power", reason="…",
                    preview="Компьютер будет выключен.")
got = channel.resolve(risky.id, True, UNTIL)
check("опасному действию область понижена до одноразовой",
      got["scope"] == ONCE and got["downgraded"] is True)

# Неопасному — выдаётся, и подтверждение переживает предъявление.
mild = channel.ask("set_volume", {"level": 30}, permission="system.media",
                   reason="…", preview="Громкость станет 30 %.")
kept = channel.resolve(mild.id, True, UNTIL)
check("неопасному действию область сохранена",
      kept["scope"] == UNTIL and kept["downgraded"] is False)
channel.ledger.redeem(kept["confirmation_id"], "set_volume", {"level": 30})
again = channel.ledger.redeem(kept["confirmation_id"], "set_volume",
                              {"level": 30})
check("подтверждение «до срока» не сгорает при первом предъявлении",
      again.id == kept["confirmation_id"])

check("неизвестная область отклонена",
      fault(lambda: channel.resolve(
          channel.ask("set_volume", {"level": 1}, permission="system.media",
                      reason="…", preview="Громкость станет 1 %.").id,
          True, "навсегда"), ERROR_INVALID_PAYLOAD) is not None)


# ---------------------------------------------------------------------------
print()
print("=== D13: канал актуации — только спецификация ===")

actuation = CAPS["actuation"]
section12 = spec_text[spec_text.index("## 12. Канал актуации"):]
section12 = section12[:section12.index(chr(10) + "---" + chr(10))]
spec_actuation = set()
for line in section12.split("\n"):
    if line.startswith("|") and not line.startswith("|---"):
        spec_actuation |= set(re.findall(r"`([a-z]+\.[a-z.]+)`",
                                         line.split("|")[1]))
check("таблица §12 прочитана", len(spec_actuation) >= 7,
      f"| {len(spec_actuation)}")
check("методы актуации описаны и заведены",
      spec_actuation == set(actuation.methods),
      f"| только в документе: {sorted(spec_actuation - set(actuation.methods))},"
      f" только в коде: {sorted(set(actuation.methods) - spec_actuation)}")
check("возможность actuation не объявляет никто",
      "actuation" not in SHELL_CAPABILITIES
      and "actuation" not in CORE_CAPABILITIES)

pair = Session(side=Side.CORE)
pair.handle_hello(Session(side=Side.SHELL).hello_payload())
for method in sorted(actuation.methods):
    if fault(lambda m=method: pair.check_incoming(m),
             ERROR_UNKNOWN_METHOD) is None:
        check(f"{method} отвечает «неизвестный метод»", False)
check("все методы актуации отвечают «неизвестный метод»", True,
      f"| {len(actuation.methods)} шт.")
check("вид потока screen.frame просит именно actuation",
      capability_for_kind("screen.frame") == "actuation")


# ---------------------------------------------------------------------------
print()
print("=== D14: живость канала ===")

t = [100.0]
live = Liveness(clock=lambda: t[0])
check("свежая сторона жива и вопросов не требует",
      not live.due() and not live.dead())

t[0] += SILENCE - 0.1
check("до порога тишины не спрашиваем", not live.due())
t[0] += 0.2
check("после порога пора спросить", live.due())

live.sent_ping()
check("вопрос задан и ждёт ответа", live.awaiting and live.missed == 1)
live.note_pong()
check("понг снимает счётчик", live.missed == 0 and not live.awaiting)

# Любое сообщение считается за ответ: занятый канал пинговать незачем.
t[0] += 10
live.sent_ping()
live.note_traffic()
check("обычное сообщение засчитано как признак жизни",
      live.missed == 0 and not live.due())

# Три неотвеченных подряд — смерть; двух мало.
for i in range(MISSED_LIMIT - 1):
    t[0] += SILENCE
    live.sent_ping()
check("двух неотвеченных мало", not live.dead(), f"| {live.missed}")
t[0] += SILENCE
live.sent_ping()
check("три неотвеченных подряд — сторона мертва",
      live.dead(), f"| {live.missed}")
live.reset()
check("после переподключения счётчик чист",
      not live.dead() and live.missed == 0)


# ---------------------------------------------------------------------------
print()
print("=== D14: что обрыв уносит с собой ===")

clock = [500.0]
perm = PermissionChannel(clock=lambda: clock[0])
granted = perm.resolve(perm.ask("set_volume", {"level": 20},
                                permission="system.media", reason="…",
                                preview="Громкость станет 20 %.").id,
                       True, UNTIL)
perm.ask("power_action", {"action": "shutdown"}, permission="system.power",
         reason="…", preview="Компьютер будет выключен.")

jobs = Registry(IdGenerator("c-"))
running_task = jobs.create()
running_task.start()

bytes_out = DataSender()
bytes_out.open_stream(61, "audio.input")
bytes_out.open_stream(62, "audio.output")

words_out = StreamSender(IdGenerator("c-"))
words_out.begin()

link = Session(side=Side.CORE)
link.handle_hello(Session(side=Side.SHELL).hello_payload())

volatile = VolatileState(permissions=perm, tasks=jobs,
                         data_streams=bytes_out, text_streams=words_out,
                         session=link)
before = volatile.snapshot()
check("до обрыва всё на месте",
      before == {"разрешения": 1, "просьбы": 1, "задачи": 1,
                 "потоки данных": 2, "потоки текста": 1},
      f"| {before}")

was = volatile.reset()
after = volatile.snapshot()
check("обрыв унёс всё перечисленное в §13",
      after == {"разрешения": 0, "просьбы": 0, "задачи": 0,
                "потоки данных": 0, "потоки текста": 0},
      f"| {after}")
check("сброс отчитался, чего сколько было", was == before)
check("сессия снова требует рукопожатия",
      not link.ready and link.state == SessionState.CLOSED)

# Главное: выданное разрешение не переживает обрыв.
try:
    perm.ledger.redeem(granted["confirmation_id"], "set_volume", {"level": 20})
    check("разрешение, выданное до обрыва, не действует", False)
except ConfirmationError as exc:
    check("разрешение, выданное до обрыва, не действует",
          exc.code == "confirmation.invalid")

check("после обрыва поток открывается заново без спора",
      (bytes_out.open_stream(61, "audio.input") or True)
      and bytes_out.available(61) == 0)


# ---------------------------------------------------------------------------
print()
print("=== D17: правила совместимости проверяемы ===")

import json as _json
from tools.check_contract import SNAPSHOT, current as contract_now, diff

check("снимок контракта существует", os.path.isfile(SNAPSHOT))
snapshot = _json.load(open(SNAPSHOT, encoding="utf-8"))
same_added, same_broken = diff(snapshot, contract_now())
check("код и снимок сходятся", not same_added and not same_broken,
      f"| можно: {same_added}, ломает: {same_broken}")

# Проверка обязана ловить каждое из ломающих изменений §4 — иначе она
# декоративна, а декоративная проверка хуже её отсутствия: на неё полагаются.
base = contract_now()


def mutated(change):
    copy = _json.loads(_json.dumps(base))
    change(copy)
    return diff(base, copy)


def drop_method(c):
    c["methods"].pop("speech.say")


def move_method(c):
    c["methods"]["task.cancel"] = "plugins"


def retype_field(c):
    c["events"]["assistant.thinking"]["active"]["type"] = "string"


def require_field(c):
    c["events"]["speech.recognized"]["язык"] = {
        "type": "string", "required": True, "choices": [],
        "low": None, "high": None}


def drop_choice(c):
    c["events"]["stream.end"]["reason"]["choices"].remove("failed")


def change_error(c):
    c["errors"]["app.not_found"]["retryable"] = True


def drop_field(c):
    c["events"]["apps.not_found"].pop("query")


for what, change in (("удаление метода", drop_method),
                     ("переезд метода в другую возможность", move_method),
                     ("смена типа поля", retype_field),
                     ("новое обязательное поле", require_field),
                     ("убранное значение перечисления", drop_choice),
                     ("смена повторяемости ошибки", change_error),
                     ("удаление поля события", drop_field)):
    _, breaks = mutated(change)
    check(f"поймано ломающее: {what}", len(breaks) == 1, f"| {breaks}")


def add_optional(c):
    c["events"]["history.changed"]["когда"] = {
        "type": "number", "required": False, "choices": [],
        "low": None, "high": None}


def add_event(c):
    c["events"]["рина.загрустила"] = {}


def add_choice(c):
    c["events"]["window.action"]["action"]["choices"].append("restore")


for what, change in (("новое необязательное поле", add_optional),
                     ("новое событие", add_event),
                     ("новое значение перечисления", add_choice)):
    ok, breaks = mutated(change)
    check(f"пропущено разрешённое: {what}", not breaks and len(ok) == 1,
          f"| можно: {ok}, ломает: {breaks}")


# ---------------------------------------------------------------------------
print()
print("=== E05: форма сработавшего напоминания ===")

# Хранилищу подсовывается память, а не диск: проверка не должна ничего
# писать даже во временную папку, если может обойтись.
from core.settings_api import MemorySettings
from voice.reminders import ReminderStore

fired = ReminderStore(MemorySettings()).add("timer", 9e9, "проверить тесты")

# Форма из §10 спецификации читается прямо оттуда, а не переписывается сюда.
section10 = spec_text[spec_text.index("### Форма `reminder.fired.item`"):]
section10 = section10[:section10.index(chr(10) + chr(10) + "**")]
documented = set(re.findall(r"^\| `([a-z_]+)` \|", section10, re.M))
check("форма описана в спецификации", len(documented) >= 5,
      f"| {sorted(documented)}")
check("хранилище кладёт ровно описанные поля",
      set(fired) == documented,
      f"| только в документе: {sorted(documented - set(fired))}, "
      f"только в хранилище: {sorted(set(fired) - documented)}")

# И всё это обязано пережить провод: событие несёт item объектом.
import json as _json2

check("напоминание сериализуется без потерь",
      _json2.loads(_json2.dumps(fired, ensure_ascii=False)) == fired)
carried = event("reminder.fired", {"item": fired}, id="c-700",
                trace_id="t-rem")
back = decode(encode(carried))
check("и доезжает через конверт целым", back.payload["item"] == fired)
check("событие объявлено в каталоге", "reminder.fired" in EVENTS)

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
