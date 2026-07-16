from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QStackedWidget, QFrame, QButtonGroup,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QBrush, QPen, QShortcut,
    QKeySequence, QLinearGradient,
)

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius, PAGE_ICONS, theme_manager
from core.assets import app_icon, logo_pixmap
from components.titlebar import TitleBar
from components.nav_button import NavButton
from components.status_dot import StatusDot
from pages.pages import build_page
from animations.effects import fade_window_in, page_transition
from core.settings_store import settings
from app.tray import SystemTray
from core.app_signals import app_signals
from core.hotkey import HotkeyManager
from voice.service import VoiceService
from voice.overlays import ListeningOverlay, Toast, MicWidget


PAGES = [
    "Рина", "Команды", "Горячие клавиши", "История",
    "Настройки", "О программе", "Плагины",
]


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rina Assistant")
        self.setWindowIcon(app_icon())
        self.resize(1120, 720)
        self.setMinimumSize(940, 620)

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._current_index = 0
        self._force_quit = False
        self.create_ui()
        self.setWindowOpacity(0)

        # системный трей
        self.tray = SystemTray(self)
        self.tray.show_requested.connect(self.show_from_tray)
        self.tray.quit_requested.connect(self.quit_app)
        if settings.get("minimize_to_tray"):
            self.tray.show()

        # перекраска при смене темы
        theme_manager.changed.connect(self.apply_theme)

        # реакция на изменение настройки трея
        app_signals.tray_pref_changed.connect(self._sync_tray)

        # глобальный хоткей
        self.hotkey = HotkeyManager(self)
        self.hotkey.activated.connect(self._on_hotkey)
        self.hotkey.action_activated.connect(self._on_action_hotkey)
        self._qt_shortcut = None
        self._setup_hotkey()
        app_signals.hotkey_changed.connect(self._setup_hotkey)
        app_signals.language_changed.connect(self._on_language_changed)

        # голосовой слой
        self._setup_voice()

    def _setup_voice(self):
        from plugins.manager import plugin_manager
        self.voice = VoiceService(plugin_manager=plugin_manager, parent=self)
        self.voice.set_host(self)  # для системных команд (свернуть/выход/…)

        # окна голосового интерфейса
        self.listening_overlay = ListeningOverlay()
        self.toast = Toast()
        self.mic_widget = MicWidget()
        self.mic_widget.clicked.connect(self._toggle_always_listen)

        # плавающая командная строка (поверх окон при сворачивании)
        from voice.floating_bar import FloatingCommandBar
        self.floating_bar = FloatingCommandBar()
        self.floating_bar.submitted.connect(
            lambda t: self.voice.process_command(t, source="typed"))
        self.floating_bar.mic_requested.connect(self.voice.listen_once)
        self.floating_bar.closed.connect(self._on_floating_closed)

        # связываем сигналы сервиса с UI (всё приходит в GUI-поток)
        self.voice.listening_started.connect(self.listening_overlay.show_overlay)
        self.voice.listening_stopped.connect(self.listening_overlay.hide_overlay)
        self.voice.always_capturing.connect(self.mic_widget.set_active)
        self.voice.responded.connect(self._on_assistant_response)
        self.voice.recognized.connect(self._on_recognized)
        self.voice.error.connect(self._on_voice_error)

        # режим «всегда слушать» из настроек
        if settings.get("always_listen"):
            self._set_always_listen(True)

        # реагируем на изменение тумблера «всегда слушать» в настройках Рины
        app_signals.always_listen_changed.connect(self._set_always_listen)

        # выполнение пользовательской команды по кнопке «Выполнить»
        app_signals.run_command.connect(self.voice.run_command_by_id)

        # плагины: вкладки, окна, уведомления, голос
        plugin_manager.pages_changed.connect(self.on_plugin_pages_changed)
        plugin_manager.window_requested.connect(self._open_plugin_window)
        plugin_manager.notify_requested.connect(self._plugin_notify)
        plugin_manager.response.connect(self._on_plugin_response)
        self._plugin_windows = []

    def _on_plugin_response(self, pid, text):
        # плагин что-то ответил -> тот же путь, что и у ассистента (toast + голос)
        self.voice.say(text)

    def _open_plugin_window(self, pid, widget, title, w, h):
        from voice.overlays import Toast  # переиспользуем стиль окна не нужен
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        from PySide6.QtCore import Qt as _Qt
        win = QWidget()
        win.setWindowTitle(title)
        win.setMinimumSize(w, h)
        lay = QVBoxLayout(win)
        lay.setContentsMargins(0, 0, 0, 0)
        if widget is not None:
            lay.addWidget(widget)
        win.setStyleSheet(f"background: {Color.BASE};")
        win.show()
        self._plugin_windows.append(win)  # держим ссылку

    def _plugin_notify(self, pid, title, message):
        if settings.get("notifications", True) and hasattr(self, "tray"):
            self.tray.notify(title, message)

    def _on_assistant_response(self, text):
        # ответ ассистента: toast + (озвучка идёт в сервисе)
        self.toast.show_toast(text)

    def _on_recognized(self, text):
        # можно показывать распознанную фразу; пока просто заголовок overlay
        pass

    def _on_typed_command(self, text):
        # команда, введённая текстом: гоним через тот же конвейер, что и голос
        self.voice.process_command(text, source="typed")

    def _on_voice_error(self, text):
        self.toast.show_toast(text, duration=2600)

    def _toggle_always_listen(self):
        new_state = not self.voice.is_always_listen()
        settings.set("always_listen", new_state)
        settings.save()
        self._set_always_listen(new_state)

    def _set_always_listen(self, on):
        self.voice.set_always_listen(on)
        if on:
            self.mic_widget.show_widget()
        else:
            self.mic_widget.hide()

    # ---------- системные действия для голосовых команд ----------
    def action_minimize(self):
        if settings.get("minimize_to_tray"):
            self.hide()
            self.tray.show()
        else:
            self.showMinimized()
        self._maybe_show_floating()

    def action_show(self):
        self.show_from_tray()

    def action_quit(self):
        self.quit_app()

    # ---------- плавающая командная строка ----------
    def _maybe_show_floating(self):
        """Показать плавающую строку, если включена настройка."""
        if settings.get("floating_command_bar") and hasattr(self, "floating_bar"):
            self.floating_bar.show_bar()

    def _hide_floating(self):
        if hasattr(self, "floating_bar"):
            self.floating_bar.hide_bar()

    def _on_floating_closed(self):
        # пользователь закрыл строку крестиком — просто прячем на эту сессию
        pass

    def toggle_floating_bar(self):
        """Показать/скрыть плавающую строку вручную (напр. по хоткею)."""
        if not hasattr(self, "floating_bar"):
            return
        if self.floating_bar.isVisible():
            self.floating_bar.hide_bar()
        else:
            self.floating_bar.show_bar()

    def action_mute(self):
        settings.set("voice_reply", False)
        settings.save()

    def action_unmute(self):
        settings.set("voice_reply", True)
        settings.save()

    def _setup_hotkey(self):
        """Регистрирует глобальный хоткей + запасной QShortcut (при фокусе)."""
        seq = settings.get("hotkey")

        # 1) глобальный (через pynput) — работает даже из трея
        ok = self.hotkey.register(seq, settings.get("action_hotkeys", {}) or {})

        # 2) запасной QShortcut — срабатывает, когда окно в фокусе.
        #    Полезен и как fallback без pynput, и просто для скорости.
        if self._qt_shortcut is not None:
            self._qt_shortcut.setEnabled(False)
            self._qt_shortcut.deleteLater()
            self._qt_shortcut = None
        try:
            ks = QKeySequence(seq)
            if not ks.isEmpty():
                self._qt_shortcut = QShortcut(ks, self)
                self._qt_shortcut.activated.connect(self._on_hotkey)
        except Exception:
            pass

        # уведомим настройки, доступен ли глобальный режим
        app_signals.hotkey_status.emit(self.hotkey.available and ok)

    def _on_hotkey(self):
        # горячая клавиша запускает разовое прослушивание микрофона.
        # Окно «Слушаю…» покажется через сигнал listening_started.
        self.voice.listen_once()

    def _on_action_hotkey(self, action_id):
        # доп. действия по назначенным клавишам
        if action_id == "listen":
            self.voice.listen_once()
        elif action_id == "toggle_always":
            self._toggle_always_listen()
        elif action_id == "show_hide":
            if self.isVisible() and not self.isMinimized():
                self.action_minimize()
            else:
                self.show_from_tray()
        elif action_id == "mute":
            cur = settings.get("voice_reply", True)
            settings.set("voice_reply", not cur)
            settings.save()
            self.toast.show_toast(
                tr("Озвучка выключена") if cur else tr("Озвучка включена"), 1800)
        elif action_id == "focus_command":
            self.show_from_tray()
            if hasattr(self, "command_bar"):
                self.command_bar.input.setFocus()
        elif action_id == "floating_bar":
            self.toggle_floating_bar()

    def _sync_tray(self):
        if settings.get("minimize_to_tray"):
            self.tray.show()
        else:
            self.tray.hide()

    # ---------- фон окна ----------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        rect = self.rect().adjusted(0, 0, -1, -1)
        path.addRoundedRect(rect, Radius.LG, Radius.LG)
        painter.fillPath(path, QBrush(QColor(Color.BASE)))

        # неоновая окантовка окна: акцент→розовый→синий по диагонали
        edge = QLinearGradient(rect.left(), rect.top(),
                               rect.right(), rect.bottom())
        c1 = QColor(Color.ACCENT);  c1.setAlphaF(0.55)
        c2 = QColor(Color.ACCENT2); c2.setAlphaF(0.30)
        c3 = QColor(Color.ACCENT3); c3.setAlphaF(0.55)
        edge.setColorAt(0.0, c1)
        edge.setColorAt(0.5, c2)
        edge.setColorAt(1.0, c3)
        pen = QPen(QBrush(edge), 1.4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()

    # ---------- построение UI ----------
    def create_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.titlebar = TitleBar(self)
        main_layout.addWidget(self.titlebar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())
        body_layout.addWidget(self._build_content(), 1)

        main_layout.addWidget(body, 1)

        # строка ввода команд (командная строка ассистента)
        from components.command_bar import CommandBar
        self.command_bar = CommandBar()
        self.command_bar.submitted.connect(self._on_typed_command)
        main_layout.addWidget(self.command_bar)

        self.buttons[0].setChecked(True)

        self.titlebar.close_clicked.connect(self.close)
        self.titlebar.minimize_clicked.connect(self.showMinimized)
        self.titlebar.maximize_clicked.connect(self.toggle_maximize)

    def _build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(238)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(16, 16, 16, 18)
        layout.setSpacing(4)

        # ---- брендовый блок: эмблема + градиентный вордмарк ----
        from components.gradient_text import GradientText
        brand = QHBoxLayout()
        brand.setContentsMargins(4, 0, 0, 0)
        brand.setSpacing(12)

        self.logo_img = QLabel()
        self.logo_img.setPixmap(logo_pixmap(40))
        self.logo_img.setFixedSize(40, 40)
        self.logo_img.setAlignment(Qt.AlignCenter)
        brand.addWidget(self.logo_img)

        wordmark = QVBoxLayout()
        wordmark.setSpacing(0)
        self.logo = GradientText("RINA", size=19, letter_spacing=2.0)
        self.logo_sub = QLabel("ASSISTANT")
        wordmark.addWidget(self.logo)
        wordmark.addWidget(self.logo_sub)
        brand.addLayout(wordmark)
        brand.addStretch()

        layout.addLayout(brand)
        layout.addSpacing(24)

        # контейнер для кнопок навигации (пересобирается)
        self._nav_layout = QVBoxLayout()
        self._nav_layout.setSpacing(4)
        layout.addLayout(self._nav_layout)

        layout.addStretch()

        self.status_frame = QFrame()
        sl = QHBoxLayout(self.status_frame)
        sl.setContentsMargins(12, 8, 14, 8)
        sl.setSpacing(6)
        self.status_dot = StatusDot("GREEN", diameter=9)
        self.status_txt = QLabel("Rina Online")
        sl.addWidget(self.status_dot)
        sl.addWidget(self.status_txt)
        sl.addStretch()
        layout.addWidget(self.status_frame)

        self.buttons = []
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.button_group.idClicked.connect(self.switch_page)

        self._rebuild_nav_buttons()
        self._style_sidebar()
        return self.sidebar

    def _current_page_names(self):
        """Итоговый список вкладок: статические + вкладки включённых плагинов."""
        names = list(PAGES)
        try:
            from plugins.manager import plugin_manager
            self._plugin_page_ids = []
            for pid, lp in plugin_manager.page_plugins():
                title, _ = plugin_manager.plugin_page_meta(pid)
                names.append(("plugin", pid, title))
                self._plugin_page_ids.append(pid)
        except Exception:
            self._plugin_page_ids = []
        return names

    def _rebuild_nav_buttons(self):
        # очистить старые кнопки
        for btn in getattr(self, "buttons", []):
            self.button_group.removeButton(btn)
            btn.setParent(None)
            btn.deleteLater()
        self.buttons = []

        self._page_specs = self._current_page_names()
        for i, spec in enumerate(self._page_specs):
            if isinstance(spec, tuple):  # плагинная вкладка
                _, pid, title = spec
                from plugins.manager import plugin_manager
                _, icon = plugin_manager.plugin_page_meta(pid)
                btn = NavButton(title, icon)
            else:
                btn = NavButton(tr(spec), PAGE_ICONS.get(spec, "•"))
            self.buttons.append(btn)
            self.button_group.addButton(btn, i)
            self._nav_layout.addWidget(btn)

    def _style_sidebar(self):
        self.sidebar.setStyleSheet(f"""
            QFrame#sidebar {{
                background: {Color.MANTLE};
                border-top-left-radius: {Radius.LG}px;
                border-bottom-left-radius: {Radius.LG}px;
                border-right: 1px solid {Color.SURFACE_0};
            }}
        """)
        self.logo.update()
        self.logo_sub.setStyleSheet(
            f"color: {Color.OVERLAY}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 3px;")
        self.status_frame.setStyleSheet(f"""
            QFrame {{
                background: {Color.CRUST};
                border: 1px solid {Color.SURFACE_0};
                border-radius: {Radius.MD}px;
            }}
        """)
        self.status_txt.setStyleSheet(
            f"color: {Color.SUBTEXT}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;")

    def _build_content(self):
        self.content_wrap = QFrame()
        self.content_wrap.setObjectName("content_wrap")
        wl = QVBoxLayout(self.content_wrap)
        wl.setContentsMargins(0, 0, 0, 0)

        self.content = QStackedWidget()
        wl.addWidget(self.content)
        self._rebuild_content()
        self._style_content()
        return self.content_wrap

    def _build_one_page(self, spec):
        """Строит виджет страницы по спецификации (имя или ('plugin', pid, title))."""
        if isinstance(spec, tuple):
            _, pid, _ = spec
            return self._build_plugin_page_widget(pid)
        return build_page(spec)

    def _build_plugin_page_widget(self, pid):
        """
        Собирает вкладку плагина: если плагин отдал create_page — используем её;
        плюс, если есть settings_schema — добавляем автопанель настроек сверху.
        Всё оборачиваем в скролл.
        """
        from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QLabel
        from plugins.manager import plugin_manager

        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(34, 28, 34, 28)
        v.setSpacing(18)

        title, icon = plugin_manager.plugin_page_meta(pid)
        header = QLabel(f"{icon}  {title}")
        header.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        header.setStyleSheet(f"color: {Color.TEXT};")
        v.addWidget(header)

        # автопанель настроек (если плагин её объявил)
        lp = plugin_manager.plugins.get(pid)
        if lp and plugin_manager.has_settings_schema(lp):
            from plugins.settings_panel import PluginSettingsPanel
            schema = plugin_manager.get_settings_schema(pid)
            v.addWidget(PluginSettingsPanel(pid, schema, plugin_manager))

        # кастомный виджет плагина
        custom = plugin_manager.build_plugin_page(pid)
        if custom is not None:
            v.addWidget(custom)

        v.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(holder)
        return scroll

    def _rebuild_content(self):
        current = getattr(self, "_current_index", 0)
        while self.content.count():
            w = self.content.widget(0)
            self.content.removeWidget(w)
            w.deleteLater()
        for spec in self._page_specs:
            self.content.addWidget(self._build_one_page(spec))
        if current >= self.content.count():
            current = 0
        self._current_index = current
        self.content.setCurrentIndex(current)

    def _style_content(self):
        self.content_wrap.setStyleSheet(f"""
            QFrame#content_wrap {{
                background: {Color.BASE};
                border-top-right-radius: {Radius.LG}px;
                border-bottom-right-radius: {Radius.LG}px;
            }}
        """)

    def on_plugin_pages_changed(self):
        """Плагин включён/выключен — пересобрать навигацию и контент."""
        active = self._current_index
        self._rebuild_nav_buttons()
        self._rebuild_content()
        # выделить активную кнопку (в пределах нового диапазона)
        if 0 <= active < len(self.buttons):
            self.buttons[active].setChecked(True)
        elif self.buttons:
            self.buttons[0].setChecked(True)
        self._style_sidebar()

    def _on_language_changed(self):
        """Язык интерфейса сменён — пересобрать весь интерфейс на новом языке."""
        active = self._current_index
        # обновить подписи титлбара/командной строки, если есть
        if hasattr(self, "command_bar") and hasattr(self.command_bar, "retranslate"):
            self.command_bar.retranslate()
        self._rebuild_nav_buttons()
        self._rebuild_content()
        if 0 <= active < len(self.buttons):
            self.buttons[active].setChecked(True)
        elif self.buttons:
            self.buttons[0].setChecked(True)
        self._style_sidebar()

    # ---------- перекраска темы ----------
    def apply_theme(self):
        self._style_sidebar()
        self._style_content()

        for btn in self.buttons:
            btn.update()

        if hasattr(self.titlebar, "apply_theme"):
            self.titlebar.apply_theme()

        if hasattr(self, "command_bar"):
            self.command_bar.apply_theme()

        if hasattr(self, "floating_bar"):
            self.floating_bar.apply_theme()
            self.floating_bar.update()

        self._rebuild_content()
        self.update()  # фон окна

    # ---------- поведение ----------
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def switch_page(self, index):
        if index == self._current_index:
            return
        self._current_index = index
        self.content.setCurrentIndex(index)
        page = self.content.widget(index)
        page_transition(page, duration=280, offset=26)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            fade_window_in(self, 460)

    # ---------- трей / закрытие ----------
    def closeEvent(self, event):
        # если включено сворачивание в трей и это не явный выход — прячем окно
        if settings.get("minimize_to_tray") and not self._force_quit:
            event.ignore()
            self.hide()
            self.tray.show()
            self._maybe_show_floating()
            if settings.get("notifications"):
                self.tray.notify(
                    tr("Rina свёрнута"),
                    tr("Приложение работает в фоне. Кликните значок, чтобы открыть.")
                )
        else:
            self.tray.hide()
            self._hide_floating()
            event.accept()

    def show_from_tray(self):
        self._hide_floating()   # при разворачивании прячем плавающую строку
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hideEvent(self, event):
        # окно свёрнуто в панель задач (не в трей) — тоже показать строку
        super().hideEvent(event)
        if self.isMinimized():
            self._maybe_show_floating()

    def quit_app(self):
        self._force_quit = True
        self.hotkey.unregister()  # остановить фоновый слушатель клавиатуры
        if hasattr(self, "voice"):
            self.voice.shutdown()
        self._hide_floating()
        self.tray.hide()
        self.close()
        QApplication.quit()


def run():
    import sys
    settings.load()

    # применяем язык интерфейса до построения UI
    from core.i18n import set_language
    set_language(settings.get("ui_language", "Русский"))

    # применяем сохранённую тему ДО построения UI
    theme_manager.apply(settings.get("theme"), settings.get("accent"))

    # обнаруживаем и подключаем плагины (включённые ранее — загрузятся)
    from plugins.manager import plugin_manager
    plugin_manager.discover()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # чтобы жить в трее

    # первый запуск — показать онбординг
    if settings.get("first_run", True):
        from dialogs.onboarding import OnboardingDialog
        dlg = OnboardingDialog()
        dlg.exec()

    window = MainWindow()
    if settings.get("start_minimized") and settings.get("minimize_to_tray"):
        window.tray.show()
    else:
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
