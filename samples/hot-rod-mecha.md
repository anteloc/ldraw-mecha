# 42022 Hot Rod rebuilt as a mecha robot, with a running chest engine

A blue-and-black robot built from the parts of the LEGO Technic 42022 Hot Rod, plus extra parts, playing a 10-second "power on" loop: it turns its head, raises its arms, rotates its wrists and wheels, and the V6 engine in its chest runs with all six pistons. It was made through the project's dockerised web app by its agent (OpenAI gpt-6-astra), in about an hour of work spread over two days.

▶ [Watch the video](hot-rod-mecha.mp4)

## At a glance

| | |
|---|---|
| LEGO model | 42022 Hot Rod (the donor); source file `data/models-annotated/42022-1.mpd`. The robot is a new model: [hot-rod-mecha/mecha/Hot-Rod-Mecha.mpd](hot-rod-mecha/mecha/Hot-Rod-Mecha.mpd), 345 parts (186 from the car, 159 added) |
| Made by | The ldraw-mecha web app's agent (OpenAI gpt-6-astra) |
| When | 2026-10-18 16:32 to 2026-10-19 09:22, Madrid time |
| Working time | About 64 min of agent work. The run was interrupted twice and resumed hours later (waits of about 6 h and 9.5 h) |
| Result | [hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend](hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend): 301 frames at 30 fps (10 s loop) |

## How to view it

1. Open [hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend](hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend) in Blender 5.2 or later.
2. Press Play (Space). The loop is the action "HOT ROD / Power On - 10 second loop".
3. To see what drives the motion, select `CTRL_Hot_Rod_Mecha` and open **Object Properties → Custom Properties**: shoulders, elbows, wrists, neck, wheels and `engine`. The hips and knees exist for posing but stay still in this loop. The waist is locked.

The video was recorded from the web app's own Blender session file, [hot-rod-mecha/blender/session.blend](hot-rod-mecha/blender/session.blend), which holds the same robot.

## What was asked

> turn the attached model into a mecha robot

The user had selected the 42022 Hot Rod in the web app. Two later messages changed the work; they are quoted below.

## What happened

1. The agent inspected the Hot Rod (414 parts, with a six-piston engine, wheels and steering) and said up front that the car has no car-to-robot transformation. It proposed rebuilding the parts as a robot instead.
2. The user added: "add more parts in order to make a better mecha robot, if available part are not enough". The agent added 159 parts, including turntables for the joints, a stronger frame and armour.
3. A collision scan found the waist and the largest arm poses running into other parts. The agent locked the waist and reduced the shoulder and elbow travel.
4. It animated the head, arms, wrists and wheels with the feet planted, and left the engine still until its moving parts could be checked.
5. The user pointed out: "something is missing: the engine on the robot's chest, that should be animated, too". The agent drove all six pistons and rods from one crankshaft, eight turns per loop. A collision scan caught the lowest middle piston hitting the decorative radiator, so it lowered the radiator by 8 mm.
6. Final checks passed, and the agent published the result through the web app.
7. The service then failed with a rate-limit error before the agent could write its final reply, so the chat shows as "failed" although the work was complete. The interruptions in between were resumed with the web app's standard "Resume the interrupted task…" message, which is sent by its resume button, not typed by the user.

## Files

All paths are relative to `samples/`. The folder is the web app's working folder for this chat (originally `data/output/20261018-143230-aa3081`), renamed for readability.

| File | What it is | Why it exists |
|---|---|---|
| [hot-rod-mecha.mp4](hot-rod-mecha.mp4) | Screen recording of the animation playing in Blender, made by the user | To show the result |
| [hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend](hot-rod-mecha/mecha/Hot-Rod-Mecha-animated.blend) | The rigged and animated robot, with the running engine | The final result: open this |
| [hot-rod-mecha/mecha/README.md](hot-rod-mecha/mecha/README.md) | The agent's guide to the result: deliverables, playback, engine design and checks | Reference for anyone reusing the file |
| [hot-rod-mecha/NOTES.md](hot-rod-mecha/NOTES.md) | The agent's hand-over note, written just before publishing | Lets an interrupted run resume where it stopped |
| [hot-rod-mecha/mecha/Hot-Rod-Mecha.mpd](hot-rod-mecha/mecha/Hot-Rod-Mecha.mpd), [hot-rod-mecha/mecha/robot-bom.csv](hot-rod-mecha/mecha/robot-bom.csv), [hot-rod-mecha/mecha/additional-parts.csv](hot-rod-mecha/mecha/additional-parts.csv) | The robot as an LDraw model, its full parts list, and the list of the 159 added parts | The robot itself, and what you would need to build it |
| [hot-rod-mecha/mecha/plan.json](hot-rod-mecha/mecha/plan.json), [hot-rod-mecha/mecha/parts.json](hot-rod-mecha/mecha/parts.json), [hot-rod-mecha/mecha/animation.json](hot-rod-mecha/mecha/animation.json) | The motion plan (16 controls, 30 moving pieces), the role of each reused part, and the animation keys | The rig and the loop are built from them |
| [hot-rod-mecha/mecha/rigged.blend](hot-rod-mecha/mecha/rigged.blend), [hot-rod-mecha/mecha/inspected.blend](hot-rod-mecha/mecha/inspected.blend) | The rig before animation, and the inspection scene of the robot | Intermediate steps |
| [hot-rod-mecha/mecha/verification-summary.json](hot-rod-mecha/mecha/verification-summary.json) | All final checks, file fingerprints and limits in one place | Shows what was verified |
| `hot-rod-mecha/mecha/*check*.json`, `clearance-*.json`, `validation.json`, `sweep.json`, `audit.json` | The individual checks: plan consistency, the rig in Blender, every one of the 301 played frames, reopening, and collision scans | The evidence behind the summary file |
| `hot-rod-mecha/mecha/engine-*.json`, `base-engine-v2.json`, `engine-build.log` | Engine measurements: crank, rod and piston connections, and the piston maths | How the engine motion was worked out |
| [hot-rod-mecha/mecha/preview.png](hot-rod-mecha/mecha/preview.png), [hot-rod-mecha/mecha/engine-review.png](hot-rod-mecha/mecha/engine-review.png), `pose-*.png`, `engine-frame-*.png`, `rest-study.png` | Stills of the whole robot, the engine close up, the key poses and the resting pose | Visual review by the agent |
| [hot-rod-mecha/mecha/study/](hot-rod-mecha/mecha/study/), [hot-rod-mecha/mecha/study-engine-v2/](hot-rod-mecha/mecha/study-engine-v2/) | The toolkit's analysis of the robot, before and after the radiator was lowered | Starting data for the rig |
| [hot-rod-mecha/mecha/initial-range-study/](hot-rod-mecha/mecha/initial-range-study/), [hot-rod-mecha/mecha/pre-engine/](hot-rod-mecha/mecha/pre-engine/), [hot-rod-mecha/mecha/engine-first-clearance/](hot-rod-mecha/mecha/engine-first-clearance/) | Snapshots kept from earlier stages: the first joint ranges, the robot before the engine was animated, and the first engine collision scan | Show how the result changed |
| [hot-rod-mecha/source-study/](hot-rod-mecha/source-study/), [hot-rod-mecha/part-study.json](hot-rod-mecha/part-study.json), [hot-rod-mecha/assessments/42022-1.json](hot-rod-mecha/assessments/42022-1.json) | The analysis of the original Hot Rod, a study of candidate parts, and the agent's verdict that the car is suitable | The groundwork for the redesign |
| [hot-rod-mecha/build_mecha.py](hot-rod-mecha/build_mecha.py), [hot-rod-mecha/author_mecha_plan.py](hot-rod-mecha/author_mecha_plan.py), [hot-rod-mecha/animate_mecha.py](hot-rod-mecha/animate_mecha.py), [hot-rod-mecha/add_chest_engine.py](hot-rod-mecha/add_chest_engine.py) | The agent's scripts: build the robot, write its plan, animate it, add the engine | To rebuild the result |
| [hot-rod-mecha/blender/](hot-rod-mecha/blender/), [hot-rod-mecha/generators/](hot-rod-mecha/generators/) | The web app's Blender session file, and every script the agent ran through the web app | A full record of the run |

## Known limits

- The robot is a design concept: its frame and armour have not been checked as a buildable LEGO model.
- The waist is locked, because it ran into other parts. The hips and knees are not used in the loop.
- The original car's steering and drivetrain are not part of the robot.
- The engine keeps the source's small rod-to-piston offsets (about 0.1–0.2 mm) instead of stretching the rods.
- The collision scans checked sample poses only.

## Source

Chat `20261018-143230-aa3081` in the ldraw-mecha web app, stored on the author's machine under `ldraw-mecha-docker/data/chats/20261018-143230-aa3081/`. Times come from the chat log. The file dates in this folder come from a later copy, not from when the files were made.
