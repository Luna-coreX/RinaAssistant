from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from components.toggle_switch import ToggleSwitch
from components.controls import (
    styled_slider, styled_combo, styled_lineedit, SettingRow, Divider
)
from core.settings_store import settings
from core.app_signals import app_signals
from voice import tts as tts_mod
from voice import stt as stt_mod


class RinaPage(QWidget):
    """Страница настроек ассистента «Рина»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True     # блокирует автосохранение во время инициализации
        self._build()
        self._apply_saved()      # выставить значения из хранилища
        self._connect_signals()  # подключить автосохранение
        self._loading = False

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # скролл — настроек много, окно может быть маленьким
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
                background: {Color.SURFACE_1};
                border-radius: 4px; min-height: 30px;
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
        layout.addWidget(self._voice_card())
        layout.addWidget(self._behavior_card())
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ---------- шапка ----------
    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel("🌸")
        ic.setStyleSheet("font-size: 30px;")
        t = QLabel(tr("Рина"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(ic)
        row.addWidget(t)
        row.addStretch()

        self.saved_label = QLabel("")
        self.saved_label.setStyleSheet(f"""
            color: {Color.GREEN}; font-size: 12px; font-weight: 600;
        """)
        row.addWidget(self.saved_label)

        status = QLabel("● Online")
        status.setStyleSheet(f"""
            background: {Color.alpha(Color.GREEN, '22')}; color: {Color.GREEN};
            border-radius: 10px; padding: 4px 12px;
            font-size: 12px; font-weight: 600;
        """)
        row.addWidget(status)

        sub = QLabel(tr("Настройте голос и поведение вашего ассистента"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")

        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _section_title(self, text):
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {Color.SUBTEXT};")
        return lbl

    # ---------- карточка «Голос» ----------
    def _voice_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("🎙  Голос и речь")))
        cl.addSpacing(2)

        # 0. Выбор TTS-движка (самой системы синтеза)
        self._tts_ids = []
        tts_labels = []
        for eid, label, avail in tts_mod.engine_choices():
            self._tts_ids.append(eid)
            tts_labels.append(label + ("" if avail else tr("  (не установлен)")))
        self.tts_combo = styled_combo(tts_labels, 0)
        cl.addWidget(SettingRow(
            "🧠", tr("Система синтеза (TTS)"),
            tr("Движок озвучки. «Без озвучки» показывает только текст."),
            self.tts_combo
        ))
        cl.addWidget(Divider())

        # 0b. Выбор STT-движка (распознавание речи)
        self._stt_ids = []
        stt_labels = []
        for eid, label, avail in stt_mod.engine_choices():
            self._stt_ids.append(eid)
            stt_labels.append(label + ("" if avail else tr("  (недоступен)")))
        self.stt_combo = styled_combo(stt_labels, 0)
        cl.addWidget(SettingRow(
            "👂", tr("Распознавание речи (STT)"),
            tr("Движок микрофона. «Выключено» — ассистент не слушает."),
            self.stt_combo
        ))
        cl.addWidget(Divider())

        # 1. Выбор голоса (зависит от выбранного движка)
        self.voice_combo = styled_combo([tr("Системный голос")], 0)
        cl.addWidget(SettingRow(
            "🗣️", tr("Голос"), tr("Конкретный голос выбранного движка"),
            self.voice_combo
        ))
        cl.addWidget(Divider())

        # 2. Как обращаться к Рине (имя активации)
        self.wake_edit = styled_lineedit(tr("Рина, Рену, Рино"), tr("Рина"))
        cl.addWidget(SettingRow(
            "💬", tr("Слова активации"),
            tr("Варианты через запятую (распознавание бывает неточным)"),
            self.wake_edit
        ))
        cl.addWidget(Divider())

        # 3. Громкость
        self.volume_slider = styled_slider(0, 100, 75)
        self.volume_val = QLabel("75%")
        self.volume_val.setStyleSheet(
            f"color: {Color.ACCENT}; font-weight: 600; font-size: 12px;")
        self.volume_val.setFixedWidth(42)
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_val.setText(f"{v}%"))
        vol_ctrl = self._slider_with_value(self.volume_slider, self.volume_val)
        cl.addWidget(SettingRow(
            "🔊", tr("Громкость"), tr("Уровень громкости голоса Рины"), vol_ctrl
        ))
        cl.addWidget(Divider())

        # 4. Скорость
        self.speed_slider = styled_slider(50, 200, 100)
        self.speed_val = QLabel("1.0x")
        self.speed_val.setStyleSheet(
            f"color: {Color.ACCENT}; font-weight: 600; font-size: 12px;")
        self.speed_val.setFixedWidth(42)
        self.speed_slider.valueChanged.connect(
            lambda v: self.speed_val.setText(f"{v/100:.1f}x"))
        spd_ctrl = self._slider_with_value(self.speed_slider, self.speed_val)
        cl.addWidget(SettingRow(
            "⚡", tr("Скорость речи"), tr("Темп произношения ответов"), spd_ctrl
        ))
        cl.addWidget(Divider())

        # Проверка голоса — прослушать выбранные движок/голос/громкость/скорость
        cl.addWidget(self._voice_test_row())

        # Язык распознавания речи теперь общий с языком интерфейса —
        # настраивается один раз в «Настройки → Язык».
        return card

    # ---------- проверка голоса ----------
    def _voice_test_row(self):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 6, 0, 6)
        h.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(3)
        tl = QLabel(tr("Проверка голоса"))
        tl.setFont(QFont(FONT_FAMILY, 12, QFont.Bold))
        tl.setStyleSheet(f"color: {Color.TEXT};")
        left.addWidget(tl)
        self.voice_test_status = QLabel(
            tr("Рина произнесёт короткую фразу выбранным голосом"))
        self.voice_test_status.setStyleSheet(
            f"color: {Color.OVERLAY}; font-size: 11px;")
        self.voice_test_status.setWordWrap(True)
        left.addWidget(self.voice_test_status)
        h.addLayout(left, 1)

        self.voice_test_btn = QPushButton(tr("🔊 Проверить"))
        self.voice_test_btn.setCursor(Qt.PointingHandCursor)
        self.voice_test_btn.setFixedHeight(36)
        self.voice_test_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
            QPushButton:disabled {{ color: {Color.OVERLAY}; }}
        """)
        self.voice_test_btn.clicked.connect(self._run_voice_test)
        h.addWidget(self.voice_test_btn, 0, Qt.AlignVCenter)

        from voice.voice_tester import VoiceTester
        self._voice_tester = VoiceTester(self)
        self._voice_tester.started.connect(self._on_voice_test_started)
        self._voice_tester.finished.connect(self._on_voice_test_finished)
        return row

    def _run_voice_test(self):
        engine_id = self._current_tts_id()
        if engine_id == "silent":
            self.voice_test_status.setText(
                tr("Сначала выберите движок озвучки (TTS) выше"))
            return
        vidx = self.voice_combo.currentIndex()
        voice_ids = getattr(self, "_voice_ids", [])
        voice_id = voice_ids[vidx] if 0 <= vidx < len(voice_ids) else None
        self._voice_tester.run_test(
            engine_id, voice_id,
            self.volume_slider.value(), self.speed_slider.value(),
            tr("Привет! Меня зовут Рина. Это проверка голоса."))

    def _on_voice_test_started(self):
        self.voice_test_btn.setEnabled(False)
        self.voice_test_btn.setText(tr("● Говорю…"))
        self.voice_test_status.setText(tr("Воспроизведение…"))

    def _on_voice_test_finished(self, err):
        self.voice_test_btn.setEnabled(True)
        self.voice_test_btn.setText(tr("🔊 Проверить"))
        if err:
            self.voice_test_status.setText(tr("Ошибка озвучки: ") + err)
        else:
            self.voice_test_status.setText(tr("Готово ✓"))

    # ---------- карточка «Поведение» ----------
    def _behavior_card(self):
        card = Card()
        cl = card.layout()
        cl.addWidget(self._section_title(tr("🧠  Поведение")))
        cl.addSpacing(2)

        # 6. Отвечать голосом / молчать
        self.voice_reply = ToggleSwitch(checked=True)
        cl.addWidget(SettingRow(
            "🔈", tr("Отвечать голосом"),
            tr("Если выключено — Рина отвечает только текстом"),
            self.voice_reply
        ))
        cl.addWidget(Divider())

        # 7. Всегда слушать
        self.always_listen = ToggleSwitch(checked=False)
        cl.addWidget(SettingRow(
            "👂", tr("Всегда слушать"),
            tr("Активация по слову без нажатия горячей клавиши"),
            self.always_listen
        ))
        return card

    # ---------- helper ----------
    def _slider_with_value(self, slider, value_label):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        slider.setFixedWidth(200)
        h.addWidget(slider)
        h.addWidget(value_label)
        return w

    # ---------- загрузка сохранённых значений ----------
    def _apply_saved(self):
        # выбранный TTS-движок
        saved_tts = settings.get("tts_engine", "silent")
        if saved_tts in self._tts_ids:
            self.tts_combo.setCurrentIndex(self._tts_ids.index(saved_tts))
        # выбранный STT-движок
        saved_stt = settings.get("stt_engine", "disabled")
        if saved_stt in self._stt_ids:
            self.stt_combo.setCurrentIndex(self._stt_ids.index(saved_stt))
        self._populate_voices()  # заполнить голоса под движок

        # выбрать сохранённый голос по id
        saved_voice = settings.get("voice")
        if saved_voice in getattr(self, "_voice_ids", []):
            self.voice_combo.setCurrentIndex(self._voice_ids.index(saved_voice))
        wake_list = settings.get("wake_words") or [settings.get("wake_word", tr("Рина"))]
        self.wake_edit.setText(", ".join(str(w) for w in wake_list))
        self.volume_slider.setValue(int(settings.get("volume")))
        self.speed_slider.setValue(int(settings.get("speed")))
        self.voice_reply.setChecked(bool(settings.get("voice_reply")))
        self.always_listen.setChecked(bool(settings.get("always_listen")))
        # обновить подписи значений
        self.volume_val.setText(f"{self.volume_slider.value()}%")
        self.speed_val.setText(f"{self.speed_slider.value()/100:.1f}x")

    def _populate_voices(self):
        """Перезаполняет список голосов голосами текущего TTS-движка."""
        engine_id = self._current_tts_id()
        engine = tts_mod.get_engine(engine_id)
        self._voice_ids = []
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for vid, label in engine.voices():
            self._voice_ids.append(vid)
            self.voice_combo.addItem(label)
        self.voice_combo.blockSignals(False)

    def _current_tts_id(self):
        idx = self.tts_combo.currentIndex()
        if 0 <= idx < len(self._tts_ids):
            return self._tts_ids[idx]
        return "silent"

    def _current_stt_id(self):
        idx = self.stt_combo.currentIndex()
        if 0 <= idx < len(self._stt_ids):
            return self._stt_ids[idx]
        return "disabled"

    def _wake_list(self):
        """Список слов активации из поля (через запятую), без пустых."""
        return [w.strip() for w in self.wake_edit.text().split(",") if w.strip()]

    def _set_combo(self, combo, value):
        idx = combo.findText(str(value))
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ---------- подключение автосохранения ----------
    def _connect_signals(self):
        self.tts_combo.currentIndexChanged.connect(self._on_tts_changed)
        self.stt_combo.currentIndexChanged.connect(self._save)
        self.voice_combo.currentIndexChanged.connect(self._save)
        self.wake_edit.textChanged.connect(self._save)
        self.volume_slider.valueChanged.connect(self._save)
        self.speed_slider.valueChanged.connect(self._save)
        self.voice_reply.toggled.connect(self._save)
        self.always_listen.toggled.connect(self._save)
        self.always_listen.toggled.connect(
            lambda on: app_signals.always_listen_changed.emit(bool(on)))

    def _on_tts_changed(self, *args):
        if self._loading:
            return
        self._populate_voices()
        self._save()

    # ---------- сбор текущих настроек ----------
    def get_settings(self):
        # id голоса из выбранного пункта
        vidx = self.voice_combo.currentIndex()
        voice_id = (self._voice_ids[vidx]
                    if 0 <= vidx < len(getattr(self, "_voice_ids", []))
                    else settings.get("voice"))
        return {
            "tts_engine": self._current_tts_id(),
            "stt_engine": self._current_stt_id(),
            "voice": voice_id,
            "wake_word": self._wake_list()[0] if self._wake_list() else tr("Рина"),
            "wake_words": self._wake_list(),
            "volume": self.volume_slider.value(),
            "speed": self.speed_slider.value(),
            "voice_reply": self.voice_reply.isChecked(),
            "always_listen": self.always_listen.isChecked(),
        }

    # ---------- сохранение ----------
    def _save(self, *args):
        if self._loading:
            return
        settings.update(self.get_settings())
        settings.save()
        self._flash_saved()

    def _flash_saved(self):
        self.saved_label.setText(tr("✓ Сохранено"))
        # спрятать через 1.5 с
        from PySide6.QtCore import QTimer
        if not hasattr(self, "_save_timer"):
            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(
                lambda: self.saved_label.setText(""))
        self._save_timer.start(1500)
