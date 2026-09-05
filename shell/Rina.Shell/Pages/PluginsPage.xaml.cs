using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Plugins: what is installed, what is on, and what a plugin says about
/// itself.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F04</c>, its last part.
/// </para>
/// <para>
/// <b>A plugin's page is drawn by the shell and described by the
/// plugin.</b> This was a 3.1.0 decision (<c>plugins/page_spec.py</c>),
/// taken before the processes were split: a plugin stopped returning a
/// ready-made widget and began returning a list of elements. Back then it
/// was foresight; now it is the one thing thanks to which the page of a
/// plugin written in Python is drawn in another process in another
/// language without a single change to the plugin itself.
/// </para>
/// <para>
/// <b>An unfamiliar element is shown, not skipped.</b> The same rule with
/// teeth as for an unfamiliar setting in
/// [ADR 0006](../../../docs/adr/0006-settings-ownership.md): the plugin
/// used an element the shell does not know — and skipping it in silence
/// would make part of its page invisible without a single trace.
/// </para>
/// <para>
/// <b>A broken plugin stays in the list.</b> A person installed it
/// themselves and must see the reason; a plugin that vanished looks like
/// "I never installed it".
/// </para>
/// </remarks>
public partial class PluginsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly Dictionary<string, string> _names = [];
    private string _open = "";

    /// <summary>How many plugins are shown — for the end-to-end check.</summary>
    public int PluginCount => Items.Children.Count;

    /// <summary>The list has arrived and been laid out.</summary>
    public event Action? Ready;

    public PluginsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        if (_link is null)
        {
            Empty.Content = EmptyState.For(
                S("Ядро не на связи"),
                S("Плагины живут в ядре, а связи с ним сейчас нет."));
            Empty.Visibility = Visibility.Visible;
            return;
        }
        Loaded += async (_, _) => await LoadAsync();
    }

    /// <summary>
    /// Switch on the first plugin that has a page of its own and open it.
    /// </summary>
    /// <remarks>
    /// For the end-to-end check: it cannot click on cards, but it is
    /// obliged to go the whole round — the list, switching on, the page.
    ///
    /// <b>And put things back.</b> The check runs against the real core,
    /// that is, against a person's settings; it has no right to leave
    /// plugins switched on behind it. Exactly the same rule by which the
    /// autostart check puts the registry entry back.
    /// </remarks>
    /// <returns>How many elements the page had while it was open.</returns>
    /// <param name="keepOpen">
    /// Leave it switched on and open. The screenshot needs this: it is
    /// taken **after** the call, and putting everything back would mean
    /// photographing an empty list. The person's settings are restored all
    /// the same — what stays on is the plugin, not the record of it.
    /// </param>
    public async Task<int> OpenFirstPageAsync(bool keepOpen = false)
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return 0;

        _wasEnabled = items.OfType<JsonObject>()
            .Where(p => p["enabled"]?.GetValue<bool>() == true)
            .Select(p => p["plugin_id"]?.GetValue<string>() ?? "")
            .ToHashSet();
        var wasEnabled = _wasEnabled;

        try
        {
            foreach (var plugin in items.OfType<JsonObject>())
            {
                var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
                if (id.Length == 0 || plugin["broken"]?.GetValue<bool>() == true)
                    continue;

                // Only a plugin that is on has a page: a plugin that is
                // off is not loaded, and there is nothing to ask it.
                await SetEnabledAsync(id, true);
                var after = await Ask(Methods.PluginsList);
                var hasPage = after?["items"]?.AsArray()
                    .OfType<JsonObject>()
                    .FirstOrDefault(p => p["plugin_id"]?.GetValue<string>() == id)
                    ?["has_page"]?.GetValue<bool>() ?? false;
                if (!hasPage) continue;

                _open = id;
                await ShowPageAsync();
                // Count now: restoring the state below will close the
                // page, and asking afterwards would be too late.
                return PageElementCount;
            }
            return 0;
        }
        finally
        {
            // With `keepOpen` the restore is put off until
            // `RestoreAsync`: the screenshot is taken afterwards, and
            // restoring the state here would mean photographing an empty
            // list.
            var now = keepOpen ? null : await Ask(Methods.PluginsList);
            foreach (var plugin in now?["items"]?.AsArray()
                                   ?.OfType<JsonObject>() ?? [])
            {
                var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
                if (plugin["enabled"]?.GetValue<bool>() == true
                    && !wasEnabled.Contains(id))
                    await SetEnabledAsync(id, false);
            }
        }
    }

    /// <summary>Which plugins are on right now — for the end-to-end check.</summary>
    public async Task<string[]> EnabledAsync()
    {
        var now = await Ask(Methods.PluginsList);
        return (now?["items"]?.AsArray() ?? [])
            .OfType<JsonObject>()
            .Where(p => p["enabled"]?.GetValue<bool>() == true)
            .Select(p => p["plugin_id"]?.GetValue<string>() ?? "")
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();
    }

    /// <summary>What was on before we interfered.</summary>
    private HashSet<string> _wasEnabled = [];

    /// <summary>
    /// Put back what was switched on.
    /// </summary>
    /// <remarks>
    /// The screenshot needs this: it opens a plugin's page, which means
    /// switching the plugin on — and it is obliged to switch it back off.
    /// The settings under a check are real, a person's own; the same rule
    /// by which the autostart check puts the registry entry back.
    /// </remarks>
    public async Task RestoreAsync()
    {
        _open = "";
        var now = await Ask(Methods.PluginsList);
        foreach (var plugin in now?["items"]?.AsArray()
                               ?.OfType<JsonObject>() ?? [])
        {
            var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
            if (plugin["enabled"]?.GetValue<bool>() == true
                && !_wasEnabled.Contains(id))
                await SetEnabledAsync(id, false);
        }
    }

    /// <summary>
    /// Install a plugin from an unpacked folder.
    /// </summary>
    /// <remarks>
    /// The shell shows the picker, the core installs: a dialogue is
    /// interface, while unpacking and checking the manifest are work with
    /// data. It is also what refuses when the folder has no `plugin.json`
    /// or `main.py`.
    /// </remarks>
    private async void OnInstallFolder(object sender, RoutedEventArgs e)
    {
        var folder = new Microsoft.Win32.OpenFolderDialog
        {
            Title = S("Папка с плагином"),
        };
        if (folder.ShowDialog() == true) await InstallAsync(folder.FolderName);
    }

    private async void OnInstallArchive(object sender, RoutedEventArgs e)
    {
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Title = S("Архив с плагином"),
            Filter = S("Архивы (*.zip)|*.zip|Все файлы|*.*"),
        };
        if (file.ShowDialog() == true) await InstallAsync(file.FileName);
    }

    private async Task InstallAsync(string source)
    {
        Note.Text = S("Ставлю…");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");

        var answer = await Ask(Methods.PluginsInstall, new JsonObject
        {
            ["source"] = source,
        });
        if (answer is null) return;          // причину уже сказали в Note

        var id = answer["plugin_id"]?.GetValue<string>() ?? "";
        // The core forcibly switches a replaced plugin off: a new
        // plugin's code runs when it is switched on, and inheriting
        // somebody else's "on" means running a slipped-in archive without
        // the person knowing.
        Note.Text = answer["replaced"]?.GetValue<bool>() == true
            ? S("Заменён: {0}. Он выключен — включите, если доверяете.", id)
            : S("Поставлен: {0}. Включите его, чтобы начал работать.", id);
        await LoadAsync();
    }

    /// <summary>
    /// Re-read the plugin catalogue.
    /// </summary>
    /// <remarks>
    /// A folder is put there by hand, and Rina does not find out about it:
    /// watching the catalogue all the time means keeping a watcher for an
    /// event that happens once a month. A button is more honest.
    /// </remarks>
    private async void OnRefresh(object sender, RoutedEventArgs e)
    {
        Note.Text = S("Перечитываю…");
        await LoadAsync();
        if (_link is not null) await _link.RefreshPluginSectionsAsync();
        Note.Text = S("Список обновлён.");
    }

    private async Task LoadAsync()
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return;

        Items.Children.Clear();
        foreach (var item in items.OfType<JsonObject>())
        {
            var id = item["plugin_id"]?.GetValue<string>() ?? "";
            if (id.Length > 0)
                _names[id] = item["name"]?.GetValue<string>() ?? id;
            Items.Children.Add(BuildRow(item));
        }

        // The last row has no seam: it would coincide with the edge of the
        // block and cross out the rounding.
        if (Items.Children.Count > 0
            && Items.Children[^1] is Border tail)
            tail.BorderThickness = new Thickness(0);

        Empty.Content = items.Count == 0
            ? EmptyState.For(
                S("Плагинов пока нет"),
                S("Плагин добавляет Рине умение: свою команду, свой раздел или и то и другое. Папку с плагином кладут рядом с программой."))
            : null;
        Empty.Visibility = items.Count == 0 ? Visibility.Visible
                                            : Visibility.Collapsed;
        Legend.Text = items.Count == 0 ? S("УСТАНОВЛЕННЫЕ")
                                       : S("УСТАНОВЛЕННЫЕ · {0}", items.Count);
        Ready?.Invoke();
    }

    private UIElement BuildRow(JsonObject plugin)
    {
        var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
        var broken = plugin["broken"]?.GetValue<bool>() ?? false;
        var enabled = plugin["enabled"]?.GetValue<bool>() ?? false;
        var hasPage = plugin["has_page"]?.GetValue<bool>() ?? false;

        var card = new Border
        {
            Style = (Style)FindResource("Rows.Item"),
        };
        var row = new Grid();
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var icon = new TextBlock
        {
            Text = plugin["icon"]?.GetValue<string>() ?? "🧩",
            FontSize = 20,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, 0, 12, 0),
        };
        Grid.SetColumn(icon, 0);
        row.Children.Add(icon);

        var about = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        about.Children.Add(new TextBlock
        {
            Text = plugin["name"]?.GetValue<string>() ?? id,
            Style = (Style)FindResource("Text.Body"),
        });

        // The failure goes instead of the description, not next to it: the
        // reason matters more than what the plugin said about itself while
        // it worked.
        var note = broken
            ? plugin["error"]?.GetValue<string>() ?? S("плагин не загрузился")
            : Describe(plugin);
        about.Children.Add(new TextBlock
        {
            Text = note,
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, 0, 0),
            Foreground = broken ? (System.Windows.Media.Brush)FindResource("C.Signal")
                                : (System.Windows.Media.Brush)FindResource("C.InkFaint"),
        });
        Grid.SetColumn(about, 1);
        row.Children.Add(about);

        if (hasPage && enabled)
        {
            var open = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = _open == id ? S("Скрыть") : S("Открыть"),
                Margin = new Thickness(0, 0, 8, 0),
                VerticalAlignment = VerticalAlignment.Center,
            };
            open.Click += async (_, _) =>
            {
                _open = _open == id ? "" : id;
                await ShowPageAsync();
                await LoadAsync();          // подписи кнопок изменились
            };
            Grid.SetColumn(open, 2);
            row.Children.Add(open);
        }

        var toggle = new CheckBox
        {
            Style = (Style)FindResource("Toggle"),
            IsChecked = enabled,
            // A broken one cannot be switched on: switching would change
            // nothing, and a toggle that springs back looks like a
            // breakage.
            IsEnabled = !broken,
            VerticalAlignment = VerticalAlignment.Center,
        };
        toggle.Click += async (_, _) => await SetEnabledAsync(id, toggle.IsChecked == true);
        Grid.SetColumn(toggle, 3);
        row.Children.Add(toggle);

        card.Child = row;
        return card;
    }

    private static string Describe(JsonObject plugin)
    {
        var parts = new List<string>();
        var description = plugin["description"]?.GetValue<string>() ?? "";
        if (description.Length > 0) parts.Add(description);
        var version = plugin["version"]?.GetValue<string>() ?? "";
        if (version.Length > 0) parts.Add(S("версия {0}", version));
        var author = plugin["author"]?.GetValue<string>() ?? "";
        if (author.Length > 0 && author != "unknown") parts.Add(author);
        return string.Join(" · ", parts);
    }

    private async Task SetEnabledAsync(string id, bool enabled)
    {
        var answer = await Ask(Methods.PluginsSetEnabled, new JsonObject
        {
            ["plugin_id"] = id,
            ["enabled"] = enabled,
        });
        if (answer?["plugin"] is not JsonObject plugin) return;

        // The core returned the state **after** the change: the plugin
        // could have refused to load, and "on" would have been an untruth.
        var now = plugin["enabled"]?.GetValue<bool>() ?? false;
        var shown = plugin["name"]?.GetValue<string>() ?? id;
        Note.Text = now == enabled
            ? (now ? S("«{0}» включён.", shown) : S("«{0}» выключен.", shown))
            : S("«{0}» не включился: {1}", shown,
                plugin["error"]?.GetValue<string>() ?? "");
        Note.SetResourceReference(ForegroundProperty,
                                  now == enabled ? "C.InkFaint" : "C.Signal");

        if (!now && _open == id) _open = "";
        await ShowPageAsync();
        await LoadAsync();
        // A plugin's section in the column appears and disappears together
        // with it, not after a restart: the person switched notes on — they
        // expect them on the left.
        if (_link is not null) await _link.RefreshPluginSectionsAsync();
    }

    /// <summary>Show the open plugin's page.</summary>
    private async Task ShowPageAsync()
    {
        Draw();
        // Wait for the draw rather than relying on `Loaded`: elements are
        // counted right after this call, and "zero" would mean not an empty
        // page but a page nobody has asked for yet.
        if (_view is not null) await _view.ReloadAsync();
    }

    /// <summary>
    /// Show the open plugin's page.
    /// </summary>
    /// <remarks>
    /// Drawn by <see cref="PluginView"/> — the same one as in the plugin's
    /// own section. A copy of the renderer here would be a second place
    /// where the version 2 schema is understood in its own way.
    /// </remarks>
    private void Draw()
    {
        PageBody.Children.Clear();
        if (_open.Length == 0)
        {
            PageBox.Visibility = Visibility.Collapsed;
            return;
        }

        PageBox.Visibility = Visibility.Visible;
        // The name, not the number: "NOTES" is what the plugin is called
        // in the file system, and a person knows it as "Notes".
        PageLegend.Text = (_names.GetValueOrDefault(_open) ?? _open)
            .ToUpperInvariant();

        var view = new PluginView(_link, _open);
        view.Noted += text => Note.Text = text;
        PageBody.Children.Add(view);
        _view = view;
    }

    private PluginView? _view;

    /// <summary>How many elements the open page has — for the check.</summary>
    public int PageElementCount => _view?.ElementCount ?? 0;

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        if (!connection.MayCall(method))
        {
            Note.Text = S("Ядро не объявило возможность «плагины».");
            return null;
        }
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
