# InCad Stage 5 — Combine between Assembly Parts (design)

Base: stage-1 roadmap row 5 ("Combine with clearance between assembly parts: pocket written into the target part
file, updates with the tool") and stage 3 (Combine in a part). Written autonomously; decisions are rulings.

## 1. Behaviour

- In an assembly, **Combine** (Assemble ▸ Component group): Base = one component, Tools = other components,
  Cut only (ruling: Join/Intersect across files make little sense for printing). Clearance + apply_to as in stage 3.
- The cut is written into the **base part's file**: a hidden "<Tool> in <Assembly>" link to the tool's solid,
  placed relative to the base as in the assembly, and a stage-3 Combine Boolean (with the clearance helpers) in the
  base solid. A fit copy (apply_to tool/split) is made in the base part's file too ("<Tool> fit").
- **Updates with the tool**: the tool's shape follows by the link; its position is re-synced by InCad whenever the
  assembly changes (constraints, ground, placement) — the part file recomputes then. Part files changed this way
  are marked modified (FreeCAD asks to save them).
- The assembly keeps a hidden record per cut ("Relationships" lists it as "Cut <Base>"), double-click edits.
- One dialog = one undo step in every document it touches (assembly and base part); Cancel leaves both unchanged.

## 2. Probed facts (FreeCAD 1.1.3)

- A part-file `App::Link` to a body in another file, offset by `Part::Offset`, cuts exactly in a PartDesign
  Boolean (11437.57 mm³ for a 10.4×10.4×5.2 cavity in 40×30×10).
- Binding that link's Placement with a cross-document expression to the assembly placements makes a cycle
  (assembly → part → assembly): "The graph must be a DAG". Hence the explicit re-sync.

## 3. Testing

Headless: cut volume; moving the tool in the assembly + sync moves the pocket; editing the tool part updates the
pocket; apply_to tool → fit body in the base file; edit removes old proxies; Cancel (abort in both documents) leaves
no proxy. GUI: Combine in an assembly → OK → base part file holds the pocket; constraint moves the tool → pocket
follows.
