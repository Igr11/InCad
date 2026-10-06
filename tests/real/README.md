# Real-input robot

Drives a real FreeCAD + InCad with **real** mouse and keyboard events (macOS CGEvent), the way a person does.
InCad's QTest-driven GUI tests (`tests/gui`) kept passing while the same steps failed live: FreeCAD's 3D view
takes the keyboard on real mouse moves, Sketcher tools only react to real Coin events, a right-click in the
model tree needs the OS's context-menu event. Only real input reproduces those.

## Build

    tests/real/build_tools.sh        # swiftc → tests/real/bin/{click,move,keys} (git-ignored)

The Terminal (or whatever runs the scripts) needs **Accessibility** permission (System Settings → Privacy &
Security → Accessibility), or the events are silently dropped.

## Run

    tests/real/run_scenario.sh tests/real/scenarios/dimension_place_type_enter.json
    for f in tests/real/scenarios/*.json; do tests/real/run_scenario.sh $f; done

**The screen must be free while a scenario runs**: the robot moves the real mouse and types real keys into
whatever window is in front. Don't touch the machine; don't let the screen lock. One FreeCAD per scenario,
started with a throwaway `user.cfg` (the user's settings are never touched), killed at the end.
Each run keeps its files (state, FreeCAD log, InCad log, screenshots of every FAIL) in `tests/real/runs/<name>-<time>/`.

Menus of a real FreeCAD can be driven with System Events **by the process's unix id** (`first process whose unix
id is <pid>`), never by name — the user's own FreeCAD is usually running too and has the same name.

## How it works

`run_scenario.sh` starts FreeCAD with `driver.py`, which opens InCad with a new part and then polls
`<run>/fc.cmd`; every 150 ms (and after each command) it writes `<run>/fc.state` (JSON): the sketch's named
dimensions and values, the dimension box (name, text, error), the focused widget, the feature dialog (title,
active pick, values, error), busy, the marking menu's items, and the **screen positions** of everything the
robot clicks: dimension labels (via `incad.core.sketch.label_point`), ribbon buttons, model-tree rows, plane-panel
buttons, dialog buttons (OK/Cancel/Apply and choice buttons like `operation.cut`), the dimension box's ✓/✕, and
named 3D points of the current sketch (`point:name=x,y,z`, sketch coordinates).

## Scenario file

```json
{"name": "…", "steps": ["setup:rect_sketch_open", "cmd:sketch.dimension", "click:bottom", "type:15", "keys:36",
                        "expect:s['box'] is None", …]}
```

Step kinds (driver side, sent through the command file):

| step | meaning |
|---|---|
| `setup:<name>` | `empty_part`, `rect_sketch` (20×10 rectangle "SketchA"), `rect_sketch_open` (same, opened for editing, with points bottom/top/left/right, *_place, inside, away), `block` (the rectangle padded 10, Tip = "Pad"), `block_with_top_sketch` (+ "TopSketch" with a circle on the top face) |
| `cmd:<id>` | run an InCad registry command (`sketch.dimension`, `feature.hole`, `sketch.finish`, …) |
| `py:<expr>` | evaluate inside FreeCAD (`App`, `Gui`, `shell`, `commands`, `document`, `sketches`, `util`, `ST`) |
| `point:name=x,y,z` | add a named 3D point (sketch coordinates) to click on |
| `ribbon:id1,id2` | report more ribbon buttons' positions |
| `quit_discard` | answer InCad's Save dialog with Don't Save (for quit scenarios) |

Step kinds (real input, host side):

| step | meaning |
|---|---|
| `click:<spot>` / `dblclick:<spot>` / `rclick:<spot>` | real click at a spot |
| `move:<spot>` | real mouse move to a spot (hover) |
| `keys:<code,code,…>` | real key presses by macOS keycode; `S` prefix = Shift, `C` = Command (`C12` = ⌘Q) |
| `type:<text>` | types the text (US layout; letters, digits, `+-*/()=.,:;` etc.) |
| `wait:<seconds>` | sleep |
| `memo:<key>=<expr>` | remember a value from the state for later steps (`m['key']`) |
| `expect:<python expr>` | PASS/FAIL; `s` is the state, `m` the memo; a FAIL takes a screenshot |
| `shot:<name>` | screenshot of the FreeCAD window |
| `exited:<seconds>` | PASS if FreeCAD ended by itself with exit 0 and no new crash report |

Spots: a named point (`bottom`, `bottom_place`, `away`, …), `label.<dim>` (a dimension's text, e.g.
`label.{m[d0]}` with a memo), `ribbon.<command id>`, `tree.<object name>`, `menu.<item text>`,
`plane.<XY_Plane|XZ_Plane|YZ_Plane>`, `dialog.ok|cancel|apply`, `dialog.<field>.<choice>` (e.g.
`dialog.operation.cut`), `box.apply|cancel`.

Keycodes: 0–9 = 29 18 19 20 21 23 22 26 28 25 · Return 36 · Esc 53 · Tab 48 · Delete 51 · Space 49 ·
`/` 44 · `=` 24 (`+` = S24) · `-` 27 · `*` = S28 · letters a0 s1 d2 f3 h4 g5 z6 x7 c8 v9 b11 q12 w13 e14 r15
y16 t17 o31 u32 i34 p35 l37 j38 k40 n45 m46.

## Writing a scenario

Start from a setup, drive InCad with the ribbon/tree/menu like the user does (prefer `click:ribbon.…` over
`cmd:` where the click itself is under test), `memo` the names FreeCAD assigns (`d0`, `Pad001`), assert with
`expect` after a `wait` long enough for the recompute (1–2 s). Look at `<run>/fc.state` of a failed run to see
what the robot saw; `fail-N.png` shows the screen at that moment.
