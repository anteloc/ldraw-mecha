# Plant wind catalog: twenty LEGO plants in the wind

Twenty LEGO plants (palms, bamboo, flowers, grass, reeds, vines, a tree with hinged branches and more) stand in one shared field and sway in the same wind, which blows from left to right in three strengths: breeze, gusty and storm. This is a catalog of 60 separate animations sharing one scene: each plant moves in its own way (whips, flaps, sways, spins, nods, swings), and each animation is stored on its own so it can be reused. Claude Code built the plants and the wind in about 85 minutes.

▶ [Watch the video](plants.mp4)

## At a glance

| | |
|---|---|
| LEGO model | None given: twenty small plant scenes built from the plant parts in `data/categories/parts/plants.py`, copying official LEGO sets where they use the same parts |
| Made by | Claude Code (Claude Opus 5.5) |
| When | 2026-10-07 23:53 to 2026-10-08 01:56, Madrid time |
| Working time | About 85 min of agent work, plus two waits of about 20 min for the user (plan approval, then "continue") |
| Result | [plants/plants.blend](plants/plants.blend): scene "Wind", 752 frames at 24 fps (31 s) |

## How to view it

1. Open [plants/plants.blend](plants/plants.blend) in Blender 5.2 or later.
2. Press Play (Space). The breeze plays in frames 1–240, the gusty wind in 257–496 and the storm in 513–752. The blue arrow shows the wind's strength.
3. To watch one plant alone, make its camera (`CAM_P01` to `CAM_P20`) the active camera.
4. Each plant has its own controller, `CTRL_plant_01_palm_tree` to `CTRL_plant_20_friends_palm`, with one control per joint under **Object Properties → Custom Properties**. Each animation is a separate Blender action, named like `P01_palm_tree.storm`, on its own NLA track. [plants/CATALOG.md](plants/CATALOG.md) explains how to reuse them.

## What was asked

> Do the following: read @instructions.md , and then let's do something different: animate plants, trees, etc. as if they were moved by the wind.
>
> You've got the different parts categories under @data/categories/parts, on every .py file you'll find parts in the category the filename says, look for plants, trees, flowers, etc. on those files.
>
> Find the typically moveable ones, e.g. maybe flowers that can rotate, tree branches also moveable, and so on. Ignore immovable plants like e.g. cabbages or similar.
>
> Once you've got that, do the following: build 20 different cases, different moveable plants, etc. and animate them in different ways, in order to have a catalog of movements.
>
> Final scenario should have all 20 different cases, animated together as if they would be receiving wind from the same direction.
>
> End result should be a .blend file with the single requested scenario on it, and requested animations
>
> Regarding the end result, clearly separate every different animation for every different case, so this scenario "howto" can be selected by other agents for the particular needs they have when building a new model, and understanding how to animate trees, flowers, bamboo canes, etc

## What happened

1. The agent checked which plant parts have a connection that can actually move, and asked two questions. The user chose:
    - motion at real LEGO connections, plus small, clearly labelled tilts where a real piece would only bend (bamboo canes, grass, thin stems);
    - three wind strengths per plant.
2. It designed the twenty plant scenes, copying official LEGO sets where they use the same parts. One-piece trees, bushes and vegetables were left out, because nothing on them can move.
3. After a pause, the user said "continue". The agent wrote the wind: one field with gusts that travel across it, so the right-hand plants feel each gust about 2 seconds after the left-hand ones. Each joint responds like a damped spring, pushed by the wind in the direction it can swing; flowers can spin like rotors, and leaves can turn downwind like weathervanes. The breeze loops seamlessly.
4. It found that Blender 5.2 rounds very small driver values to zero, which put the top of a bamboo cane slightly out of place. The agent fixed this in the shared toolkit and re-tested older rigs.
5. Reviewing rendered images, it fixed what looked wrong:
    - an oak branch that hardly moved;
    - two plants that overflowed their spots, so the grid was widened;
    - fronds and canes that hit their neighbours, so their ranges were narrowed;
    - washed-out lighting and loose camera framing.
6. All checks passed, including 398 tests, and the agent delivered at 01:56.

## Files

All paths are relative to `samples/`.

| File | What it is | Why it exists |
|---|---|---|
| [plants.mp4](plants.mp4) | Screen recording of the field playing in Blender, made by the user | To show the result |
| [plants/plants.blend](plants/plants.blend) | The field with the twenty rigged plants, the wind and all 60 animations | The final result: open this |
| [plants/CATALOG.md](plants/CATALOG.md) | Guide for reusing the animations: every plant, control and animation, an index by style ("which plant shows a whip?"), collision results and copy-paste snippets | The main reference for anyone reusing a plant's motion |
| [plants/REPORT.md](plants/REPORT.md) | The agent's full write-up: the wind model, each plant, findings worth reusing, checks and limits. Its `previews/` folder was not kept in this sample | Background for the catalog |
| [plants/catalog.json](plants/catalog.json), [plants/clips/](plants/clips/) | The same catalog as data, one file per animation (60 in all), and the shared wind (`WIND.json`) | To reuse the animations without Blender |
| [plants/P01_palm_tree/](plants/P01_palm_tree/) … [plants/P20_friends_palm/](plants/P20_friends_palm/) | One folder per plant, with the same layout: `source/scenario.mpd` (the plant as an LDraw model) and `source/parts.json` (parts, joints and how each was verified), the motion plan, its checks and the toolkit's analysis (`study/`) | Everything needed to understand or rebuild one plant |
| [plants/mpd-summary.json](plants/mpd-summary.json), [plants/plan-summary.json](plants/plan-summary.json) | One-line summaries per plant: parts, joints and official-set comparisons; plan status | Quick overview of all twenty |
| [plants/cli-checks.txt](plants/cli-checks.txt), [plants/pytest.log](plants/pytest.log) | Results of the toolkit's plan checks on all twenty plants, and of the test suite (398 passed) | Shows the plans and code pass |
| [plants/animation-check.json](plants/animation-check.json), [plants/animation.log](plants/animation.log) | Check that every plant follows its animation at 26 sample frames, and the build log | Shows the field plays as planned |
| [plants/reopen-check.json](plants/reopen-check.json), [plants/reopen.log](plants/reopen.log) | Check after reopening the file, including one plant's storm played on another plant | Shows the file and the reuse work on their own |
| [plants/clearance-summary.json](plants/clearance-summary.json), [plants/clearance.log](plants/clearance.log) | Collision scan of every plant's joints and animations | Where the narrowed ranges come from |
| [plants/adapter-checks/](plants/adapter-checks/) | Re-tests of three plants' rigs, and of the toolkit's workflow check on the bamboo, after the toolkit fix | Shows the fix broke nothing; not part of the catalog |

## Known limits

- The wind response is a simple artistic model, not real aerodynamics. Chains of parts follow each other with a delay rather than pushing on each other.
- 25 of the 112 joints are small stand-in tilts where a real piece would bend. They are labelled `flex_approx` in the catalog.
- Ball joints tilt in one direction only, and the spinning flowers spin for effect: real flowers have no blade pitch.
- Each animation is made for its plant's spot in the field. A plant moved elsewhere needs its animations regenerated; `CATALOG.md` shows how ("Reusing a wind response").
- The collision scans checked sample frames only. Six plants show shallow overlaps, caused by the stand-in tilts or by parts that already touch at rest.

## Source

Claude Code chat `303a9e8e-c41a-4307-b787-6296e0bf1026`, stored on the author's machine under `~/.claude/projects/-Users-captain-workspaces-workspace-ai-ldraw-mecha/`. Times come from the chat log, not from file dates.
