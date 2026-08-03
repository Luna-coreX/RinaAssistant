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
from voice.user_commands import UserCommandStore, type_label


class CommandsPage(QWidget):
    """Список встроенных и пользовательских команд + конструктор."""

    # индекс программ пересобирается в фоне — результат возвращаем сигналом
    index_refreshed = Signal(int)

    # сколько найденных программ показывать без фильтра: их больше тысячи,
    # список целиком бесполезен и тормозит отрисовку
    PROGRAMS_PREVIEW = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = UserCommandStore(settings)
        self._filter = ""
        self._build()
        app_signals.commands_changed.connect(self._reload)
        self.index_refreshed.connect(self._on_index_refreshed)

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
        t = QLabel(tr("Команды"))
        t.setFont(QFont(FONT_FAMILY, 24, QFont.Bold))
        t.setStyleSheet(f"color: {Color.TEXT};")
        row.addWidget(t)
        row.addStretch()

        add = QPushButton(tr("Новая команда"))
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
        bar.setPlaceholderText(tr("Поиск команды…"))
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

        # --- программы, показанные вручную ---
        learned = self._learned_card()
        if learned is not None:
            self._list_holder.addWidget(self._section(tr("Запомненные программы")))
            self._list_holder.addWidget(learned)

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

        # --- найденные программы ---
        self._list_holder.addWidget(self._programs_card())

    # ---------- запомненные программы ----------
    def _learned_card(self):
        """
        Программы, которые пользователь показал сам («укажи путь») или выбрал
        в уточняющем вопросе. Управлять ими логично здесь, рядом с командами,
        а не только скопом в настройках.
        """
        from components.controls import Divider

        aliases = settings.get("app_aliases", {}) or {}
        rows = []
        for phrase, data in sorted(aliases.items()):
            if isinstance(data, str):       # старый формат
                data = {"path": data, "name": ""}
            name = data.get("name") or data.get("path", "")
            if self._match_filter(phrase, name):
                rows.append((phrase, name))
        if not rows:
            return None

        card = Card()
        cl = card.layout()
        note = QLabel(tr("Рина запомнила, что вы имеете в виду под этими словами."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
        cl.addWidget(note)

        for i, (phrase, name) in enumerate(rows):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 6, 0, 6)
            h.setSpacing(12)

            box = QVBoxLayout()
            box.setSpacing(2)
            title = QLabel(f"«{phrase}»")
            title.setStyleSheet(
                f"color: {Color.TEXT}; font-size: 13px; font-weight: 600;")
            sub = QLabel(name)
            sub.setWordWrap(True)
            sub.setStyleSheet(f"color: {Color.OVERLAY}; font-size: 11px;")
            box.addWidget(title)
            box.addWidget(sub)
            h.addLayout(box, 1)

            forget = self._mini_btn(tr("Забыть"), Color.RED)
            forget.clicked.connect(
                lambda _checked=False, p=phrase: self._forget_alias(p))
            h.addWidget(forget, 0, Qt.AlignVCenter)

            cl.addWidget(row)
            if i < len(rows) - 1:
                cl.addWidget(Divider())
        return card

    def _forget_alias(self, phrase):
        from voice import app_launcher
        app_launcher.forget(phrase)
        self._reload()

    # ---------- найденные программы ----------
    def _programs_card(self):
        """
        Что Рина нашла на компьютере и может запускать голосом.
        Список большой, поэтому без фильтра показываем только начало.
        """
        from voice import app_index

        card = Card()
        cl = card.layout()

        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel(tr("Найденные программы"))
        title.setFont(QFont(FONT_FAMILY, 13, QFont.Bold))
        title.setStyleSheet(f"color: {Color.SUBTEXT};")
        head.addWidget(title)
        head.addStretch()

        self.reindex_btn = QPushButton(tr("Обновить список"))
        self.reindex_btn.setCursor(Qt.PointingHandCursor)
        self.reindex_btn.setFixedHeight(30)
        self.reindex_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Color.SURFACE_0}; color: {Color.TEXT};
                border: none; border-radius: {Radius.SM}px;
                padding: 2px 14px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {Color.SURFACE_1}; }}
            QPushButton:disabled {{ color: {Color.OVERLAY}; }}
        """)
        self.reindex_btn.clicked.connect(self._refresh_index)
        head.addWidget(self.reindex_btn)
        cl.addLayout(head)

        entries = app_index.get_index()
        if self._filter:
            shown = app_index.find(self._filter, limit=30, entries=entries)
            note = (tr("Совпадений: {count}", count=len(shown)) if shown
                    else tr("Ничего не найдено по запросу"))
        else:
            shown = entries[:self.PROGRAMS_PREVIEW]
            note = tr("Всего найдено: {count}. Скажите «запусти» и название — "
                      "искать в списке не нужно.", count=len(entries))

        self.programs_note = QLabel(note)
        self.programs_note.setWordWrap(True)
        self.programs_note.setStyleSheet(
            f"color: {Color.OVERLAY}; font-size: 11px;")
        cl.addWidget(self.programs_note)

        if shown:
            grid = QLabel(",   ".join(e.name for e in shown))
            grid.setWordWrap(True)
            grid.setStyleSheet(f"color: {Color.TEXT}; font-size: 12px;")
            cl.addWidget(grid)
        return card

    def _refresh_index(self):
        from voice import app_index
        self.reindex_btn.setEnabled(False)
        self.reindex_btn.setText(tr("Ищу…"))
        app_index.refresh_async(
            lambda entries: self.index_refreshed.emit(len(entries)))

    def _on_index_refreshed(self, _count):
        # список пересобираем целиком — заодно обновится и счётчик
        self._reload()

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
        run = self._mini_btn(tr("Выполнить"), Color.GREEN)
        run.clicked.connect(lambda: self._run_cmd(cmd["id"]))
        edit = self._mini_btn(tr("Изменить"), Color.BLUE)
        edit.clicked.connect(lambda: self._open_builder_edit(cmd))
        delete = self._mini_btn(tr("Удалить"), Color.RED)
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
