# Animating an LDraw model

This guide shows the **different steps required** in order to animate an LDraw model. Some of them to be performed by the user, but most of them by the agent itself.

We will **illustrate** this process by **animating an example car.**

The actual process is **iterative** in nature, where **self-corrections** are done by the agent in **feedback loops**, taking into account both **analytical** and **visual aspects**, as shown on this diagram:
```mermaid
flowchart LR
    s1["1. Annotate<br/>annotated car.mpd"] --> s2["2. Convert<br/>IDs + model.glb"]
    s2 --> s3["3. Plan<br/>plan.json"]
    s3 --> s4["4. Animate<br/>ai-animated.blend"]
    s4 --> s5["5. Verify<br/>checks + stills"]
    s5 -. "fix limits" .-> s3
```

| Step | Action   | Output                                     |
| ---- | -------- | ------------------------------------------ |
| 1    | Annotate | Annotated `car.mpd`                        |
| 2    | Convert  | `plan.json` (draft), annotated `model.glb` |
| 3    | Plan     | `plan.json` (ready)                        |
| 4    | Animate  | `ai-animated.blend`                        |
| 5    | Verify   | Final `.blend` + notes                     |

## Preliminars

We will assume that this process will be carried out on **Visual Studio Code**, with the **current repo project open** and also **a new chat session with the agent**.

We will need **an LDraw model to start with**, the one that will be **given to an agent** through the chat session.

**Two options** here:

1. **Give your own:** the agent will annotate and refine it in order to make it easier to analyze.
2. **Select a pre-annotated one:** run the following to open the model **selector app**, and **copy the model's .mpd file path** by clicking the **"Copy path"** button for the selected one.
3. 
```sh
python3 model-selector/serve.py
```

After choosing a model and getting its path, enter the following **prompt** in the **chat session:**

```
Animate the following model: some/path/car.mpd (your extra instructions if needed)
```

**The example car** we will be animating is this one:

<a href="img/car-open.png"><img src="img/car-open.png" width="320" alt="Sample car"></a>

---

## Step 1: Annotate

This step will be carried out **only if the provided model is unnanotated.**

**The agent** turns the **source code** of parts into a tree of **described assemblies**, also keeping the pre-existing ones:

1. Run [ldraw-annotator-nova](https://github.com/anteloc/ldraw-annotator-nova) to get **every part's name and colour** from a parts database
2. ... and then it will add those to the model's `.mpd` source as **comments**:
	`0 // Plate  2 x 10 (black)`.
3. The agent **reads the enriched .mpd sources** and **infers (reverse-engineers) the mechanisms present.**
4. The file is rewritten as a **tree of submodels**, being the **main** one the **root** for the tree.

### Before and after

**Before:** Four basic submodels, only names but **no real descriptions.** 

Every submodel that makes the car is one **flat list** of parts:

```mermaid
flowchart TD
    main["106 - main.ldr<br/>“main”"]
    car["106 - car.ldr<br/>“car”<br/>45 loose parts"]
    wheel["106 - wheel assembly.ldr<br/>“wheel assembly”<br/>2 parts"]
    fig["106 - Minifig.ldr<br/>“Minifig”<br/>10 parts"]
    main --> car
    main --> fig
    car -->|×5| wheel
```

**After:** A **refined version** for the former tree, this time with detailed descriptions.

These **new submodels**, smaller and also better described, encode the **hierarchy** and semantics **found** by the agent:



```mermaid
flowchart TD
    main["106 - main.ldr<br/>Complete model: blue UNICEF car<br/>with a smiling driver minifig"]
    car["106 - car.ldr<br/>Blue UNICEF car on a black chassis,<br/>with four grey wheels and a spare"]
    chassis["106 - chassis.ldr<br/>Black chassis: plates, car base, mudguards,<br/>steering wheel, red rear lights<br/>19 parts"]
    wheels["106 - wheels.ldr<br/>Wheel set: four wheels and a spare<br/>on wheel-pin plates<br/>2 parts"]
    wheel["106 - wheel assembly.ldr<br/>Light grey rim with black tyre<br/>2 parts"]
    body["106 - cabin-body.ldr<br/>Blue body with UNICEF logo panels<br/>10 parts"]
    front["106 - front-end.ldr<br/>Headlight bricks, yellow lights,<br/>black grille<br/>8 parts"]
    doors["106 - doors.ldr<br/>Pair of blue hinged doors<br/>2 parts"]
    roof["106 - hinged-roof.ldr<br/>Clear windscreen and blue hinged roof<br/>4 parts"]
    fig["106 - Minifig.ldr<br/>Driver minifig: brown hair,<br/>smiling head, blue torso<br/>10 parts"]
    main --> car
    main --> fig
    car --> chassis
    car --> wheels
    car --> body
    wheels -->|×5| wheel
    body --> front
    body --> doors
    body --> roof
    classDef new fill:#d9f2e3,stroke:#2e7d4f,color:#123
    class chassis,wheels,body,front,doors,roof new
```

**Source code** comparison:

```
Before                                   After
0 FILE 106 - car.ldr                     0 FILE 106 - chassis.ldr
0 car                                    0 Black car chassis: long plates and car base with mudguards, …
0 Name: 106 - car.ldr                    0 Name: 106 - chassis.ldr
…                                        …
1 0 0 0 0 1 0 0 0 1 0 0 0 1 3832.dat     0 // Plate  2 x 10 (black)
                                         1 0 0 0 0 1 0 0 0 1 0 0 0 1 3832.dat
```

---

## Step 2: Convert

**You.** Nothing to do.

**The agent** gives every piece an ID, lists how the pieces connect, and converts the model to
`model.glb`, a glTF 3D file that Blender imports, with each piece's ID and description inside.

**Why.** Blender can't read `.mpd` files. From here on, the plan and Blender must refer to
exactly the same pieces, and the ID is how they do it.

**Under the hood.** One command, `ldraw-mecha prepare`. It writes a draft `plan.json` (every
piece with its ID and position, plus candidate connections and mechanisms, but no motion yet)
and `model.glb`.

### IDs

An ID is a piece's path through the model's tree. Each number is the index of a part or
submodel line inside its parent, counting from 0:

```
0            106 - car.ldr            line 0 of the main model
0/1          106 - cabin-body.ldr     line 1 of car.ldr
0/1/10       106 - hinged-roof.ldr    line 10 of cabin-body.ldr
0/1/10/2     4213.dat                 line 2 of hinged-roof.ldr: the roof
```

Part numbers can't do this job. The car has five identical tyres (`4084.dat`), and each one is
a separate piece that turns on its own: `0/2/0/1` (the spare), `0/2/3/1`, `0/2/4/1`… IDs are
valid for one version of the file; if the file changes, the agent prepares it again.

### IDs in Blender

The converter (`mpd2glb`) keeps the model's tree: one glTF node per part and submodel. It
writes each node's metadata into glTF `extras`, which Blender imports as **Custom
Properties**. The roof's, under **Object Properties → Custom Properties**:

```
fileName       4213.dat
description    Hinge Car Roof  4 x  4
colorCode      1
mecha_id       0/1/10/2
mecha_section  106 - main.ldr
mecha_source   b247a29a…   (SHA-256 of car.mpd)
```

Any Blender object can be traced back to the exact source line, by you and by the agent's
scripts.

### Connection evidence

`prepare` also lists which pieces touch, hinge, share an axle or mesh as gears. For the roof
it finds the hinge between the roof holder `0/1/10/1` and the roof `0/1/10/2`:

```json
"c_5f04a4e8697090b8": {
  "a": "0/1/10/1", "b": "0/1/10/2", "kind": "revolute", "status": "candidate",
  "measurements": { "first_kind": "hinge", "position": [0, -92, 36], "axis": [1, 0, 0] }
}
```

This is evidence, not a decision: a contact may be rigid or may move. Step 3 decides.

---

## Step 3: Plan

**You.** The agent lists the mechanisms it found and asks what you want. Typical questions:

- Which mechanisms to animate? (For the car: roof, doors, wheels.)
- One animation of the whole model, or each mechanism on its own?
- What to deliver: a `.blend` file, stills, a video?
- For big models: hide the bodywork? Leave out hoses and cables?

Answer them; the rest of the work follows from your answers. For examples, see the questions
asked in [42083](samples/42083-mechanisms.md), [42110](samples/42110.md) and
[minifigs](samples/minifigs.md).

**The agent** decides, for each mechanism, which pieces move, around which point and axis, how
far, and what drives them, and records it in `plan.json`.

This is where the reverse engineering happens. Nothing in `car.mpd` says the roof opens: the
agent infers it from a roof, a roof holder and the hinge between them.

**Why.** Motion must be measured, not guessed. A wrong axis or gear ratio looks broken. The plan
keeps every decision with its evidence, and it can be checked without Blender.

For the roof, the agent takes the hinge position and axis from the evidence, picks the axis
sign that lifts the roof (LDraw's up is −Y), and writes:

```json
"controls": { "roof": { "min": 0, "max": 1.309, "unit": "radian", "description": "Open the roof" } },
"bodies":   { "roof": { "instances": ["0/1/10/2"], "kind": "revolute",
                        "origin": [0, -92, 36], "axis": [-1, 0, 0], "signal": "roof" } }
```

In words: the control `roof` turns the piece `0/1/10/2` from 0 to 75° (1.309 rad) around the
hinge. Positions are in LDraw units (LDU; 1 stud = 20). Hinges, sliders, gear trains,
connecting rods and springs all use this format; see [docs/motion-plan.md](docs/motion-plan.md).

**Under the hood.** The agent edits `plan.json` through a small Python API, then runs
`ldraw-mecha check`, which validates the plan and sweeps every control through its range
without Blender.

### How agents work out a plan

Strategies used across the [samples](GALLERY.md):

1. **Read the tree and descriptions.** Submodels named `doors`, `hinged-roof` or `wheels` are
   the first candidates.
2. **Read the connection evidence.** Hinges, shared axles and gear meshes give positions and
   axes. Scans can miss things: in [42110](samples/42110.md), some gears were hidden from the
   first scan.
3. **Ask you for the scope**, as above.
4. **Work on a copy when the source falls short.** Extract one mechanism, split parts stored as
   one piece, add missing parts. Your original is never changed.
   ([42043 crane](samples/42043-crane.md), [3625](samples/3625.md),
   [42083](samples/42083-mechanisms.md))
5. **Compare with a reference.** Use a hand-made rig or an official set with the same parts.
   ([42000](samples/42000.md), [movables](samples/movables.md), [plants](samples/plants.md))
6. **Do the maths.** Gear ratios, rod lengths, every gear combination.
   ([42000](samples/42000.md), [42110](samples/42110.md))

### Look inside: x-ray boards

Mechanisms are usually hidden behind bodywork. Before building anything, the agent renders an
x-ray board of each moving body: the body in colour, everything else ghosted. It checks every
board for four things:

1. Exactly the right pieces are coloured.
2. The axis runs through the hinge, axle or pin.
3. Positive angles turn the right way.
4. The limit poses stay clear of grey neighbours.

The car's roof (image by [ldraw-xray](https://github.com/anteloc/ldraw-xray), which has more
examples):

![X-ray board of the car's roof](img/xray-roof.png)

*Coloured: the moving piece. Ghosted: the rest of the car. Green rod: the hinge axis (drawn
in, not a LEGO part). Panels 3 to 5: the roof at 0°, 40° and 75°.*

---

## Step 4: Animate

**You.** Nothing to do.

**The agent** builds the plan in Blender, adding a pivot per moving body, a slider per control
and a demonstration animation, and saves `ai-animated.blend`.

**Why.** The result is a standard `.blend` file. It plays in plain Blender with no add-on, no
Python auto-run and no agent.

```mermaid
flowchart LR
    plan["plan.json<br/>roof → 0/1/10/2"] --> script["rig"]
    glb["Blender object 4213.dat<br/>mecha_id = 0/1/10/2"] --> script
    script --> rig["PIV_car_roof driven by<br/>slider roof on CTRL_car"]
    rig --> blend["ai-animated.blend"]
```

**Under the hood.** `ldraw-mecha rig` runs Blender in the background and:

1. Imports `model.glb` and finds each object by its `mecha_id`.
2. Checks it's the right model: the `mecha_source` hash matches the plan, and every object is
   still at its source position.
3. Adds a pivot per body at the plan's origin and axis, parents the body's objects to it, and
   drives the pivot from a custom property on one control object, `CTRL_car`.
4. Keys the controls into a demonstration animation.
5. Compares every moving object against the plan, then saves.
6. Opens the saved file in a fresh Blender and compares again.

---

## Step 5: Verify

**The agent** scans the motion for collisions, renders stills and looks at them, and fixes
what it finds. A rig can match the plan exactly and still be wrong, for example a door that
swings through the bodywork.

- **Collisions.** What the scan finds goes **back to Step 3**. At 90° the car's doors and roof
  hit other parts, so the agent set their limit to 75°. ([106](samples/106.md),
  [hot rod mecha](samples/hot-rod-mecha.md))
- **Stills.** These catch what numbers miss: a window opening away from the viewer, a staff
  swinging into a leg. ([movables](samples/movables.md), [minifigs](samples/minifigs.md))

**You.** Open the `.blend`, select `CTRL_car`, and drag its sliders under **Object Properties →
Custom Properties**, or press play. Tell the agent what's wrong or missing. In the
[hot rod mecha](samples/hot-rod-mecha.md) sample, the user pointed out that "the engine on the
robot's chest … should be animated, too", and the agent added it.

**What you get back:** clickable links to the `.blend` file, the x-ray boards, the stills, the
plan, the check reports, and the agent's notes on what it decided, what it left out and the
known limits. In VS Code, clicking a link also selects the file in the Explorer. The agent
then offers to open the `.blend` in Blender for you; say yes, and Blender opens with the
animated model, ready to play.

**Limits.** The collision scan checks sampled poses, not the continuous motion. Parts are rigid,
with no friction, play or forces. Passing checks don't prove the model is physically buildable
or working.

---

## Learn more

- [GALLERY.md](GALLERY.md): ten models done this way, each with the request, what happened and
  every output file.
- [docs/how-it-works.md](docs/how-it-works.md): the design behind each step.
- [docs/motion-plan.md](docs/motion-plan.md): the plan format: joints, gears, rods, equations.
- [docs/validation.md](docs/validation.md): what each check proves, and what it doesn't.
