# -*- coding: utf-8 -*-
"""
Сборка макетов экранов (задача плана 4.0-R05).

Оболочки на WPF ещё нет, а экраны нужно увидеть и проверить до того, как
XAML написан. Макет собирается **из tokens.json**, а не рисуется отдельно:
иначе макет и система разойдутся, и спорить будет не с чем.

Это макет для рассмотрения, а не реализация. HTML взят потому, что его видно
без сборки; ни одна строка отсюда в оболочку не переедет.

Запуск:
    python tools/build_mockups.py
    -> docs/design/mockups.html
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS = os.path.join(ROOT, "docs", "design", "tokens.json")
OUT = os.path.join(ROOT, "docs", "design", "mockups.html")


def css_vars(colors, prefix="--c-"):
    return "\n".join(f"      {prefix}{k.lower().replace('_','-')}: {v};"
                     for k, v in colors.items())


def build():
    tokens = json.load(open(TOKENS, encoding="utf-8"))
    silver = tokens["finishes"]["silver"]["color"]
    black = tokens["finishes"]["black"]["color"]
    space = tokens["space"]
    size = tokens["size"]
    radius = tokens["radius"]
    motion = tokens["motion"]
    hatch = tokens["hatch"]

    style = f"""
    :root {{
{css_vars(silver)}
      --sp-hair: {space['hair']}px;
      --sp-tight: {space['tight']}px;
      --sp-inner: {space['inner']}px;
      --sp-within: {space['within']}px;
      --sp-between: {space['between']}px;
      --sp-danger: {space['danger']}px;
      --radius: {radius['max']}px;
      --row: {size['row']}px;
      --control: {size['control']}px;
      --legend-col: {size['legend_column']}px;
      --strip: {size['level_strip']}px;
      --t-press: {motion['press']}ms;
      --t-state: {motion['state']}ms;
      --ease: {motion['easing']['default']};
      --ui: "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
      --mono: "Cascadia Mono", "Consolas", monospace;
    }}
    .black {{
{css_vars(black)}
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 40px;
      background: #141416; font-family: var(--ui);
      color: #cfcdc8; -webkit-font-smoothing: antialiased;
    }}
    h1 {{ font-size: 22px; font-weight: 600; letter-spacing: -.01em;
         margin: 0 0 8px; color: #efece7; }}
    .note {{ font-size: 13px; color: #8f8d87; margin: 0 0 28px;
             max-width: 720px; line-height: 1.6; }}
    .note code {{ font-family: var(--mono); font-size: 12px; }}
    .caption {{ font-size: 11px; letter-spacing: .10em; text-transform: uppercase;
                color: #6f6d68; margin: 40px 0 12px; font-weight: 600; }}

    /* ---------- каркас окна ---------- */
    .win {{
      width: 940px; background: var(--c-face); color: var(--c-ink);
      border-radius: 6px; overflow: hidden;
      display: grid; grid-template-rows: auto 1fr auto;
    }}
    .titlebar {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 var(--sp-within); height: var(--row);
      background: var(--c-face-low);
      font-size: 12px; font-weight: 500; color: var(--c-ink-soft);
    }}
    .wbtn {{ display: inline-block; width: 30px; text-align: center;
             font-style: normal; color: var(--c-ink-faint); }}
    .body {{ display: grid; grid-template-columns: var(--legend-col) 1fr;
             min-height: 470px; }}

    /* ---------- колонка разделов ---------- */
    .nav {{
      background: var(--c-face-low);
      display: flex; flex-direction: column; padding: var(--sp-tight) 0;
    }}
    .nav a {{
      display: block; padding: 0 var(--sp-within);
      height: var(--row); line-height: var(--row);
      font-size: 13px; font-weight: 500;
      color: var(--c-ink-soft); text-decoration: none;
      border-left: 2px solid transparent;
      transition: background var(--t-state) var(--ease);
    }}
    .nav a.on {{ color: var(--c-ink); background: var(--c-face);
                 border-left-color: var(--c-signal); }}
    .nav a.hover {{ background: var(--c-face-high); }}
    .nav .foot {{ margin-top: auto; padding: var(--sp-within);
                  font-size: 11px; color: var(--c-ink-faint); line-height: 1.7; }}
    .nav .foot b {{ display: block; font-family: var(--mono);
                    color: var(--c-ink-soft); font-weight: 400; }}

    /* ---------- содержимое ---------- */
    .pane {{ padding: var(--sp-between); display: flex; flex-direction: column;
             gap: var(--sp-between); overflow: hidden; }}
    .pane > .head {{
      font-size: 20px; font-weight: 600; letter-spacing: -.01em;
      color: var(--c-ink); margin: 0 0 calc(0px - var(--sp-within));
    }}
    .section > .legend {{
      font-size: 11px; letter-spacing: .10em; text-transform: uppercase;
      font-weight: 600; color: var(--c-ink-soft);
      margin-bottom: var(--sp-within);
    }}
    .rows {{ display: flex; flex-direction: column; gap: var(--sp-tight); }}
    .row {{ display: flex; align-items: center; justify-content: space-between;
            gap: var(--sp-within); min-height: var(--row); }}
    .row .label {{ font-size: 13px; }}
    .row .hint {{ font-size: 13px; color: var(--c-ink-soft); }}

    /* ---------- стекло ---------- */
    .glass {{
      background: var(--c-glass); color: var(--c-glass-text);
      border-radius: var(--radius); padding: var(--sp-within);
      flex: 1; display: flex; flex-direction: column; gap: var(--sp-within);
      font-size: 15px; line-height: 1.6; overflow: hidden;
    }}
    .turn {{ display: flex; gap: var(--sp-within); }}
    .turn .who {{ font-size: 11px; color: var(--c-glass-dim);
                  min-width: 46px; font-family: var(--mono);
                  line-height: 1.9; }}
    .turn .said {{ flex: 1; }}
    .turn.rina .said {{ color: var(--c-glass-text); }}

    /* ---------- управление ----------
       Второстепенная кнопка не нарисована коробкой: она заподлицо с панелью
       и проявляется при наведении. Заметность даёт единственная первичная
       кнопка, залитая чернилами, — иерархия без второго акцента. */
    .btn {{
      height: var(--control); padding: 0 var(--sp-within);
      background: transparent; color: var(--c-ink);
      border: 0; border-radius: var(--radius);
      font-family: var(--ui); font-size: 13px; font-weight: 500;
      cursor: default; white-space: nowrap;
      transition: background var(--t-press) var(--ease);
    }}
    .btn.hover {{ background: var(--c-face-high); }}
    .btn.press {{ background: var(--c-face-low); }}
    .btn.focus {{ outline: 2px solid var(--c-signal); outline-offset: 2px; }}
    .btn[disabled] {{ color: var(--c-ink-faint); }}
    .btn.primary {{ background: var(--c-ink); color: var(--c-face); }}
    .btn.danger {{
      margin-top: var(--sp-danger);
      background-image: repeating-linear-gradient(
        {hatch['angle']}deg,
        color-mix(in srgb, var(--c-hatch) {int(hatch['opacity'] * 100)}%, transparent) 0 {hatch['line']}px,
        transparent {hatch['line']}px {hatch['gap']}px);
    }}
    .field {{
      height: var(--control); flex: 1; padding: 0 var(--sp-inner);
      background: var(--c-face-sunk); color: var(--c-ink);
      border: 0; border-radius: var(--radius);
      font-family: var(--ui); font-size: 14px; line-height: var(--control);
    }}
    .field.placeholder {{ color: var(--c-ink-faint); }}
    .field.error {{ color: var(--c-signal); }}
    .toggle {{ width: 40px; height: 22px; border-radius: 11px; flex: none;
               background: var(--c-face-sunk); position: relative;
               transition: background var(--t-state) var(--ease); }}
    .toggle i {{ position: absolute; top: 4px; left: 4px;
                 width: 14px; height: 14px; border-radius: 50%;
                 background: var(--c-ink-faint); }}
    .toggle.on {{ background: var(--c-signal); }}
    .toggle.on i {{ left: auto; right: 4px; background: var(--c-face-high); }}
    .figure {{ font-family: var(--mono); font-size: 13px;
               font-variant-numeric: tabular-nums; }}
    .card {{
      border: 0; border-radius: var(--radius); min-height: 56px;
      background: var(--c-face-high); padding: var(--sp-inner) var(--sp-within);
      display: flex; align-items: center; gap: var(--sp-within);
    }}
    .card .grow {{ flex: 1; }}
    .card .title {{ font-size: 14px; }}
    .card .meta {{ font-size: 12px; color: var(--c-ink-soft); margin-top: 2px; }}
    .empty {{ font-size: 14px; color: var(--c-ink-soft);
              padding: var(--sp-between) 0; }}
    .bar {{ display: flex; gap: var(--sp-tight); align-items: center; }}
    .bar.wide {{ gap: var(--sp-within); }}

    /* ---------- полоса уровня ---------- */
    .strip {{ height: var(--strip); background: var(--c-face-sunk);
              position: relative; }}
    .strip i {{ position: absolute; inset: 0 62% 0 0;
                background: linear-gradient(90deg,
                  var(--c-signal), color-mix(in srgb, var(--c-signal) 25%, transparent)); }}
    .strip.idle i {{ inset: 0 92% 0 0; opacity: .35; }}

    .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px;
             align-items: start; }}
    """

    def win(finish_class, active, content, strip_class="", strip_note=""):
        nav_items = ["Диалог", "Команды", "Напоминания", "Плагины",
                     "Настройки"]
        nav = "".join(
            f'<a class="{"on" if n == active else ""}">{n}</a>'
            for n in nav_items)
        return f"""
    <div class="win {finish_class}">
      <div class="titlebar"><span>Rina Assistant</span>
        <span><i class="wbtn">–</i><i class="wbtn">▢</i><i class="wbtn">✕</i></span>
      </div>
      <div class="body">
        <div class="nav">{nav}
          <div class="foot">вид · о программе<b>4.0.0</b></div>
        </div>
        <div class="pane"><div class="head">{active}</div>{content}</div>
      </div>
      <div class="strip {strip_class}" title="{strip_note}"><i></i></div>
    </div>"""

    dialog = """
      <div class="glass">
        <div class="turn"><span class="who">20:41</span>
          <span class="said">запусти телеграм</span></div>
        <div class="turn rina"><span class="who">Рина</span>
          <span class="said">Запускаю Telegram Desktop.</span></div>
        <div class="turn"><span class="who">20:42</span>
          <span class="said">поставь таймер на 1 час 30 минут</span></div>
        <div class="turn rina"><span class="who">Рина</span>
          <span class="said">Засекла 1 ч 30 мин.</span></div>
      </div>
      <div class="bar wide">
        <span class="field placeholder">Скажите или напишите команду…</span>
        <button class="btn primary">Отправить</button>
      </div>
      <div class="bar wide">
        <span class="row" style="gap:10px"><span class="toggle on"><i></i></span>
          <span class="hint">Отвечать голосом</span></span>
        <span class="row" style="gap:10px"><span class="toggle"><i></i></span>
          <span class="hint">Всегда слушать</span></span>
      </div>"""

    commands = """
      <div class="section">
        <div class="legend">Мои команды</div>
        <div class="rows">
          <div class="card"><span class="grow"><span class="title">мой дискорд</span>
            <div class="meta">Программа · Discord</div></span>
            <span class="toggle on"><i></i></span>
            <button class="btn">Выполнить</button>
            <button class="btn">Удалить</button></div>
          <div class="card"><span class="grow"><span class="title">рабочее место</span>
            <div class="meta">Последовательность · 4 шага</div></span>
            <span class="toggle"><i></i></span>
            <button class="btn">Выполнить</button>
            <button class="btn">Удалить</button></div>
        </div>
      </div>
      <div class="section">
        <div class="legend">Найденные программы</div>
        <div class="bar wide"><span class="figure">124</span>
          <span class="hint">обновлено сегодня в 19:04</span>
          <button class="btn">Обновить</button></div>
      </div>
      <div class="bar"><button class="btn primary">Новая команда</button>
        <button class="btn">Импорт</button><button class="btn">Экспорт</button></div>"""

    reminders = """
      <div class="section">
        <div class="legend">Новое напоминание</div>
        <div class="bar wide"><span class="field placeholder">О чём напомнить…</span>
          <span class="field figure" style="max-width:72px">10</span>
          <span class="field" style="max-width:112px">минут</span>
          <button class="btn primary">Поставить</button></div>
      </div>
      <div class="section">
        <div class="legend">Запланировано · 2</div>
        <div class="rows">
          <div class="card"><span class="grow"><span class="title">Таймер</span>
            <div class="meta">проверить тесты</div></span>
            <span class="figure">09:59</span>
            <button class="btn">Отменить</button></div>
          <div class="card"><span class="grow"><span class="title">Будильник</span>
            <div class="meta">подъём</div></span>
            <span class="figure">07:30</span>
            <button class="btn">Отменить</button></div>
        </div>
      </div>"""

    settings = """
      <div class="section">
        <div class="legend">Голос</div>
        <div class="rows">
          <div class="row"><span class="label">Система синтеза</span>
            <span class="field" style="max-width:280px">Edge Neural</span></div>
          <div class="row"><span class="label">Распознавание</span>
            <span class="field" style="max-width:280px">Vosk (офлайн)</span></div>
          <div class="row"><span class="label">Слова активации</span>
            <span class="field" style="max-width:280px">Рина, Rina</span></div>
          <div class="row"><span class="label">Проверка голоса</span>
            <button class="btn">Проверить</button></div>
        </div>
      </div>
      <div class="section">
        <div class="legend">Приватность</div>
        <div class="rows">
          <div class="row"><span class="label">Сохранять историю</span>
            <span class="toggle on"><i></i></span></div>
          <div class="row"><span class="label">Записывать тексты реплик</span>
            <span class="toggle"><i></i></span></div>
          <div class="row"><span class="label">Подробность журнала</span>
            <span class="field" style="max-width:160px">INFO</span></div>
        </div>
        <button class="btn danger">Сбросить настройки</button>
      </div>"""

    plugins = """
      <div class="section">
        <div class="legend">Установленные</div>
        <div class="rows">
          <div class="card"><span class="grow"><span class="title">Заметки</span>
            <div class="meta">v1.0.0 · вкладка, настройки</div></span>
            <span class="toggle on"><i></i></span></div>
          <div class="card"><span class="grow"><span class="title">Часы</span>
            <div class="meta">v1.0.0</div></span>
            <span class="toggle"><i></i></span></div>
          <div class="card"><span class="grow"><span class="title">Кубик</span>
            <div class="meta">v1.0.0 · манифест повреждён</div></span>
            <span class="toggle"><i></i></span></div>
        </div>
      </div>
      <div class="bar"><button class="btn primary">Из папки</button>
        <button class="btn">Из архива</button>
        <button class="btn" disabled>Обновить…</button></div>"""

    states = """
      <div class="section">
        <div class="legend">Состояния органа управления</div>
        <div class="bar">
          <button class="btn">Обычное</button>
          <button class="btn hover">Наведение</button>
          <button class="btn press">Нажатие</button>
          <button class="btn focus">Фокус</button>
          <button class="btn" disabled>Выключено</button>
          <button class="btn primary">Первичная</button>
        </div>
      </div>
      <div class="section">
        <div class="legend">Поле</div>
        <div class="bar wide">
          <span class="field">значение</span>
          <span class="field placeholder">подсказка</span>
          <span class="field error">не удалось проверить связь</span>
        </div>
      </div>
      <div class="section">
        <div class="legend">Пусто</div>
        <div class="empty">Ничего не запланировано.</div>
      </div>
      <div class="section">
        <div class="legend">Необратимое</div>
        <button class="btn danger">Выключить компьютер</button>
      </div>"""

    screens = [
        ("Диалог — история и есть главный экран", "Диалог", dialog, "", "слушает"),
        ("Команды", "Команды", commands, "idle", "покой"),
        ("Напоминания", "Напоминания", reminders, "idle", "покой"),
        ("Плагины", "Плагины", plugins, "idle", "покой"),
        ("Настройки", "Настройки", settings, "idle", "покой"),
    ]

    blocks = []
    for caption, active, content, strip, note in screens:
        blocks.append(f'<div class="caption">{caption}</div>'
                      f'<div class="pair">{win("", active, content, strip, note)}'
                      f'{win("black", active, content, strip, note)}</div>')

    blocks.append('<div class="caption">Состояния и краевые случаи (4.0-R06)'
                  '</div><div class="pair">'
                  + win("", "Настройки", states, "idle")
                  + win("black", "Настройки", states, "idle") + "</div>")

    html = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Макеты 4.0 — «Аппарат»</title>
<style>{style}</style></head>
<body>
<h1>Макеты 4.0 — «Аппарат»</h1>
<p class="note">Задача плана 4.0-R05. Собрано из
<code>docs/design/tokens.json</code>: значения не набраны руками, поэтому
макет и дизайн-система разойтись не могут. Слева отделка «серебро», справа
«чёрное» — не режимы, а два исполнения одного прибора.
Это макет для рассмотрения; ни одна строка отсюда в оболочку не переедет.</p>
{''.join(blocks)}
</body></html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"собрано: {os.path.relpath(OUT, ROOT)}")
    print(f"  экранов: {len(screens)} по 2 отделки + состояния")
    return 0


if __name__ == "__main__":
    sys.exit(build())
