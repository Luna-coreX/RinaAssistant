from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius, theme_manager
from components.card import Card
from components.toggle_switch import ToggleSwitch
from components.controls import (
    styled_combo, styled_lineedit, SettingRow, Divider
)
from core.settings_store import settings
from core.app_signals import app_signals
from voice import audio_devices
from voice.mic_tester import MicTester


class SettingsPage(QWidget):
    """Настройки приложения (тема, поведение окна, приватность и т.д.)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True
        self._build()
        self._apply_saved()
        self._connect_signals()
        self._loading = False

    # ---------- построение ----------
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {Color.SURFACE_1}; border-radius: 4px; min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {Color.SURFACE_2}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(20)

        layout.addLayout(self._header())
        layout.addWidget(self._appearance_card())
        layout.addWidget(self._audio_card())
        layout.addWidget(self._models_card())
        layout.addWidget(self._behavior_card())
        layout.addWidget(self._search_card())
        layout.addWidget(self._privacy_card())
        layout.addWidget(self._reset_row())
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        t = QLabel(tr("Настройки"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(t)
        row.addStretch()

        self.saved_label = QLabel("")
        self.saved_label.setStyleSheet(
            f"color: {Color.GREEN}; font-size: 12px; font-weight: 600;")
        row.addWidget(self.saved_label)

        sub = QLabel(tr("Персонализация и параметры приложения"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _section_title(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {Color.SUBTEXT};")
        return lbl

    # ---------- Внешний вид ----------
    def _appearance_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Внешний вид")))
        cl.addSpacing(2)

        self.theme_combo = styled_combo(
            ["Catppuccin Mocha", "Catppuccin Macchiato",
             "Tokyo Night", "Nord", "Dracula"], 0)
        cl.addWidget(SettingRow(
            tr("Тема оформления"), tr("Цветовая схема приложения"),
            self.theme_combo))
        cl.addWidget(Divider())

        self.accent_combo = styled_combo(
            ["Mauve", "Pink", "Blue", "Green", "Peach", "Teal"], 0)
        cl.addWidget(SettingRow(
            tr("Акцентный цвет"), tr("Основной цвет кнопок и выделений"),
            self.accent_combo))
        cl.addWidget(Divider())

        from core.i18n import LANGUAGES
        self.language_combo = styled_combo(LANGUAGES, 0)
        cl.addWidget(SettingRow(
            tr("Язык"), tr("Язык интерфейса и распознавания речи"),
            self.language_combo))
        return card

    # ---------- Аудио ----------
    def _audio_card(self):
        from components.level_meter import LevelMeter

        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Аудио")))
        cl.addSpacing(2)

        # устройство ввода (микрофон)
        self._input_ids = []
        in_labels = []
        for did, label in audio_devices.input_devices():
            self._input_ids.append(did)
            in_labels.append(tr(label))
        self.input_combo = styled_combo(in_labels, 0)
        cl.addWidget(SettingRow(
            tr("Микрофон"), tr("Устройство ввода для распознавания речи"),
            self.input_combo))
        cl.addWidget(Divider())

        # устройство вывода (динамик)
        self._output_ids = []
        out_labels = []
        for did, label in audio_devices.output_devices():
            self._output_ids.append(did)
            out_labels.append(tr(label))
        self.output_combo = styled_combo(out_labels, 0)
        cl.addWidget(SettingRow(
            tr("Динамик"), tr("Устройство вывода для озвучки"),
            self.output_combo))
        cl.addWidget(Divider())

        # проверка микрофона
        test_row = QWidget()
        test_layout = QHBoxLayout(test_row)
        test_layout.setContentsMargins(0, 6, 0, 6)
        test_layout.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(3)
        tl = QLabel(tr("Проверка микрофона"))
        tl.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        tl.setStyleSheet(f"color: {Color.TEXT};")
        left.addWidget(tl)
        self.mic_status = QLabel(tr("Нажмите «Проверить» и говорите 2 секунды"))
        self.mic_status.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        self.mic_status.setWordWrap(True)
        left.addWidget(self.mic_status)
        self.level_meter = LevelMeter()
        left.addWidget(self.level_meter)
        test_layout.addLayout(left, 1)

        self.mic_test_btn = QPushButton(tr("Проверить"))
        self.mic_test_btn.setCursor(Qt.PointingHandCursor)
        self.mic_test_btn.setFixedHeight(36)
        self.mic_test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
            QPushButton:disabled {{ color: {Color.OVERLAY}; }}
        """)
        self.mic_test_btn.clicked.connect(self._run_mic_test)
        test_layout.addWidget(self.mic_test_btn, 0, Qt.AlignVCenter)
        cl.addWidget(test_row)

        # тестер (фоновый поток -> сигнал)
        self._mic_tester = MicTester(self)
        self._mic_tester.started.connect(self._on_mic_test_started)
        self._mic_tester.finished.connect(self._on_mic_test_finished)

        if not self._mic_tester.available:
            self.mic_status.setText(
                tr("Тест недоступен — установите sounddevice и numpy ") +
                "(pip install sounddevice numpy).")
            self.mic_test_btn.setEnabled(False)

        return card

    # ---------- Модели распознавания/синтеза ----------
    def _models_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Модели голоса")))
        cl.addSpacing(2)

        # Whisper — размер модели
        self.whisper_combo = styled_combo(
            ["tiny", "base", "small", "medium"], 1)
        cur = settings.get("whisper_model", "base")
        idx = self.whisper_combo.findText(str(cur))
        if idx >= 0:
            self.whisper_combo.setCurrentIndex(idx)
        self.whisper_combo.currentTextChanged.connect(
            lambda t: (settings.set("whisper_model", t), settings.save()))
        cl.addWidget(SettingRow(
            tr("Модель Whisper"), tr("Размер (больше = точнее и медленнее)"),
            self.whisper_combo))
        cl.addWidget(Divider())

        # Vosk — папка модели
        self.vosk_path = self._path_row(
            cl, tr("Модель Vosk"), tr("Папка со скачанной моделью Vosk"),
            settings.get("vosk_model", ""), key="vosk_model", is_dir=True)
        cl.addWidget(Divider())

        # Piper — файл .onnx
        self.piper_path = self._path_row(
            cl, tr("Модель Piper"), tr("Файл .onnx голоса Piper"),
            settings.get("piper_model", ""), key="piper_model", is_dir=False)

        hint = QLabel(
            tr("Vosk: alphacephei.com/vosk/models · Whisper скачивается сам при ") +
            tr("первом запуске · Piper: файлы .onnx с huggingface."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        cl.addWidget(hint)
        return card

    def _path_row(self, parent_layout, title, desc, value, key, is_dir):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 6, 2, 6)
        h.setSpacing(10)

        box = QVBoxLayout()
        box.setSpacing(2)
        t = QLabel(title)
        t.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        d = QLabel(desc)
        d.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        box.addWidget(t)
        box.addWidget(d)

        edit = styled_lineedit(tr("не выбрано"), value)
        edit.textChanged.connect(
            lambda txt, k=key: (settings.set(k, txt), settings.save()))
        pick = QPushButton(tr("Обзор…"))
        pick.setCursor(Qt.PointingHandCursor)
        pick.setFixedHeight(34)
        pick.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 14px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)

        def choose():
            if is_dir:
                p = QFileDialog.getExistingDirectory(self, tr("Папка модели"))
            else:
                p, _ = QFileDialog.getOpenFileName(self, tr("Файл модели"),
                                                   "", tr("Модели (*.onnx);;Все файлы (*)"))
            if p:
                edit.setText(p)
        pick.clicked.connect(choose)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_row.addWidget(edit, 1)
        path_row.addWidget(pick)
        box.addLayout(path_row)

        h.addLayout(box, 1)
        parent_layout.addWidget(row)
        return edit

    def _run_mic_test(self):
        device = self._current_input_id()
        self._mic_tester.run_test(device, seconds=2.0)

    def _on_mic_test_started(self):
        self.mic_test_btn.setEnabled(False)
        self.mic_test_btn.setText(tr("Запись…"))
        self.mic_status.setText(tr("Говорите… идёт запись 2 секунды"))

    def _on_mic_test_finished(self, result):
        self.mic_test_btn.setEnabled(True)
        self.mic_test_btn.setText(tr("Проверить"))
        if result.ok:
            self.level_meter.animate_to(result.level)
            if result.level < 0.03:
                self.mic_status.setText(
                    tr("Почти тишина — проверьте, что микрофон не отключён."))
            elif result.level < 0.5:
                self.mic_status.setText(tr("Микрофон работает, уровень нормальный."))
            else:
                self.mic_status.setText(tr("Микрофон работает, громкий сигнал."))
            QTimer.singleShot(2500, self.level_meter.reset)
        else:
            self.mic_status.setText(result.error or tr("Не удалось проверить микрофон."))
            self.level_meter.reset()

    def _current_input_id(self):
        idx = self.input_combo.currentIndex()
        if 0 <= idx < len(self._input_ids):
            return self._input_ids[idx]
        return "default"

    def _current_output_id(self):
        idx = self.output_combo.currentIndex()
        if 0 <= idx < len(self._output_ids):
            return self._output_ids[idx]
        return "default"

    # ---------- Поведение ----------
    def _behavior_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Поведение приложения")))
        cl.addSpacing(2)

        self.autostart = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Запуск с системой"), tr("Открывать Рину при старте ОС"),
            self.autostart))
        cl.addWidget(Divider())

        self.tray = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Сворачивать в трей"), tr("Прятать окно вместо закрытия"),
            self.tray))
        cl.addWidget(Divider())

        self.start_min = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Запускать свёрнутым"), tr("Стартовать сразу в трее"),
            self.start_min))
        cl.addWidget(Divider())

        self.floating_bar = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Плавающая строка команд"),
            tr("Показывать строку ввода поверх окон, когда Рина свёрнута"),
            self.floating_bar))
        cl.addWidget(Divider())

        self.notifications = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Уведомления"), tr("Показывать всплывающие уведомления"),
            self.notifications))
        cl.addWidget(Divider())

        self.sfx = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Звуковые эффекты"), tr("Звук активации и ответов"),
            self.sfx))
        cl.addWidget(Divider())

        self.updates = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Проверять обновления"), tr("Автопроверка новых версий"),
            self.updates))

        # кнопка ручной проверки + статус
        upd_row = QWidget()
        ur = QHBoxLayout(upd_row)
        ur.setContentsMargins(42, 2, 0, 4)
        ur.setSpacing(10)
        self.update_status = QLabel("")
        self.update_status.setWordWrap(True)
        self.update_status.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        ur.addWidget(self.update_status, 1)
        self.check_update_btn = QPushButton(tr("Проверить сейчас"))
        self.check_update_btn.setCursor(Qt.PointingHandCursor)
        self.check_update_btn.setFixedHeight(32)
        self.check_update_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 2px 14px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
            QPushButton:disabled {{ color: {Color.OVERLAY}; }}
        """)
        self.check_update_btn.clicked.connect(self._run_update_check)
        ur.addWidget(self.check_update_btn, 0, Qt.AlignVCenter)
        cl.addWidget(upd_row)

        # проверяльщик обновлений
        from voice.updates import UpdateChecker
        self._update_checker = UpdateChecker(self)
        self._update_checker.checking.connect(self._on_update_checking)
        self._update_checker.result.connect(self._on_update_result)
        return card

    def _on_autostart_toggled(self, on):
        if self._loading:
            return
        from voice import autostart
        ok = autostart.set_autostart(bool(on))
        if not ok:
            # не удалось — откатываем тумблер и сообщаем
            self._loading = True
            self.autostart.setChecked(not on)
            self._loading = False
            settings.set("autostart", not on)
            settings.save()

    def _run_update_check(self):
        self._update_checker.check()

    def _on_update_checking(self):
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText(tr("Проверяю…"))
        self.update_status.setText("")

    def _on_update_result(self, available, message):
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText(tr("Проверить сейчас"))
        color = Color.GREEN if available else Color.OVERLAY
        self.update_status.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.update_status.setText(message)

    # ---------- Поиск ----------
    def _search_card(self):
        from voice import websearch

        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Поиск в интернете")))
        cl.addSpacing(2)

        self._engine_ids = []
        labels = []
        for eid, label in websearch.engine_choices():
            self._engine_ids.append(eid)
            labels.append(label)
        self.engine_combo = styled_combo(labels, 0)
        cl.addWidget(SettingRow(
            tr("Поисковая система"),
            tr("Куда уходят запросы вида «найди рецепт борща»"),
            self.engine_combo))
        cl.addWidget(Divider())

        self.search_fallback = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Искать нераспознанное"),
            tr("Если команда не найдена — открыть поиск в браузере. "
               "В режиме «всегда слушать» не срабатывает."),
            self.search_fallback))
        return card

    def _current_engine_id(self):
        idx = self.engine_combo.currentIndex()
        if 0 <= idx < len(self._engine_ids):
            return self._engine_ids[idx]
        return "google"

    # ---------- Приватность ----------
    def _privacy_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("Приватность")))
        cl.addSpacing(2)

        self.save_history = ToggleSwitch()
        cl.addWidget(SettingRow(
            tr("Сохранять историю"), tr("Хранить историю запросов локально"),
            self.save_history))
        return card

    # ---------- Сброс ----------
    def _reset_row(self):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 0, 2, 0)
        h.addStretch()

        btn = QPushButton(tr("Сбросить настройки"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(38)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {Color.RED};
                border: 1px solid {Color.alpha(Color.RED, '55')};
                border-radius: {Radius.SM}px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {Color.alpha(Color.RED, '22')};
                border: 1px solid {Color.RED};
            }}
        """)
        btn.clicked.connect(self._reset)
        h.addWidget(btn)
        return row

    # ---------- загрузка/сохранение ----------
    def _apply_saved(self):
        self._set_combo(self.theme_combo, settings.get("theme"))
        self._set_combo(self.accent_combo, settings.get("accent"))
        self._set_combo(self.language_combo, settings.get("ui_language", "Русский"))
        self.autostart.setChecked(bool(settings.get("autostart")))
        # синхронизируем с реальным состоянием ОС (могли отключить извне)
        try:
            from voice import autostart as _auto
            real = _auto.is_autostart_enabled()
            self.autostart.setChecked(real)
            if real != bool(settings.get("autostart")):
                settings.set("autostart", real)
        except Exception:
            pass
        self.tray.setChecked(bool(settings.get("minimize_to_tray")))
        self.start_min.setChecked(bool(settings.get("start_minimized")))
        self.floating_bar.setChecked(bool(settings.get("floating_command_bar")))
        self.notifications.setChecked(bool(settings.get("notifications")))
        self.sfx.setChecked(bool(settings.get("sound_effects")))
        self.updates.setChecked(bool(settings.get("check_updates")))
        self.save_history.setChecked(bool(settings.get("save_history")))
        self.search_fallback.setChecked(bool(settings.get("web_search_fallback")))
        saved_engine = settings.get("search_engine", "google")
        if saved_engine in getattr(self, "_engine_ids", []):
            self.engine_combo.setCurrentIndex(self._engine_ids.index(saved_engine))

        # аудио-устройства (по id)
        saved_in = settings.get("input_device", "default")
        if saved_in in getattr(self, "_input_ids", []):
            self.input_combo.setCurrentIndex(self._input_ids.index(saved_in))
        saved_out = settings.get("output_device", "default")
        if saved_out in getattr(self, "_output_ids", []):
            self.output_combo.setCurrentIndex(self._output_ids.index(saved_out))

    def _set_combo(self, combo, value):
        idx = combo.findText(str(value))
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _connect_signals(self):
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        self.accent_combo.currentTextChanged.connect(self._on_accent_changed)
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        self.autostart.toggled.connect(self._save)
        self.autostart.toggled.connect(self._on_autostart_toggled)
        self.tray.toggled.connect(self._save)
        self.tray.toggled.connect(lambda _: app_signals.tray_pref_changed.emit())
        self.start_min.toggled.connect(self._save)
        self.floating_bar.toggled.connect(self._save)
        self.notifications.toggled.connect(self._save)
        self.sfx.toggled.connect(self._save)
        self.updates.toggled.connect(self._save)
        self.save_history.toggled.connect(self._save)
        self.search_fallback.toggled.connect(self._save)
        self.engine_combo.currentIndexChanged.connect(self._save)
        self.input_combo.currentIndexChanged.connect(self._save)
        self.output_combo.currentIndexChanged.connect(self._save)

    def get_settings(self):
        return {
            "theme": self.theme_combo.currentText(),
            "accent": self.accent_combo.currentText(),
            "autostart": self.autostart.isChecked(),
            "minimize_to_tray": self.tray.isChecked(),
            "start_minimized": self.start_min.isChecked(),
            "floating_command_bar": self.floating_bar.isChecked(),
            "notifications": self.notifications.isChecked(),
            "sound_effects": self.sfx.isChecked(),
            "check_updates": self.updates.isChecked(),
            "save_history": self.save_history.isChecked(),
            "web_search_fallback": self.search_fallback.isChecked(),
            "search_engine": self._current_engine_id(),
            "input_device": self._current_input_id(),
            "output_device": self._current_output_id(),
        }

    def _on_theme_changed(self, name):
        if self._loading:
            return
        # сохраняем ПЕРЕД сменой темы: apply_theme пересоберёт эту страницу,
        # и текущий объект перестанет быть активным.
        settings.set("theme", name)
        settings.save()
        theme_manager.set_theme(name)  # -> MainWindow.apply_theme -> rebuild

    def _on_accent_changed(self, name):
        if self._loading:
            return
        settings.set("accent", name)
        settings.save()
        theme_manager.set_accent(name)

    def _on_language_changed(self, name):
        if self._loading:
            return
        settings.set("ui_language", name)
        settings.save()
        from core.i18n import set_language
        set_language(name)
        app_signals.language_changed.emit()

    def _save(self, *args):
        if self._loading:
            return
        settings.update(self.get_settings())
        settings.save()
        self._flash_saved()

    def _flash_saved(self):
        self.saved_label.setText(tr("Сохранено"))
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(
                lambda: self.saved_label.setText(""))
        self._save_timer.start(1500)

    def _reset(self):
        settings.reset()
        # применяем тему по умолчанию — это пересоберёт страницы,
        # поэтому _apply_saved на текущем объекте вызывать после уже не нужно.
        theme_manager.apply(settings.get("theme"), settings.get("accent"))
