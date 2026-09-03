using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Страница одного плагина: то, что он о себе рассказал.
/// </summary>
/// <remarks>
/// <para>
/// Рендерер схемы версии 2 (<c>4.0-H02</c>) живёт здесь один на всех: его
/// показывает и список плагинов, и собственный раздел плагина в колонке.
/// Два рендерера одной схемы разъехались бы на первой же правке — один
/// научился бы новому виду, другой нет.
/// </para>
/// <para>
/// <b>Плагин не рисует — он описывает.</b> Всё, что здесь строится,
/// собрано из данных, пришедших из другого процесса; ни одной строки
/// плагина в этом процессе не выполняется.
/// </para>
/// </remarks>
public partial class PluginView : UserControl
{
    private readonly CoreLink? _link;
    private readonly string _plugin;

    /// <summary>Что-то пошло не так — сказать это странице-хозяйке.</summary>
    public event Action<string>? Noted;

    public PluginView(CoreLink? link, string pluginId)
    {
        InitializeComponent();
        _link = link;
        _plugin = pluginId;
        // Своя загрузка — только если хозяин не попросил её сам: страница
        // в списке плагинов рисуется по требованию, и второй заход стоил бы
        // лишнего круга по проводу.
        Loaded += async (_, _) => { if (!_drawn) await ReloadAsync(); };
    }

    /// <summary>Сколько элементов нарисовано — для сквозной проверки.</summary>
    public int ElementCount => Body.Children.Count;

    /// <summary>Перечитать страницу у плагина.</summary>
    public async Task ReloadAsync()
    {
        var got = await Ask(Methods.PluginsPage, new JsonObject
        {
            ["plugin_id"] = _plugin,
        });
        Draw(got);
    }

    private bool _drawn;

    private void Draw(JsonObject? page)
    {
        _drawn = true;
        Body.Children.Clear();
        DrawnElements = 0;
        if (page?["elements"] is not JsonArray elements) return;
        foreach (var element in elements.OfType<JsonObject>())
            Body.Children.Add(BuildElement(element, depth: 0));
    }

    /// <summary>
    /// Докуда рендерер спускается по вложенности.
    /// </summary>
    /// <remarks>
    /// То же число, что в <c>plugins/page_spec.py</c>. Ограничение не про
    /// красоту: описание страницы приходит из другого процесса, и «сколько
    /// угодно вложенных карточек» — способ занять оболочку рисованием
    /// вместо ответа человеку.
    /// </remarks>
    private const int MaxDepth = 4;

    /// <summary>Сколько элементов нарисовано — для сквозной проверки.</summary>
    public int DrawnElements { get; private set; }

    /// <summary>
    /// Содержимое контейнера.
    /// </summary>
    /// <remarks>
    /// Пустой контейнер не рисуется вовсе: карточка без содержимого — это
    /// рамка вокруг ничего, и выглядит она как поломка, которой нет.
    /// </remarks>
    private List<FrameworkElement> BuildChildren(JsonObject element, int depth)
    {
        var made = new List<FrameworkElement>();
        if (element["children"] is not JsonArray children) return made;
        foreach (var child in children.OfType<JsonObject>())
            made.Add(BuildElement(child, depth + 1));
        return made;
    }

    /// <summary>
    /// Один элемент описания страницы.
    /// </summary>
    /// <remarks>
    /// Виды взяты из <c>plugins/page_spec.py</c>. Незнакомый вид не
    /// пропускается: плагин что-то сказал, и оболочка обязана это показать,
    /// даже если не знает как, — иначе часть страницы исчезнет без следа.
    /// </remarks>
    private FrameworkElement BuildElement(JsonObject element, int depth)
    {
        var kind = element["kind"]?.GetValue<string>() ?? "";
        var text = element["text"]?.GetValue<string>() ?? "";
        DrawnElements++;

        // Глубже не спускаемся, и говорим об этом вслух: молча обрезанная
        // страница выглядит как страница, которую плагин так и задумал.
        if (depth >= MaxDepth)
            return new TextBlock
            {
                Text = S("[слишком глубокая вложенность]"),
                Style = (Style)FindResource("Text.Meta"),
            };

        switch (kind)
        {
            // --- контейнеры (схема версии 2, 4.0-H01) ---
            case "card":
                var inside = BuildChildren(element, depth);
                if (inside.Count == 0) return Nothing();
                var card = new Border
                {
                    Style = (Style)FindResource("Card"),
                    Margin = new Thickness(0, 0, 0, 8),
                };
                var body = new StackPanel();
                if (text.Length > 0)
                    body.Children.Add(new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Body"),
                        Margin = new Thickness(0, 0, 0, 6),
                    });
                foreach (var one in inside) body.Children.Add(one);
                card.Child = body;
                return card;

            case "group":
                var members = BuildChildren(element, depth);
                if (members.Count == 0) return Nothing();
                var group = new StackPanel { Margin = new Thickness(0, 0, 0, 16) };
                if (text.Length > 0)
                    group.Children.Add(new TextBlock
                    {
                        Text = text.ToUpperInvariant(),
                        Style = (Style)FindResource("Text.Section"),
                        Margin = new Thickness(0, 0, 0, 8),
                    });
                foreach (var one in members) group.Children.Add(one);
                return group;

            case "row":
                var side = BuildChildren(element, depth);
                if (side.Count == 0) return Nothing();
                // «Рядом» — просьба, а не приказ: `WrapPanel` сам поставит
                // содержимое столбиком, когда рядом уже не помещается.
                var row = new WrapPanel
                {
                    Orientation = Orientation.Horizontal,
                    Margin = new Thickness(0, 0, 0, 6),
                };
                foreach (var one in side)
                {
                    one.Margin = new Thickness(0, 0, 8, 6);
                    row.Children.Add(one);
                }
                return row;

            case "title":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Body"),
                    Margin = new Thickness(0, 0, 0, 8),
                };

            case "text":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Body"),
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(0, 0, 0, 6),
                };

            case "note":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(0, 0, 0, 6),
                };

            case "divider":
                return new Border
                {
                    Height = 1,
                    Margin = new Thickness(0, 10, 0, 10),
                    Background = (System.Windows.Media.Brush)FindResource("C.Seam"),
                };

            case "items":
                var list = new StackPanel { Margin = new Thickness(0, 0, 0, 6) };
                foreach (var one in element["items"]?.AsArray()
                                    ?? new JsonArray())
                    list.Children.Add(new TextBlock
                    {
                        Text = "· " + (one?.GetValue<string>() ?? ""),
                        Style = (Style)FindResource("Text.Body"),
                        TextWrapping = TextWrapping.Wrap,
                        Margin = new Thickness(0, 2, 0, 0),
                    });
                return list;

            case "button":
                var danger = element["variant"]?.GetValue<string>() == "danger";
                var button = new Button
                {
                    Style = (Style)FindResource(danger ? "Btn.Danger" : "Btn"),
                    Content = text,
                    HorizontalAlignment = HorizontalAlignment.Left,
                    Margin = new Thickness(0, 6, 0, 0),
                };
                var action = element["action"]?.GetValue<string>() ?? "";
                button.Click += async (_, _) => await ActAsync(action);
                return button;

            case "input":
                var typed = new TextBox
                {
                    Style = (Style)FindResource("Field"),
                    Width = 220,
                    Text = element["value"]?.GetValue<string>() ?? "",
                    // Подсказка внутри поля — это подсказка, а не значение:
                    // введённое пустым не отправляется вовсе.
                    Tag = text,
                };
                var send = new Button
                {
                    Style = (Style)FindResource("Btn"),
                    Content = element["variant"]?.GetValue<string>() is
                              { Length: > 0 } label ? label : S("Готово"),
                    Margin = new Thickness(8, 0, 0, 0),
                };
                var typedAction = element["action"]?.GetValue<string>() ?? "";
                async Task SendAsync()
                {
                    var written = typed.Text.Trim();
                    if (written.Length == 0) return;
                    typed.Clear();
                    await ActAsync(typedAction, written);
                }
                send.Click += async (_, _) => await SendAsync();
                // Enter — то же, что нажать кнопку: человек, набравший
                // строку, жмёт Enter, а не ищет глазами кнопку.
                typed.KeyDown += async (_, key) =>
                {
                    if (key.Key == System.Windows.Input.Key.Return)
                        await SendAsync();
                };
                var field = new StackPanel
                {
                    Orientation = Orientation.Horizontal,
                    Margin = new Thickness(0, 4, 0, 4),
                };
                field.Children.Add(typed);
                field.Children.Add(send);
                return field;

            case "badge":
                // Метка состояния. Цвет здесь решает оболочка: плагин
                // сказал «предупреждение», а не «оранжевый».
                var tone = element["variant"]?.GetValue<string>() ?? "normal";
                return new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource(
                        tone is "danger" or "warn" ? "C.Signal" : "C.FaceHigh"),
                    CornerRadius = new CornerRadius(10),
                    Padding = new Thickness(10, 3, 10, 3),
                    HorizontalAlignment = HorizontalAlignment.Left,
                    Margin = new Thickness(0, 2, 0, 2),
                    Child = new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Meta"),
                        Foreground = (System.Windows.Media.Brush)FindResource(
                            tone is "danger" or "warn" ? "C.Face" : "C.Ink"),
                    },
                };

            case "progress":
                var done = element["value"]?.GetValue<double>() ?? 0;
                var bar = new StackPanel { Margin = new Thickness(0, 4, 0, 6) };
                if (text.Length > 0)
                    bar.Children.Add(new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Meta"),
                        Margin = new Thickness(0, 0, 0, 4),
                    });
                var track = new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource("C.FaceSunk"),
                    CornerRadius = new CornerRadius(3),
                    Height = 6,
                    Width = 240,
                    HorizontalAlignment = HorizontalAlignment.Left,
                };
                track.Child = new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource("C.Signal"),
                    CornerRadius = new CornerRadius(3),
                    Width = Math.Max(0, Math.Min(1, done)) * 240,
                    HorizontalAlignment = HorizontalAlignment.Left,
                };
                bar.Children.Add(track);
                return bar;

            case "table":
                var grid = new Grid { Margin = new Thickness(0, 4, 0, 8) };
                var rows = element["items"]?.AsArray() ?? [];
                var headers = element["value"]?.AsArray();
                var width = Math.Max(
                    headers?.Count ?? 0,
                    rows.OfType<JsonArray>().Select(r => r.Count)
                        .DefaultIfEmpty(0).Max());
                if (width == 0) return Nothing();

                for (var column = 0; column < width; column++)
                    grid.ColumnDefinitions.Add(new ColumnDefinition
                    {
                        Width = new GridLength(1, GridUnitType.Star),
                    });

                var line = 0;
                if (headers is not null && headers.Count > 0)
                {
                    grid.RowDefinitions.Add(new RowDefinition
                    {
                        Height = GridLength.Auto,
                    });
                    for (var column = 0; column < headers.Count; column++)
                    {
                        var head = new TextBlock
                        {
                            Text = headers[column]?.GetValue<string>() ?? "",
                            Style = (Style)FindResource("Text.Section"),
                            Margin = new Thickness(0, 0, 8, 4),
                        };
                        Grid.SetRow(head, 0);
                        Grid.SetColumn(head, column);
                        grid.Children.Add(head);
                    }
                    line = 1;
                }

                foreach (var one in rows.OfType<JsonArray>())
                {
                    grid.RowDefinitions.Add(new RowDefinition
                    {
                        Height = GridLength.Auto,
                    });
                    for (var column = 0; column < one.Count; column++)
                    {
                        var cell = new TextBlock
                        {
                            Text = one[column]?.GetValue<string>() ?? "",
                            Style = (Style)FindResource("Text.Body"),
                            Margin = new Thickness(0, 0, 8, 2),
                            TextTrimming = TextTrimming.CharacterEllipsis,
                        };
                        Grid.SetRow(cell, line);
                        Grid.SetColumn(cell, column);
                        grid.Children.Add(cell);
                    }
                    line++;
                }
                return grid;

            default:
                // Незнакомый вид показывается заметно и с именем: плагин
                // собран под схему новее оболочки, и молчаливый пропуск
                // сделал бы часть его страницы невидимой без следа. Чинят
                // некрасивое; незаметное не чинят.
                return new TextBlock
                {
                    Text = $"[{kind}] {text}",
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    ToolTip = S("оболочка не знает такого элемента страницы"),
                };
        }
    }

    /// <summary>Ничего не рисуем: пустой контейнер — рамка вокруг ничего.</summary>
    private static FrameworkElement Nothing()
        => new StackPanel { Visibility = Visibility.Collapsed };


    /// <summary>
    /// Нажали кнопку или отправили строку.
    /// </summary>
    /// <remarks>
    /// Ответ несёт новую страницу целиком: кнопка меняет то, что нарисовано
    /// рядом с ней, и спрашивать второй раз значило бы показать её
    /// устаревшей ровно на один круг.
    /// </remarks>
    private async Task ActAsync(string action, string? value = null)
    {
        var payload = new JsonObject
        {
            ["plugin_id"] = _plugin,
            ["action"] = action,
        };
        if (value is not null) payload["value"] = value;
        Draw(await Ask(Methods.PluginsAction, payload));
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        if (!connection.MayCall(method))
        {
            Noted?.Invoke(S("Ядро не объявило возможность «плагины»."));
            return null;
        }
        try
        {
            var answer = await connection.CallAsync(method, payload,
                                                    TimeSpan.FromSeconds(20));
            if (answer.IsError) { Noted?.Invoke(answer.ErrorMessage); return null; }
            return answer.Payload;
        }
        catch (Exception error) { Noted?.Invoke(error.Message); return null; }
    }
}
