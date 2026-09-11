using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Shapes;

namespace Rina.Shell;

/// <summary>
/// A slice of the background, softened, under something laid over it
/// (<c>4.0b-E02</c>).
/// </summary>
/// <remarks>
/// <para>
/// WPF has no way to ask what is already drawn beneath an element, so glass
/// cannot be made by softening "what is behind". What it can do is draw the
/// same picture a second time, cut to the piece that happens to lie behind —
/// which is exactly what the title bar does, and this is the same trick
/// where the piece is not the whole width of a window.
/// </para>
/// <para>
/// The piece is worked out from position on the screen and nothing else,
/// which is why this is handed the element rather than the picture:
/// "behind" is a question about where things are, and a bitmap does not
/// know where it is being shown.
/// </para>
/// <para>
/// <b>Never an ancestor of the layer.</b> A brush pointed at something the
/// layer stands inside is a visual asking to draw itself, and WPF answers
/// by drawing nothing at all — silently. That is the reason the home
/// screen's contents live in a box beside the list rather than around it.
/// </para>
/// <para>
/// It costs a softening pass per frame while the panel is open, and nothing
/// at all while it is shut: the brush has no reason to redraw when its
/// element is not on screen.
/// </para>
/// </remarks>
internal static class Glaze
{
    /// <summary>
    /// Keep <paramref name="layer"/> showing the piece of
    /// <paramref name="under"/> that lies behind it.
    /// </summary>
    public static void Follow(Rectangle layer, FrameworkElement under,
                              double blur)
    {
        var brush = new VisualBrush(under)
        {
            ViewboxUnits = BrushMappingMode.Absolute,
            Stretch = Stretch.Fill,
        };
        layer.Fill = brush;
        layer.Effect = new BlurEffect
        {
            Radius = blur,
            KernelType = KernelType.Gaussian,
            RenderingBias = RenderingBias.Performance,
        };

        // On layout rather than on size: the panel moves as well as growing
        // — it rises when it opens and the window it is in can be resized —
        // and a piece worked out once would be of the place the panel used
        // to be. Writing the viewbox does not invalidate layout, so this
        // does not chase its own tail; it is guarded all the same, because
        // a brush told the same rectangle every pass is a redraw nobody
        // asked for.
        layer.LayoutUpdated += (_, _) =>
        {
            if (!layer.IsVisible || !under.IsVisible) return;
            if (layer.ActualWidth <= 0 || under.ActualWidth <= 0) return;

            var at = layer.TransformToVisual(under).Transform(new Point(0, 0));
            var piece = new Rect(at.X, at.Y,
                                 layer.ActualWidth, layer.ActualHeight);
            if (brush.Viewbox != piece) brush.Viewbox = piece;
        };
    }
}
