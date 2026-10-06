# InCad Stage 4 — Assemblies (design)

Base: stage-1 spec roadmap row 4 and the brainstorm decisions: Inventor-style separate part and assembly files,
first part grounded, both constraints and joints, create in place. Native FreeCAD 1.1.3 Assembly objects underneath.
Written autonomously; decisions are rulings for the user's later review.

## 1. Behaviour

- **New ▸ Assembly** (New dialog tile, and `file.new_assembly`): an assembly document (Assembly object + Joints
  group, marker `InCadAssembly` in doc.Meta, units like parts). Mode "assembly": ribbon tab **Assemble**
  [Place, Create] [Constrain: Mate, Flush, Angle, Tangent, Insert] [Joints: Rigid, Rotational, Slider,
  Cylindrical, Ball] [Ground]; View tab as in parts.
- **Place** (P): pick a part (or assembly) file; it is linked (App::Link to its main solid), placed at the origin
  (first) or beside the bounding box of what is there (next ones). The **first placed component is grounded**.
  Placing the same file again adds another occurrence.
- **Create** (in place): asks for a name, saves a new InCad part file next to the assembly (same units), places it
  grounded-free at the origin and opens it in its own tab for modeling (Inventor "open" rather than in-place
  editing — ruling). The assembly follows the part's changes when it recomputes.
- **Constraints** (Inventor) → FreeCAD joints: Mate = Distance (faces opposed, offset), Flush = Distance with the
  second face reversed (faces same direction, offset), Angle = Angle (value), Tangent = Distance on a cylinder/face
  pair, Insert = Revolute on two circular edges (axes aligned, planes mated). **Joints**: Rigid = Fixed,
  Rotational = Revolute, Slider, Cylindrical, Ball. Offsets/angles are model parameters (Parameters panel).
- **Ground / Unground** a component (marking menu and ribbon). Browser: components with a pin on grounded ones,
  a "Relationships" group listing constraints/joints (double-click edits).
- Assembly files must be saved before linking: Place/Create on an unsaved assembly ask for its file first.

## 2. Probed facts (FreeCAD 1.1.3)

- `Assembly::AssemblyObject` + `Assembly::JointGroup`; joints are `App::FeaturePython` with
  `JointObject.Joint(obj, JointTypes.index(type))`; grounding: `JointObject.GroundedJoint(obj, part)`.
- References must name the moving component: `[link, ["Face5", "Face5"]]` (element only); then
  `joint.Proxy.setJointConnectors(joint, refs)` + `assembly.solve()` places it (Mate probe: block onto plate,
  zmin = 10). Assembly-root paths (`[assembly, ["Link.Body.Pad.Face5"]]`) do not solve headless.
- Linking to another file needs the assembly document saved first ("Owner document not saved").

## 3. Out of scope (stage 4)

Dragging components with the mouse (moved by constraints and by Ground/position values only), sub-assembly
flexibility, patterns of components, BOM, exploded views, contact/collision.

## 4. Testing

Headless: make/recognise assemblies, place grounds the first, second placed beside, each constraint and joint
solves to the expected placement, offset parameter drives the solve, ground/unground, create part file next to the
assembly. GUI: New assembly → Place two saved parts → Mate → one undo step; browser shows the components.
