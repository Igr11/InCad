# InCad 5 — Combine between Assembly Parts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Cut one assembly component by others (with print clearance), written into the base part file and kept in
sync with the tools' shape and position.

**Architecture:** `incad/core/asm_cut.py` creates/updates per-tool proxy links in the base part file and syncs
their placements from the assembly; the stage-3 Combine kind accepts links as tools; an assembly kind
`ASM_COMBINE` drives it through the feature dialog with transactions opened in every touched document.

**Spec:** `docs/superpowers/specs/2026-10-06-incad-stage5-assembly-combine-design.md`

## Global Constraints
- Stage-1..4 constraints hold. No cross-document expressions (cycle). Tools are never modified.

## Review Focus
1. Cancel leaves the base part file unchanged (Task 3 GUI test).
2. Moving the tool by a constraint moves the pocket (Task 2/3 tests).
3. Deleting the record (or the tool component) leaves the base part valid (Task 2 test).
4. A base that is not an InCad part (plain FreeCAD file) is refused plainly (Task 2 test).
5. Two assemblies cutting the same part do not fight (proxies are keyed by assembly file) (Task 2 test).

### Task 1: Combine accepts links as tools
`features/combine.py`: tools may be App::Links (to bodies); tests in `tests/headless/test_combine.py`.
### Task 2: asm_cut model
`core/asm_cut.py`: `create(asm_doc, base_link, tool_links, values) -> record`, `update(record, values)`,
`sync(asm_doc) -> [changed docs]`, `remove(record)`, `records(asm_doc)`; tests `tests/headless/test_asm_cut.py`.
### Task 3: Kind, session transactions in several documents, command, GUI test
`features/asm_combine.py` (kind with `documents(doc, values)`), `ui/feature_session.py` (extra transactions),
`ui/shell.py` (sync after assembly changes), `actions.py` (`assembly.combine`), ribbon, `core/tree.py` (records in
Relationships), `tests/gui/test_asm_combine.py`, README.
