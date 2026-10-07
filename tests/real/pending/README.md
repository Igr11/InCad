# Pending scenarios

Written while the screen was locked (2026-10-07 03:40), so never run against real input: they may still have
scenario mistakes. Run each with `tests/real/run_scenario.sh tests/real/pending/<name>.json` when the screen is
unlocked and nobody is using the mouse; move the passing ones into `scenarios/`.

- quit_save_dialog_dont_save — ⌘Q with unsaved changes → InCad's Save dialog → real click on Don't Save → exits
- new_part_dialog_real_clicks — New dialog: real clicks on Inches and Create → new part document in inches
- extrude_cut_dialog_real_clicks — Extrude dialog: real click on Cut, then OK → volume drops
- marking_menu_3d_new_sketch_on_face — right-click on a face in the 3D view → marking menu → Start 2D Sketch on that face
