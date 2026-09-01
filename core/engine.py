"""
Ядро ассистента: распознавание, конвейер команд, озвучка, напоминания.

Здесь нет ни одного импорта Qt — и это главное свойство модуля. Ядро можно
запустить без окна (в тестах, из консоли, в отдельном процессе), а оболочка
подписывается на события шины и решает, как их показывать.

Разделение обязанностей:
  ядро     — что делать: понять фразу, выполнить, ответить, запланировать;
  оболочка — как это выглядит: окна, всплывающие подсказки, значок в трее.

Всё блокирующее (микрофон, синтез речи, паузы в последовательностях) уходит
в фоновые потоки: ядро не должно зависеть от того, кто его вызвал.
"""

import queue
import threading
import time

from core.events import bus
from core.i18n import t as tr
from core.logging_setup import get_logger, safe, security_log
from core.protocol import Events
from core.settings_store import settings
from voice import stt as stt_mod
from voice import tts as tts_mod
from voice.commands import handle_builtin_command
from voice.history import HistoryStore
from voice.user_commands import UserCommandStore


log = get_logger("engine")


class RinaEngine:
    """Логика ассистента, независимая от интерфейса."""

    # через минуту заданный вопрос считается неактуальным
    PENDING_TTL = 60

    # согласие/отказ на опасное действие. Требуем явного «да» — молчаливое
    # непонимание не должно выключать компьютер.
    YES_WORDS = ("да", "давай", "подтверждаю", "точно", "выключай",
                 "перезагружай", "усыпляй", "ага", "yes", "confirm")
    NO_WORDS = ("нет", "отмена", "отмени", "не надо", "стоп", "no", "cancel")

    def __init__(self, plugin_manager=None, event_bus=None):
        self.bus = event_bus or bus
        self._plugins = plugin_manager
        self._busy = False
        self._always_listen = False
        self._always_thread = None
        self._stop_always = threading.Event()
        self._cmd_store = UserCommandStore(settings)
        self._history = HistoryStore(settings)
        self._host = None                    # действия над окном (см. set_host)
        # «Рина сейчас говорит». Считаем говорящих, а не держим один флаг:
        # при перекрывающихся ответах первый закончивший сбрасывал флаг,
        # микрофон открывался под ещё звучащую речь, и Рина слышала себя.
        self._speaking = threading.Event()
        self._speak_lock = threading.Lock()
        self._speak_count = 0
        self._pending = None                 # незакрытый уточняющий вопрос

        # планировщик напоминаний: обычный поток, а не таймер интерфейса
        self._stop_reminders = threading.Event()
        self._reminder_thread = None

        # Очередь команд. Конвейер запускает программы, ходит в сеть и ждёт
        # ответа модели — в потоке интерфейса это секунды замороженного окна.
        # Очередь одна на все источники: конвейер держит общее состояние
        # (незакрытый уточняющий вопрос), и параллельная обработка его портит.
        self._commands = queue.Queue()
        self._command_worker = None
        self._command_lock = threading.Lock()

    # ------------------------------------------------------------------
    # события
    # ------------------------------------------------------------------
    def _emit(self, name, **payload):
        self.bus.emit(name, **payload)

    def set_host(self, host):
        """host выполняет действия над окном (свернуть/показать/выйти)."""
        self._host = host

    # ------------------------------------------------------------------
    # озвучка
    # ------------------------------------------------------------------
    def say(self, text, sound="response"):
        """Ответить: записать в историю, сообщить оболочке и произнести."""
        from voice import sounds

        if sound == "response":
            sounds.play_response(settings)
        elif sound == "error":
            sounds.play_error(settings)

        self._history.add("assistant", text)
        self._emit(Events.HISTORY_CHANGED)
        self._emit(Events.RESPONSE, text=text)
        threading.Thread(target=self._speak_blocking, args=(text,),
                         daemon=True).start()

    def _speak_blocking(self, text):
        if not settings.get("voice_reply", True):
            return  # режим «молчать» — только текст, без голоса
        engine = tts_mod.get_engine(settings.get("tts_engine", "silent"))
        self._begin_speaking()
        try:
            engine.speak(
                text,
                voice=settings.get("voice"),
                volume=int(settings.get("volume", 75)),
                rate=int(settings.get("speed", 100)),
            )
        except Exception as e:
            self._emit(Events.ERROR, text=tr("Ошибка озвучки: ") + str(e))
        finally:
            # пауза после речи, чтобы «хвост» не попал обратно в микрофон
            time.sleep(0.4)
            self._end_speaking()

    def _begin_speaking(self):
        with self._speak_lock:
            self._speak_count += 1
            self._speaking.set()

    def _end_speaking(self):
        with self._speak_lock:
            self._speak_count = max(0, self._speak_count - 1)
            if self._speak_count == 0:
                self._speaking.clear()

    def _wait_while_speaking(self):
        while self._speaking.is_set() and not self._stop_always.is_set():
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # микрофон
    # ------------------------------------------------------------------
    def listen_once(self):
        """Однократное прослушивание (по горячей клавише)."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        from voice import sounds

        sounds.play_activation(settings)
        self._emit(Events.LISTENING_STARTED)
        result = None
        try:
            engine = stt_mod.get_engine(settings.get("stt_engine", "disabled"))
            result = engine.listen_once(
                language=self.lang_code(),
                timeout=self.listen_seconds(),
            )
        except Exception as e:
            # Раньше здесь был только finally: индикатор гас, исключение
            # уносило поток, и пользователь видел, что «ничего не произошло»,
            # без единой подсказки почему.
            log.exception("Сбой распознавания")
            self.say(tr("Не получилось распознать речь: ") + str(e),
                     sound="error")
            return
        finally:
            self._emit(Events.LISTENING_STOPPED)
            self._busy = False

        if result is None:
            return
        if result.ok and result.text:
            self._emit(Events.RECOGNIZED, text=result.text)
            # по хоткею слово активации не нужно: пользователь уже позвал явно
            self.handle_command_async(result.text, require_wake=False,
                                      source="voice")
        elif result.error:
            # движки отдают текст ошибки по-русски — переводим на границе
            self._emit(Events.ERROR, text=tr(result.error))

    def set_always_listen(self, on):
        on = bool(on)
        if on == self._always_listen:
            return
        self._always_listen = on
        self._emit(Events.ALWAYS_LISTEN, enabled=on)
        if on:
            # у каждого запуска свой признак остановки: старый поток может ещё
            # ждать микрофон, и общий сброшенный флаг оставлял бы его в работе —
            # тогда одна фраза распознавалась и выполнялась дважды
            self._stop_always = threading.Event()
            self._always_thread = threading.Thread(
                target=self._always_worker, args=(self._stop_always,),
                daemon=True)
            self._always_thread.start()
        else:
            self._stop_always.set()

    def is_always_listen(self):
        return self._always_listen

    def _always_worker(self, stop_flag=None):
        stop_flag = stop_flag or self._stop_always
        engine = stt_mod.get_engine(settings.get("stt_engine", "disabled"))
        if engine.id == "disabled":
            self._emit(Events.ERROR, text=tr(
                "Режим «всегда слушать» требует выбранного движка распознавания."))
            self._always_listen = False
            self._emit(Events.ALWAYS_LISTEN, enabled=False)
            return

        while not stop_flag.is_set():
            # пока Рина говорит — не слушаем, иначе распознаётся её же голос
            if self._speaking.is_set():
                self._wait_while_speaking()
                continue

            self._emit(Events.CAPTURING, active=True)
            try:
                result = engine.listen_once(language=self.lang_code(), timeout=5)
            except Exception:
                result = stt_mod.STTResult(error="listen error")
            self._emit(Events.CAPTURING, active=False)

            if stop_flag.is_set():
                break
            if result.ok and result.text:
                # здесь слово активации обязательно: иначе ассистент реагировал
                # бы на любой разговор в комнате
                self.handle_command_async(result.text, require_wake=True,
                                          source="always", wait=True)
                self._wait_while_speaking()

    # ------------------------------------------------------------------
    # напоминания
    # ------------------------------------------------------------------
    def start_reminders(self):
        """Запускает проверку запланированного (раз в секунду, в фоне)."""
        if self._reminder_thread is not None:
            return
        self._stop_reminders.clear()
        self._reminder_thread = threading.Thread(
            target=self._reminder_worker, daemon=True)
        self._reminder_thread.start()

    def _reminder_worker(self):
        from voice.reminders import ReminderStore

        store = ReminderStore(settings)
        while not self._stop_reminders.wait(1.0):
            try:
                for item in store.due():
                    store.mark_done(item["id"])
                    self._emit(Events.REMINDER_FIRED, item=item)
            except Exception:
                pass          # сбой чтения не должен убивать планировщик

    # ------------------------------------------------------------------
    # слово активации
    # ------------------------------------------------------------------
    def _extract_command(self, text, require_wake):
        """
        Текст команды без слова активации.
        None — активации не было и команду надо проигнорировать.
        """
        if not require_wake:
            return text.strip()

        from voice.wake import get_wake_words, strip_wake

        wake_words = get_wake_words(settings)
        if not wake_words:
            return text.strip()
        return strip_wake(text, wake_words)

    # ------------------------------------------------------------------
    # уточняющие вопросы
    # ------------------------------------------------------------------
    def _resolve_pending(self, command):
        """True — фраза была ответом на вопрос, дальше по конвейеру не идём."""
        pending = self._pending
        if not pending:
            return False
        if time.time() - pending.get("ts", 0) > self.PENDING_TTL:
            self._pending = None
            return False
        if pending.get("kind") in ("confirm_action", "confirm_command"):
            return self._resolve_confirm(command, pending)
        if pending.get("kind") != "choose_app":
            return False

        from voice import app_index, app_launcher

        options = pending.get("options") or []
        if not options:                 # состояние повреждено — вопроса больше нет
            self._pending = None
            return False
        entry, cancelled = app_launcher.choose(command, options)
        if cancelled:
            self._pending = None
            self.say(tr("Хорошо, отменяю."))
            return True
        if entry is None:
            return False       # не похоже на ответ — считаем новой командой

        query = pending.get("query")
        self._pending = None
        if app_index.launch(entry):
            # запоминаем выбор: в следующий раз запустится сразу
            if query:
                app_launcher.remember(query, entry.launch, entry.kind, entry.name)
            self.say(tr("Запускаю {app}.", app=entry.name))
        else:
            self.say(tr("Не получилось запустить {app}.", app=entry.name),
                     sound="error")
        return True

    def _resolve_confirm(self, command, pending):
        from voice import system_control
        from voice.textmatch import normalize

        words = normalize(command).split()

        if any(w in words for w in self.NO_WORDS):
            security_log().info(
                "Опасное действие отменено пользователем: %s",
                pending.get("action") or "пользовательская команда")
            self._pending = None
            self.say(tr("Хорошо, отменяю."))
            return True
        if any(w in words for w in self.YES_WORDS):
            self._pending = None
            if pending.get("command") is not None:
                self._run_user_command(pending["command"])
            else:
                self.say(system_control.run(pending.get("action")))
            return True
        # ответ невнятный — действие не выполняем, трактуем как новую команду
        return False

    # ------------------------------------------------------------------
    # обработчики шагов конвейера
    # ------------------------------------------------------------------
    def _handle_reminder(self, command):
        """Текст ответа, если фраза про время, иначе None."""
        from voice import reminders

        parsed = reminders.parse(command)
        if parsed is None:
            return None

        store = reminders.ReminderStore(settings)

        if parsed.action == "list":
            items = sorted(store.active(), key=lambda r: r.get("fire_at", 0))
            if not items:
                return tr("Ничего не запланировано.")
            return tr("Запланировано: ") + "; ".join(
                reminders.describe(i) for i in items[:5])

        if parsed.action == "cancel":
            removed = store.clear_active()
            if not removed:
                return tr("Нечего отменять.")
            return tr("Отменила: {count}.", count=removed)

        fire_at = parsed.at if parsed.at else time.time() + (parsed.delay or 0)
        store.add(parsed.kind, fire_at, parsed.text)

        if parsed.delay:
            left = reminders.humanize_left(parsed.delay)
            if parsed.text:
                return tr("Напомню через {left}: {text}.",
                          left=left, text=parsed.text)
            return tr("Засекла {left}.", left=left)

        when = reminders.when_text(fire_at)
        if parsed.text:
            return tr("Напомню в {time}: {text}.", time=when, text=parsed.text)
        return tr("Разбужу в {time}.", time=when)

    def _run_user_command(self, user_cmd):
        """
        Выполняет пользовательскую команду.

        Последовательности уходят в фоновый поток: между шагами бывает пауза,
        а вызывающий поток (в том числе поток интерфейса) блокировать нельзя.
        """
        from voice.user_commands import execute

        self._cmd_store.bump_stat(user_cmd.get("id"))
        if user_cmd.get("type") == "sequence":
            def worker():
                _ok, resp = execute(user_cmd, self._host)
                self.say(resp)
            threading.Thread(target=worker, daemon=True).start()
            return
        _ok, resp = execute(user_cmd, self._host)
        self.say(resp)

    def run_command_by_id(self, command_id):
        """
        Выполнить команду по её id (кнопка «Выполнить» в списке).

        Тоже в фоне: последовательность с паузами выполняется секундами,
        а нажимают кнопку из потока интерфейса.
        """
        for cmd in self._cmd_store.all():
            if cmd.get("id") == command_id:
                self._ensure_command_worker()
                threading.Thread(
                    target=self._run_user_command, args=(cmd,),
                    name="rina-run-command", daemon=True).start()
                return

    # ------------------------------------------------------------------
    # очередь команд
    # ------------------------------------------------------------------
    def _ensure_command_worker(self):
        with self._command_lock:
            worker = self._command_worker
            if worker is None or not worker.is_alive():
                self._command_worker = threading.Thread(
                    target=self._command_loop, name="rina-commands",
                    daemon=True)
                self._command_worker.start()

    def _command_loop(self):
        while True:
            text, require_wake, source, done = self._commands.get()
            try:
                self.handle_command(text, require_wake=require_wake,
                                    source=source)
            except Exception as e:
                # без этого исключение уносило бы воркер, и все следующие
                # команды остались бы в очереди навсегда
                log.exception("Сбой обработки команды")
                try:
                    self.say(tr("Не получилось выполнить команду: ") + str(e),
                             sound="error")
                except Exception:
                    pass
            finally:
                done.set()

    def handle_command_async(self, text, require_wake=False, source="typed",
                             wait=False):
        """
        Поставить команду в очередь обработки.

        Оболочка вызывает это вместо handle_command: конвейер работает в
        своём потоке, окно остаётся живым, а порядок команд сохраняется.
        wait=True нужен режиму «всегда слушать»: он не должен слушать
        дальше, пока предыдущая фраза не отработала.
        """
        self._ensure_command_worker()
        done = threading.Event()
        self._commands.put((text, require_wake, source, done))
        if wait:
            done.wait()
        return done

    # ------------------------------------------------------------------
    # конвейер команд
    # ------------------------------------------------------------------
    def handle_command(self, text, require_wake=False, source="typed"):
        if not text:
            return

        command = self._extract_command(text, require_wake)
        if command is None:
            return          # активации не было — молчим
        if not command:
            # активация прозвучала, но команды нет. В режиме «всегда слушать»
            # не отвечаем: Рина услышала бы собственный ответ и зациклилась.
            if source != "always":
                self._history.add("user", "Рина", source=source)
                self._emit(Events.HISTORY_CHANGED)
                self.say(tr("Да? Слушаю."))
            return

        log.info("Команда (%s): %s", source, safe(command))
        self._history.add("user", command, source=source)
        self._emit(Events.HISTORY_CHANGED)

        # 0) ответ на ранее заданный вопрос
        if self._resolve_pending(command):
            return
        # это новая команда, а не ответ — старый вопрос снимаем, иначе
        # следующее «второй» ответило бы на давно неактуальный вопрос
        self._pending = None

        # 1) плагины
        if self._plugins is not None:
            try:
                if self._plugins.dispatch_command(command):
                    log.debug("Команду обработал плагин")
                    return
            except Exception:
                # плагин — чужой код; его сбой не должен рвать конвейер,
                # но и пропадать бесследно тоже не должен
                log.exception("Сбой плагина при разборе команды")

        # 2) пользовательские команды
        try:
            from voice.user_commands import matches, command_needs_confirm

            for user_cmd in self._cmd_store.all():
                if not matches(user_cmd, command):
                    continue
                if command_needs_confirm(user_cmd):
                    self._pending = {
                        "kind": "confirm_command",
                        "command": user_cmd,
                        "ts": time.time(),
                    }
                    self.say(tr("Команда «{name}» выключит или перезагрузит "
                                "компьютер. Точно выполнить?",
                                name=(user_cmd.get("triggers") or ["?"])[0]))
                else:
                    self._run_user_command(user_cmd)
                return
        except Exception:
            log.exception("Сбой при разборе пользовательских команд")

        # 3) таймеры, будильники и напоминания
        reminder_reply = self._handle_reminder(command)
        if reminder_reply is not None:
            self.say(reminder_reply)
            return

        # 4) управление системой и медиа
        from voice import system_control

        action_id, needs_confirm = system_control.match_action(command)
        if action_id:
            if needs_confirm:
                self._pending = {
                    "kind": "confirm_action",
                    "action": action_id,
                    "ts": time.time(),
                }
                self.say(system_control.confirm_question(action_id))
            else:
                self.say(system_control.run(action_id))
            return

        # 5) запуск программ по индексу установленного ПО
        from voice import app_launcher

        outcome = app_launcher.resolve(command)
        if outcome is not None:
            if outcome.status == "ambiguous":
                self._pending = {
                    "kind": "choose_app",
                    "options": outcome.options,
                    "query": outcome.query,
                    "ts": time.time(),
                }
            self.say(outcome.message,
                     sound="error" if outcome.status == "not_found" else "response")
            if outcome.status == "not_found" and outcome.query:
                self._emit(Events.APP_NOT_FOUND, query=outcome.query)
            return

        # 6) встроенные команды (счёт, поиск, простые ответы)
        response = handle_builtin_command(command)
        if response:
            self.say(response)
            return

        # 7) свободный вопрос — отвечает локальная модель (если включена).
        # Ответ занимает секунды, поэтому уходит в фоновый поток: конвейер
        # может выполняться и в потоке интерфейса (команда из строки ввода).
        from core import llm

        if llm.is_enabled():
            self._ask_llm_async(command, source)
            return

        self._fallback_reply(command, source)

    def _ask_llm_async(self, command, source):
        """Спрашивает модель в фоне и отвечает, когда та ответит."""
        from core import llm

        def worker():
            self._emit(Events.THINKING, active=True)
            try:
                answer = llm.ask(command, self._history.all())
            except llm.LLMError:
                # модель не ответила — ведём себя как без неё
                self._emit(Events.THINKING, active=False)
                self._fallback_reply(command, source)
                return
            except Exception:
                self._emit(Events.THINKING, active=False)
                self._fallback_reply(command, source)
                return
            self._emit(Events.THINKING, active=False)
            self.say(answer)

        threading.Thread(target=worker, daemon=True).start()

    def _fallback_reply(self, command, source):
        """
        Запасной вариант — поиск в интернете.

        В режиме «всегда слушать» не ищем: туда попадают шум и случайная
        речь, открывать по ним браузер нельзя.
        """
        if settings.get("web_search_fallback", True) and source != "always":
            from voice import websearch

            found = websearch.fallback_search(
                command, settings.get("search_engine", websearch.DEFAULT_ENGINE))
            if found:
                self.say(found)
                return

        self.say(tr("Извини, я не поняла команду."), sound="error")

    # ------------------------------------------------------------------
    # настройки, зависящие от языка и микрофона
    # ------------------------------------------------------------------
    def listen_seconds(self):
        try:
            value = int(settings.get("listen_seconds", 8))
        except (TypeError, ValueError):
            return 8
        return max(3, min(20, value))

    def lang_code(self):
        """Язык распознавания = язык интерфейса (единая настройка)."""
        lang_map = {"Русский": "ru", "English": "en", "Українська": "uk",
                    "Español": "es", "Deutsch": "de"}
        return lang_map.get(settings.get("ui_language", "Русский"), "ru")

    def shutdown(self):
        self._stop_always.set()
        self._stop_reminders.set()
