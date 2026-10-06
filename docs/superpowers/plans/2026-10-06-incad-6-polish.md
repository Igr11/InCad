# InCad 6 — Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Sweep, Loft, Coil, Draft, materials, section view and an InCad-aware Delete.
**Spec:** `docs/superpowers/specs/2026-10-06-incad-stage6-polish-design.md`

## Global Constraints
- Stage-1..5 constraints hold.

## Review Focus
1. Coil never claims a thread (and vice versa) (Task 1 test).
2. Delete of a Combine leaves no hidden helper keeping a parameter in use (Task 3 test).
3. Delete is one undo step and undo restores formulas (Task 3 test).
4. A Loft with sections in the wrong order or one section is refused plainly (Task 1 test).
5. Mass Properties follows the material (Task 2 test).

### Task 1: Sweep, Loft, Coil, Draft kinds — `features/shapes.py`, `tests/headless/test_shapes.py`
### Task 2: Materials — `core/materials.py`, `core/inspect.py`, `tests/headless/test_materials.py`
### Task 3: Delete — `core/delete.py`, `tests/headless/test_delete.py`
### Task 4: Commands, icons, ribbon, section view, GUI tests, README
