/* Порождено tools/gen_site.py по docs/golden/utterances.json.
 * Руками не править.
 *
 * Это записанные фразы программы — те же, которыми закреплён
 * её разбор. Макет ничего не выдумывает: он показывает то,
 * что по этой фразе поняла настоящая Рина. */

window.RINA_CASES = [
 {
  "id": "app.launch.plain.1",
  "say": "запусти телеграм",
  "intent": "app.launch",
  "args": {
   "app": "Telegram Desktop"
  },
  "state": "сделала",
  "said": "Открываю Telegram Desktop.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.plain.2",
  "say": "открой телеграм",
  "intent": "app.launch",
  "args": {
   "app": "Telegram Desktop"
  },
  "state": "сделала",
  "said": "Открываю Telegram Desktop.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.plain.3",
  "say": "запусти telegram",
  "intent": "app.launch",
  "args": {
   "app": "Telegram Desktop"
  },
  "state": "сделала",
  "said": "Открываю Telegram Desktop.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.plain.4",
  "say": "включи телеграм",
  "intent": "app.launch",
  "args": {
   "app": "Telegram Desktop"
  },
  "state": "сделала",
  "said": "Открываю Telegram Desktop.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.translit.chrome",
  "say": "запусти хром",
  "intent": "app.launch",
  "args": {
   "app": "Google Chrome"
  },
  "state": "сделала",
  "said": "Открываю Google Chrome.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.translit.discord",
  "say": "открой дискорд",
  "intent": "app.launch",
  "args": {
   "app": "Discord"
  },
  "state": "сделала",
  "said": "Открываю Discord.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.translit.blender",
  "say": "запусти блендер",
  "intent": "app.launch",
  "args": {
   "app": "Blender"
  },
  "state": "сделала",
  "said": "Открываю Blender.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.translit.steam",
  "say": "открой стим",
  "intent": "app.launch",
  "args": {
   "app": "Steam"
  },
  "state": "сделала",
  "said": "Открываю Steam.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.translit.firefox",
  "say": "запусти файрфокс",
  "intent": "app.launch",
  "args": {
   "app": "Mozilla Firefox"
  },
  "state": "сделала",
  "said": "Открываю Mozilla Firefox.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.partial.obs",
  "say": "запусти obs",
  "intent": "app.launch",
  "args": {
   "app": "OBS Studio"
  },
  "state": "сделала",
  "said": "Открываю OBS Studio.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.partial.code",
  "say": "запусти vs code",
  "intent": "app.not_found",
  "args": {},
  "state": "не нашла",
  "said": "Такой программы в указателе нет.",
  "heavy": false,
  "note": "сокращение «vs code» индекс не связывает с «Visual Studio Code» — предел поиска в 3.1.0, не дефект"
 },
 {
  "id": "app.launch.uwp",
  "say": "открой калькулятор",
  "intent": "app.launch",
  "args": {
   "app": "Калькулятор"
  },
  "state": "сделала",
  "said": "Открываю Калькулятор.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.role.browser",
  "say": "запусти браузер",
  "intent": "app.launch",
  "args": {},
  "state": "сделала",
  "said": "Открываю .",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.polite",
  "say": "рина открой дискорд",
  "intent": "app.launch",
  "args": {
   "app": "Discord"
  },
  "state": "сделала",
  "said": "Открываю Discord.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.filler",
  "say": "открой мне пожалуйста стим",
  "intent": "app.launch",
  "args": {
   "app": "Steam"
  },
  "state": "сделала",
  "said": "Открываю Steam.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.launch.wake",
  "say": "Рина, запусти телеграм",
  "intent": "app.launch",
  "args": {
   "app": "Telegram Desktop"
  },
  "state": "сделала",
  "said": "Открываю Telegram Desktop.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.notfound.1",
  "say": "запусти фотошоп",
  "intent": "app.not_found",
  "args": {},
  "state": "не нашла",
  "said": "Такой программы в указателе нет.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.notfound.2",
  "say": "открой майкрософт ворд",
  "intent": "app.not_found",
  "args": {},
  "state": "не нашла",
  "said": "Такой программы в указателе нет.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "app.notfound.3",
  "say": "запусти абракадабра",
  "intent": "app.not_found",
  "args": {},
  "state": "не нашла",
  "said": "Такой программы в указателе нет.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.1",
  "say": "поставь таймер на 10 минут",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.2",
  "say": "засеки 5 минут",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.3",
  "say": "таймер на полчаса",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.4",
  "say": "поставь таймер на 1 час 30 минут",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.5",
  "say": "засеки пять секунд",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.timer.6",
  "say": "рина засеки 2 часа 15 минут",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.remind.1",
  "say": "напомни через 15 минут выключить духовку",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "text": "выключить духовку"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.remind.2",
  "say": "напомни через полчаса позвонить маме",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.remind.3",
  "say": "напомнить через час про встречу",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.remind.4",
  "say": "напомни через 20 минут проверить тесты",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.alarm.1",
  "say": "разбуди в 7:30",
  "intent": "reminder.create",
  "args": {
   "kind": "alarm"
  },
  "state": "поставила",
  "said": "Будильник поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.alarm.2",
  "say": "поставь будильник на 9 утра",
  "intent": "reminder.create",
  "args": {
   "kind": "alarm"
  },
  "state": "поставила",
  "said": "Будильник поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.alarm.3",
  "say": "разбуди меня в 6 00",
  "intent": "reminder.create",
  "args": {
   "kind": "alarm"
  },
  "state": "поставила",
  "said": "Будильник поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.list.empty.1",
  "say": "какие таймеры",
  "intent": "reminder.list",
  "args": {
   "empty": true
  },
  "state": "ответила",
  "said": "Пока ничего не заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.list.empty.2",
  "say": "мои напоминания",
  "intent": "reminder.list",
  "args": {
   "empty": true
  },
  "state": "ответила",
  "said": "Пока ничего не заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.list.empty.3",
  "say": "что запланировано",
  "intent": "reminder.list",
  "args": {
   "empty": true
  },
  "state": "ответила",
  "said": "Пока ничего не заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.list.empty.4",
  "say": "список напоминаний",
  "intent": "reminder.list",
  "args": {
   "empty": true
  },
  "state": "ответила",
  "said": "Пока ничего не заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.cancel.empty.1",
  "say": "отмени все таймеры",
  "intent": "reminder.cancel",
  "args": {
   "empty": true
  },
  "state": "отменила",
  "said": "Отменила всё, что было заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.cancel.empty.2",
  "say": "убери напоминания",
  "intent": "reminder.cancel",
  "args": {
   "empty": true
  },
  "state": "отменила",
  "said": "Отменила всё, что было заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.seq.create",
  "say": "поставь таймер на 10 минут",
  "intent": "reminder.create",
  "args": {
   "kind": "timer"
  },
  "state": "поставила",
  "said": "Таймер поставлен.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.seq.list",
  "say": "какие таймеры",
  "intent": "reminder.list",
  "args": {
   "empty": false
  },
  "state": "ответила",
  "said": "Пока ничего не заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.seq.cancel",
  "say": "отмени все таймеры",
  "intent": "reminder.cancel",
  "args": {
   "empty": false
  },
  "state": "отменила",
  "said": "Отменила всё, что было заведено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.up.1",
  "say": "громче",
  "intent": "system.action",
  "args": {
   "action": "volume_up"
  },
  "state": "сделала",
  "said": "Прибавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.up.2",
  "say": "прибавь звук",
  "intent": "system.action",
  "args": {
   "action": "volume_up"
  },
  "state": "сделала",
  "said": "Прибавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.up.3",
  "say": "увеличь громкость",
  "intent": "system.action",
  "args": {
   "action": "volume_up"
  },
  "state": "сделала",
  "said": "Прибавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.down.1",
  "say": "тише",
  "intent": "system.action",
  "args": {
   "action": "volume_down"
  },
  "state": "сделала",
  "said": "Убавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.down.2",
  "say": "убавь громкость",
  "intent": "system.action",
  "args": {
   "action": "volume_down"
  },
  "state": "сделала",
  "said": "Убавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.mute.1",
  "say": "выключи звук",
  "intent": "system.action",
  "args": {
   "action": "volume_mute"
  },
  "state": "сделала",
  "said": "Выключила звук",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.mute.2",
  "say": "приглуши",
  "intent": "system.action",
  "args": {
   "action": "volume_mute"
  },
  "state": "сделала",
  "said": "Выключила звук",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.media.next.1",
  "say": "следующий трек",
  "intent": "system.action",
  "args": {
   "action": "media_next"
  },
  "state": "сделала",
  "said": "Следующий трек",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.media.next.2",
  "say": "переключи трек",
  "intent": "system.action",
  "args": {
   "action": "media_next"
  },
  "state": "сделала",
  "said": "Следующий трек",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.media.prev.1",
  "say": "предыдущий трек",
  "intent": "system.action",
  "args": {
   "action": "media_prev"
  },
  "state": "сделала",
  "said": "Предыдущий трек",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.media.pause.1",
  "say": "поставь на паузу",
  "intent": "system.action",
  "args": {
   "action": "media_play_pause"
  },
  "state": "сделала",
  "said": "Пауза",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.media.pause.2",
  "say": "пауза",
  "intent": "system.action",
  "args": {
   "action": "media_play_pause"
  },
  "state": "сделала",
  "said": "Пауза",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.lock.1",
  "say": "заблокируй компьютер",
  "intent": "system.action",
  "args": {
   "action": "lock"
  },
  "state": "сделала",
  "said": "Заблокировала рабочий стол",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.lock.2",
  "say": "заблокируй экран",
  "intent": "system.action",
  "args": {
   "action": "lock"
  },
  "state": "сделала",
  "said": "Заблокировала рабочий стол",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.screenshot.1",
  "say": "сделай скриншот",
  "intent": "system.action",
  "args": {
   "action": "screenshot"
  },
  "state": "сделала",
  "said": "Сняла экран",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.screenshot.2",
  "say": "снимок экрана",
  "intent": "system.action",
  "args": {
   "action": "screenshot"
  },
  "state": "сделала",
  "said": "Сняла экран",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.confirm.shutdown",
  "say": "выключи компьютер",
  "intent": "system.confirm",
  "args": {
   "action": "shutdown"
  },
  "state": "переспросила",
  "said": "Выключить компьютер — это необратимо. Точно?",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.shutdown.yes",
  "say": "да",
  "intent": "system.action",
  "args": {
   "action": "shutdown"
  },
  "state": "сделала",
  "said": "Выключить компьютер",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.restart",
  "say": "перезагрузи компьютер",
  "intent": "system.confirm",
  "args": {
   "action": "restart"
  },
  "state": "переспросила",
  "said": "Перезагрузить компьютер — это необратимо. Точно?",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.restart.no",
  "say": "нет",
  "intent": "cancelled",
  "args": {},
  "state": "отменила",
  "said": "Хорошо, отменила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.confirm.sleep",
  "say": "усыпи компьютер",
  "intent": "system.confirm",
  "args": {
   "action": "sleep"
  },
  "state": "переспросила",
  "said": "Усыпить компьютер — это необратимо. Точно?",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.sleep.cancel",
  "say": "отмена",
  "intent": "cancelled",
  "args": {},
  "state": "отменила",
  "said": "Хорошо, отменила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.confirm.mixed",
  "say": "выключи пк",
  "intent": "system.confirm",
  "args": {
   "action": "shutdown"
  },
  "state": "переспросила",
  "said": "Выключить компьютер — это необратимо. Точно?",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.mixed.refusal_wins",
  "say": "нет, давай",
  "intent": "cancelled",
  "args": {},
  "state": "отменила",
  "said": "Хорошо, отменила.",
  "heavy": false,
  "note": "отказ проверяется раньше согласия — странность 3.1.0"
 },
 {
  "id": "system.confirm.dropped",
  "say": "выключи компьютер",
  "intent": "system.confirm",
  "args": {
   "action": "shutdown"
  },
  "state": "переспросила",
  "said": "Выключить компьютер — это необратимо. Точно?",
  "heavy": true,
  "note": ""
 },
 {
  "id": "system.confirm.dropped.unrelated",
  "say": "как тебя зовут",
  "intent": "builtin.answer",
  "args": {
   "topic": "name"
  },
  "state": "ответила",
  "said": "Меня зовут Рина.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.confirm.dropped.late_yes",
  "say": "да",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": "подтверждение исчезло на посторонней фразе — странность 3.1.0"
 },
 {
  "id": "system.volume.down.3",
  "say": "убавь звук",
  "intent": "system.action",
  "args": {
   "action": "volume_down"
  },
  "state": "сделала",
  "said": "Убавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "system.volume.regression.pair",
  "say": "убавь громкость",
  "intent": "system.action",
  "args": {
   "action": "volume_down"
  },
  "state": "сделала",
  "said": "Убавила громкость",
  "heavy": false,
  "note": "баг 3.1.0, найденный этим набором: нечёткое сравнение считало её похожей на «прибавь громкость», и громкость росла"
 },
 {
  "id": "system.priority.sound_not_power",
  "say": "выключи звук",
  "intent": "system.action",
  "args": {
   "action": "volume_mute"
  },
  "state": "сделала",
  "said": "Выключила звук",
  "heavy": false,
  "note": "длинные фразы проверяются раньше коротких"
 },
 {
  "id": "calc.mul.1",
  "say": "посчитай 15*12",
  "intent": "calc",
  "args": {
   "result": "180"
  },
  "state": "посчитала",
  "said": "180",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.mul.2",
  "say": "сколько будет 15 умножить на 12",
  "intent": "calc",
  "args": {
   "result": "180"
  },
  "state": "посчитала",
  "said": "180",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.add.1",
  "say": "2+2",
  "intent": "calc",
  "args": {
   "result": "4"
  },
  "state": "посчитала",
  "said": "4",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.add.2",
  "say": "посчитай 100 плюс 250",
  "intent": "calc",
  "args": {
   "result": "350"
  },
  "state": "посчитала",
  "said": "350",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.sub.1",
  "say": "вычисли 100 минус 37",
  "intent": "calc",
  "args": {
   "result": "63"
  },
  "state": "посчитала",
  "said": "63",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.div.1",
  "say": "раздели 100 на 4",
  "intent": "calc",
  "args": {
   "result": "25"
  },
  "state": "посчитала",
  "said": "25",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.percent.1",
  "say": "20% от 3000",
  "intent": "calc",
  "args": {
   "result": "600"
  },
  "state": "посчитала",
  "said": "600",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.percent.2",
  "say": "посчитай 20 процентов от 3000",
  "intent": "calc",
  "args": {
   "result": "600"
  },
  "state": "посчитала",
  "said": "600",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.zero",
  "say": "посчитай 10 / 0",
  "intent": "calc.zero_division",
  "args": {},
  "state": "отказалась",
  "said": "На ноль не делится.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "calc.not_a_calc",
  "say": "скинули 20 процентов от 3000 рублей беру",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": "обычная речь не перехватывается арифметикой"
 },
 {
  "id": "websearch.1",
  "say": "найди рецепт борща",
  "intent": "websearch",
  "args": {
   "query": "рецепт борща"
  },
  "state": "ищет",
  "said": "Ищу: рецепт борща.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "websearch.2",
  "say": "поищи погоду в москве",
  "intent": "websearch",
  "args": {},
  "state": "ищет",
  "said": "Ищу: .",
  "heavy": false,
  "note": ""
 },
 {
  "id": "websearch.3",
  "say": "загугли что такое ipc",
  "intent": "websearch",
  "args": {},
  "state": "ищет",
  "said": "Ищу: .",
  "heavy": false,
  "note": ""
 },
 {
  "id": "websearch.4",
  "say": "погугли курс доллара",
  "intent": "websearch",
  "args": {},
  "state": "ищет",
  "said": "Ищу: .",
  "heavy": false,
  "note": ""
 },
 {
  "id": "websearch.5",
  "say": "search for python asyncio",
  "intent": "websearch",
  "args": {},
  "state": "ищет",
  "said": "Ищу: .",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.name.1",
  "say": "как тебя зовут",
  "intent": "builtin.answer",
  "args": {
   "topic": "name"
  },
  "state": "ответила",
  "said": "Меня зовут Рина.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.name.2",
  "say": "твоё имя",
  "intent": "builtin.answer",
  "args": {
   "topic": "name"
  },
  "state": "ответила",
  "said": "Меня зовут Рина.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.name.3",
  "say": "what is your name",
  "intent": "builtin.answer",
  "args": {
   "topic": "name"
  },
  "state": "ответила",
  "said": "Меня зовут Рина.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.thanks.1",
  "say": "спасибо",
  "intent": "builtin.answer",
  "args": {
   "topic": "thanks"
  },
  "state": "ответила",
  "said": "Пожалуйста.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.thanks.2",
  "say": "благодарю",
  "intent": "builtin.answer",
  "args": {
   "topic": "thanks"
  },
  "state": "ответила",
  "said": "Пожалуйста.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.caps.1",
  "say": "что ты умеешь",
  "intent": "builtin.answer",
  "args": {
   "topic": "capabilities"
  },
  "state": "ответила",
  "said": "Открываю программы, ставлю таймеры, считаю, управляю системой.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "builtin.caps.2",
  "say": "твои возможности",
  "intent": "builtin.answer",
  "args": {
   "topic": "capabilities"
  },
  "state": "ответила",
  "said": "Открываю программы, ставлю таймеры, считаю, управляю системой.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "fallback.search.1",
  "say": "столица австралии",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "fallback.search.2",
  "say": "расскажи анекдот",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "fallback.search.3",
  "say": "почему небо голубое",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "fallback.none.always.1",
  "say": "Рина столица австралии",
  "intent": "fallback.none",
  "args": {},
  "state": "не поняла",
  "said": "Не узнала фразу, а искать в сети сейчас не буду.",
  "heavy": false,
  "note": "в режиме «всегда слушать» веб-поиск не делается"
 },
 {
  "id": "fallback.none.always.2",
  "say": "Рина расскажи анекдот",
  "intent": "fallback.none",
  "args": {},
  "state": "не поняла",
  "said": "Не узнала фразу, а искать в сети сейчас не буду.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "wake.bare.1",
  "say": "Рина",
  "intent": "ask.wake",
  "args": {},
  "state": "слушает",
  "said": "Да?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "wake.bare.2",
  "say": "рина!",
  "intent": "ask.wake",
  "args": {},
  "state": "слушает",
  "said": "Да?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "wake.bare.always",
  "say": "Рина",
  "intent": "silence",
  "args": {},
  "state": "промолчала",
  "said": "",
  "heavy": false,
  "note": "в режиме «всегда слушать» на голое слово активации не отвечаем"
 },
 {
  "id": "wake.missing.1",
  "say": "просто разговор в комнате",
  "intent": "silence",
  "args": {},
  "state": "промолчала",
  "said": "",
  "heavy": false,
  "note": ""
 },
 {
  "id": "wake.missing.2",
  "say": "выключи компьютер",
  "intent": "silence",
  "args": {},
  "state": "промолчала",
  "said": "",
  "heavy": false,
  "note": "без слова активации опасное не выполняется"
 },
 {
  "id": "wake.fuzzy.1",
  "say": "Рита запусти дискорд",
  "intent": "silence",
  "args": {},
  "state": "промолчала",
  "said": "",
  "heavy": false,
  "note": "«Рита» похожа на «Рина» лишь на 0.75 при пороге 0.8 — активации нет"
 },
 {
  "id": "wake.fuzzy.2",
  "say": "ирина громче",
  "intent": "system.action",
  "args": {
   "action": "volume_up"
  },
  "state": "сделала",
  "said": "Прибавила громкость",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.teach.rule",
  "say": "когда я говорю писалка, запускай Notepad",
  "intent": "alias.teach",
  "args": {
   "word": "писалка",
   "app": "Notepad"
  },
  "state": "запомнила",
  "said": "«писалка» — это Notepad. Запомнила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.teach.works",
  "say": "запусти писалка",
  "intent": "app.launch",
  "args": {
   "app": "Notepad"
  },
  "state": "сделала",
  "said": "Открываю Notepad.",
  "heavy": false,
  "note": "слово, которого индекс не знает: запуск возможен только через выученное"
 },
 {
  "id": "alias.teach.otkryvaj",
  "say": "когда я говорю мессенджер, открывай Telegram Desktop",
  "intent": "alias.teach",
  "args": {
   "word": "мессенджер",
   "app": "Telegram Desktop"
  },
  "state": "запомнила",
  "said": "«мессенджер» — это Telegram Desktop. Запомнила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.teach.eto",
  "say": "когда я говорю блендер, это Blender",
  "intent": "alias.teach",
  "args": {
   "word": "блендер",
   "app": "Blender"
  },
  "state": "запомнила",
  "said": "«блендер» — это Blender. Запомнила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.teach.uwp",
  "say": "когда я говорю счёты, запускай Калькулятор",
  "intent": "alias.teach",
  "args": {
   "word": "счёты",
   "app": "Калькулятор"
  },
  "state": "запомнила",
  "said": "«счёты» — это Калькулятор. Запомнила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.teach.uwp.works",
  "say": "запусти счёты",
  "intent": "app.launch",
  "args": {
   "app": "Калькулятор"
  },
  "state": "сделала",
  "said": "Открываю Калькулятор.",
  "heavy": false,
  "note": "у приложения Магазина вместо пути идентификатор — проверять его на диске нечего"
 },
 {
  "id": "alias.unknown",
  "say": "когда я говорю жаба, запускай Eclipse",
  "intent": "alias.unknown",
  "args": {
   "query": "Eclipse"
  },
  "state": "не нашла",
  "said": "«Eclipse» я не нашла — запоминать нечего.",
  "heavy": false,
  "note": "нечего запоминать — отказ, а не запись наугад"
 },
 {
  "id": "alias.ambiguous",
  "say": "когда я говорю среда, запускай visual studio",
  "intent": "alias.ambiguous",
  "args": {
   "word": "среда"
  },
  "state": "переспросила",
  "said": "Под «среда» подходит несколько: Visual Studio Code, Visual Studio 2022. Какую?",
  "heavy": false,
  "note": "выученное живёт годами: спрашиваем всегда, когда кандидатов больше одного"
 },
 {
  "id": "alias.fix.launch",
  "say": "запусти обс",
  "intent": "app.launch",
  "args": {
   "app": "OBS Studio"
  },
  "state": "сделала",
  "said": "Открываю OBS Studio.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.fix.correct",
  "say": "нет, я имел в виду Visual Studio 2022",
  "intent": "alias.teach",
  "args": {
   "word": "обс",
   "app": "Visual Studio 2022"
  },
  "state": "запомнила",
  "said": "«обс» — это Visual Studio 2022. Запомнила.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.fix.stale",
  "say": "нет, я имел в виду Discord",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": "поправка живёт один ход: прошлый ход её уже израсходовал, и цепляться ей больше не к чему"
 },
 {
  "id": "alias.fix.female.launch",
  "say": "запусти обс",
  "intent": "app.launch",
  "args": {
   "app": "OBS Studio"
  },
  "state": "сделала",
  "said": "Открываю OBS Studio.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "alias.fix.female",
  "say": "я имела в виду Visual Studio 2022",
  "intent": "alias.teach",
  "args": {
   "app": "Visual Studio 2022"
  },
  "state": "запомнила",
  "said": "«» — это Visual Studio 2022. Запомнила.",
  "heavy": false,
  "note": "род говорящего ничего не меняет и не должен"
 },
 {
  "id": "alias.fix.nothing",
  "say": "нет, я имел в виду Discord",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": "поправка без запуска перед ней ничего не выдумывает"
 },
 {
  "id": "reminder.when.tail",
  "say": "напомни проверить пиар когда открою visual studio code",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "on": "Visual Studio Code",
   "text": "проверить пиар"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.when.head",
  "say": "напомни когда открою obs studio включить микрофон",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "on": "OBS Studio",
   "text": "включить микрофон"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": "условие впереди дела: границу проводит индекс, запятых речь не даёт"
 },
 {
  "id": "reminder.when.short",
  "say": "напомни когда открою обс включить микрофон",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "on": "OBS Studio",
   "text": "включить микрофон"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": "«обс» уже однозначно, и «студио» из «обс студио» тоже часть названия, а не дела"
 },
 {
  "id": "reminder.when.greedy",
  "say": "напомни при запуске visual studio code слить ветку",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "on": "Visual Studio Code",
   "text": "слить ветку"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": "поиск нестрогий, и «visual studio code слить» находит то же, что без «слить»: лишнее слово не должно уехать в название и забрать у дела глагол"
 },
 {
  "id": "reminder.when.launch",
  "say": "напомни при запуске блендера размять шею",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "on": "Blender",
   "text": "размять шею"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.when.ambiguous",
  "say": "напомни когда открою visual studio проверить почту",
  "intent": "reminder.ambiguous",
  "args": {},
  "state": "переспросила",
  "said": "Программ с таким именем несколько: Visual Studio Code, Visual Studio 2022.",
  "heavy": false,
  "note": "привязка живёт до срабатывания, и ошибка в ней обнаружится тогда, когда на неё рассчитывали"
 },
 {
  "id": "reminder.when.unknown",
  "say": "напомни когда открою фотошоп что-нибудь",
  "intent": "reminder.unknown_app",
  "args": {},
  "state": "не нашла",
  "said": "К такой программе привязать нечего.",
  "heavy": false,
  "note": ""
 },
 {
  "id": "reminder.when.time_still_works",
  "say": "напомни через 20 минут проверить тесты",
  "intent": "reminder.create",
  "args": {
   "kind": "reminder",
   "text": "проверить тесты"
  },
  "state": "поставила",
  "said": "Напоминание поставлено.",
  "heavy": false,
  "note": "часы никуда не делись"
 },
 {
  "id": "degenerate.empty",
  "say": "",
  "intent": "silence",
  "args": {},
  "state": "промолчала",
  "said": "",
  "heavy": false,
  "note": ""
 },
 {
  "id": "degenerate.spaces",
  "say": "     ",
  "intent": "ask.wake",
  "args": {},
  "state": "слушает",
  "said": "Да?",
  "heavy": false,
  "note": "странность 3.1.0: пустая строка молчит, а строка из пробелов отвечает «Да? Слушаю.» — обрезка даёт пустую команду, а не пустой ввод"
 },
 {
  "id": "degenerate.punctuation",
  "say": "?!.,;",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "degenerate.emoji",
  "say": "🙂🙃",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "degenerate.long",
  "say": "ааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааааа",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "degenerate.number",
  "say": "42",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": ""
 },
 {
  "id": "degenerate.big_power",
  "say": "посчитай 2**2**2**2**2",
  "intent": "fallback.search",
  "args": {},
  "state": "переспросила",
  "said": "Не узнала фразу. Поискать в сети?",
  "heavy": false,
  "note": "степень ограничена — выражение не считается"
 }
];
window.RINA_CHIPS = ["app.launch.plain.2", "reminder.timer.1", "calc.mul.2", "system.volume.up.1", "system.confirm.shutdown", "alias.teach.rule", "builtin.name.1"];
