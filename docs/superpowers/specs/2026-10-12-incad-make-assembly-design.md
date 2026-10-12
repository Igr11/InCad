# InCad — Split by sketch and Make Assembly from a part's separate pieces (design)

Agreed with the user on 2026-10-12 (Inventor's Make Components). Replaces Move Solid, which is dropped: shapes are made
in the part with sketches and part tools; separate parts are positioned in an assembly (Assemble's constraints) and
combined there with the assembly Boolean (stage 5). The branch `move-solid` is not merged; its Boolean Keep tool,
clearance labels, dialog fixes and the `detach_lump` fixes go to `main` separately. The gizmo spec of today is cancelled.

## 1. Split by sketch (part feature)

- **Command** 3D Model ▸ Modify ▸ **Split** (`feature.split`). Pick a **sketch** with one or more **lines** (segments,
  arcs, splines; open or closed). Each line is extruded along the sketch's normal, both ways, through the whole part
  into a **surface of zero thickness** (a straight line gives a plane, an arc or a spline a curved surface); these
  surfaces are the knife.
- **Mode** (choice): **Split** — the part is divided along them and every piece stays (the pieces touch but are
  separate solids); **Cut** — only the pieces clicked in the view stay (Keep field, picks on the preview), the rest is
  removed.
- A step in the history (`PartDesign::FeaturePython`, proxy `SplitFeature` in `incad.features.split`, like Hole ▸
  Chamfer): editing the sketch re-splits, delete / End of Part as for any feature. Kept pieces are stored as points
  (a picked spot inside each); on recompute the piece holding (nearest to) each point stays.
- A sketch line that misses the part, or a knife that splits nothing: "The sketch does not cut the part".

## 2. Make Assembly

- **Command** 3D Model ▸ **Make Assembly** (`file.make_assembly`), also in the empty-space right-click list. Needs at
  least **two pieces**: every Solid (Body) of the part, and every solid of a Solid's shape — a box drawn away from the
  part (kept in the part by an older file — Thread_1) or the pieces of a Split. Otherwise: "This part is one piece:
  nothing to assemble". Features that touch and fuse are one piece (the user builds separate parts with a known gap,
  or splits them).
- The part must be saved (its folder takes the files); an unsaved part is refused with "Save the part first".
- **One dialog with the names**, filled in: the assembly `<Part>-Assembly`, each piece `<Part>-Solid1`, `-Solid2`, …
  (largest first), each row with the piece's volume; hovering a row highlights that piece in the view. A name whose
  file exists is refused in the dialog (never overwritten). Files go to the part's folder.
- **OK** makes:
  - **one part file per piece, with its history** (sketches, features, threads, model parameters): a copy of the part
    file from which the other pieces are removed — separate pieces of a Solid are first split into Solids with
    `document.detach_lump`, then every other Solid is deleted; the pieces of a Split stay in its history and the copy's
    Split is set to Cut keeping that piece. All model parameters are kept in every copy.
  - **the assembly file** (stage 4 `assembly.make_assembly` / `place`): every part linked **where it was** (identity
    placement: the part files keep the original coordinates), the **largest grounded**.
  - The original part file is **not changed**; the assembly opens in a new tab.
- **Failure**: if a piece's copy has a feature in error after the split, or a file can't be written, nothing is left:
  files already made are removed, and the message names the piece and the reason.

## Code

- `incad/features/split.py` (new): the Split kind and the proxy (knife faces from the sketch's edges extruded past the
  part's bounding box; `BOPTools.SplitAPI.slice(base, faces, "Split")`; Cut keeps the pieces at the stored points).
- `incad/core/make_assembly.py` (new): `pieces(doc)` (Bodies and their separate pieces, by volume), `default_names`,
  `make(doc, names)` → the assembly path; uses `document.lump_at` / `detach_lump`, `assembly.make_assembly`, `place`,
  `ground`. Copies are made by saving the part to the new file names and opening them (freecadcmd-safe).
- `incad/ui/make_assembly_dialog.py` (new): the names dialog (row hover → highlight via `core/feature_faces`-style
  ShapeAppearance or a view marker).
- `incad/actions.py`, `ui/ribbon_layout.py`, `ui/marking_layout.py`, `tools/make_icons.py`: command and icon.

## Testing

- Headless `test_split.py`: a line through a box gives two pieces of the right volumes; an arc gives a curved cut;
  two lines give three pieces; Cut keeps the clicked piece and follows a changed sketch; a missing cut is refused;
  save and reopen recomputes (proxy found).
- Headless `test_make_assembly.py`: a part with a box drawn away (one Body, two pieces) and a part with two Solids →
  two part files, each one piece, no feature in error, history kept (the box's Pad and sketch are there), the assembly
  links both at their old places, the largest grounded, the original file unchanged; an existing file name is refused;
  a one-piece part is refused; a failure removes the files made; a split box gives two part files whose Split keeps
  one piece each.
- GUI: the dialog on a two-piece part, OK opens the assembly tab. Then once on a copy of the user's Thread_1: the
  block and the main part (which keeps its stub and Thread002).

## Out of scope

A gap made by the Split itself (the user models clearance), surfaces other than extruded sketch lines, choosing which pieces go (all separate ones do), keeping the part and assembly
linked back (the part file stays as it was), multi-level assemblies.
