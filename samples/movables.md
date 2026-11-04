# Movable elements catalog: twenty classic LEGO doors, lids and hinges in motion

Twenty small LEGO scenes, each built around one classic movable element: a house door, windows and shutters, a garden gate, cupboards, a treasure chest, a trap door, car doors, a spaceship canopy, a forklift, a radar, a mini crane, a drawbridge and more. Each scene moves its element in three different ways, from a smooth open-and-close to a slam with a bounce, so this is a catalog of 60 separate animations, all playing at once on one floor in the video. Claude Code built the scenes and the animations in about 77 minutes.

▶ [Watch the video](movables.mp4)

## At a glance

| | |
|---|---|
| LEGO model | None given: twenty small scenes built from the part lists in `data/categories/parts/` (doors, windows, hinges, containers and others), copying official LEGO sets where they use the same parts |
| Made by | Claude Code (Claude Opus 5.5) |
| When | 2026-10-07, 20:02–22:00 Madrid time |
| Working time | About 77 min of agent work, plus a 41 min wait for the user's answers to two questions |
| Result | [movables/movables.blend](movables/movables.blend): an overview scene plus one scene per element, 480 frames at 24 fps (20 s) |

## How to view it

1. Open [movables/movables.blend](movables/movables.blend) in Blender 5.2 or later.
2. Press Play (Space). The **Catalog** scene shows all twenty elements in a labelled grid. Each one plays its first animation in frames 1–144, its second in 161–304 and its third in 321–464.
3. To see one element alone, switch to its own scene, from `S01 House front door` to `S20 Control levers`, in the scene selector at the top right. Each has its own camera and timeline markers named after its three animations.
4. Each element has its own controller, `CTRL_movable_01_…` to `CTRL_movable_20_…`, with its controls under **Object Properties → Custom Properties**. Each animation is a separate Blender action, named like `S07_treasure_chest.slow_reveal`, on its own NLA track. [movables/CATALOG.md](movables/CATALOG.md) explains how to reuse them.

## What was asked

> Do the following: read @instructions.md , and then let's do something different: animate typical lego movable elements, like e.g. windows, doors, etc.
>
> You've got the different parts categories under @data/categories/parts, on every .py file you'll find parts in the category the filename says, like e.g. doors.py, windows.py, etc.
>
> Find the typically moveable ones, again classical LEGO (i.e. non-technics), excluding minifigs (that's already done).
>
> Once you've got that, do the following: build 20 different mock scenarios, and animate them in different ways, in order to have a catalog of movements.
>
> Mock scenarios would be like e.g. a small wall with an attached window, animated to open and close repeatedly, same as with doors, traps, non-technic car doors, ramps...
>
> End result should be a .blend file with the requested scenarios on it, and requested animations
>
> Regarding the end result, clearly separate every different animation for every different case, so that every scenario "howto" can be selected by other agents for the particular needs they have when building a new model.

## What happened

1. The agent searched the part lists for elements that can move and whose hinge or pin positions are known. It asked two questions; the user chose three animations per element, and an overview scene plus one scene per element.
2. For each element it built a small static setting from plain bricks (a wall, a fence, a car body, a castle gate). Where an official LEGO set uses the same pair of parts, it checked its placement against that set; most match exactly.
3. Some candidates were dropped:
    - a roll-up shutter, because it bends and cannot move as one piece (the forklift replaced it);
    - click hinges for the drawbridge, which collided at once (plain hinges replaced them);
    - several doors with no connection data and no official model to copy from.
4. It found that one hinge plate's built-in connection data points along the plate instead of along its hinge. The tipper uses the matching hinge tile's axis instead, and the finding is noted for future work.
5. Reviewing rendered images, it fixed what looked wrong:
    - the casement window opened away from the viewer, so it was turned around;
    - the spaceship canopy's front had to be flattened to let it swing open;
    - the overview camera hid the labels of the back rows.
6. All checks passed, including 296 tests, and the agent delivered at 22:00.

## Files

All paths are relative to `samples/`.

| File | What it is | Why it exists |
|---|---|---|
| [movables.mp4](movables.mp4) | Screen recording of the Catalog scene playing in Blender, made by the user | To show the result |
| [movables/movables.blend](movables/movables.blend) | The twenty rigged elements with all 60 animations: one overview scene and one scene per element | The final result: open this |
| [movables/CATALOG.md](movables/CATALOG.md) | Guide for reusing the animations: every element and its controls, every animation, an index by style ("which one shows a slam with a bounce?"), collision results and copy-paste snippets | The main reference for anyone reusing an element's motion |
| [movables/REPORT.md](movables/REPORT.md) | The agent's full write-up: how each element was placed, findings worth reusing, checks and limits. Its `previews/` folder was not kept in this sample | Background for the catalog |
| [movables/catalog.json](movables/catalog.json), [movables/clips/](movables/clips/) | The same catalog as data, and one file per animation (60 in all) with its keyframes and its value at every frame | To reuse the animations without Blender |
| [movables/S01_house_door/](movables/S01_house_door/) … [movables/S20_levers/](movables/S20_levers/) | One folder per element, with the same layout: `source/scenario.mpd` (the scene as an LDraw model) and `source/parts.json` (each part's role and the official-set comparison), the motion plan, its checks and the toolkit's analysis (`study/`) | Everything needed to understand or rebuild one element |
| [movables/mpd-summary.json](movables/mpd-summary.json), [movables/plan-summary.json](movables/plan-summary.json) | One-line summaries per element: parts, joints and official-set comparisons; plan status | Quick overview of all twenty |
| [movables/cli-checks.txt](movables/cli-checks.txt), [movables/pytest.log](movables/pytest.log) | Results of the toolkit's plan checks on all twenty elements, and of the test suite (296 passed) | Shows the plans and code pass |
| [movables/animation-check.json](movables/animation-check.json), [movables/animation.log](movables/animation.log) | Check that every element follows its animation at 28 sample frames, in the overview and in its own scene, and the build log | Shows the file plays as planned |
| [movables/reopen-check.json](movables/reopen-check.json), [movables/reopen.log](movables/reopen.log) | Check after reopening the file, including the car-door animation played on the cabinet | Shows the file and the reuse work on their own |
| [movables/clearance-summary.json](movables/clearance-summary.json), [movables/clearance.log](movables/clearance.log) | Collision scan of every element's controls and animations | Where the movement ranges come from |
| [movables/adapter-checks/](movables/adapter-checks/) | Rebuild-and-remove checks of the three elements with linked parts (forklift, crane, drawbridge) | Shows those rigs are safe to reuse; not part of the catalog |

## Known limits

- Bounces, overshoots, swings and drops are animation curves, not physics.
- The settings around each element are invented from plain bricks, not taken from official sets.
- The forklift's spring is stretched as a whole, so its coils touch the forks slightly (about 0.6 mm).
- Three elements touch at their edges just before closing: the two casement panes, the gate against the fence, and the canopy against the hull.
- The crane's hook hangs from a brick with a hole instead of a string.
- The collision scans checked sample frames only.

## Source

Claude Code chat `3693ec63-5516-4063-ae73-15503685b2cb`, stored on the author's machine under `~/.claude/projects/-Users-captain-workspaces-workspace-ai-ldraw-mecha/`. Times come from the chat log, not from file dates. The file dates all fall in the last minutes of the session, because the agent rebuilt everything in one final run.
