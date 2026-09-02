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

from core.wire import (CONTROL_FRAME_LIMIT, CORE_CAPABILITIES, Envelope,
                       FrameDecoder, IdGenerator, MessageType, ProtocolFault,
                       SHELL_CAPABILITIES, Session, SessionState, Side,
                       decode, encode, encode_frame, new_trace_id, negotiate)
from core.wire.errors import (ERROR_FRAME_TOO_LARGE, ERROR_INCOMPATIBLE,
                              ERROR_INVALID_ENVELOPE, ERROR_NOT_READY,
                              ERROR_UNKNOWN_METHOD, ProtocolError)

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

print()
print("ИТОГО ошибок:", fails)
sys.exit(1 if fails else 0)
