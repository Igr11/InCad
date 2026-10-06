# InCad 3 — Combine with Clearance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Combine solids of a part (Join/Cut/Intersect) keeping the tools, with a parametric print clearance on
the cavity, on a fit copy of the tool, or split.

**Architecture:** One kind module drives a native `PartDesign::Boolean` in the base body; clearance goes through
`Part::Offset` helpers bound to a model parameter; fit copies are Bodies based on a shrunk offset.

**Tech Stack:** FreeCAD 1.1.3 PartDesign Boolean, Part Offset, PySide6.

**Spec:** `docs/superpowers/specs/2026-10-06-incad-stage3-combine-design.md`

## Global Constraints

- Stage-1/2 constraints hold. Tools are never deleted or modified by Combine. Helpers are named after their tool.

## Review Focus

1. Cancel/undo leaves no helper offsets or fit bodies behind (Task 2 GUI test).
2. Editing a tool body updates the result and the fit copy (Task 1 test).
3. Switching apply_to or operation on edit removes helpers that are no longer used (Task 1 test).
4. Picking a face of a solid as base/tool means that solid (Task 1 test).
5. A tool equal to the base is refused plainly (Task 1 test).

### Task 1: Combine kind (headless)
Files: `InCad/incad/features/combine.py`, `features/__init__.py`, `features/common.py` (pick `body`),
`core/tree.py` (hide helper offsets, list fit bodies), `tests/headless/test_combine.py`.
Tests: cut+cavity 0.2 volume = block − π·4.2²·10; tool+tool: cavity exact, fit body volume of the shrunk pin
(offset of every face), original tool hidden; split: cavity r 4.1, fit r 3.9; parameter 0.2 → 0.5 updates both;
join and intersect volumes; edit cavity→tool removes the grown offset; base == tool refused; face pick resolves
to the body; tool edit (pad length) updates the result.

### Task 2: Command, icon, ribbon, GUI tests
Files: `tools/make_icons.py` (combine), `actions.py` (`feature.combine`), `ribbon_layout.py` (Modify group),
`tests/gui/test_combine.py`, `tests/widgets/test_actions.py`.
Tests: two solids selected → Combine (base = first, tools = rest) → Cut, clearance on Tool → OK → fit body exists,
one undo step "Combine"; Cancel leaves no new objects.

### Task 3: Look check, README.
