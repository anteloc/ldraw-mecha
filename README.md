# ldraw-mecha

**Give an [LDraw](https://www.ldraw.org/) LEGO© model to an AI agent, get back a Blender-animated version of it.**

The **agent** will:

- **Reverse-engineer** (infer) the **LDraw model's mechanics** from its **.mpd source code file** 🤓 
- **Study** the **discovered** mechanisms.
- **Plan** the **interactions** between their different mechanical components.
- And finally, turn those **plans** into **python code for Blender**, that will:
	- **Create** the required **rigs** for controlling the different mechanisms.
	- **Animate** them according to **plan**! 🤯

Take a look at the [▶ HOWTO video](https://youtu.be/P4aKXKNOBig)!

<a href="https://youtu.be/P4aKXKNOBig"><img src="img/demo-video.png" width="500" alt="YouTube demo video"></a>

## Installation

> [!NOTE]
> The installation process will **install** every required tool and dependency **locally** on this project repo, in order to **avoid polluting the host OS**.
> 
> However, there is a requirement of setting several **env vars** on rc files, like e.g. `.bashrc` or `.zshrc`
> 
> The installed dependencies, like e.g. Blender, are **git-ignored** by default.

You'll need **Python 3.12+** installed.

| System                            | Requirements                                       |
| --------------------------------- | -------------------------------------------------- |
| **macOS**                         | git-lfs (`brew install git-lfs`)                   |
| **Linux, x86_64** (WIP, untested) | git-lfs, Blender and LeoCAD required graphics libs |
| **Windows** (WIP, untested)       | Run inside WSL2 (Ubuntu)                           |

Start by **cloning** the repo and **running the setup script**, pick the right one for your OS:

```sh
git clone https://github.com/anteloc/ldraw-mecha.git
cd ldraw-mecha
./setup-macos.sh            # or ./setup-linux.sh, ./setup-win-wsl.sh
```

### Installed during setup

| Item                                                               | Version |
| ------------------------------------------------------------------ | ------- |
| uv                                                                 | 0.9.3   |
| bun                                                                | 1.4.4   |
| [ldraw-annotator](https://github.com/anteloc/ldraw-annotator-nova) | 0.5.0   |
| [ldraw-xray](https://github.com/anteloc/ldraw-xray)                | 0.5.0   |
| [jev-rerank](https://github.com/anteloc/jev-rerank)                | 0.5.0   |
| [mpd2glb](https://github.com/anteloc/mpd2glb)                      | 0.9.1   |
| Blender                                                            | 5.2.3   |
| LeoCAD                                                             | 26.09   |
| LDraw parts library                                                | latest  |

At the end of the setup process, you'll get a snippet with the env vars to be **added to your shell profile** (`.bashrc`, `.zshrc`, etc.), something like e.g.:

```sh
# >>> ldraw-mecha (from setup-macos.sh) >>>
export LDRAW_DIR="/Users/me/ldraw-mecha/data/ldraw"
export LDRAWDIR="$LDRAW_DIR"
export BLENDER_BIN="/Users/me/ldraw-mecha/bin/Blender.app/Contents/MacOS/Blender"
export LEOCAD="/Users/me/ldraw-mecha/bin/LeoCAD.app/Contents/MacOS/LeoCAD"
export LDRAW_XRAY_CACHE="/Users/me/ldraw-mecha/.cache/ldraw-xray"
export LDRAW_ANNOTATOR_DB="/Users/me/ldraw-mecha/data/ldraw-info.db"
# export TYPESAFE_API_KEY=...   # optional: Jev semantic search (jev-rerank)
# other env vars...
# <<< ldraw-mecha <<<
```

If you're on **VS Code** or a **terminal**, **restart it** in order to get an **updated env** with the newly added env vars.

## Usage

For **inspecting** and **selecting** one pre-annotated model to animate, open the **annotated models selector** by running:
```sh
python3 model-selector/serve.py
```

Then, take a look at the [▶ HOWTO video](https://youtu.be/P4aKXKNOBig) for a **step-by-step usage example**.

## Samples

> [!NOTE]
> More samples available at: [Gallery](GALLERY.md)
> 
> Animations have been generated from **original models**, not from ai-generated ones.

These are **some samples** of animations by different agents, take a look at their **Summaries** for more details.

## 42043 Mercedes-Benz Arocs flatbed truck: the pneumatic crane on its own

- **Agent: Claude Sonnet 5.5**
- **Original model:** [42043-1_Flatbed-Trailer.mpd](data/models-annotated/42043-1_Flatbed-Trailer.mpd)
- **Context:** The model was too large and complex for fully animating it, finally I accepted Sonnet's suggestion about animating the crane alone.

<a href="samples/42043-crane.png"><img src="samples/42043-crane.png" width="320" alt="42043 Mercedes-Benz Arocs flatbed truck"></a>

[▶ Video](https://anteloc.github.io/ldraw-mecha/samples/42043-crane.mp4) · [Summary](samples/42043-crane.md)

**Original**

<a href="img/42043-1_Flatbed-Trailer.png"><img src="img/42043-1_Flatbed-Trailer.png" width="320" alt="42043 Mercedes-Benz Arocs flatbed truck"></a>

## 3625 Fabuland plane: take-off, flight and landing

- **Agent: Claude Sonnet 5.5**
- **Original model:** [3625-1.mpd](data/models-annotated/3625-1.mpd)
- **Context:** Asked for an in-place animation, to avoid the plane moving around.

<a href="samples/3625.png"><img src="samples/3625.png" width="320" alt="3625 Fabuland plane"></a>

[▶ Video](https://anteloc.github.io/ldraw-mecha/samples/3625.mp4) · [Summary](samples/3625.md)

## Minifig movement catalog: ten minifigs, three moves each

- **Agent: Claude Opus 5.5**
- **Original model:** None
- **Context:** This one is actually a **generated composition**, from several **different minifigs**, to be used as a **"howto reference"** for other agents also animating minifigs.

<a href="samples/minifigs.png"><img src="samples/minifigs.png" width="320" alt="Minifig movement catalog"></a>

[▶ Video](https://anteloc.github.io/ldraw-mecha/samples/minifigs.mp4) · [Summary](samples/minifigs.md)

## Agent's informational sources

| Need                                            | Read                                                                           |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| The whole process, step by step, on one example | [Process](PROCESS.md)                                                          |
| Everyday commands and recovery                  | [Workflow](docs/workflow.md)                                                   |
| Joint types, equations, frames and fields       | [Motion plan](docs/motion-plan.md)                                             |
| Source discovery and live Blender tools         | [API guide](docs/discovery-and-blender.md)                                     |
| Look boards for candidates and authored joints  | [Visual inspection with ldraw-xray](docs/xray.md)                              |
| Missed contacts, rounded transforms, coverage   | [Discovery quality](docs/discovery-quality.md)                                 |
| Part families, descriptions and dimensions      | [Part information](docs/part-information.md)                                   |
| Testing, clearance and evidence limits          | [Validation](docs/validation.md)                                               |
| Code boundaries                                 | [Architecture](docs/architecture.md)                                           |
| Publishing a selected working example           | [Curation](docs/reference/curation.md) and [asset archive](examples/README.md) |

## Why and How?

After publishing [LDraw Nova](https://github.com/anteloc/ldraw-nova), a sibling project for **agentic generation of LDraw models**, several people reached out to me asking about if models could be **animated** somehow.

During the development of Nova, I noticed that **adding** some **special annotations** to `.mpd` **original** model **source files**, and then giving those to **agents**, would:

- **Help** agents in **understanding how to build** other different models.
- But also, in **understanding how a model was built**.

Which gave me the idea that, maybe, an agent would **also understand how a model would work.**

### Reverse-engineering mechanisms from their sources

As a first step to it, I gave **annotated models** to different agents, and prompted them to **infer (reverse-engineer)** their **constituent submodels** (see **Haiku 5.5. experiment** below).

Results from **inference experiments** were both pretty **good** and **consistent** across different agents, and I also noticed the following: **many of the submodels inferred were actually mechanisms.**

After questioning several agents about those inferred mechanisms, regarding how would they **actually work**, I also got consistent results: agents would **describe behaviours** based on the **descriptions for the parts** on a **mechanism!** 🤯

At this point, I had the following:
- Agents would **split and refine** models into submodels and mechanisms.
- Agents would **understand** each mechanism in **isolation**.
- Agents would **understand** how **individual** mechanisms **worked**.

The **result** of an actual **divide-and-conquer process**, right? 🤓

Which would make **handling individual mechanisms** manageable. 🤩

### Correlating LDraw source code to a 3D model

Now, there was the matter of giving agents the **means to actually animate** mechanisms they already knew how they worked.

I was playing with **Blender MCP** at the time, and Blender looked promising as a tool that would provide agents a way to **manipulate LDraw models in 3D**, imported into Blender as **glTF (.glb) files.**

But there was still an **open issue:** 

***How to map from a refined model source code an agent would understand, to its equivalent 3D model in glTF format an agent could manipulate?***

And the **solution** I found was: 

***Annotate the 3D glTF model's nodes with the same annotations as the source code, so the agent would:***
- **Outside Blender: plan on submodels** 🤔  and parts as **source code.**
- **Inside Blender: execute on matching nodes** ✨ on the **3D glTF model.**

### Putting the pieces together 😉

Now, I had a **draft** for a **process**, but **no tools for the agent** to use and carry it forward.

Given that the process would require a **high amount of complex geometric and spatial calculations**, I asked the agent to **derive a new python toolset** from the one created for [ldraw-nova](https://github.com/anteloc/ldraw-nova)

The new [**python toolset**](docs/architecture.md) I refined **iteratively**, by giving the agent **simple models** at the beginning, and **increasingly complex ones** each time.

And to test it, I gave an agent **instructions** to:

- **first, plan** from an annotated and refined `.mpd` model
- then, **generate a glTF 3D version of it, with matching annotations** 
- then, **upload it to Blender**
- and then, **produce the Blender python scripts** that would **animate the model as planned.**

**And it finally [worked](GALLERY.md)!** 🚀🚀🚀

(but not perfectly) 😜

## Experiment - Claude Haiku 5.5 reverse-engineering session

**Prompt:**

*This is a fragment, a submodel, from an LDraw .mpd file model.*

*This is not an executable code fragment, but more like a 3D CAD model fragment written in LDraw language.*  
***Infer what this submodel is, and also split it into submodels** (starting with: 0 FILE):*

- *always with relevant, semantical meaning,*
- *the first 0-line following every 0 FILE line is the "description line" for the submodel, according to the LDaw standard*
- *add the description for every submodel there, a one-liner, as a person would describe it while looking at it*
- *at the answer, first place the parent model, then the child one(s) and then the grandchildren, and then descendants... etc.: go from containers or parents to containees or children, children of children. etc.*

---

<details>
<summary>Expand code...</summary>

```
0 FILE file-01  
0 file-01  
0 Name: file-01.ldr  
0 Author: Unknown  
0 !LDRAW_ORG Model  
0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt
0 // Plate 2 x 12 (dark_bluish_grey)  
1 72 0 0 0 1 0 0 0 1 0 0 0 1 2445.dat  
0 // Tile 1 x 2 Grille with Groove (metallic_silver)  
1 80 -110 -8 0 0 0 1 0 1 0 -1 0 0 2412b.dat  

0 STEP  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 -80 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 -40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 0 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 100 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 100 8 -20 1 0 0 0 1 0 0 0 1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 0 8 -20 1 0 0 0 1 0 0 0 1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 -40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat  
0 // Slope Brick Curved 2 x 2 x 0.667 (metallic_silver)  
1 80 -80 8 -20 1 0 0 0 1 0 0 0 1 15068.dat  
0 // Slope Brick Curved 4 x 1 Double with Red "NASA", Black "ESA", and Silver Background Pattern (light_bluish_grey)  
1 71 70 8 0 -1 0 0 0 1 0 0 0 -1 10283 - 93273p01.dat  
0 STEP  
0 // Tile 2 x 2 Inverted (light_bluish_grey)  
1 71 100 8 -20 1 0 0 0 1 0 0 0 1 11203.dat  
0 // Tile 2 x 2 Inverted (light_bluish_grey)  
1 71 100 8 20 1 0 0 0 1 0 0 0 1 11203.dat
```

</details>

---

**Answer:**

*This is a **rounded silver hull section, probably a spacecraft piece such as a fairing, payload-bay shell, or module skin**. It sits on a 2x12 dark-grey base plate, with a grille tile at the -X end and two light-grey inverted tiles at the +X end. The ridge slope carries red "NASA" and black "ESA" printing, so it likely comes from a space-agency-themed LEGO model, though the parts alone don't identify the exact set.*

*The split below follows the physical groups, which also match the three build steps in the original. The parent comes first, then its children (`hull-shell.ldr` and `end-cap-tiles.ldr`), then the grandchildren (the two slope rows). Coordinates are unchanged, so each submodel keeps its absolute positions and the parents reference children with an identity transform at the origin.*

---

<details>
<summary>Expand code...</summary>

```
0 FILE curved-hull-section.ldr
0 Rounded silver hull section on a long dark-grey base plate, with a grille at the -X end and light-grey tiles at the +X end
0 Name: curved-hull-section.ldr
0 Author: Unknown
0 !LDRAW_ORG Model
0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt

0 // Plate  2 x 12 (dark_bluish_grey)
1 72 0 0 0 1 0 0 0 1 0 0 0 1 2445.dat
0 // Tile  1 x  2 Grille with Groove (metallic_silver)
1 80 -110 -8 0 0 0 1 0 1 0 -1 0 0 2412b.dat
0 STEP
1 16 0 0 0 1 0 0 0 1 0 0 0 1 hull-shell.ldr
0 STEP
1 16 0 0 0 1 0 0 0 1 0 0 0 1 end-cap-tiles.ldr

0 FILE hull-shell.ldr
0 Curved silver shell made of two rows of slopes joined by a NASA/ESA-marked ridge piece
1 16 0 0 0 1 0 0 0 1 0 0 0 1 shell-row-positive-z.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 shell-row-negative-z.ldr
0 // Slope Brick Curved 4 x 1 Double with Red "NASA", Black "ESA", and Silver Background Pattern (light_bluish_grey)
1 71 70 8 0 -1 0 0 0 1 0 0 0 -1 10283 - 93273p01.dat

0 FILE end-cap-tiles.ldr
0 Two light-grey inverted 2x2 tiles closing off the +X end of the hull shell
0 // Tile  2 x  2 Inverted (light_bluish_grey)
1 71 100 8 -20 1 0 0 0 1 0 0 0 1 11203.dat
0 // Tile  2 x  2 Inverted (light_bluish_grey)
1 71 100 8 20 1 0 0 0 1 0 0 0 1 11203.dat

0 FILE shell-row-positive-z.ldr
0 Row of five silver curved slopes forming one side of the shell, on the +Z side
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -80 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 0 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 100 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat

0 FILE shell-row-negative-z.ldr
0 Row of five silver curved slopes forming the other side of the shell, on the -Z side
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -80 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 0 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 100 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
```
</details>

---

*I replaced the original description `file-01`, which was only a file name, with real one-liners. I also renamed the root from `file-01` to `curved-hull-section.ldr`, so if the outer MPD references `file-01`, that reference needs updating. All 15 original part lines are preserved, and I can save this as a .mpd file if you want it as a download.*
*This is the same fragment I split a moment ago, so here is the same answer again. It is a rounded silver hull section, probably a spacecraft piece, on a 2x12 dark-grey base plate, with a grille at the -X end and two light-grey inverted tiles at the +X end. The ridge slope has red "NASA" and black "ESA" printing, so it **likely comes from a space-themed LEGO model**, though the parts don't identify the exact set.*

*The parent comes first, then its children (`hull-shell.ldr` and `end-cap-tiles.ldr`), then the grandchildren (the two slope rows). Coordinates are unchanged, and the parents reference their children with an identity transform at the origin.*

---

<details>
<summary>Expand code...</summary>

```
0 FILE curved-hull-section.ldr
0 Rounded silver hull section on a long dark-grey base plate, with a grille at the -X end and light-grey tiles at the +X end
0 Name: curved-hull-section.ldr
0 Author: Unknown
0 !LDRAW_ORG Model
0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt

0 // Plate  2 x 12 (dark_bluish_grey)
1 72 0 0 0 1 0 0 0 1 0 0 0 1 2445.dat
0 // Tile  1 x  2 Grille with Groove (metallic_silver)
1 80 -110 -8 0 0 0 1 0 1 0 -1 0 0 2412b.dat
0 STEP
1 16 0 0 0 1 0 0 0 1 0 0 0 1 hull-shell.ldr
0 STEP
1 16 0 0 0 1 0 0 0 1 0 0 0 1 end-cap-tiles.ldr

0 FILE hull-shell.ldr
0 Curved silver shell made of two rows of slopes joined by a NASA/ESA-marked ridge piece
1 16 0 0 0 1 0 0 0 1 0 0 0 1 shell-row-positive-z.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 shell-row-negative-z.ldr
0 // Slope Brick Curved 4 x 1 Double with Red "NASA", Black "ESA", and Silver Background Pattern (light_bluish_grey)
1 71 70 8 0 -1 0 0 0 1 0 0 0 -1 10283 - 93273p01.dat

0 FILE end-cap-tiles.ldr
0 Two light-grey inverted 2x2 tiles closing off the +X end of the hull shell
0 // Tile  2 x  2 Inverted (light_bluish_grey)
1 71 100 8 -20 1 0 0 0 1 0 0 0 1 11203.dat
0 // Tile  2 x  2 Inverted (light_bluish_grey)
1 71 100 8 20 1 0 0 0 1 0 0 0 1 11203.dat

0 FILE shell-row-positive-z.ldr
0 Row of five silver curved slopes forming one side of the shell, on the +Z side
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -80 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 0 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 40 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 100 8 20 -1 0 0 0 1 0 0 0 -1 15068.dat

0 FILE shell-row-negative-z.ldr
0 Row of five silver curved slopes forming the other side of the shell, on the -Z side
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -80 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 -40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 0 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 40 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
0 // Slope Brick Curved  2 x  2 x  0.667 (metallic_silver)
1 80 100 8 -20 1 0 0 0 1 0 0 0 1 15068.dat
```

</details>

---

*I replaced the original `file-01` description, which was just a file name, with real one-liners, and renamed the root to `curved-hull-section.ldr`. If the outer MPD references `file-01`, that reference will need updating. All 15 original part lines are preserved, and I can save this as a .mpd file if you want a download.*

## Development

This is a **very preliminar release** that, however, yields many [good results](GALLERY.md), but far from being optimal:

- **Complex mechanisms** and **large models** take **too much time and effort to animate.**
- Also for those, agents would go through **"rabbit holes"** and **get lost during animation sessions.**
- **Broken animations** for **flexible parts** on models like e.g. hoses or cables.
- Low-end models, like e.g. **Claude Haiku 5.5** or **GPT-6 Luna**, can produce animations, but most of them have **noticeable defects.**
- **No proper physics**, it doesn't take into account e.g. **gravity** or any **forces** interactions, **weights**, **inertia**, etc.
- And **more**... 🤫


## Acknowledgements

I'd like to thank the following:

- [The LDraw Community](https://www.ldraw.org/)
- [LDView](https://tcobbs.github.io/ldview/)'s Travis Cobbs (@tcobbs), and contributors.
- [LeoCAD](https://github.com/leozide/leocad)'s Leonardo Zide (@leozide), and contributors.
- [LDCad](https://www.melkert.net/LDCad) and Shadow Library, Roland Melkert.
- [pyldraw3](https://github.com/hbmartin/pyldraw3)'s  Harold Martin (@hbmartin), and contributors.

... and thanks to all of the many other LDraw creators!

**NOTE:** For this work, I've used many LDraw models, libraries, tools, docs... from many sources.

There is a lot **amazing people** that generously contributed to this, even for **decades**, by **generously donating their finest work** to the public domain and open source community. 

If you think you should be included on this section, please **drop me an email!**

## Trademarks

**LEGO(R)** is a trademark of the **LEGO Group** of companies which does not sponsor, authorize or endorse this software.
