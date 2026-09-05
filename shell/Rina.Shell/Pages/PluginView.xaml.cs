using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// One plugin's page: what it told about itself.
/// </summary>
/// <remarks>
/// <para>
/// The version 2 schema renderer (<c>4.0-H02</c>) lives here, one for
/// everyone: both the plugin list and the plugin's own section in the
/// column show it. Two renderers of one schema would drift apart on the
/// first change — one would learn a new element kind, the other would not.
/// </para>
/// <para>
/// <b>A plugin does not draw — it describes.</b> Everything built here is
/// assembled from data that came from another process; not one line of the
/// plugin runs in this one.
/// </para>
/// </remarks>
public partial class PluginView : UserControl
{
    private readonly CoreLink? _link;
    private readonly string _plugin;

    /// <summary>Something went wrong — tell the host page about it.</summary>
    public event Action<string>? Noted;

    public PluginView(CoreLink? link, string pluginId)
    {
        InitializeComponent();
        _link = link;
        _plugin = pluginId;
        // Load on our own only if the host has not asked for it: the page
        // in the plugin list is drawn on demand, and a second pass would
        // cost an extra round over the wire.
        Loaded += async (_, _) => { if (!_drawn) await ReloadAsync(); };
    }

    /// <summary>How many elements are drawn — for the end-to-end check.</summary>
    public int ElementCount => Body.Children.Count;

    /// <summary>Re-read the page from the plugin.</summary>
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
    /// How far down the nesting the renderer goes.
    /// </summary>
    /// <remarks>
    /// The same number as in <c>plugins/page_spec.py</c>. The limit is not
    /// about beauty: the page description comes from another process, and
    /// "as many nested cards as you like" is a way to keep the shell busy
    /// drawing instead of answering a person.
    /// </remarks>
    private const int MaxDepth = 4;

    /// <summary>How many elements are drawn — for the end-to-end check.</summary>
    public int DrawnElements { get; private set; }

    /// <summary>
    /// The contents of a container.
    /// </summary>
    /// <remarks>
    /// An empty container is not drawn at all: a card with no contents is a
    /// frame around nothing, and it looks like a breakage that is not there.
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
    /// One element of a page description.
    /// </summary>
    /// <remarks>
    /// The kinds are taken from <c>plugins/page_spec.py</c>. An unfamiliar
    /// kind is not skipped: the plugin said something, and the shell is
    /// obliged to show it even when it does not know how — otherwise part
    /// of the page vanishes without a trace.
    /// </remarks>
    private FrameworkElement BuildElement(JsonObject element, int depth)
    {
        var kind = element["kind"]?.GetValue<string>() ?? "";
        var text = element["text"]?.GetValue<string>() ?? "";
        DrawnElements++;

        // We go no deeper, and we say so out loud: a page cut short in
        // silence looks like a page the plugin meant to be that way.
        if (depth >= MaxDepth)
            return new TextBlock
            {
                Text = S("[слишком глубокая вложенность]"),
                Style = (Style)FindResource("Text.Meta"),
            };

        switch (kind)
        {
            // --- containers (schema version 2, 4.0-H01) ---
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
                // "Side by side" is a request, not an order: `WrapPanel`
                // will stack the contents into a column by itself once
                // side by side no longer fits.
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
                    // A hint inside a field is a hint, not a value: what
                    // was left empty is not sent at all.
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
                // Enter is the same as pressing the button: a person who
                // has typed a line presses Enter rather than hunting for a
                // button with their eyes.
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
                // A state label. The colour is the shell's decision here:
                // the plugin said "warning", not "orange".
                var tone = element["variant"]?.GetValue<string>() ?? "normal";
                return new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource(
                        tone is "danger" or "warn" ? "C.Signal" : "C.FaceHigh"),
                    CornerRadius = new CornerRadius(3),   // предел системы
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
                // An unfamiliar kind is shown conspicuously and by name:
                // the plugin was built against a schema newer than the
                // shell, and skipping it in silence would make part of its
                // page invisible without a trace. What is ugly gets fixed;
                // what goes unnoticed does not.
                return new TextBlock
                {
                    Text = $"[{kind}] {text}",
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    ToolTip = S("оболочка не знает такого элемента страницы"),
                };
        }
    }

    /// <summary>Draw nothing: an empty container is a frame around nothing.</summary>
    private static FrameworkElement Nothing()
        => new StackPanel { Visibility = Visibility.Collapsed };


    /// <summary>
    /// A button was pressed or a line was submitted.
    /// </summary>
    /// <remarks>
    /// The answer carries a whole new page: a button changes what is drawn
    /// next to it, and asking a second time would mean showing it stale by
    /// exactly one round.
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
