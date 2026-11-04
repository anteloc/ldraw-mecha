# 42083 Bugatti Chiron: five mechanisms, each on its own

Five mechanisms of the LEGO Technic Bugatti Chiron, each taken out of the car and animated side by side in one scene: the all-wheel drivetrain, the 8-speed gearbox with paddle shifters, the drive/neutral/reverse selector, the opening doors and the rising rear wing. They all play at the same time. Claude Code found the car's mechanisms, let the user choose, and built the five animations in about 1.5 hours.

▶ [Watch the video](42083-mechanisms.mp4)

## At a glance

| | |
|---|---|
| LEGO model | 42083 Bugatti Chiron; source file `data/models-annotated/42083-1.mpd` |
| Made by | Claude Code (Claude Opus 5.5) |
| When | 2026-10-06 22:23 to 2026-10-07 00:35, Madrid time |
| Working time | About 87 min of agent work, plus a 45 min wait before the user's follow-up question |
| Result | [42083-mechanisms/mechanisms.blend](42083-mechanisms/mechanisms.blend): five mechanisms in one scene, 480 frames at 24 fps (20 s) |

## How to view it

1. Open [42083-mechanisms/mechanisms.blend](42083-mechanisms/mechanisms.blend) in Blender 5.2 or later.
2. Press Play (Space). From left to right:
    - doors: each door opens and closes in turn;
    - drivetrain: the car rolls through an S-bend, so the differentials split;
    - gearbox: the paddles shift up from 1st to 8th and back down;
    - selector: neutral, drive, neutral, reverse, neutral;
    - wing: rises, holds and lowers.
3. Each mechanism has its own controller, named `CTRL_chiron_42083_doors`, `…_drivetrain`, `…_gearbox`, `…_dnr` and `…_wing`. Its controls are under **Object Properties → Custom Properties**.

## What was asked

> read @instructions.md, and then analyze the following model: @data/models-annotated/42083-1.mpd
>
> What I want is: find the mechanisms it has, and offer me a list for me to select wich one(s) I'm interested in, and for those selected, create animations for all of them, adding those to a single .blend file

## What happened

1. The agent analysed how the car's parts connect and offered a list of mechanisms.
2. The user chose:
    - the drivetrain, gearbox, selector, doors and wing (not the engine, steering or suspension);
    - each mechanism on its own, side by side;
    - all of them playing at once.
3. The source file turned out to be missing two small gears. LEGO's official parts list has eight, the file has six, and without them the "8-speed" gearbox only gives 3 speeds. The agent added the two gears only in the gearbox's own copy, in the empty slots where they mesh, and left the original file unchanged.
4. While building, the agent found that:
    - what looked like door latches are the side mirrors, which ride on the doors;
    - tilting the wing hits the bodywork, so it rises straight up instead;
    - the driver's left paddle shifts up, the opposite of a real car.
5. It fixed two bugs in the shared toolkit on the way: connecting rods twisted once a model was moved away from the scene centre, and a wheel speed was 6% off.
6. All checks passed, and the agent delivered at 23:49. At 00:34 the user asked it to rank the tools and documents it had used by usefulness.

## Files

All paths are relative to `samples/`.

| File | What it is | Why it exists |
|---|---|---|
| [42083-mechanisms.mp4](42083-mechanisms.mp4) | Screen recording of the animation playing in Blender, made by the user | To show the result |
| [42083-mechanisms/mechanisms.blend](42083-mechanisms/mechanisms.blend) | The five rigged and animated mechanisms in one scene | The final result: open this |
| [42083-mechanisms/REPORT.md](42083-mechanisms/REPORT.md) | The agent's full write-up: how each mechanism works, gear ratios, assumptions, checks and open points. Its `previews/` folders were not kept in this sample | Reference for anyone reusing the file |
| [42083-mechanisms/drivetrain/](42083-mechanisms/drivetrain/), [42083-mechanisms/gearbox/](42083-mechanisms/gearbox/), [42083-mechanisms/dnr/](42083-mechanisms/dnr/), [42083-mechanisms/doors/](42083-mechanisms/doors/), [42083-mechanisms/wing/](42083-mechanisms/wing/) | One folder per mechanism, with the same layout | Everything needed to understand or rebuild one mechanism |
| `42083-mechanisms/<mechanism>/source/` | That mechanism taken out of the car as its own LDraw file, with a map back to the original piece numbers. The two added gears are in [42083-mechanisms/gearbox/source/42083-gearbox.mpd](42083-mechanisms/gearbox/source/42083-gearbox.mpd) | The model each rig was built from |
| `42083-mechanisms/<mechanism>/plan.json`, `kinematics.json`, `evaluate-*.json` | The motion plan, the gear and linkage maths, and test positions | How the motion was worked out and tested |
| `42083-mechanisms/<mechanism>/clearance.json`, `lifecycle.json`, `study/` | Collision scan, rebuild/remove check, and the toolkit's analysis of the extract | Checks and starting data |
| [42083-mechanisms/doors/clearance-context/](42083-mechanisms/doors/clearance-context/), [42083-mechanisms/wing/clearance-context/](42083-mechanisms/wing/clearance-context/) | Collision scans with the surrounding bodywork put back | Where the door and wing limits come from |
| [42083-mechanisms/evidence/](42083-mechanisms/evidence/) | Connection data for the car's mechanical parts, and the gear pairs found | Used to find what moves together |
| [42083-mechanisms/animation-check.json](42083-mechanisms/animation-check.json), [42083-mechanisms/animation.log](42083-mechanisms/animation.log) | Check that the animation matches the plans, and the build log | Shows the animation works as planned |
| [42083-mechanisms/reopen-check.json](42083-mechanisms/reopen-check.json), [42083-mechanisms/reopen.log](42083-mechanisms/reopen.log) | Check after reopening the saved file in a fresh Blender | Shows the file works on its own |

## Known limits

- The two added gears are a reconstruction from the official parts list, not part of the source file.
- The rising wing is an assumption. The real car tilts it with a top-speed key that this model does not include.
- Each mechanism runs on its own. Where two mechanisms meet, the shared gears turn as a stand-in, not as one connected system.
- Gear teeth and paddle-to-ratchet contact are not simulated.
- The collision scans checked sample poses only. In the gearbox and selector, parts that ride on each other by design are reported as touching.

## Source

Claude Code chat `bff4579d-99da-4a8d-b020-3dbbbb40c2ff`, stored on the author's machine under `~/.claude/projects/-Users-captain-workspaces-workspace-ai-ldraw-mecha/`. Times come from the chat log, not from file dates.
