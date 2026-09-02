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
import contextvars
import threading
import time

from core.events import bus
from core.trace import trace_scope
from core.i18n import t as tr
from core import router as router_mod
from core import dialog as dialog_mod
from core.dialog import Dialog, Question
from core.executor import Executor
from core.toolrunner import ToolContext, ToolRunner
from voice.wake import get_wake_words
from voice.reminders import ReminderStore
from core.logging_setup import get_logger, safe, security_log
from core.protocol import Events
from core.features import default_features
from core.settings_api import default_settings
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

    # Слова согласия и отказа живут в роутере: это часть разбора, и роутер
    # обязан работать, не поднимая ядро. Здесь — псевдонимы, чтобы не менять
    # обращения RinaEngine.YES_WORDS по коду и в тестах.
    YES_WORDS = router_mod.YES_WORDS
    NO_WORDS = router_mod.NO_WORDS

    def __init__(self, plugin_manager=None, event_bus=None, settings=None,
                 features=None):
        """
        settings — любой объект по core.settings_api.SettingsProvider.
        По умолчанию общее хранилище приложения; в тестах — MemorySettings,
        чтобы не трогать файл пользователя.

        features — по core.features.FeatureProvider. По умолчанию бесплатный
        план, где доступно всё.
        """
        self.bus = event_bus or bus
        self._settings = settings if settings is not None else default_settings()
        self._features = features if features is not None else default_features()
        settings = self._settings          # локальное имя для кода ниже
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
        self._reminders = ReminderStore(settings)

        # Разбор, память о заданном вопросе и исполнение разведены по
        # отдельным объектам (4.0-B02, B03, B04). Ядро их связывает.
        self._dialog = Dialog()

        # Всё, что меняет мир, проходит через реестр инструментов
        # (4.0-C03). Исполнитель ниже ничего не делает сам — он переводит
        # намерения в вызовы.
        self._tools = ToolRunner(
            ToolContext(
                settings=settings,
                reminders=self._reminders,
                commands=self._cmd_store,
                plugins=plugin_manager,
                # Через лямбду, а не связанным методом: озвучку и шину ядро
                # может подменить позже (тесты, оболочка), и инструменты
                # обязаны следовать за текущей, а не за той, что была при
                # сборке.
                emit=lambda name, **data: self._emit(name, **data),
                host=None,
                on_alias=self._remember_choice,
            ),
            features=self._features,
        )
        self._executor = Executor(
            say=lambda text, sound="response": self.say(text, sound=sound),
            tools=self._tools,
            emit=lambda name, **data: self._emit(name, **data),
        )

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

    @property
    def features(self):
        """
        Доступность возможностей. Спрашивать только здесь.

        Оболочка показывает состояние, но не решает его: решение принимает
        ядро, иначе его можно обойти со стороны интерфейса (4.0-B08).
        """
        return self._features

    def set_host(self, host):
        """host выполняет действия над окном (свернуть/показать/выйти)."""
        self._host = host
        self._tools._ctx.host = host
        self._executor._host = host

    # ------------------------------------------------------------------
    # озвучка
    # ------------------------------------------------------------------
    def say(self, text, sound="response"):
        """Ответить: записать в историю, сообщить оболочке и произнести."""
        from voice import sounds

        if sound == "response":
            sounds.play_response(self._settings)
        elif sound == "error":
            sounds.play_error(self._settings)

        self._history.add("assistant", text)
        self._emit(Events.HISTORY_CHANGED)
        self._emit(Events.RESPONSE, text=text)
        threading.Thread(target=self._speak_blocking, args=(text,),
                         daemon=True).start()

    def _speak_blocking(self, text):
        if not self._settings.get("voice_reply", True):
            return  # режим «молчать» — только текст, без голоса
        engine = tts_mod.get_engine(self._settings.get("tts_engine", "silent"))
        self._begin_speaking()
        try:
            engine.speak(
                text,
                voice=self._settings.get("voice"),
                volume=int(self._settings.get("volume", 75)),
                rate=int(self._settings.get("speed", 100)),
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

        sounds.play_activation(self._settings)
        self._emit(Events.LISTENING_STARTED)
        result = None
        try:
            engine = stt_mod.get_engine(self._settings.get("stt_engine", "disabled"))
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
        engine = stt_mod.get_engine(self._settings.get("stt_engine", "disabled"))
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
        """
        Планировщик: раз в секунду смотрит, не пора ли.

        **Каждое срабатывание открывает свою цепочку трассировки** (4.0-D15).
        Напоминание никем не вызвано — оно само и есть начало действия, и
        всё, что за ним последует (событие оболочке, произнесённая фраза,
        записи в журнале), принадлежит одной цепочке. Без этого сработавший
        будильник выглядел бы в журнале набором несвязанных строк, а
        разобрать «почему она заговорила ночью» было бы нечем.
        """
        store = self._reminders
        while not self._stop_reminders.wait(1.0):
            try:
                for item in store.due():
                    with trace_scope():
                        store.mark_done(item["id"])
                        # Снимок из due() сделан до пометки и всё ещё говорит
                        # done: false. Отправить его как есть значит сообщить
                        # оболочке о срабатывании напоминания, которое по
                        # собственным словам не сработало: событие
                        # противоречило бы хранилищу, откуда оболочка возьмёт
                        # список секундой позже.
                        self._emit(Events.REMINDER_FIRED,
                                   item={**item, "done": True})
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

        wake_words = get_wake_words(self._settings)
        if not wake_words:
            return text.strip()
        return strip_wake(text, wake_words)

    # ------------------------------------------------------------------
    # уточняющие вопросы и исполнение
    # ------------------------------------------------------------------
    # Решает, что значит фраза, — роутер (core/router.py).
    # Помнит незакрытый вопрос — диалог (core/dialog.py).
    # Делает — исполнитель (core/executor.py).
    # Ядру остаётся связать их и вести историю.

    def _router_context(self, source, require_wake):
        """Всё, что роутер должен знать о мире, — снимок на этот момент."""
        from voice import app_index, app_launcher
        from core import llm

        question = self._dialog.current()
        return router_mod.RouterContext(
            apps=app_index.cached_index() or [],
            aliases=dict(self._settings.get("app_aliases", {}) or {}),
            pending=question.to_dict() if question else None,
            wake_words=tuple(get_wake_words(self._settings)),
            require_wake=require_wake,
            source=source,
            reminders_active=len(self._reminders.active()),
            llm_enabled=llm.is_enabled(),
            web_fallback=bool(self._settings.get("web_search_fallback", True)),
        )

    def _remember_choice(self, query, entry):
        from voice import app_launcher

        app_launcher.remember(query, entry.launch, entry.kind, entry.name)

    def _ask(self, question):
        """Задать вопрос и озвучить его."""
        self._dialog.ask(question)


    def _run_user_command(self, user_cmd):
        """Выполнить пользовательскую команду — через исполнителя."""
        return self._executor.run_user_command(user_cmd)


    def run_command_by_id(self, command_id):
        """
        Выполнить команду по её id (кнопка «Выполнить» в списке).

        Тоже в фоне: последовательность с паузами выполняется секундами,
        а нажимают кнопку из потока интерфейса.
        """
        for cmd in self._cmd_store.all():
            if cmd.get("id") == command_id:
                self._ensure_command_worker()
                ctx = contextvars.copy_context()
                threading.Thread(
                    target=ctx.run, args=(self._run_user_command, cmd),
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
            text, require_wake, source, done, ctx = self._commands.get()
            try:
                ctx.run(self.handle_command, text,
                        require_wake=require_wake, source=source)
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
        # Вместе с командой в очередь кладётся контекст выполнения. В нём
        # едет сквозная трассировка (4.0-D15): рабочий поток долгоживущий и
        # обслуживает много команд подряд, поэтому связать его с одной из них
        # нельзя — контекст принадлежит команде, а не потоку.
        #
        # Первый прогон двух процессов показал это прямо: ответ Рины приходил
        # с трассировкой, не совпадающей с трассировкой запроса, и связать
        # запрос с ответом в двух журналах было нечем.
        self._commands.put((text, require_wake, source, done,
                            contextvars.copy_context()))
        if wait:
            done.wait()
        return done

    # ------------------------------------------------------------------
    # конвейер команд
    # ------------------------------------------------------------------
    def handle_command(self, text, require_wake=False, source="typed"):
        ctx = self._router_context(source, require_wake)
        intent = router_mod.route(text, ctx)

        # Индекс программ мог быть ещё не построен: в 3.1.0 его строила первая
        # же команда запуска. Повторяем разбор ровно один раз и только когда
        # индекс пуст — иначе первое «громче» ждало бы обхода диска.
        if intent.name == "app.not_found" and not ctx.apps:
            from voice import app_index

            ctx.apps = app_index.get_index() or []
            if ctx.apps:
                intent = router_mod.route(text, ctx)

        if intent.name == "silence":
            return

        if intent.name == "ask.wake":
            self._history.add("user", "Рина", source=source)
            self._emit(Events.HISTORY_CHANGED)
            self._executor.execute(intent, source)
            return

        command = intent.text
        log.info("Команда (%s): %s", source, safe(command))
        self._history.add("user", command, source=source)
        self._emit(Events.HISTORY_CHANGED)

        # Фраза была ответом на заданный вопрос — роутер это уже понял.
        if intent.stage == "pending":
            self._dialog.answered()
            if intent.name == "cancelled":
                security_log().info(
                    "Опасное действие отменено пользователем: %s",
                    intent.arg("action") or "пользовательская команда")
            self._executor.execute(intent, source)
            return

        # Не ответ — вопрос снимается. Так ведёт себя 3.1.0: любая
        # нераспознанная реплика забывает заданный вопрос (инвентарь, §6).
        self._dialog.dropped()

        # Плагины и пользовательские команды роутер пока не разбирает:
        # плагин — чужой код, и «взял бы он фразу» узнаётся только запуском.
        if self._dispatch_plugin(command):
            return
        if self._dispatch_user_command(command):
            return

        # Языковая модель — единственное, что ядро делает само: ответ идёт
        # секундами, и ждать его в этом потоке нельзя.
        if intent.name == "llm.answer":
            self._ask_llm_async(command, source)
            return

        # Намерение, после которого ждём ответа, сначала исполняется
        # (вопрос надо озвучить), а затем становится заданным вопросом.
        # Порядок важен: подтверждение выдаётся при исполнении, и его
        # идентификатор нужно положить в вопрос.
        result = self._executor.execute(intent, source)

        if intent.needs_answer:
            self._dialog.ask(self._question_for(intent, result))

    @staticmethod
    def _question_for(intent, result=None):
        """
        Намерение, ждущее ответа, -> заданный вопрос.

        Для опасного действия в вопрос кладётся выданное подтверждение:
        согласие человека относится к конкретному вызову, а не к тому, что
        вопрос когда-то задавали (4.0-C05).
        """
        confirmation_id = ""
        if result is not None:
            confirmation_id = str(result.data.get("confirmation_id", ""))

        if intent.name == "app.ambiguous":
            return Question(kind=dialog_mod.CHOOSE_APP,
                            options=tuple(intent.arg("options") or ()),
                            query=intent.arg("query") or "")
        if intent.name == "system.confirm":
            return Question.confirm_action(intent.arg("action"),
                                           confirmation_id)
        return Question.confirm_command(intent.arg("command_id") or "",
                                        confirmation_id)

    def _dispatch_plugin(self, command):
        if self._plugins is None:
            return False
        try:
            if self._plugins.dispatch_command(command):
                log.debug("Команду обработал плагин")
                return True
        except Exception:
            # плагин — чужой код; его сбой не должен рвать конвейер,
            # но и пропадать бесследно тоже не должен
            log.exception("Сбой плагина при разборе команды")
        return False

    def _dispatch_user_command(self, command):
        from voice.user_commands import matches, command_needs_confirm

        try:
            for user_cmd in self._cmd_store.all():
                if not matches(user_cmd, command):
                    continue
                if command_needs_confirm(user_cmd):
                    self._ask(Question.confirm_command(user_cmd.get("id")))
                    self.say(tr("Команда «{name}» выключит или перезагрузит "
                                "компьютер. Точно выполнить?",
                                name=(user_cmd.get("triggers") or ["?"])[0]))
                else:
                    self._executor.run_user_command(user_cmd)
                return True
        except Exception:
            log.exception("Сбой при разборе пользовательских команд")
        return False


    def _ask_llm_async(self, command, source):
        """
        Спрашивает модель в фоне и отвечает, когда та ответит.

        Через реестр, а не напрямую: обращение к модели — сетевой вызов с
        разрешением `network.local`, и он обязан попадать в журнал вызовов
        наравне с остальными (4.0-C06, C07).
        """
        def worker():
            self._emit(Events.THINKING, active=True)
            try:
                result = self._tools.call(
                    "ask_model",
                    {"question": command, "context": self._history.all()},
                    source=source)
            finally:
                self._emit(Events.THINKING, active=False)

            if result.ok and result.message:
                self.say(result.message)
                return
            # модель не ответила — ведём себя как без неё
            self._fallback_reply(command, source)

        threading.Thread(target=worker, daemon=True).start()

    def _fallback_reply(self, command, source):
        """
        Запасной вариант — поиск в интернете.

        В режиме «всегда слушать» не ищем: туда попадают шум и случайная
        речь, открывать по ним браузер нельзя.
        """
        allowed = (self._settings.get("web_search_fallback", True)
                   and source != "always")
        if allowed:
            result = self._tools.call("web_search", {"query": command},
                                      source=source)
            if result.ok:
                # Формулировка отличается от явного поиска: человек не
                # просил искать, и об этом честнее сказать.
                self.say(tr("Не нашла такой команды — поищу «{query}» "
                            "в интернете.", query=command))
                return

        self.say(tr("Извини, я не поняла команду."), sound="error")

    # ------------------------------------------------------------------
    # настройки, зависящие от языка и микрофона
    # ------------------------------------------------------------------
    def listen_seconds(self):
        try:
            value = int(self._settings.get("listen_seconds", 8))
        except (TypeError, ValueError):
            return 8
        return max(3, min(20, value))

    def lang_code(self):
        """Язык распознавания = язык интерфейса (единая настройка)."""
        lang_map = {"Русский": "ru", "English": "en", "Українська": "uk",
                    "Español": "es", "Deutsch": "de"}
        return lang_map.get(self._settings.get("ui_language", "Русский"), "ru")

    def shutdown(self):
        self._stop_always.set()
        self._stop_reminders.set()
