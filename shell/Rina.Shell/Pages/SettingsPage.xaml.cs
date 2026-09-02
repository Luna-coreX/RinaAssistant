using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

namespace Rina.Shell.Pages;

/// <summary>
/// Настройки: десять секций одной панелью.
/// </summary>
/// <remarks>
/// <para>
/// Здесь встречаются две половины [ADR 0006](../../../docs/adr/0006-settings-ownership.md).
/// Ядро прислало смысл — тип, умолчание, перечисление, диапазон, зависимость,
/// признак «нужен перезапуск». Оболочка знает вид — подписи и секции
/// (<see cref="SettingsLayout"/>). Ни одна половина не может быть выведена
/// из другой, и в этом всё решение.
/// </para>
/// <para>
/// <b>Зависимые поля гаснут, а не прячутся.</b> «Адрес модели» при
/// выключенной модели бесполезен, но спрятать его значит заставить человека
/// гадать, куда он делся. Выключенное обязано читаться как выключенное, а не
/// как отсутствующее — то же правило, что и в дизайн-системе про контраст.
/// </para>
/// <para>
/// <b>Предупреждение — не отказ.</b> «Адрес не локальный» значит, что
/// значение записано, а человеку сказано, чем это обернётся. Решать ему.
/// </para>
/// </remarks>
public partial class SettingsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly Dictionary<string, JsonObject> _schema = [];
    private readonly Dictionary<string, JsonNode?> _values = [];
    private readonly Dictionary<string, FrameworkElement> _editors = [];

    /// <summary>Сколько секций построено — для сквозной проверки.</summary>
    public int SectionCount => Body.Children.Count;

    /// <summary>Ключей, которые ядро прислало, а оболочка разложила.</summary>
    public int KeyCount => _schema.Count;

    /// <summary>Готово: схема получена и разложена.</summary>
    public event Action? Ready;

    public SettingsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        if (_link is null)
        {
            Note.Text = "Ядро не на связи — настройки недоступны.";
            return;
        }
        Loaded += async (_, _) => await LoadAsync();
    }

    private async Task LoadAsync()
    {
        var described = await Ask(Methods.SettingsDescribe);
        if (described?["schema"] is not JsonObject schema) return;

        // Пропускаются два признака, и они значат разное. `obsolete` —
        // «заменено» (пять палитр 3.1.0 уступили двум отделкам). `secret` —
        // «служебное»: состояние хранилища, а не настройка, и показывать его
        // человеку незачем, как и писать в журнал.
        foreach (var (key, spec) in schema)
            if (spec is JsonObject entry
                && entry["obsolete"] is null && entry["secret"] is null)
                _schema[key] = entry;

        var got = await Ask(Methods.SettingsGet, new JsonObject
        {
            ["keys"] = new JsonArray(_schema.Keys
                .Select(k => (JsonNode)k!).ToArray()),
        });
        if (got?["values"] is JsonObject values)
            foreach (var (key, value) in values)
                _values[key] = value?.DeepClone();

        Build();
        Ready?.Invoke();
    }

    private void Build()
    {
        Body.Children.Clear();
        var placed = new HashSet<string>();

        foreach (var section in SettingsLayout.Sections)
        {
            var keys = section.Keys.Where(k => _schema.ContainsKey(k.Key))
                                   .ToArray();
            if (keys.Length == 0) continue;
            Body.Children.Add(BuildSection(section.Title,
                                           keys.Select(k => k.Key)));
            foreach (var k in keys) placed.Add(k.Key);
        }

        // Правило с зубами из ADR 0006: незнакомый ключ показывается, а не
        // прячется. Ядро завело настройку, оболочку не обновили — и без
        // этой секции настройка стала бы недостижимой незаметно.
        var strangers = _schema.Keys
            .Where(k => !placed.Contains(k)
                        && !SettingsLayout.Elsewhere.Contains(k))
            .OrderBy(k => k, StringComparer.Ordinal)
            .ToArray();
        if (strangers.Length > 0)
            Body.Children.Add(BuildSection(SettingsLayout.Other, strangers));
    }

    private UIElement BuildSection(string title, IEnumerable<string> keys)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 0, 0, 32) };
        stack.Children.Add(new TextBlock
        {
            Text = title.ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });
        foreach (var key in keys) stack.Children.Add(BuildRow(key));
        return stack;
    }

    private UIElement BuildRow(string key)
    {
        var spec = _schema[key];
        var row = new Grid { MinHeight = 40, Margin = new Thickness(0, 0, 0, 6) };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var label = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        label.Children.Add(new TextBlock
        {
            Text = SettingsLayout.TitleOf(key),
            Style = (Style)FindResource("Text.Body"),
        });

        var notes = new List<string>();
        if (SettingsLayout.HintOf(key).Length > 0)
            notes.Add(SettingsLayout.HintOf(key));
        if (spec["restart_required"] is not null)
            notes.Add("применится после перезапуска");
        if (!SettingsLayout.Known.Contains(key))
            notes.Add($"ключ {key} оболочке незнаком");
        if (notes.Count > 0)
            label.Children.Add(new TextBlock
            {
                Text = string.Join(" · ", notes),
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 2, 0, 0),
                TextWrapping = TextWrapping.Wrap,
            });

        Grid.SetColumn(label, 0);
        row.Children.Add(label);

        var editor = BuildEditor(key, spec);
        _editors[key] = editor;
        Grid.SetColumn(editor, 1);
        row.Children.Add(editor);

        ApplyDependency(key, spec, row);
        return row;
    }

    private FrameworkElement BuildEditor(string key, JsonObject spec)
    {
        var type = spec["type"]?.GetValue<string>() ?? "string";
        var value = _values.GetValueOrDefault(key);

        if (type == "boolean")
        {
            var toggle = new CheckBox
            {
                Style = (Style)FindResource("Toggle"),
                IsChecked = value?.GetValue<bool>() ?? false,
                VerticalAlignment = VerticalAlignment.Center,
            };
            toggle.Click += async (_, _) =>
                await SaveAsync(key, toggle.IsChecked == true);
            return toggle;
        }

        if (spec["choices"] is JsonArray choices)
        {
            var box = new ComboBox
            {
                Width = 260,
                Height = 36,
                VerticalContentAlignment = VerticalAlignment.Center,
                ItemsSource = choices.Select(c => c!.GetValue<string>()).ToArray(),
                SelectedItem = value?.GetValue<string>(),
            };
            box.SelectionChanged += async (_, _) =>
            {
                if (box.SelectedItem is string chosen)
                    await SaveAsync(key, chosen);
            };
            return box;
        }

        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Width = 260,
            Text = Show(value),
        };
        field.LostFocus += async (_, _) => await SaveAsync(key, Parse(field.Text, type));
        return field;
    }

    /// <summary>
    /// Погасить поле, если оно зависит от выключенного.
    /// </summary>
    /// <remarks>
    /// Зависимость знает ядро: только оно понимает, что «адрес модели» без
    /// «отвечать моделью» ничего не значит. Оболочка лишь показывает это.
    /// </remarks>
    private void ApplyDependency(string key, JsonObject spec, Grid row)
    {
        if (spec["depends_on"]?.GetValue<string>() is not { } master) return;
        var on = _values.GetValueOrDefault(master)?.GetValue<bool>() ?? false;
        row.IsEnabled = on;
        row.Opacity = on ? 1.0 : 0.5;
    }

    private static string Show(JsonNode? value) => value switch
    {
        null => "",
        JsonArray array => string.Join(", ",
            array.Select(v => v?.ToString() ?? "")),
        JsonObject => "…",
        _ => value.ToString(),
    };

    private static JsonNode? Parse(string text, string type) => type switch
    {
        "integer" => int.TryParse(text, out var i) ? i : null,
        "number" => double.TryParse(text, out var d) ? d : null,
        "array" => new JsonArray(text.Split(',')
            .Select(p => p.Trim()).Where(p => p.Length > 0)
            .Select(p => (JsonNode)p!).ToArray()),
        _ => text,
    };

    private async Task SaveAsync(string key, JsonNode? value)
    {
        if (value is null) { Note.Text = $"«{SettingsLayout.TitleOf(key)}»: не понял значение."; return; }

        var answer = await Ask(Methods.SettingsSet, new JsonObject
        {
            ["values"] = new JsonObject { [key] = value.DeepClone() },
        });
        if (answer?["verdicts"]?[key] is not JsonObject verdict) return;

        var accepted = verdict["accepted"]?.GetValue<bool>() ?? false;
        var message = verdict["message"]?.GetValue<string>() ?? "";
        var code = verdict["code"]?.GetValue<string>() ?? "";

        // Предупреждение не отказ: значение записано, а человеку сказано,
        // чем это обернётся.
        Note.Text = accepted && message.Length == 0
            ? $"«{SettingsLayout.TitleOf(key)}» сохранено."
            : message;
        Note.SetResourceReference(ForegroundProperty,
            accepted && code.Length == 0 ? "C.InkFaint" : "C.Signal");

        if (accepted)
        {
            _values[key] = value;
            if (key == "finish" && _link is not null)
                await _link.SetFinishAsync(value.GetValue<string>());
            Build();          // зависимости могли измениться
        }
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        try
        {
            var answer = await connection.CallAsync(method, payload,
                                                    TimeSpan.FromSeconds(20));
            if (answer.IsError) { Note.Text = answer.ErrorMessage; return null; }
            return answer.Payload;
        }
        catch (Exception error) { Note.Text = error.Message; return null; }
    }
}
