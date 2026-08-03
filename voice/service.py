"""
Голосовой сервис: связывает микрофон (STT), обработку команд и озвучку (TTS).

Всё, что блокирует (прослушивание микрофона, синтез речи), выполняется в
фоновом потоке. С GUI общаемся ТОЛЬКО через сигналы Qt (они потокобезопасны):

    listening_started   — начали слушать (показать окно «Слушаю…»)
    listening_stopped   — закончили слушать
    recognized(text)    — распознали фразу пользователя
    responded(text)     — ассистент отвечает (показать toast + озвучить)
    error(text)         — что-то пошло не так
    always_listen_changed(bool) — режим постоянного прослушивания

Команды сначала уходят в плагины (plugin_manager.dispatch_command). Если ни
один плагин не обработал — пробуем встроенные команды (voice/commands.py).
"""

import threading
import time

from PySide6.QtCore import QObject, Signal

from core.settings_store import settings
from core.i18n import t as tr
from voice import tts as tts_mod
from voice import stt as stt_mod
from voice.commands import handle_builtin_command
from voice.user_commands import UserCommandStore, dispatch_user_command
from voice.history import HistoryStore


class VoiceService(QObject):
    listening_started = Signal()
    listening_stopped = Signal()
    recognized = Signal(str)
    responded = Signal(str)
    error = Signal(str)
    always_listen_changed = Signal(bool)
    always_capturing = Signal(bool)   # захват в режиме «всегда слушать» (для мик-виджета)

    def __init__(self, plugin_manager=None, parent=None):
        super().__init__(parent)
        self._plugins = plugin_manager
        self._busy = False
        self._always_listen = False
        self._always_thread = None
        self._stop_always = threading.Event()
        self._cmd_store = UserCommandStore(settings)
        self._history = HistoryStore(settings)
        self._host = None  # объект для системных действий (ставит окно)
        self._speaking = threading.Event()  # Рина сейчас озвучивает ответ
        # незакрытый уточняющий вопрос: {"kind", "options", "ts"}
        self._pending = None

    def set_host(self, host):
        """host предоставляет action_minimize/show/quit/mute/unmute для команд."""
        self._host = host

    # ---------- озвучка ----------
    def say(self, text, sound="response"):
        """Показать ответ (toast) и озвучить его в фоне."""
        from voice import sounds
        if sound == "response":
            sounds.play_response(settings)
        elif sound == "error":
            sounds.play_error(settings)
        self._history.add("assistant", text)
        self._emit_history_changed()
        self.responded.emit(text)
        threading.Thread(target=self._speak_blocking, args=(text,),
                         daemon=True).start()

    def _emit_history_changed(self):
        try:
            from core.app_signals import app_signals
            app_signals.history_changed.emit()
        except Exception:
            pass

    def _speak_blocking(self, text):
        if not settings.get("voice_reply", True):
            return  # режим «молчать» — только toast, без голоса
        engine = tts_mod.get_engine(settings.get("tts_engine", "silent"))
        self._speaking.set()
        try:
            engine.speak(
                text,
                voice=settings.get("voice"),
                volume=int(settings.get("volume", 75)),
                rate=int(settings.get("speed", 100)),
            )
        except Exception as e:
            self.error.emit(f"Ошибка озвучки: {e}")
        finally:
            # небольшая пауза после речи, чтобы «хвост»/эхо не попал в микрофон
            import time
            time.sleep(0.4)
            self._speaking.clear()

    def _wait_while_speaking(self):
        """Блокирует, пока Рина говорит (для режима «всегда слушать»)."""
        while self._speaking.is_set() and not self._stop_always.is_set():
            import time
            time.sleep(0.1)

    # ---------- разовое прослушивание (по хоткею) ----------
    def listen_once(self):
        """Однократно слушает микрофон (вызывается по горячей клавише)."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._listen_worker, daemon=True).start()

    def _listen_worker(self):
        from voice import sounds
        sounds.play_activation(settings)
        self.listening_started.emit()
        try:
            engine = stt_mod.get_engine(settings.get("stt_engine", "disabled"))
            # даём короткую паузу, чтобы пользователь успел начать говорить,
            # и увеличенный лимит фразы
            result = engine.listen_once(
                language=self._lang_code(),
                timeout=8,
            )
        finally:
            self.listening_stopped.emit()
            self._busy = False

        if result.ok and result.text:
            self.recognized.emit(result.text)
            # по хоткею слово активации НЕ обязательно: пользователь уже явно
            # активировал ассистента нажатием клавиши
            self.process_command(result.text, require_wake=False, source="voice")
        elif result.error:
            # движки распознавания отдают текст ошибки по-русски — переводим
            # здесь, на границе с интерфейсом, а не в каждом движке
            self.error.emit(tr(result.error))

    # ---------- режим «всегда слушать» ----------
    def set_always_listen(self, on):
        on = bool(on)
        if on == self._always_listen:
            return
        self._always_listen = on
        self.always_listen_changed.emit(on)
        if on:
            self._stop_always.clear()
            self._always_thread = threading.Thread(
                target=self._always_worker, daemon=True)
            self._always_thread.start()
        else:
            self._stop_always.set()

    def is_always_listen(self):
        return self._always_listen

    def _always_worker(self):
        engine = stt_mod.get_engine(settings.get("stt_engine", "disabled"))
        # если распознавание выключено — не крутим бесполезный цикл
        if engine.id == "disabled":
            self.error.emit(
                tr("Режим «всегда слушать» требует выбранного движка распознавания."))
            self._always_listen = False
            self.always_listen_changed.emit(False)
            return
        while not self._stop_always.is_set():
            # пока Рина говорит — не слушаем (иначе микрофон ловит её же голос
            # и распознавание зацикливается на собственных ответах)
            if self._speaking.is_set():
                self._wait_while_speaking()
                continue

            # НЕ показываем окно «Слушаю…» в режиме «всегда слушать» —
            # индикатором служит мини-виджет микрофона. Шлём отдельный
            # сигнал, чтобы виджет мог пульсировать во время захвата.
            self.always_capturing.emit(True)
            try:
                result = engine.listen_once(language=self._lang_code(), timeout=5)
            except Exception:
                result = stt_mod.STTResult(error="listen error")
            self.always_capturing.emit(False)

            if self._stop_always.is_set():
                break
            if result.ok and result.text:
                # в режиме «всегда слушать» слово активации ОБЯЗАТЕЛЬНО:
                # без него фраза просто игнорируется (никаких ответов).
                # source="always" — чтобы не отвечать на «голое» слово активации.
                self.process_command(result.text, require_wake=True, source="always")
                # ждём, пока ответ договорится, прежде чем слушать снова
                self._wait_while_speaking()

    # ---------- слово активации ----------
    def _extract_command(self, text, require_wake):
        """
        Возвращает текст команды.
        require_wake=True: нужно слово активации (из списка синонимов, нечётко);
        иначе -> None (команда игнорируется). Слово вырезается.
        require_wake=False: возвращаем текст как есть.
        """
        if not require_wake:
            return text.strip()

        from voice.wake import get_wake_words, strip_wake
        wake_words = get_wake_words(settings)
        if not wake_words:
            return text.strip()

        return strip_wake(text, wake_words)  # None если активации нет

    # ---------- уточняющие вопросы ----------
    PENDING_TTL = 60      # через минуту вопрос считается неактуальным

    def _resolve_pending(self, command):
        """
        Пытается понять фразу как ответ на заданный ранее вопрос.
        True — фраза обработана как ответ, дальше по конвейеру не идём.
        """
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
        entry, cancelled = app_launcher.choose(command, pending["options"])

        if cancelled:
            self._pending = None
            self.say(tr("Хорошо, отменяю."))
            return True
        if entry is None:
            # не похоже на ответ — считаем это новой командой
            return False

        query = pending.get("query")
        self._pending = None
        if app_index.launch(entry):
            # запоминаем выбор: в следующий раз «обс» сразу запустит то же самое
            if query:
                app_launcher.remember(query, entry.launch, entry.kind, entry.name)
            self.say(tr("Запускаю {app}.", app=entry.name))
        else:
            self.say(tr("Не получилось запустить {app}.", app=entry.name),
                     sound="error")
        return True

    # согласие/отказ на опасное действие. Требуем явного «да» — молчаливое
    # непонимание не должно выключать компьютер.
    YES_WORDS = ("да", "давай", "подтверждаю", "точно", "выключай",
                 "перезагружай", "усыпляй", "ага", "yes", "confirm")
    NO_WORDS = ("нет", "отмена", "отмени", "не надо", "стоп", "no", "cancel")

    def _run_user_command(self, user_cmd):
        """
        Выполняет пользовательскую команду.

        Последовательности уходят в фоновый поток: между шагами может стоять
        пауза, а блокировать поток интерфейса (команда из строки ввода)
        нельзя — окно бы «зависало» на всё время выполнения.
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

    def _resolve_confirm(self, command, pending):
        from voice import system_control
        from voice.textmatch import normalize

        low = normalize(command)
        words = low.split()

        if any(w in words for w in self.NO_WORDS):
            self._pending = None
            self.say(tr("Хорошо, отменяю."))
            return True
        if any(w in words for w in self.YES_WORDS):
            self._pending = None
            # подтверждали либо одиночное действие, либо команду целиком
            if pending.get("command") is not None:
                self._run_user_command(pending["command"])
            else:
                self.say(system_control.run(pending.get("action")))
            return True
        # ответ не похож ни на согласие, ни на отказ — на всякий случай
        # считаем это новой командой, действие не выполняем
        return False

    # ---------- обработка команды ----------
    def process_command(self, text, require_wake=False, source="typed"):
        if not text:
            return

        command = self._extract_command(text, require_wake)
        if command is None:
            # слово активации не прозвучало — тихо игнорируем, без ответов
            return
        if not command:
            # активация прозвучала, но команды после неё нет.
            # В режиме «всегда слушать» НЕ отвечаем «Да? Слушаю» — иначе Рина
            # услышит собственный ответ и уйдёт в повторение. Отвечаем только
            # при явной активации (хоткей/разовое прослушивание).
            if source != "always":
                self._history.add("user", "Рина", source=source)
                self._emit_history_changed()
                self.say(tr("Да? Слушаю."))
            return
        # записываем в историю то, что пользователь сказал/ввёл
        self._history.add("user", command, source=source)
        self._emit_history_changed()

        # 0) ответ на заданный ранее уточняющий вопрос («второй», «obs studio»)
        if self._resolve_pending(command):
            return
        # фраза оказалась новой командой, а не ответом — старый вопрос снимаем,
        # иначе следующее «второй» ответило бы на давно неактуальный вопрос
        self._pending = None

        # 1) плагины
        if self._plugins is not None:
            try:
                if self._plugins.dispatch_command(command):
                    return
            except Exception:
                pass
        # 2) пользовательские команды (из конструктора)
        try:
            from voice.user_commands import matches, command_needs_confirm
            for user_cmd in self._cmd_store.all():
                if not matches(user_cmd, command):
                    continue
                if command_needs_confirm(user_cmd):
                    # в команде есть выключение/перезагрузка/сон — переспрашиваем
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
            pass
        # 3) управление системой и медиа (громче, пауза, скриншот, выключение)
        from voice import system_control
        action_id, needs_confirm = system_control.match_action(command)
        if action_id:
            if needs_confirm:
                # выключение/перезагрузка/сон по одной распознанной фразе —
                # слишком дорогая ошибка, обязательно переспрашиваем
                self._pending = {
                    "kind": "confirm_action",
                    "action": action_id,
                    "ts": time.time(),
                }
                self.say(system_control.confirm_question(action_id))
            else:
                self.say(system_control.run(action_id))
            return

        # 4) запуск программ по индексу установленного ПО
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
            # программу не нашли — предлагаем показать файл, чтобы запомнить
            if outcome.status == "not_found" and outcome.query:
                from core.app_signals import app_signals
                app_signals.app_not_found.emit(outcome.query)
            return

        # 4) встроенные команды
        response = handle_builtin_command(command)
        if response:
            self.say(response)
            return

        # 4) запасной вариант — поиск в интернете.
        # В режиме «всегда слушать» НЕ ищем: туда попадает случайная речь и
        # шум, и открывать браузер по ним нельзя. Только явная активация.
        if (settings.get("web_search_fallback", True)
                and source != "always"):
            from voice import websearch
            found = websearch.fallback_search(
                command, settings.get("search_engine", websearch.DEFAULT_ENGINE))
            if found:
                self.say(found)
                return

        self.say(tr("Извини, я не поняла команду."), sound="error")

    def run_command_by_id(self, command_id):
        """Выполнить конкретную пользовательскую команду (кнопка «Выполнить»)."""
        for cmd in self._cmd_store.all():
            if cmd.get("id") == command_id:
                from voice.user_commands import execute
                self._cmd_store.bump_stat(command_id)
                ok, resp = execute(cmd, self._host)
                self.say(resp)
                return

    def _lang_code(self):
        # язык распознавания = язык интерфейса (единая настройка)
        lang_map = {"Русский": "ru", "English": "en", "Українська": "uk",
                    "Español": "es", "Deutsch": "de"}
        return lang_map.get(settings.get("ui_language", "Русский"), "ru")

    def shutdown(self):
        self._stop_always.set()
