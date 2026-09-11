using System.Linq;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The canvas: steps as nodes, with wires between them
/// (<c>4.0b-A09</c>).
/// </summary>
/// <remarks>
/// <para>
/// The seed of a node graph, and deliberately a seed. What is here: nodes
/// on a surface, wires drawn between them, a fork that actually forks, a
/// port on each node to grow the graph from, and an inspector for whichever
/// node is selected. What is not here: dragging nodes where you like, and
/// wires you draw by hand between arbitrary ports.
/// </para>
/// <para>
/// <b>Why those two are missing, and not by oversight.</b> A command is a
/// tree — a chain of steps, with branches inside the ones that branch — so
/// its layout follows from its shape and nothing is lost by computing it.
/// Letting a person put a node anywhere means keeping where they put it,
/// and the only place to keep it is the command, which belongs to the core.
/// Coordinates are presentation; ADR 0006 says the core owns meaning and
/// the shell owns presentation, so the place to keep them is somewhere the
/// shell owns, and the shell has no store of its own yet. That is a thing
/// to build, not a line to sneak into somebody else's data.
/// </para>
/// <para>
/// Drawn from the tree each time rather than kept as objects. A node is
/// cheap; a second model of the graph living beside the real one is not,
/// and it would be the thing that disagrees with the card on the day
/// somebody edits both.
/// </para>
/// </remarks>
public partial class CommandEditor
{
    private const double NodeWidth = 210;
    private const double NodeHeight = 58;
    private const double GapDown = 34;
    private const double GapAcross = 60;
    private const double PortSize = 18;

    //: Which node the inspector is showing. The step itself, not an index:
    //: indices shift when something above is removed, and the inspector
    //: would quietly start editing a different step.
    private JsonObject? _picked;

    /// <summary>Lay the graph out and draw it.</summary>
    private void DrawSteps()
    {
        Board.Children.Clear();
        var bottom = Place(_chain, 0, 0, null);

        // The board is as large as what is on it. Fixed, it either cut the
        // graph off or left a field of emptiness under a graph of two.
        Board.Width = Math.Max(520, _widest + NodeWidth + 40);
        Board.Height = Math.Max(220, bottom + 40);
        ShowPicked();
    }

    private double _widest;

    /// <summary>
    /// Put a list of steps on the board, one under another.
    /// </summary>
    /// <remarks>
    /// Returns the y the next thing may start at. Recursive because the
    /// thing is recursive: what is inside a repeat is a list of steps like
    /// any other, drawn one column to the right so that "inside" is visible
    /// as inside.
    /// </remarks>
    private double Place(JsonArray steps, double x, double y, JsonObject? from)
    {
        _widest = Math.Max(_widest, x);
        var previous = from;
        var top = y;

        // The port before the first step: a graph has to be growable from
        // its start, not only from its end.
        Port(steps, 0, x, y - 18);

        for (var at = 0; at < steps.Count; at++)
        {
            if (steps[at] is not JsonObject step) continue;
            var node = Node(step, steps, at, x, y);
            if (previous is not null || at > 0)
                Wire(x + NodeWidth / 2, top - 8, x + NodeWidth / 2, y);

            var kind = step["type"]?.GetValue<string>() ?? "";
            var below = y + NodeHeight;

            if (kind is "repeat" or "while")
            {
                below = Branch(step, "steps", x, below, S("делать"));
            }
            else if (kind == "if")
            {
                var left = Branch(step, "steps", x, below, S("тогда"));
                var right = Branch(step, "otherwise",
                                   x + NodeWidth + GapAcross, below,
                                   S("иначе"));
                below = Math.Max(left, right);
            }

            top = below;
            y = below + GapDown;
            Port(steps, at + 1, x, y - 18);
            previous = step;
        }

        // An empty list still offers its port, and says it is empty.
        if (steps.Count == 0)
            Board.Children.Add(Text(S("пусто"), x + 8, y - 6, "Text.Meta"));

        return y;
    }

    /// <summary>What happens inside a node, drawn inside it.</summary>
    private double Branch(JsonObject step, string name, double x, double y,
                          string label)
    {
        if (step[name] is not JsonArray inner)
        {
            inner = [];
            step[name] = inner;
        }
        var at = x + GapAcross;
        Board.Children.Add(Text(label, at + 4, y + 2, "Text.Meta"));
        Wire(x + 20, y, at + NodeWidth / 2, y + 26);
        return Place(inner, at, y + 26, step);
    }

    /// <summary>One node: what it is, and how much of what it does fits.</summary>
    private UIElement Node(JsonObject step, JsonArray owner, int at,
                           double x, double y)
    {
        var kind = step["type"]?.GetValue<string>() ?? "speak";
        var known = _stepKinds.FirstOrDefault(k => k.Value == kind);
        var chosen = ReferenceEquals(step, _picked);

        var body = new StackPanel { Margin = new Thickness(10, 6, 10, 6) };
        body.Children.Add(new TextBlock
        {
            Text = (known.Icon ?? "•") + "  " + (known.Title ?? kind),
            Style = (Style)FindResource("Text.Body"),
        });
        body.Children.Add(new TextBlock
        {
            // The short form on the canvas, the whole of it in the
            // inspector. A node wide enough for a full path is a node one
            // can fit three of on a screen.
            Text = Short(step, kind),
            Style = (Style)FindResource("Text.Meta"),
            TextTrimming = TextTrimming.CharacterEllipsis,
            Margin = new Thickness(0, 2, 0, 0),
        });

        // A node has a look of its own rather than a list row's. Borrowed,
        // the row style brought its padding — twelve points top and bottom
        // inside a box of fifty-two — and the second line of every node
        // fell outside the box. A node is not a row: it stands on a
        // surface, it is selected, and it has no neighbours above and
        // below to be separated from.
        var box = new Border
        {
            Width = NodeWidth,
            Height = NodeHeight,
            Padding = new Thickness(0),
            Background = (Brush)FindResource(
                chosen ? "C.Glass.Raised" : "C.Glass.Control"),
            BorderBrush = (Brush)FindResource(
                chosen ? "C.Ink" : "C.Seam"),
            BorderThickness = new Thickness(chosen ? 2 : 1),
            CornerRadius = (CornerRadius)FindResource("Radius.Max"),
            Child = body,
        };
        box.MouseLeftButtonDown += (_, e) =>
        {
            _picked = step;
            _pickedOwner = owner;
            _pickedAt = at;
            e.Handled = true;
            DrawSteps();
        };

        Canvas.SetLeft(box, x);
        Canvas.SetTop(box, y);
        Board.Children.Add(box);
        return box;
    }

    //: Where the selected node sits, so the inspector can move or remove it.
    private JsonArray? _pickedOwner;
    private int _pickedAt;

    /// <summary>A place a node may be added, between two others.</summary>
    private void Port(JsonArray steps, int at, double x, double y)
    {
        // A small square, not a circle. Node editors usually draw ports
        // round, and this one does not: the design system's largest radius
        // is three points, and `check_design.py` said so. A circle here
        // would be the one round thing in the whole program — which is
        // exactly the kind of exception that turns a language into a
        // collection of habits.
        var add = new Border
        {
            Width = PortSize,
            Height = PortSize,
            CornerRadius = (CornerRadius)FindResource("Radius.Max"),
            Background = (Brush)FindResource("C.Glass.Control"),
            BorderBrush = (Brush)FindResource("C.Seam"),
            BorderThickness = new Thickness(1),
            Opacity = 0.45,
            ToolTip = S("Вставить шаг сюда"),
            Child = new TextBlock
            {
                Text = "+",
                Style = (Style)FindResource("Text.Meta"),
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
            },
        };
        add.MouseEnter += (_, _) => add.Opacity = 1;
        add.MouseLeave += (_, _) => add.Opacity = 0.45;
        add.MouseLeftButtonDown += (_, e) =>
        {
            e.Handled = true;
            OfferKinds(add, steps, at);
        };
        Canvas.SetLeft(add, x + NodeWidth / 2 - PortSize / 2);
        Canvas.SetTop(add, y);
        Board.Children.Add(add);
    }

    /// <summary>A wire from one node to the next.</summary>
    /// <remarks>
    /// Drawn in two straight runs with a bend, not as a curve. A curve
    /// between two nodes directly above one another is a curve that looks
    /// like a mistake; the bend is only ever seen where the graph actually
    /// turns, which is where it means something.
    /// </remarks>
    private void Wire(double x1, double y1, double x2, double y2)
    {
        var line = new Polyline
        {
            Stroke = (Brush)FindResource("C.Seam"),
            StrokeThickness = 1.5,
            Points = Math.Abs(x1 - x2) < 1
                ? [new Point(x1, y1), new Point(x2, y2)]
                : [new Point(x1, y1), new Point(x1, (y1 + y2) / 2),
                   new Point(x2, (y1 + y2) / 2), new Point(x2, y2)],
        };
        Board.Children.Add(line);
    }

    private UIElement Text(string said, double x, double y, string style)
    {
        var words = new TextBlock
        {
            Text = said,
            Style = (Style)FindResource(style),
        };
        Canvas.SetLeft(words, x);
        Canvas.SetTop(words, y);
        return words;
    }

    /// <summary>What a node says about itself on the canvas.</summary>
    private string Short(JsonObject step, string kind)
    {
        var target = step["target"]?.GetValue<string>() ?? "";
        switch (kind)
        {
            case "system":
                var named = _actions.FirstOrDefault(a => a.Value == target);
                return named.Title ?? target;
            case "pause":
                return S("{0} с", target);
            case "repeat":
                return S("{0} раз", (int)Number(step["count"]));
            case "while":
            case "if":
                var asks = step["condition"]?.GetValue<string>() ?? "";
                var said = _conditions.FirstOrDefault(c => c.Value == asks)
                    .Title ?? asks;
                var value = step["value"]?.GetValue<string>() ?? "";
                return value.Length > 0 ? $"{said} {value}" : said;
            case "set":
                return $"{step["name"]?.GetValue<string>()} = "
                       + step["value"]?.GetValue<string>();
            case "call":
                return target.Length > 0 ? target : S("не выбрана");
            default:
                return target.Length > 0 ? target : S("не заполнено");
        }
    }
}
