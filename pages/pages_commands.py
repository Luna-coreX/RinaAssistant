from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    QLineEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from core.i18n import t as tr
from core.theme import Color, FONT_FAMILY, Radius
from components.card import Card
from components.toggle_switch import ToggleSwitch
from core.settings_store import settings
from core.app_signals import app_signals
from voice.commands import known_commands
from voice.user_commands import (
    UserCommandStore, type_label, type_icon
)


class CommandsPage(QWidget):
    """Список встроенных и пользовательских команд + конструктор."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = UserCommandStore(settings)
        self._filter = ""
        self._build()
        app_signals.commands_changed.connect(self._reload)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
            QScrollBar::handle:vertical {{
                background: {Color.SURFACE_1}; border-radius: 4px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {Color.SURFACE_2}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(18)

        layout.addLayout(self._header())
        layout.addWidget(self._search_bar())

        self._list_holder = QVBoxLayout()
        self._list_holder.setSpacing(14)
        layout.addLayout(self._list_holder)
        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

        self._reload()

    def _header(self):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(12)
        ic = QLabel("⚡")
        ic.setStyleSheet("font-size: 30px;")
        t = QLabel(tr("Команды"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(ic)
        row.addWidget(t)
        row.addStretch()

        add = QPushButton(tr("＋ Новая команда"))
        add.setCursor(Qt.PointingHandCursor)
        add.setFixedHeight(36)
        add.setStyleSheet(f"""
            QPushButton {{
                background: {Color.ACCENT}; color: #ffffff;
                border: none; border-radius: {Radius.SM}px;
                padding: 4px 18px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.MAUVE}; }}
        """)
        add.clicked.connect(self._open_builder_new)
        row.addWidget(add)

        sub = QLabel(tr("Голосовые и текстовые команды ассистента"))
        sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 13px;")
        box.addLayout(row)
        box.addWidget(sub)
        return box

    def _search_bar(self):
        bar = QLineEdit()
        bar.setPlaceholderText(tr("🔍  Поиск команды…"))
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"""
            QLineEdit {{
                background: {Color.CRUST}; color: {Color.TEXT};
                border: 1px solid {Color.SURFACE_0}; border-radius: {Radius.SM}px;
                padding: 4px 14px; font-size: 13px;
            }}
            QLineEdit:focus {{ border: 1px solid {Color.ACCENT}; }}
        """)
        bar.textChanged.connect(self._on_filter)
        return bar

    def _on_filter(self, text):
        self._filter = text.lower().strip()
        self._reload()

    def _clear(self):
        while self._list_holder.count():
            item = self._list_holder.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _match_filter(self, *texts):
        if not self._filter:
            return True
        return any(self._filter in str(t).lower() for t in texts)

    def _reload(self):
        self._clear()

        # --- пользовательские команды ---
        user_cmds = self.store.all()
        visible_user = [c for c in user_cmds
                        if self._match_filter(*(c.get("triggers", []) +
                                                [c.get("target", ""),
                                                 type_label(c.get("type"))]))]
        if visible_user:
            self._list_holder.addWidget(self._section(tr("Мои команды")))
            for c in visible_user:
                self._list_holder.addWidget(self._user_card(c))
        elif not self._filter:
            self._list_holder.addWidget(self._empty_hint())

        # --- встроенные ---
        builtin = [(name, desc) for name, desc in known_commands()
                   if self._match_filter(name, desc)]
        if builtin:
            self._list_holder.addWidget(self._section(tr("Встроенные команды")))
            card = Card()
            cl = card.layout()
            for i, (name, desc) in enumerate(builtin):
                cl.addWidget(self._builtin_row(name, desc))
                if i < len(builtin) - 1:
                    from components.controls import Divider
                    cl.addWidget(Divider())
            self._list_holder.addWidget(card)

    def _section(self, title):
        lbl = QLabel(title)
        lbl.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        lbl.setStyleSheet(f"color: {Color.SUBTEXT}; padding-top: 4px;")
        return lbl

    def _empty_hint(self):
        card = Card()
        lbl = QLabel(tr("У вас пока нет своих команд"))
        lbl.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        lbl.setStyleSheet(f"color: {Color.TEXT};")
        hint = QLabel(tr("Нажмите «Новая команда», чтобы создать запуск программы, ") +
                      tr("открытие папки или сайта, озвучку текста и не только."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 13px;")
        card.layout().addWidget(lbl)
        card.layout().addWidget(hint)
        return card

    def _builtin_row(self, name, desc):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 6, 0, 6)
        h.setSpacing(12)
        box = QVBoxLayout()
        box.setSpacing(2)
        n = QLabel(f"«{name}»")
        n.setStyleSheet(f"color: {Color.TEXT}; font-size: 13px; font-weight: 600;")
        d = QLabel(desc)
        d.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        box.addWidget(n)
        box.addWidget(d)
        h.addLayout(box, 1)
        tag = QLabel(tr("встроенная"))
        tag.setStyleSheet(f"""
            color: {Color.OVERLAY}; font-size: 10px;
            background: {Color.SURFACE_0}; border-radius: 6px; padding: 2px 8px;
        """)
        h.addWidget(tag, 0, Qt.AlignVCenter)
        return w

    def _user_card(self, cmd):
        card = Card()
        cl = card.layout()

        top = QHBoxLayout()
        top.setSpacing(12)
        icon = QLabel(type_icon(cmd.get("type")))
        icon.setStyleSheet("font-size: 24px;")
        icon.setFixedWidth(34)
        top.addWidget(icon, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        triggers = cmd.get("triggers", [])
        title = QLabel(triggers[0] if triggers else tr("(без фразы)"))
        title.setFont(QFont(FONT_FAMILY, 14, QFont.Bold))
        title.setStyleSheet(f"color: {Color.TEXT};")
        info.addWidget(title)

        meta = QLabel(f"{tr(type_label(cmd.get('type')))}  ·  {cmd.get('target','') or '—'}")
        meta.setStyleSheet(f"color: {Color.SUBTEXT}; font-size: 12px;")
        meta.setWordWrap(True)
        info.addWidget(meta)

        extra = []
        if len(triggers) > 1:
            extra.append(f"синонимы: {', '.join(triggers[1:])}")
        runs = self.store.stat(cmd.get("id"))
        if runs:
            extra.append(f"запусков: {runs}")
        if extra:
            e = QLabel("  ·  ".join(extra))
            e.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
            e.setWordWrap(True)
            info.addWidget(e)
        top.addLayout(info, 1)

        toggle = ToggleSwitch(checked=cmd.get("enabled", True))
        toggle.toggled.connect(
            lambda on, cid=cmd["id"]: self._toggle_cmd(cid, on))
        top.addWidget(toggle, 0, Qt.AlignVCenter)
        cl.addLayout(top)

        # кнопки действий
        actions = QHBoxLayout()
        actions.addStretch()
        run = self._mini_btn(tr("▶ Выполнить"), Color.GREEN)
        run.clicked.connect(lambda: self._run_cmd(cmd["id"]))
        edit = self._mini_btn(tr("✎ Изменить"), Color.BLUE)
        edit.clicked.connect(lambda: self._open_builder_edit(cmd))
        delete = self._mini_btn(tr("🗑 Удалить"), Color.RED)
        delete.clicked.connect(lambda: self._delete_cmd(cmd["id"]))
        actions.addWidget(run)
        actions.addWidget(edit)
        actions.addWidget(delete)
        cl.addLayout(actions)
        return card

    def _mini_btn(self, text, color):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedHeight(30)
        b.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {color};
                border: 1px solid {Color.alpha(color, '55')}; border-radius: 6px;
                padding: 2px 12px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.alpha(color, '22')}; border: 1px solid {color}; }}
        """)
        return b

    # ---------- действия ----------
    def _toggle_cmd(self, cid, on):
        self.store.set_enabled(cid, on)

    def _delete_cmd(self, cid):
        self.store.remove(cid)
        app_signals.commands_changed.emit()

    def _run_cmd(self, cid):
        app_signals.run_command.emit(cid)

    def _open_builder_new(self):
        from dialogs.command_builder import CommandBuilderDialog
        dlg = CommandBuilderDialog(self)
        if dlg.exec():
            self.store.add(dlg.result())
            app_signals.commands_changed.emit()

    def _open_builder_edit(self, cmd):
        from dialogs.command_builder import CommandBuilderDialog
        dlg = CommandBuilderDialog(self, command=cmd)
        if dlg.exec():
            self.store.update(dlg.result())
            app_signals.commands_changed.emit()


def build_commands_page():
    return CommandsPage()
