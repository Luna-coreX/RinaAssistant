# Шрифты

Три гарнитуры едут внутри программы — не как надежда на то, что они
установлены, а как ресурсы сборки (`shell/Rina.Shell/Rina.Shell.csproj`,
раздел `Fonts`). Раз они распространяются вместе с ней, вместе с ней
должно ехать и это.

Все три под **SIL Open Font License, Version 1.1**. Лицензия разрешает
использование, изменение и распространение, в том числе в составе другой
программы; требует сохранять уведомление об авторских правах и саму
лицензию и запрещает продавать шрифты отдельно.

Уведомления взяты из самих файлов (таблица `name`, записи 0, 9, 13, 14),
а не написаны по памяти.

| Гарнитура | Где применяется | Авторские права | Авторы |
|---|---|---|---|
| **Unbounded** | крупные заголовки, имя программы, знакомство | Copyright 2022 The Unbounded Project Authors (https://github.com/googlefonts/unbounded) | Luke Prowse, Jean-Baptiste Morizot, Fátima Lázaro, Florian Runge |
| **Onest** | почти весь интерфейс | Copyright 2021 The Onest Project Authors (https://github.com/simpals/onest) | Dmitri Voloshin, Andrey Kudryavtsev |
| **Geologica** | показания: цифры, версии, значения | Copyright 2020 The Geologica Project Authors (https://github.com/googlefonts/geologica) | Sindre Bremnes, Frode Helland |

Полный текст лицензии: <https://openfontlicense.org> (для Unbounded и
Geologica в файлах указан прежний адрес <https://scripts.sil.org/OFL> —
это тот же документ).

**Полного текста `OFL.txt` здесь пока нет.** Он должен лежать рядом с
шрифтами и попадать в поставку; положить его — при подготовке
публикации (`4.0b-D02`). До тех пор эта таблица выполняет ту часть
требования, которая касается уведомления об авторских правах, но не
всю его.

## Что едет в сборке, а что просто лежит

В сборку взяты те начертания, которые называют роли текста в
`docs/design/tokens.json`: Light, Regular, Medium, SemiBold, Bold — и
только Light, Regular, Medium у Unbounded, потому что им набраны одни
заголовки. Остальные файлы (в том числе `Geologica_Auto` и
`Geologica_Cursive`) лежат здесь как исходники и в программу не
попадают: по мегабайту за начертание, которого никто не просит.
