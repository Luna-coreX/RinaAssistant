# ADR 0005 — Control library for the shell

- **Status:** accepted
- **Date:** 2026-09-02
- **Plan item:** `4.0-F01b`
- **Follows:** `4.0-F01` (WPF), `4.0-R02`/`4.0-R03` (direction and design system)
- **Enables:** `4.0-F02` (project skeleton), `4.0-F03`, `4.0-F04`, `4.0-F07`

## Context

`4.0-F01` chose WPF. WPF ships with unstyled controls and no window chrome, so a second question follows immediately and has to be answered before the skeleton exists: do we take a control library, and if so which.

The obvious candidate is **WPF-UI** (`WPF-UI` on NuGet, `lepoco/wpfui`, MIT, 4.3.0 published 2026-05-04, targets .NET 8/9/10 and .NET Framework 4.6.2+). It offers `FluentWindow` with Windows 11 snap layouts and Mica backdrop, `TitleBar`, `NavigationView`, `NotifyIcon`, `ContentDialogService`, `SnackbarService`, `ApplicationThemeManager` and Fluent-styled versions of the base controls. Against the usual criteria — maturity, licence, coverage, cost of adoption — it wins comfortably. The licence is compatible with ours (`ADR 0001`, Apache-2.0).

The criterion that decides this, though, is not any of those. It is `4.0-R02`: the shell has a visual language of its own, written down in [`DIRECTION.md`](../design/DIRECTION.md) and [`SYSTEM.md`](../design/SYSTEM.md), and a library brings a visual language with it. So the question is narrower than "is WPF-UI good": **how much of what it provides would survive contact with our design system, and how much would we be overriding.**

That is measurable, because the direction already carries a twelve-question test for "in style or not" (`DIRECTION.md`, §6). Applying it to Fluent's defaults, verified against the library's own resource dictionaries rather than from memory:

| Question from `DIRECTION.md` §6 | Fluent's default answer | Conflict |
|---|---|---|
| Is there a written legend on every control? | `NavigationView` is icon-first; icons hide the label in compact mode | yes |
| What glows on the panel? | Mica backdrop and accent-tinted hover | yes |
| What separates regions? | dialogs, flyouts and snackbars carry drop shadows | yes |
| Corner radius over 3 px? | `ControlCornerRadius` 4, `OverlayCornerRadius` 8 | yes |
| More than one accent colour? | `SystemAccentColorPrimary`/`Secondary`/`Tertiary`, taken from the Windows accent | yes |
| Danger shown by colour rather than hatching? | `SystemFillColorCritical` = `#C42B1C` | yes |
| Icon without a caption? | title bar, number-box spinners, snackbar icons | yes |
| Proportional figures? | Segoe UI Variable, proportional by default | yes |
| Any gradient beyond the level strip? | `ControlElevationBorderBrush` is a `LinearGradientBrush` — every button and text box border carries one | yes |
| Is a command card edited in a modal constructor? | `ContentDialogService` pushes exactly that way | leans yes |
| Metal texture, bevels, screws? | no, Fluent is flat | no |
| How does the listening state change? | not the library's concern | n/a |

**Nine of the twelve conflict.** Two of those — the red critical brush and the gradient border — are not merely different taste; `tools/check_design.py` fails the build on them, because "no red in the palette" and "exactly one gradient" are asserted rules rather than preferences.

Two facts about how the library is put together matter as much as the count.

**Its styles are implicit.** `Wpf.Ui/Controls/Button/Button.xaml` declares `<Style BasedOn="{StaticResource DefaultButtonStyle}" TargetType="{x:Type Button}" />` — a style with no `x:Key`, targeting the *standard* WPF `Button`. Merging `Controls.xaml` therefore restyles the whole application, not only the places where a `ui:` control is used. Adopting the library "just for the window" is not a thing that exists: the styling comes with it and would have to be neutralised everywhere.

**Its values are `DynamicResource`.** Corner radius and every brush resolve through theme keys, so colour and radius genuinely can be retargeted by redefining those keys. This is the fair half of the picture and it should be said plainly: the palette conflicts are cheap to fix. What is not cheap is structure — icons in the navigation, spinners, shadowed overlays, the gradient border, `ApplicationThemeManager`'s assumption that a theme is Light or Dark when our two finishes are neither. Those need templates replaced, and a library whose templates are replaced is providing plumbing, not controls.

So the real question is the value of that plumbing on its own, and there is little of it. `NavigationView` solves a problem we do not have — five fixed sections, no icons, no compact mode, plugin pages nested inside a section rather than added to the rail (`4.0-R04`) — and is harder to restyle than to replace with an items control. `ContentDialogService` does not support the timeout and default-refusal that `4.0-F11` requires, so the confirmation dialog is ours in any case. `ApplicationThemeManager` works against `4.0-R08`. `NotifyIcon` is genuinely useful, and so is `FluentWindow`.

`FluentWindow` is the one real loss, because borderless windows on Windows are not a solved problem by hand: resize borders, the maximised-window padding bug, per-monitor DPI, and Windows 11 snap layouts, which require answering `WM_NCHITTEST` with `HTMAXBUTTON` over the maximise button. The in-box alternative is `System.Windows.Shell.WindowChrome`, which covers everything except the snap-layout hit test; that remainder is a bounded piece of interop, not an open-ended one.

## Decision

**Own styles over standard WPF controls. WPF-UI is not taken.**

Where a specific piece of platform plumbing is needed, it is taken from a single-purpose dependency rather than from a design library:

- **Window frame** — `System.Windows.Shell.WindowChrome`, in the box, plus a window-procedure hook returning `HTMAXBUTTON` so Windows 11 snap layouts work over our own maximise button.
- **Tray icon** — `H.NotifyIcon.Wpf` (MIT, 2.4.1, no Windows Forms dependency). WPF has no tray icon of its own and this is the narrowest way to get one.
- **MVVM** — `CommunityToolkit.Mvvm`, as already recorded in `4.0-F01`.

Two consequences of this decision are load-bearing enough to be part of it rather than notes underneath.

**`tokens.json` generates the resource dictionary.** A tool writes `Tokens.xaml` from `docs/design/tokens.json`, the same way `tools/build_mockups.py` writes the mockups today. Hand-copying values into XAML would recreate exactly the drift that keeping one value in one place was meant to prevent, and it would do so silently.

**The shell carries a control gallery.** The states sheet that exists in the mockups becomes a page in the application, reachable in debug builds. Without a library there is nothing external keeping our controls consistent, so the thing that keeps them consistent has to be ours and has to be visible.

## Alternatives considered

**WPF-UI in full.** Rejected on the count above: nine of twelve direction rules would have to be overridden, two of them are enforced by a check that fails the build, and what remains after the overrides is plumbing we mostly do not need. The gain is real for a project that wants to look like Windows. `4.0-R02` decided that this one does not.

**Hybrid — WPF-UI for the window, tray and dialogs; own styles for content.** This was the most attractive option and is the one closest to being right. It was rejected on the implicit-style fact: taking the library means merging a dictionary that restyles every base control in the application, so "only for the window" would mean auditing and neutralising styles across the whole surface — plus carrying version coupling on a library we would then be actively working around. Merging only the `FluentWindow` sub-dictionary is undocumented and would be fragile across releases. The saving over `WindowChrome` plus a hit-test hook is roughly a day; the coupling lasts as long as the shell does.

**MahApps.Metro, MaterialDesignInXAML, ModernWpf.** Rejected for the same reason as WPF-UI and more so: each brings a complete and *stronger* visual identity — Metro, Material, Fluent respectively — and none of them is ours. A library whose look we want is worth its coupling; a library whose look we override is coupling without the look.

**Windows Forms `NotifyIcon` via `UseWindowsForms`.** Rejected: pulling the Windows Forms stack into the process to get one tray icon is a larger dependency than the focused package, and it complicates trimming and single-file publication later.

## Consequences

**Gained.** No library sits between the design system and the screen. The twelve questions of `DIRECTION.md` §6 stay answerable, because nothing is quietly deciding radius, accent or elevation on our behalf. Upgrades are ours to schedule: no styling dependency can change the application's appearance in a patch release.

**Paid.** Every control is written once: button, field, toggle, card, combo box, number field, hotkey capture, scroll viewer with pinned section legends, dialog, glass transcript, level strip. This is the largest single cost in block F and it is paid up front, in `4.0-F02` and `4.0-F04`. The window frame costs interop we would otherwise have got for free.

**Constrained.** Accessibility now belongs to us in full — keyboard navigation, focus visuals, automation peers, high contrast. A library would have supplied defaults for these; nothing supplies them now, so `4.0-F04` must treat them as work rather than as behaviour that arrives with the controls.

**Deferred, with a named trigger.** If the window chrome turns into a swamp — snap layouts, DPI transitions or maximised-window padding costing materially more than the day this was estimated at — the fallback is to take WPF-UI for `FluentWindow` alone and pay the cost of neutralising its implicit styles, which is annoying but bounded and reversible. That is a change of implementation, not of this decision: the styling stays ours either way. Anything beyond that would need a record superseding this one.

**Settled elsewhere.** The `wpfui-fluent` skill is a usage guide for this library, not a design reference. With the library not adopted, the skill has no role in this project. The design-judgement skills are unaffected — that separation was already recorded under block R.
