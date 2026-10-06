# InCad Stage 3 — Combine with Clearance in a Part (design)

Base: stage-1 spec roadmap row 3 and the user's requirement: "Boolean Cut with a clearance offset on the tool, the
target or both, always keeping the cutting tool (for joining them later)". Written autonomously; decisions are
rulings for the user's later review.

## 1. Behaviour (Inventor Combine)

- **Combine** (3D Model ▸ Modify, shortcut none): Base = one solid of the part; Tools = one or more other solids;
  Operation Join / Cut / Intersect. The tool solids are **always kept** (hidden after the combine, still in the
  browser, editable; editing a tool updates the result).
- **Clearance** (Cut only), a model parameter (default 0.2 mm), applied to:
  - **Cavity** — the hole in the base is the tool grown by the clearance (the tool keeps its size);
  - **Tool** — the cavity is exact; a **fit copy** of each tool, shrunk by the clearance, is made as a new solid
    "<Tool> fit" (the original tool is hidden) — print the fit copy;
  - **Split** — half on each (cavity grown by c/2, fit copy shrunk by c/2).
- Changing the clearance parameter updates the cavity and the fit copies.

## 2. Probed facts (FreeCAD 1.1.3)

- `PartDesign::Boolean` (`Type` Fuse/Cut/Common, `Group`) accepts a `Part::Offset` whose `Source` is a Body:
  exact cavity (40×30×10 block − Ø8.4×10 = 11445.82 mm³). The tool body stays a root object.
- `Part::Offset` (`Join = "Intersection"` keeps sharp edges) `Value` can be bound by an expression; negative values
  shrink. A Body with `BaseFeature = <Part::Offset>` is a normal editable solid (fit copy).

## 3. Design

- `incad/features/combine.py`: kind COMBINE (TYPES `PartDesign::Boolean`), fields: base (pick `body`), tools
  (picks `body`), operation (join/cut/intersect), clearance (value_length, Cut), apply_to (cavity/tool/split, Cut).
  Helper objects: per tool, `Part::Offset` "<Tool> grown" (cavity, when clearance on cavity/split) and
  "<Tool> fit shape" + Body "<Tool> fit" (tool/split). Values bound to the clearance parameter with expressions
  (`InCadModel.dN`, `InCadModel.dN / 2`, `-InCadModel.dN`…). Settings stored on the Boolean (`InCadCombine`, JSON).
- Pick kind `body`: a PartDesign Body, or any feature/face of one (resolved to its Body).
- Edit regenerates helpers (removes obsolete ones), keeps the Boolean, its place and one undo step.
- The browser lists fit-copy bodies as solids; helper offsets are hidden from the browser.

## 4. Testing

Headless: cavity/tool/split volumes against analytic values, tools kept, parameter drives cavity and fit copy,
join/intersect, edit round trip removing obsolete helpers, base ≠ tool refused. GUI: select two solids → Combine →
Cut with clearance → OK (one undo step), Esc cancels leaving no helpers.
