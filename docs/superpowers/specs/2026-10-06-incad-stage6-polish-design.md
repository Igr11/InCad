# InCad Stage 6 — Polish (design)

Base: stage-1 roadmap row 6 ("Sweep, Loft, Coil, Rib, Draft, Split, materials, section view") plus items the
stage reviews deferred here (an InCad Delete that knows its helpers). Written autonomously; decisions are rulings.

## 1. Features (feature dialog, native PartDesign)
- **Sweep** = AdditivePipe / SubtractivePipe: profile sketch + path sketch (all its edges), Join/Cut.
- **Loft** = AdditiveLoft / SubtractiveLoft: two or more section sketches in order, Ruled, Closed, Join/Cut.
- **Coil** = AdditiveHelix / SubtractiveHelix: profile sketch, axis (default Z), pitch and height parameters, hand,
  Join/Cut. (Threads stay their own tool; Coil never claims an InCad thread.)
- **Draft** = PartDesign Draft: faces, neutral plane, angle parameter, reverse.
- Join/Cut is chosen when creating (switching re-creates); on edit it is fixed (ruling: switching a sweep/loft/coil
  type in place would need the same replace logic as Extrude for little gain).
- **Rib and Split are deferred** (ruling): FreeCAD 1.1.3 PartDesign has no Rib, and Split needs body splitting that
  PartDesign doesn't offer natively.

## 2. Materials
- Tools ▸ Material: PLA (1.24), PETG (1.27), ABS (1.04), ASA (1.07), TPU (1.21), Nylon (1.14), Resin (1.18),
  Aluminium (2.70), Steel (7.85) g/cm³ with a display colour. Stored per part (doc.Meta `InCadMaterial`); Mass
  Properties uses the part's material.

## 3. Section view
- View ▸ Section toggles FreeCAD's clipping plane in the active view (XZ through the origin; FreeCAD's dragger
  moves it).

## 4. Delete
- Delete (key Delete, browser marking menu): one undo step. Combine → Boolean with its helpers and untouched fit
  copies (tools shown again); Thread → helix and its profile; assembly cut record → the cut in the part file;
  constraint/joint → the joint; other features → removed from the solid (the chain is kept; the Tip moves back).

## 5. Testing
Headless per feature (volumes / validity / Tip / edit round-trip), materials (store, density in Mass Properties),
delete (helpers gone, chain kept, undo restores). GUI: ribbon commands open their dialogs; Delete from the
browser; section toggle.
