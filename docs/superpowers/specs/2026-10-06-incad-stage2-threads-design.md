# InCad Stage 2 — Real Threads for 3D Printing (design)

Base: stage-1 spec `2026-10-05-incad-stage1-design.md` (roadmap row 2). Written autonomously (the user asked
for the whole roadmap to be built without check-ins); every decision below is a ruling the user reviews later.

## 1. Intent

Threads that print: real helical geometry (no cosmetic threads), in every common standard, with a print clearance
so a printed bolt fits a printed nut (and a metal bolt fits a printed hole). Two entry points, as in Inventor:

- **Thread** (Modify group): pick a cylindrical face — outside of a shaft (external thread) or inside of a bore
  (internal thread). Standards: ISO metric coarse, ISO metric fine, UNC, UNF, G/BSP (55°), NPT (tapered),
  trapezoidal Tr (30°), ACME (29°), Print-friendly (ISO-compatible, flat crests and roots), Custom
  (pitch, flank angle, depth).
- **Hole ▸ Threaded**: the Hole dialog gets a Threaded option for FreeCAD-supported standards (ISO, ISO fine, UNC,
  UNF, UNEF, NPT, G/BSP, BSW, BSF), modeled threads, with the print clearance. Other profiles (Tr, ACME,
  print-friendly, custom) on holes: drill a plain hole of the suggested diameter, then Thread its face (the Thread
  dialog suggests the bore diameter for the chosen size).

## 2. Probed facts (FreeCAD 1.1.3)

- `PartDesign::SubtractiveHelix` with a closed groove profile cuts a valid thread: M10×1.5×20 mm in ~0.5 s;
  `Angle` (deg) tapers it (NPT), `LeftHanded`, `Reversed`, `Mode` (`pitch-height-angle` …).
- A sketch attached to a **circular edge** with `MapMode = "SectionOfRevolution"` lies on a plane through the
  axis: origin at the circle centre, local x radial, local y along the axis. Associative to the edge.
  (On a cylindrical face that mode is invalid.)
- `PartDesign::Hole`: `Threaded`, `ModelThread`, `ThreadType` (ISOMetricProfile, ISOMetricFineProfile, UNC, UNF,
  UNEF, NPT, BSP, BSW, BSF, ISOTyre), `ThreadSize` (e.g. `M8x1.25`, `1/4`), `ThreadDirection`, `ThreadDepthType`,
  `UseCustomThreadClearance` + `CustomThreadClearance`. Two modeled M8 through 15 mm: ~5 s.

## 3. Design

- `incad/threads/standards.py` (pure data, no FreeCAD): families (flank angle, crest/root flats, depth rule,
  taper, default print clearance) and size tables; `sizes(std)`, `spec(std, size) -> ThreadSpec`,
  `suggest(std, diameter, internal)`, `bore_diameter(spec, clearance)`.
- `incad/threads/profile.py` (pure geometry): the groove polygon `[(radius, axial)]` for external or internal,
  shifted by half the diametral clearance; groove width is clamped below the pitch so turns never touch (this
  also trims crests when the clearance is large); a radial run-out past the surface for a clean cut.
- `incad/features/thread.py`: Thread kind. One hidden profile sketch on the face's start edge
  (`SectionOfRevolution`) + one `SubtractiveHelix` (ReferenceAxis = the sketch's V axis). Length and offset are
  model parameters (Height bound; offset moves the profile). Standard/size/clearance/hand/internal are stored on
  the helix (`InCadThread` string property, JSON) and regenerate the profile on edit. Internal vs external is
  detected from the face (normal toward the axis = internal).
- Hole kind: `threaded`, `thread_standard`, `thread_size`, `thread_depth` (hole depth / distance),
  `clearance`, `hand` fields; modeled threads with custom clearance.
- Dialog: a `combo` field kind whose options can change with other values (`kind.options(key, values)`):
  Size follows Standard; the Size list starts at the size suggested from the picked face.
- Print clearance default: preference `InCad/ThreadClearance` = 0.2 mm (0.3 mm for Print-friendly).
- Commands: `feature.thread` (icon *thread*, ribbon Modify group, marking menu face list).

## 4. Out of scope (stage 2)

Thread run-out chamfers, multi-start threads, cosmetic threads, threaded Hole with Tr/ACME/print/custom profiles
(use Thread on the bore), automatic thread on every hole centre of a pattern.

## 5. Testing

Headless: tables (known pitches/diameters), profile widths and clearance shifts, Thread on a shaft and on a bore
(valid solid, removed volume within the analytic estimate ±10 %), left hand, taper, edit round-trip, length
parameter drives the helix, threaded Hole with clearance. Widgets: combo options follow another field. GUI: pick a
face → Thread dialog suggests the size → OK → one undo step; Hole ▸ Threaded.
