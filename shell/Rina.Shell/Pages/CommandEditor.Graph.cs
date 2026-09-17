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
/// port on each node to grow the graph from, an inspector for whichever
/// node is selected, a ruled surface and a way to move about on it. What
/// is not here: dragging nodes where you like, and wires you draw by hand
/// between arbitrary ports.
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

    /// <summary>How far a branch's contents hang below the node.</summary>
    /// <remarks>
    /// Twenty-six, and the branch's name — «делать», «тогда», «иначе» —
    /// was written into the same twenty-six points as the wire crossing
    /// them. Word over line. Forty-four gives the word a line of its own
    /// and leaves the wire above it.
    /// </remarks>
    private const double BranchDrop = 44;

    /// <summary>Where a branch's wire turns across.</summary>
    /// <remarks>
    /// Above the name rather than through the middle of the drop, which
    /// is where a wire turns by default.
    /// </remarks>
    private const double BranchBend = 12;

    /// <summary>
    /// Room above the first node, for the port that stands there.
    /// </summary>
    /// <remarks>
    /// The graph used to start at nought, and the port before the first
    /// step is drawn eighteen points higher — off the top of the surface,
    /// where half of it was cut off by the edge. A place to add a step at
    /// the very beginning that one cannot see is not a place.
    /// </remarks>
    private const double Headroom = 26;

    //: Which node the inspector is showing. The step itself, not an index:
    //: indices shift when something above is removed, and the inspector
    //: would quietly start editing a different step.
    private JsonObject? _picked;

    /// <summary>Lay the graph out and draw it.</summary>
    private void DrawSteps()
    {
        Board.Children.Clear();
        // **Reset, and it was not.** `_widest` is the rightmost column
        // the layout reached, and it was only ever raised — so a graph
        // that had once had a branch kept the width of that branch for
        // the rest of the session, however much was deleted. Hidden by
        // the old floor of 520 and by a scroll viewer that shows no
        // scrollbar for slack; visible the moment the graph had to be
        // centred in what it actually occupies.
        _widest = 0;
        _boxes.Clear();
        _byPath.Clear();
        _ports.Clear();

        // The paths match the ones the core reports. A sequence's steps
        // arrive as `steps.0`, so the canvas names them the same way; a
        // command of one node reports an empty path, and that node answers
        // to it. Two ways of naming the same place would agree only until
        // somebody changed one of them.
        // A graph of one plain node is saved as a plain command, and a
        // plain command reports one path: the empty one. Anything else is
        // a sequence, whose steps report as `steps.0`, `steps.1`.
        var only = _chain.Count == 1 ? _chain[0] as JsonObject : null;
        _alone = only is not null
                 && StandsAlone(only["type"]?.GetValue<string>() ?? "");
        var bottom = Place(_chain, 0, Headroom, null, "steps.");

        // The board is exactly as large as what is on it. It used to
        // have a floor of 520 by 220 — room for a scrollbar to decide
        // there was nothing to scroll — and the surface has no edges
        // now, so a floor would only push the graph off centre.
        Board.Width = _widest + NodeWidth;
        Board.Height = bottom;
        Rule();
        Centre();
        Paint();
        ShowPicked();
    }

    private double _widest;

    //: Whether this graph will be saved as a plain command —
    //: which decides what the core will call its one node.
    private bool _alone;

    /// <summary>
    /// Put a list of steps on the board, one under another.
    /// </summary>
    /// <remarks>
    /// Returns the y the next thing may start at. Recursive because the
    /// thing is recursive: what is inside a repeat is a list of steps like
    /// any other, drawn one column to the right so that "inside" is visible
    /// as inside.
    /// </remarks>
    private double Place(JsonArray steps, double x, double y, JsonObject? from,
                         string path = "")
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
            // The one node of a plain command answers to the empty
            // path, because that is what the core reports for it.
            var where = _alone && path == "steps." ? "" : path + at;
            var node = Node(step, steps, at, x, y, where);
            if (previous is not null || at > 0)
                Wire(x + NodeWidth / 2, top - 8, x + NodeWidth / 2, y);

            var kind = step["type"]?.GetValue<string>() ?? "";
            var below = y + NodeHeight;

            var mine = path + at + ".";
            if (kind is "repeat" or "while")
            {
                below = Branch(step, "steps", x, below, S("делать"), mine);
            }
            else if (kind == "if")
            {
                var left = Branch(step, "steps", x, below, S("тогда"), mine);
                var right = Branch(step, "otherwise",
                                   x + NodeWidth + GapAcross, below,
                                   S("иначе"), mine);
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
                          string label, string path)
    {
        if (step[name] is not JsonArray inner)
        {
            inner = [];
            step[name] = inner;
        }
        var at = x + GapAcross;
        // **Out of the node, not out of thin air.** The wire used to
        // start twenty points from the node's left edge — a point on
        // nothing — and came away looking broken. A wire leaves a node
        // where every other wire here leaves one: the middle of its
        // bottom edge.
        Wire(x + NodeWidth / 2, y, at + NodeWidth / 2, y + BranchDrop,
             y + BranchBend);
        Board.Children.Add(Text(label, at, y + BranchDrop - 20, "Text.Meta"));
        return Place(inner, at, y + BranchDrop, step, path + name + ".");
    }

    /// <summary>One node: what it is, and how much of what it does fits.</summary>
    private UIElement Node(JsonObject step, JsonArray owner, int at,
                           double x, double y, string path)
    {
        var kind = step["type"]?.GetValue<string>() ?? "speak";
        var known = _stepKinds.FirstOrDefault(k => k.Value == kind);
        var chosen = ReferenceEquals(step, _picked);

        // The grip. Without it nothing on the node says it can be moved:
        // the dragging worked and was invisible, which is the same as not
        // being there. Six dots is what a grip looks like everywhere, and
        // the cursor over the node says the same thing a second time for
        // anybody who does not read marks.
        var whole = new Grid();
        whole.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        whole.ColumnDefinitions.Add(new ColumnDefinition());

        var grip = new TextBlock
        {
            Text = "⠿",
            Style = (Style)FindResource("Text.Meta"),
            // Soft ink at three quarters, not faint ink at a half. At a
            // half it read as a smudge on the box rather than as something
            // to take hold of — and an affordance nobody recognises is the
            // same as no affordance, which is what this was added to fix.
            Foreground = (Brush)FindResource("C.InkSoft"),
            FontSize = 14,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(8, 0, 0, 0),
            Opacity = 0.75,
            ToolTip = S("Потяните, чтобы переставить"),
        };
        whole.Children.Add(grip);

        var body = new StackPanel
        {
            Margin = new Thickness(8, 6, 10, 6),
            VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(body, 1);
        whole.Children.Add(body);
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
            Cursor = System.Windows.Input.Cursors.SizeAll,
            Child = whole,
        };
        box.MouseEnter += (_, _) => grip.Opacity = 1;
        box.MouseLeave += (_, _) => grip.Opacity = 0.75;
        box.MouseLeftButtonDown += (_, e) =>
        {
            _picked = step;
            _pickedOwner = owner;
            _pickedAt = at;
            _grabbedAt = e.GetPosition(Board);
            e.Handled = true;
            DrawSteps();
        };

        // Dragging a node moves it **in the chain**, not on the surface.
        //
        // A node editor usually lets one put a box anywhere; this one puts
        // it somewhere in the order, because that is what a step has. The
        // drop targets are the ports — the same places a new node goes —
        // so "drag it there" and "add it there" mean the same place, and
        // nothing about where a person let go has to be remembered
        // afterwards.
        box.MouseMove += (sender, e) =>
        {
            if (e.LeftButton != System.Windows.Input.MouseButtonState.Pressed)
                return;
            if (_dragging is not null) return;
            var now = e.GetPosition(Board);
            if (Math.Abs(now.X - _grabbedAt.X) < 6
                && Math.Abs(now.Y - _grabbedAt.Y) < 6) return;

            _dragging = step;
            _draggingFrom = owner;
            _draggingAt = at;
            // Every port lights up while a node is in the air. A person who
            // has picked one up is asking "where may this go", and the
            // answer should be on the screen before they have to guess.
            ShowPorts(true);
            try
            {
                DragDrop.DoDragDrop((DependencyObject)sender, step,
                                    DragDropEffects.Move);
            }
            finally
            {
                _dragging = null;
                _draggingFrom = null;
                DrawSteps();
            }
        };

        _boxes[path] = box;
        _byPath[path] = step;

        Canvas.SetLeft(box, x);
        Canvas.SetTop(box, y);
        Board.Children.Add(box);
        return box;
    }

    //: Where the selected node sits, so the inspector can move or remove it.
    private JsonArray? _pickedOwner;
    private int _pickedAt;

    //: The node being dragged, and where it came from.
    private JsonObject? _dragging;
    private JsonArray? _draggingFrom;
    private int _draggingAt;
    private Point _grabbedAt;

    //: Every port on the board, so they can all be lit while a node is
    //: being dragged.
    private readonly List<Border> _ports = [];

    /// <summary>Show or hide where a dragged node may land.</summary>
    private void ShowPorts(bool during)
    {
        foreach (var port in _ports)
        {
            port.Opacity = during ? 1 : PortRest;
            port.BorderBrush = (Brush)FindResource(during ? "C.Ink" : "C.Seam");
        }
    }

    private const double PortRest = 0.45;

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
            Opacity = PortRest,
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
        add.MouseLeave += (_, _) =>
            add.Opacity = _dragging is null ? PortRest : 1;
        add.MouseLeftButtonDown += (_, e) =>
        {
            e.Handled = true;
            OfferKinds(add, steps, at);
        };

        // A port is also where a dragged node lands.
        add.AllowDrop = true;
        add.DragOver += (_, e) =>
        {
            var may = CanDrop(steps);
            e.Effects = may ? DragDropEffects.Move : DragDropEffects.None;
            add.Opacity = may ? 1 : 0.45;
            add.BorderBrush = (Brush)FindResource(may ? "C.Ink" : "C.Seam");
            e.Handled = true;
        };
        add.DragLeave += (_, _) =>
        {
            // Back to "lit because something is in the air", not to
            // "asleep": the node is still being dragged, and the other
            // ports are still where it may go.
            add.Opacity = _dragging is null ? PortRest : 1;
            add.BorderBrush = (Brush)FindResource(
                _dragging is null ? "C.Seam" : "C.Ink");
        };
        add.Drop += (_, e) =>
        {
            e.Handled = true;
            DropInto(steps, at);
        };
        _ports.Add(add);
        Canvas.SetLeft(add, x + NodeWidth / 2 - PortSize / 2);
        Canvas.SetTop(add, y);
        Board.Children.Add(add);
    }

    /// <summary>
    /// May the dragged node land in this list?
    /// </summary>
    /// <remarks>
    /// Not inside itself. A repeat dropped into its own body would be a
    /// node that contains the thing that contains it: the tree stops being
    /// a tree, drawing it never finishes, and the card that gets saved
    /// cannot be read back. Refused rather than repaired afterwards — by
    /// then the graph a person was looking at has already gone.
    /// </remarks>
    private bool CanDrop(JsonArray into)
    {
        if (_dragging is null) return false;
        return !Inside(_dragging, into);
    }

    private static bool Inside(JsonObject node, JsonArray list)
    {
        foreach (var branch in new[] { "steps", "otherwise" })
        {
            if (node[branch] is not JsonArray inner) continue;
            if (ReferenceEquals(inner, list)) return true;
            foreach (var deeper in inner.OfType<JsonObject>())
                if (Inside(deeper, list)) return true;
        }
        return false;
    }

    /// <summary>Move the dragged node to this place in the chain.</summary>
    private void DropInto(JsonArray steps, int at)
    {
        if (_dragging is null || _draggingFrom is null) return;
        if (!CanDrop(steps)) return;

        // Taken out first, then put in. The index shifts when both ends are
        // the same list and the node came from above the place it is going:
        // removing it moves everything below up by one, and inserting at
        // the old number would put it one place further on than where the
        // person let go.
        var moving = _draggingFrom[_draggingAt];
        var landing = at;
        if (ReferenceEquals(_draggingFrom, steps) && _draggingAt < at)
            landing -= 1;

        _draggingFrom.RemoveAt(_draggingAt);
        steps.Insert(Math.Clamp(landing, 0, steps.Count), moving);

        _picked = _dragging;
        _pickedOwner = steps;
        _pickedAt = Math.Clamp(landing, 0, steps.Count - 1);
        _dragging = null;
        _draggingFrom = null;
        DrawSteps();
        ShowSummary();
    }

    /// <summary>Drag a node onto a port — for the check.</summary>
    /// <remarks>
    /// The same two calls the mouse makes, in the same order. A check that
    /// moved the step itself would be checking `JsonArray`.
    /// </remarks>
    public bool DragForCheck(JsonArray from, int at, JsonArray onto, int to)
    {
        if (from[at] is not JsonObject step) return false;
        _dragging = step;
        _draggingFrom = from;
        _draggingAt = at;
        var may = CanDrop(onto);
        if (may) DropInto(onto, to);
        _dragging = null;
        _draggingFrom = null;
        return may;
    }

    // -- the trial, shown running (4.0b-A09) --------------------------------

    //: Which node is doing what right now, by its path in the tree.
    //: Cleared when a trial starts, so the previous run's colours do not
    //: sit under the next one.
    private readonly Dictionary<string, string> _running = [];

    /// <summary>
    /// The core says a step has started, finished or failed.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Green while it runs and after it is done, red where it failed — the
    /// same two answers a person is actually asking a trial for: how far
    /// did it get, and where did it stop.
    /// </para>
    /// <para>
    /// The path is where the step stands in the tree, not an identifier on
    /// it: a step has none, and giving it one would put a field in the
    /// core's card for the sake of a colour in a window. The top-level
    /// steps of a sequence arrive as <c>steps.0</c>, <c>steps.1</c>; the
    /// command as a whole arrives as an empty path, which is the only
    /// thing a command of one action ever reports.
    /// </para>
    /// </remarks>
    public void StepReported(string path, string state)
    {
        _running[path] = state;
        Paint();
    }

    /// <summary>A trial is starting; forget the last one's colours.</summary>
    public void TrialStarting()
    {
        _running.Clear();
        Paint();
    }

    /// <summary>
    /// Colour whatever the run has reached, without redrawing the graph.
    /// </summary>
    /// <remarks>
    /// The nodes are not rebuilt. A step reports twice and a scenario of
    /// twenty reports forty times; rebuilding the canvas on each would make
    /// the picture flicker through the very moment it is meant to show, and
    /// would drop whatever the person had selected.
    /// </remarks>
    private void Paint()
    {
        foreach (var (path, box) in _boxes)
        {
            var state = _running.GetValueOrDefault(path, "");
            var chosen = ReferenceEquals(_picked,
                                         _byPath.GetValueOrDefault(path));

            // Green for what is going and what went, the accent for what
            // failed. The accent is already this program's word for
            // "something is wrong"; green is a colour of its own, because
            // the accent moves with the finish — under the "moss" accent it
            // **is** green, and one colour for both answers would be no
            // answer at all.
            box.BorderBrush = (Brush)FindResource(state switch
            {
                "running" or "done" => "C.Live",
                "failed" => "C.Signal",
                _ => chosen ? "C.Ink" : "C.Seam",
            });
            box.BorderThickness = new Thickness(
                state.Length > 0 || chosen ? 2 : 1);

            // Running is filled as well as outlined: the eye finds one
            // filled shape among twenty outlined ones without looking for
            // it, and "where is it now" is a question asked at a glance.
            box.Background = (Brush)FindResource(
                state == "running" ? "C.Glass.Raised" : "C.Glass.Control");
        }
    }

    //: Where each node's box is, by path — so a colour can be put on it
    //: without rebuilding the canvas.
    private readonly Dictionary<string, Border> _boxes = [];
    private readonly Dictionary<string, JsonObject> _byPath = [];

    /// <summary>What the run has said about each node — for the check.</summary>
    public string StateOfNode(string path) =>
        _running.GetValueOrDefault(path, "");

    /// <summary>
    /// The colour a node is wearing right now — for the check.
    /// </summary>
    /// <remarks>
    /// The brush on the box, not the word in the dictionary. "The state was
    /// recorded" and "the node turned green" are different claims, and only
    /// the second is what a person sees; a check that read the dictionary
    /// would stay green with the painting removed.
    /// </remarks>
    public string ColourOfNode(string path)
    {
        // The name of the brush, or an empty string. Facts, not prose: a
        // line a person never sees has no business among the ones that get
        // translated, and the check is better at wording its own report.
        if (!_boxes.TryGetValue(path, out var box)) return "";
        foreach (var name in new[] { "C.Live", "C.Signal", "C.Ink", "C.Seam" })
            if (ReferenceEquals(box.BorderBrush, TryFindResource(name)))
                return name;
        return "?";
    }

    /// <summary>
    /// How many nodes carry a grip — for the check.
    /// </summary>
    /// <remarks>
    /// Dragging worked before any of this existed and was invisible, which
    /// is the same as not being there. So what is asserted is the mark a
    /// person sees, not the handler behind it.
    /// </remarks>
    public int GripsShown => _boxes.Values
        .SelectMany(box => Deep(box).OfType<TextBlock>())
        .Count(words => words.Text == "⠿");

    /// <summary>Does a node's cursor say it moves — for the check.</summary>
    public bool NodeSaysItMoves => _boxes.Values.All(
        box => box.Cursor == System.Windows.Input.Cursors.SizeAll);

    /// <summary>How many ports are lit right now — for the check.</summary>
    public int PortsLit => _ports.Count(p => p.Opacity > 0.9);

    /// <summary>How many ports there are at all — for the check.</summary>
    public int PortsShown => _ports.Count;

    /// <summary>Light the ports as a drag does — for the check.</summary>
    public void ShowPortsForCheck(bool during) => ShowPorts(during);

    private static IEnumerable<DependencyObject> Deep(DependencyObject root)
    {
        var count = System.Windows.Media.VisualTreeHelper
            .GetChildrenCount(root);
        for (var i = 0; i < count; i++)
        {
            var child = System.Windows.Media.VisualTreeHelper
                .GetChild(root, i);
            yield return child;
            foreach (var deeper in Deep(child)) yield return deeper;
        }
    }

    /// <summary>Which nodes the canvas knows — for the check.</summary>
    public string[] NodePaths => _boxes.Keys.ToArray();

    /// <summary>Pretend the core reported a step — for the check.</summary>
    public void ReportForCheck(string path, string state) =>
        StepReported(path, state);

    /// <summary>A wire from one node to the next.</summary>
    /// <remarks>
    /// Drawn in two straight runs with a bend, not as a curve. A curve
    /// between two nodes directly above one another is a curve that looks
    /// like a mistake; the bend is only ever seen where the graph actually
    /// turns, which is where it means something.
    /// </remarks>
    private void Wire(double x1, double y1, double x2, double y2) =>
        Wire(x1, y1, x2, y2, (y1 + y2) / 2);

    /// <summary>A wire, turning across at a height one chooses.</summary>
    private void Wire(double x1, double y1, double x2, double y2, double bend)
    {
        var line = new Polyline
        {
            Stroke = (Brush)FindResource("C.Seam"),
            StrokeThickness = 1.5,
            Points = Math.Abs(x1 - x2) < 1
                ? [new Point(x1, y1), new Point(x2, y2)]
                : [new Point(x1, y1), new Point(x1, bend),
                   new Point(x2, bend), new Point(x2, y2)],
        };
        Board.Children.Add(line);
    }

    /// <summary>
    /// Put the graph in the middle of what can be seen.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Reported: "and these commands are not centred on the canvas to
    /// begin with". They were not: the first node went at nought by
    /// nought, so a graph of two sat in the top left corner of a field
    /// of nothing.
    /// </para>
    /// <para>
    /// <b>Only until the person moves it.</b> After that the view is
    /// theirs: re-centring on every change would snatch it back every
    /// time a node was added. A double-click on the empty surface asks
    /// for the middle again.
    /// </para>
    /// <para>
    /// A graph larger than the window is put at its top left rather
    /// than centred: centring something taller than the view hides its
    /// beginning, and the beginning is where one reads from.
    /// </para>
    /// </remarks>
    private void Centre(bool anyway = false)
    {
        if (_roamed && !anyway) return;
        // Laid out first: the box's size is what this is measured
        // against, and a graph just rebuilt has not been arranged.
        Deck.UpdateLayout();
        Roaming.X = Math.Max(0, (Deck.ActualWidth - Board.ActualWidth) / 2);
        Roaming.Y = Math.Max(0, (Deck.ActualHeight - Board.ActualHeight) / 2);
        _roamed = anyway ? false : _roamed;
    }

    private bool _roamed;

    /// <summary>
    /// Rule the surface.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Asked for, and it earns its place: an unmarked field gives the eye
    /// nothing to measure a node against, so a graph on it looks crooked
    /// whether it is or not. A ruling is also what says the surface is
    /// larger than the window over it — without one, moving it about
    /// looks like nothing happening.
    /// </para>
    /// <para>
    /// A dot at each crossing rather than lines: lines through a graph
    /// made of lines would read as more wires. The step is the space
    /// scale's own «within», so the surface is ruled in the same units
    /// everything else on the screen is spaced in.
    /// </para>
    /// <para>
    /// Built here rather than in the markup because the ink is the
    /// finish's, and the finish changes while the program runs. The
    /// surface is redrawn on every change to the graph, so it is redrawn
    /// on a change of finish too.
    /// </para>
    /// </remarks>
    private void Rule()
    {
        var step = (double)FindResource("Sp.Within");
        var dot = new GeometryDrawing(
            (Brush)FindResource("C.Seam"), null,
            new RectangleGeometry(new Rect(0, 0, 1, 1)));
        // **On the box, not on the canvas.** Laid on the canvas the
        // ruling ended where the nodes did, and pulling the surface
        // aside showed a blank field beside a ruled one — the surface
        // looked as though it stopped. The tile follows the canvas by
        // its own transform, so it goes on as far as one cares to pull.
        Deck.Background = new DrawingBrush(dot)
        {
            TileMode = TileMode.Tile,
            Viewport = new Rect(0, 0, step, step),
            ViewportUnits = BrushMappingMode.Absolute,
            Stretch = Stretch.None,
            AlignmentX = AlignmentX.Left,
            AlignmentY = AlignmentY.Top,
            Opacity = 0.6,
            Transform = _ruling,
        };
    }

    private readonly TranslateTransform _ruling = new();

    /// <summary>
    /// Dragging the empty surface moves the surface.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A graph outgrows its window, and reaching the far end of one by
    /// hunting for a scrollbar is how a canvas stops being a canvas.
    /// Taking hold of the surface and pulling is what every other canvas
    /// in the world does.
    /// </para>
    /// <para>
    /// <b>Only the empty surface.</b> A node handles its own press — it
    /// selects, and it drags itself along the chain — so a press that
    /// reaches the canvas is a press on nothing, and that is the one that
    /// means "move the view". The middle button moves it from anywhere,
    /// including from on top of a node, which is the other half of the
    /// same convention.
    /// </para>
    /// <para>
    /// The cursor tells the truth: a hand only while there is somewhere
    /// to move to. On a graph of two nodes that fits, pulling does
    /// nothing, and a cursor promising otherwise is a small lie told
    /// every time the editor is opened.
    /// </para>
    /// </remarks>
    private void Roam()
    {
        Deck.MouseLeftButtonDown += (_, e) => TakeSurface(e);
        Deck.MouseDown += (_, e) =>
        {
            if (e.ChangedButton == System.Windows.Input.MouseButton.Middle)
                TakeSurface(e);
        };
        Deck.MouseMove += (_, e) => MoveSurface(e);
        Deck.MouseLeftButtonUp += (_, _) => DropSurface();
        Deck.MouseUp += (_, e) =>
        {
            if (e.ChangedButton == System.Windows.Input.MouseButton.Middle)
                DropSurface();
        };

        // A double-click on the empty surface asks for the middle back.
        // Without a way back, "move it wherever you like" is a way to
        // lose the graph.
        Deck.MouseLeftButtonDown += (_, e) =>
        {
            if (e.ClickCount == 2) Centre(anyway: true);
        };

        // The wheel moves the surface as the hand does. `ScrollViewer`
        // used to do the upright half; there is no scroll viewer any
        // more, and a graph that forks is wider than it is tall, so
        // both halves are here.
        Deck.PreviewMouseWheel += (_, e) =>
        {
            var sideways = System.Windows.Input.Keyboard.Modifiers
                           == System.Windows.Input.ModifierKeys.Shift;
            Shift(sideways ? e.Delta : 0, sideways ? 0 : e.Delta);
            e.Handled = true;
        };

        Deck.Cursor = System.Windows.Input.Cursors.Hand;
        Deck.ToolTip = S("Потяните, чтобы подвинуть холст. Двойной щелчок — вернуть на место");
    }

    private Point _tookAt;
    private Vector _tookFrom;
    private bool _holding;

    /// <summary>Move the surface by so much, and remember that it moved.</summary>
    private void Shift(double across, double down)
    {
        Roaming.X += across;
        Roaming.Y += down;
        _ruling.X = Roaming.X;
        _ruling.Y = Roaming.Y;
        _roamed = true;
    }

    private void TakeSurface(System.Windows.Input.MouseButtonEventArgs e)
    {
        _tookAt = e.GetPosition(Deck);
        _tookFrom = new Vector(Roaming.X, Roaming.Y);
        _holding = true;
        Deck.CaptureMouse();
        Deck.Cursor = System.Windows.Input.Cursors.ScrollAll;
    }

    private void MoveSurface(System.Windows.Input.MouseEventArgs e)
    {
        if (!_holding) return;
        var now = e.GetPosition(Deck);
        // **Nothing bounds this.** The surface is not a sheet with a
        // window over it; it goes where it is pulled.
        Roaming.X = _tookFrom.X + (now.X - _tookAt.X);
        Roaming.Y = _tookFrom.Y + (now.Y - _tookAt.Y);
        _ruling.X = Roaming.X;
        _ruling.Y = Roaming.Y;
        _roamed = true;
    }

    private void DropSurface()
    {
        if (!_holding) return;
        _holding = false;
        Deck.ReleaseMouseCapture();
        Deck.Cursor = System.Windows.Input.Cursors.Hand;
    }

    /// <summary>Move the surface — for the check.</summary>
    public (double Across, double Down) RoamForCheck(double across, double down)
    {
        Shift(across, down);
        Deck.UpdateLayout();
        return (Roaming.X, Roaming.Y);
    }

    /// <summary>Put it back in the middle — for the check.</summary>
    public (double Across, double Down) CentreForCheck()
    {
        Centre(anyway: true);
        return (Roaming.X, Roaming.Y);
    }

    /// <summary>Where the graph sits inside the box — for the check.</summary>
    /// <summary>The box and the graph in it — for a failing check.</summary>
    public string Sizes =>
        $"холст {Deck.ActualWidth:0}x{Deck.ActualHeight:0}, "     // not UI
        + $"граф {Board.ActualWidth:0}x{Board.ActualHeight:0}";   // not UI

    public (double Left, double Right, double Top, double Bottom) GraphSides()
    {
        Deck.UpdateLayout();
        return (Roaming.X,
                Deck.ActualWidth - Roaming.X - Board.ActualWidth,
                Roaming.Y,
                Deck.ActualHeight - Roaming.Y - Board.ActualHeight);
    }

    /// <summary>Is the surface ruled — for the check.</summary>
    public bool SurfaceRuled => Deck.Background is DrawingBrush
    {
        TileMode: TileMode.Tile,
    };

    /// <summary>
    /// Where everything on the surface sits — for the check.
    /// </summary>
    /// <remarks>
    /// "The components stand crookedly" is a sentence about numbers:
    /// something is outside the surface it stands on. Those are the
    /// numbers.
    /// </remarks>
    public (int Outside, double Worst, string Where) OffTheSurface()
    {
        var outside = 0;
        var worst = 0.0;
        var where = "";
        foreach (var child in Board.Children.OfType<FrameworkElement>())
        {
            var left = Canvas.GetLeft(child);
            var top = Canvas.GetTop(child);
            if (double.IsNaN(left) || double.IsNaN(top)) continue;
            child.Measure(new Size(double.PositiveInfinity,
                                   double.PositiveInfinity));
            var over = Math.Max(
                Math.Max(-left, -top),
                Math.Max(left + child.DesiredSize.Width - Board.Width,
                         top + child.DesiredSize.Height - Board.Height));
            if (over <= 0.5) continue;
            outside++;
            if (over <= worst) continue;
            worst = over;
            where = $"{child.GetType().Name} ({left:0}, {top:0})";
        }
        return (outside, worst, where);
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
