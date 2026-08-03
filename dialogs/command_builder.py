from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QFileDialog, QWidget, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.controls import styled_combo, styled_lineedit
from components.app_picker import AppPickerEdit
from components.sequence_editor import SequenceEditor
from voice.user_commands import (
    COMMAND_TYPES, SYSTEM_ACTIONS, make_command
)
from voice.textmatch import normalize as normalize_phrase


class CommandBuilderDialog(QDialog):
    """
    Диалог создания/редактирования команды.
    Поля меняются в зависимости от выбранного типа.
    """

    def __init__(self, parent=None, command=None):
        super().__init__(parent)
        self._editing = command is not None
        self._command = command
        self.setWindowTitle(tr("Команда"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(f"QDialog {{ background: {Color.BASE}; }}")
        self._build()
        if command:
            self._load(command)
        self._on_type_changed()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(16)

        title = QLabel(tr("Редактировать команду") if self._editing else tr("Новая команда"))
        title.setFont(QFont(FONT_FAMILY, 18, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        layout.addWidget(title)

        # --- тип команды ---
        layout.addWidget(self._label(tr("Тип команды")))
        self._type_ids = [t for t, _, _ in COMMAND_TYPES]
        type_labels = [tr(label) for _, label, icon in COMMAND_TYPES]
        self.type_combo = styled_combo(type_labels, 0)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        # --- динамическое поле цели ---
        self.target_label = self._label(tr("Программа"))
        layout.addWidget(self.target_label)

        # выбор программы из найденных (для типа «Программа»)
        self.app_picker = AppPickerEdit()
        layout.addWidget(self.app_picker)

        # обычное поле пути/ссылки (папка, сайт)
        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        self.target_edit = styled_lineedit("")
        target_row.addWidget(self.target_edit, 1)
        self.browse_btn = QPushButton(tr("Обзор…"))
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setFixedHeight(38)
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 16px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
        """)
        self.browse_btn.clicked.connect(self._browse)
        target_row.addWidget(self.browse_btn)
        self._target_row = target_row
        layout.addLayout(target_row)

        # системное действие (свой комбо, скрывается для других типов)
        self.system_combo = styled_combo(
            [tr(label) for _, label in SYSTEM_ACTIONS], 0)
        self.system_combo.hide()
        layout.addWidget(self.system_combo)

        # многострочное поле для «озвучить текст»
        self.speak_edit = QTextEdit()
        self.speak_edit.setPlaceholderText(tr("Текст, который произнесёт Рина…"))
        self.speak_edit.setFixedHeight(70)
        self.speak_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 6px 10px; font-size: 13px;
            }}
            QTextEdit:focus {{ border: 1px solid {Color.ACCENT}; }}
        """)
        self.speak_edit.hide()
        layout.addWidget(self.speak_edit)

        # редактор последовательности (скрыт для других типов)
        self.sequence_editor = SequenceEditor()
        self.sequence_editor.hide()
        layout.addWidget(self.sequence_editor)

        # --- фразы активации ---
        layout.addWidget(self._label(tr("Фразы активации (через запятую)")))
        self.triggers_edit = styled_lineedit(tr("запусти дискорд, открой discord"))
        layout.addWidget(self.triggers_edit)

        # --- режим совпадения ---
        match_row = QHBoxLayout()
        match_row.setSpacing(10)
        mlabel = self._label(tr("Совпадение"))
        match_row.addWidget(mlabel)
        self.match_combo = styled_combo(
            [tr("Содержит фразу"), tr("Точное совпадение")], 0)
        match_row.addWidget(self.match_combo, 1)
        layout.addLayout(match_row)

        # --- ответ ассистента ---
        layout.addWidget(self._label(tr("Ответ ассистента (необязательно)")))
        self.response_edit = styled_lineedit(tr("Хорошо, выполняю"))
        layout.addWidget(self.response_edit)

        # --- кнопки ---
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton(tr("Отмена"))
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setFixedHeight(38)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {Color.SUBTEXT};
                border: 1px solid {Color.SURFACE_1}; border-radius: {Radius.SM}px;
                padding: 4px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_0}; }}
        """)
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("Сохранить"))
        save.setCursor(Qt.PointingHandCursor)
        save.setFixedHeight(38)
        save.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 24px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.MAUVE}; }}
        """)
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {Color.RED}; font-size: 12px;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px; font-weight: 600;")
        return lbl

    def _current_type(self):
        idx = self.type_combo.currentIndex()
        return self._type_ids[idx] if 0 <= idx < len(self._type_ids) else "app"

    def _on_type_changed(self, *args):
        t = self._current_type()

        # по умолчанию всё скрыто
        self.target_label.hide()
        self.target_edit.hide()
        self.browse_btn.hide()
        self.app_picker.hide()
        self.system_combo.hide()
        self.speak_edit.hide()
        self.sequence_editor.hide()

        if t == "app":
            # Рина уже знает установленные программы — выбираем из них,
            # а не просим путь к .exe
            self.target_label.setText(tr("Программа"))
            self.target_label.show(); self.app_picker.show()
        elif t == "folder":
            self.target_label.setText(tr("Путь к папке"))
            self.target_label.show(); self.target_edit.show(); self.browse_btn.show()
            self.target_edit.setPlaceholderText("C:\\Users\\...\\Documents")
        elif t == "website":
            self.target_label.setText(tr("Ссылка на сайт"))
            self.target_label.show(); self.target_edit.show()
            self.target_edit.setPlaceholderText("youtube.com")
        elif t == "speak":
            self.target_label.setText(tr("Текст для озвучивания"))
            self.target_label.show(); self.speak_edit.show()
        elif t == "system":
            self.target_label.setText(tr("Системное действие"))
            self.target_label.show(); self.system_combo.show()
        elif t == "sequence":
            self.target_label.setText(tr("Шаги последовательности"))
            self.target_label.show()
            self.sequence_editor.show()
            # если пусто — добавим один пустой шаг для удобства
            if not self.sequence_editor.to_steps() and not self._editing:
                if not getattr(self, "_seq_initialized", False):
                    self.sequence_editor.add_step()
                    self._seq_initialized = True

    def _browse(self):
        t = self._current_type()
        if t == "folder":
            path = QFileDialog.getExistingDirectory(self, tr("Выберите папку"))
        else:
            path, _ = QFileDialog.getOpenFileName(self, tr("Выберите программу"))
        if path:
            self.target_edit.setText(path)

    # ---------- загрузка при редактировании ----------
    def _load(self, cmd):
        t = cmd.get("type", "app")
        if t in self._type_ids:
            self.type_combo.setCurrentIndex(self._type_ids.index(t))
        self.triggers_edit.setText(", ".join(cmd.get("triggers", [])))
        self.match_combo.setCurrentIndex(
            1 if cmd.get("match") == "exact" else 0)
        self.response_edit.setText(cmd.get("response", ""))
        if t == "speak":
            self.speak_edit.setPlainText(cmd.get("target", ""))
        elif t == "system":
            actions = [a for a, _ in SYSTEM_ACTIONS]
            if cmd.get("target") in actions:
                self.system_combo.setCurrentIndex(actions.index(cmd["target"]))
        elif t == "sequence":
            self.sequence_editor.load_steps(cmd.get("steps", []))
            self._seq_initialized = True
        elif t == "app":
            self.app_picker.set_target(cmd.get("target", ""),
                                       cmd.get("target_kind", "file"))
        else:
            self.target_edit.setText(cmd.get("target", ""))

    # ---------- сохранение ----------
    def _save(self):
        t = self._current_type()
        triggers = [s.strip() for s in self.triggers_edit.text().split(",")
                    if s.strip()]
        if not triggers:
            return self._error(tr("Добавьте хотя бы одну фразу активации."))

        steps = []
        target_kind = "file"
        if t == "app":
            target = self.app_picker.target().strip()
            target_kind = self.app_picker.target_kind()
            if not target:
                return self._error(tr("Выберите программу."))
        elif t == "speak":
            target = self.speak_edit.toPlainText().strip()
            if not target:
                return self._error(tr("Введите текст для озвучивания."))
        elif t == "system":
            target = SYSTEM_ACTIONS[self.system_combo.currentIndex()][0]
        elif t == "sequence":
            target = ""
            steps = self.sequence_editor.to_steps()
            if not steps:
                return self._error(tr("Добавьте хотя бы один шаг последовательности."))
        else:
            target = self.target_edit.text().strip()
            if not target:
                return self._error(tr("Укажите путь или ссылку."))

        conflict = self._find_conflict(triggers)
        if conflict:
            phrase, other = conflict
            if normalize_phrase(other) == normalize_phrase(phrase):
                return self._error(tr(
                    "Фраза «{phrase}» уже используется другой командой — "
                    "сработает она. Измените фразу.", phrase=phrase))
            return self._error(tr(
                "Фраза «{phrase}» уже занята командой «{other}» — она "
                "сработает первой. Измените фразу.",
                phrase=phrase, other=other))

        match = "exact" if self.match_combo.currentIndex() == 1 else "contains"
        response = self.response_edit.text().strip()

        cmd = make_command(
            cmd_type=t, triggers=triggers, target=target,
            response=response, match=match, enabled=True, steps=steps,
            target_kind=target_kind,
        )
        if self._editing and self._command:
            cmd["id"] = self._command["id"]
            cmd["enabled"] = self._command.get("enabled", True)
        self._result = cmd
        self.accept()

    def _find_conflict(self, triggers):
        """
        Ищет фразу, уже занятую другой командой.

        Команды перебираются по порядку, срабатывает первая подходящая —
        поэтому дубликат означал бы, что новая команда просто не запустится.
        Возвращает (фраза, имя чужой команды) или None.
        """
        from core.settings_store import settings
        from voice.user_commands import UserCommandStore
        from voice.textmatch import normalize

        my_id = self._command.get("id") if self._editing and self._command else None
        mine = {normalize(t) for t in triggers}

        for cmd in UserCommandStore(settings).all():
            if cmd.get("id") == my_id:
                continue
            for other in cmd.get("triggers", []):
                if normalize(other) in mine:
                    label = (cmd.get("triggers") or [tr("(без фразы)")])[0]
                    return other, label
        return None

    def _error(self, msg):
        self.error_label.setText(msg)
        self.error_label.show()

    def result(self):
        return getattr(self, "_result", None)
