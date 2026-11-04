# Minifig movement catalog: ten minifigs, three moves each

Ten LEGO minifigures, from a police officer to a diver, stand on one shared stage and each plays its own three short moves at the same time: walks, jumps, sword slashes, waves, a somersault and more. This is a catalog of 30 separate animations sharing one scene, not one story: each move is stored on its own, so it can be reused on another figure. Claude Code built the figures from scratch and animated them in about 75 minutes.

▶ [Watch the video](minifigs.mp4)

## At a glance

| | |
|---|---|
| LEGO model | None given: ten minifigures built from the part lists in `data/categories/parts/minifig/`, checked against the official minifig of set 6682 |
| Made by | Claude Code (Claude Opus 5.5) |
| When | 2026-10-07, 00:59–11:27 Madrid time |
| Working time | About 75 min of agent work: planning that night, then an overnight pause of about 9 h before the user said "continue" |
| Result | [minifigs/minifigs.blend](minifigs/minifigs.blend): ten figures, 30 moves, 480 frames at 24 fps (20 s) |

## How to view it

1. Open [minifigs/minifigs.blend](minifigs/minifigs.blend) in Blender 5.2 or later.
2. Press Play (Space). Every figure plays its first move in frames 1–144, its second in 161–304 and its third in 321–464. The floor labels name each figure and its moves.
3. Each figure has its own controller, `CTRL_minifig_01_police` to `CTRL_minifig_10_diver`, with the same 13 controls under **Object Properties → Custom Properties**: head, shoulders, wrists and hips, plus six that move the whole figure (forward, left, up, turn, lean forward, lean sideways).
4. Each move is a separate Blender action, named like `MF03_knight.sword_slash`, on its own NLA track. To reuse a move on another figure, assign its action to that figure's controller. [minifigs/CATALOG.md](minifigs/CATALOG.md) explains how.

## What was asked

> do the following: read @instructions.md , and then let's do something different: animate Minifigs
>
> you've got the minifigs parts info info under @data/categories/parts/minifig/
>
> now, once you've got that, do the following: build 10 different minifigs, and animate them in different ways, in order to have a catalog of movements.
>
> end result should be a .blend file with the 10 minifigs on it, and requested animations
>
> regarding the end result, clearly separate every different animation for every different minifig, so that information can be chosen for different models by other agents

## What happened

1. The agent studied the part lists and the project's Blender pipeline, then asked two questions. The user chose three themed moves per figure, and moves that can carry the whole figure (walking, jumping, lying down), not just turn its joints.
2. The planning ended late at night. The next morning the user said "continue".
3. The agent put each figure together by fitting each part's connection points into its neighbour's, and checked the result against an official LEGO minifig: it matches to within about half a millimetre.
4. Torsos that come with their arms moulded on could not move their arms, so every figure uses a plain torso with separate arms.
5. It wrote all 30 moves as reusable clips and reviewed each one in rendered images. It fixed what looked wrong: crowded stage labels, the chef's frying pan (now held level), and the wizard's staff swinging into its own leg.
6. A collision scan found hands passing through the head in three moves that swing an arm overhead: the spaceman's wave, the athlete's spin jump and the diver's swim. With these LEGO parts a raised hand always passes inside the head at certain angles, so held poses avoid those angles and only the overhead swings still cross.
7. It proved a move can be reused by playing the knight's sword slash on the chef, and delivered at 11:27.

## Files

All paths are relative to `samples/`.

| File | What it is | Why it exists |
|---|---|---|
| [minifigs.mp4](minifigs.mp4) | Screen recording of the stage playing in Blender, made by the user | To show the result |
| [minifigs/minifigs.blend](minifigs/minifigs.blend) | The stage with the ten rigged figures and all 30 moves | The final result: open this |
| [minifigs/CATALOG.md](minifigs/CATALOG.md) | Guide for reusing the moves: the controls, a table of every move, a Blender snippet, and which moves work cleanly on which figures | The main reference for anyone reusing a move |
| [minifigs/REPORT.md](minifigs/REPORT.md) | The agent's full write-up: figures, joints, checks and limits. Its `previews/` folder was not kept in this sample | Background for the catalog |
| [minifigs/catalog.json](minifigs/catalog.json), [minifigs/clips/](minifigs/clips/) | The same catalog as data, and one file per move (30 in all) with its keyframes and its value at every frame | To reuse the moves without Blender |
| [minifigs/MF01_police/](minifigs/MF01_police/) … [minifigs/MF10_diver/](minifigs/MF10_diver/) | One folder per figure, with the same layout: `source/minifig.mpd` (the figure as an LDraw model) and `source/parts.json` (which part plays which role), the motion plan, its checks and the toolkit's analysis (`study/`) | Everything needed to understand or rebuild one figure |
| [minifigs/animation-check.json](minifigs/animation-check.json), [minifigs/animation.log](minifigs/animation.log) | Check that every figure follows its moves at 23 sample frames, and the build log | Shows the stage plays as planned |
| [minifigs/reopen-check.json](minifigs/reopen-check.json), [minifigs/reopen.log](minifigs/reopen.log) | Check after reopening the file, including the sword slash played on the chef | Shows the file and the reuse work on their own |
| [minifigs/clearance-summary.json](minifigs/clearance-summary.json), [minifigs/clearance.log](minifigs/clearance.log) | Collision scan of each figure's own moves | Records where hands cross the head |
| [minifigs/clearance-summary-all-clips.json](minifigs/clearance-summary-all-clips.json), [minifigs/clearance-all-clips.log](minifigs/clearance-all-clips.log) | Collision scan of every move on every figure | Feeds the "which moves suit which figure" table in the catalog |
| [minifigs/adapter-checks/](minifigs/adapter-checks/) | Re-tests of two earlier models (the 106 car and the 42083 engine) | Shows a change the agent made to the shared toolkit broke nothing; not part of the catalog |

## Known limits

- Moving the whole figure is staging, not physics: feet slide in the walk and run, and jumps and the somersault are scripted.
- There are no props: no ladder, pot, water or chair.
- Hats, the shield, the hose nozzle and the flippers are placed by convention; the automatic connection check could not confirm them.
- Many moves pass through a hand-held item or a hat when played on a figure with long items or a wide hat (see the table in `CATALOG.md`). The bare-handed figures can play 27 of the 30 moves cleanly.
- The collision scans checked sample frames only.

## Source

Claude Code chat `ac745407-eadd-4a56-a92b-a4645586d67e`, stored on the author's machine under `~/.claude/projects/-Users-captain-workspaces-workspace-ai-ldraw-mecha/`. Times come from the chat log, not from file dates.
