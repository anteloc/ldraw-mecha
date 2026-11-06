---
aliases:
---
# ldraw-mecha

**Give an [LDraw](https://www.ldraw.org/) LEGO© model to an AI agent, get back a Blender-animated version of it.**

The agent will:

- **Reverse-engineer** (infer) the **LDraw model's mechanics** from its **.mpd source code file**
- **Study** the **discovered** mechanisms.
- **Plan** the **interactions** between their different mechanical components.
- And finally, turn those **plans** into **python code for Blender**, that will:
	- **Create** the required **rigs** for controlling the different mechanisms.
	- **Animate** them according to **plan**!

## Why?

After publishing [LDraw Nova](https://github.com/anteloc/ldraw-nova), a sibling project for **agentic generation of LDraw models**, several people reached out to me asking about if models could be animated somehow.

During the development of Nova, I've noticed that **adding** some **special annotations** to `.mpd` **original** model **source files**, and then giving those to **agents**, would:

- **Help** agents in **understanding how to build** other different models.
- But also, in **understanding how a model was built**.

Which gave me the idea that, maybe, an agent would also **understand how a model would work.**

As a first step to it, I gave annotated models to different agents, and prompted them to infer (reverse-engineer) their constituent submodels, like e.g. the following experiment:



**Prompt (Claude Haiku 5.5)**

*This is a fragment, a submodel, from an LDraw .mpd file model.*

*This is not an executable code fragment, but more like a 3D CAD model fragment written in LDraw language.*  
*Infer what this submodel is, and also split it into submodels (starting with: 0 FILE):*

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



## Installation

> [!INFO]
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

Take a look at the [Process](PROCESS.md) guide for a **step-by-step usage example**.

## Samples

> [!INFO]
> More samples available at: [Gallery](GALLERY.md)
> Animations have been generated from **original models**, not from ai-generated ones.

These are **some samples** of animations by different agents, take a look at their Summaries for more details.

## 42043 Mercedes-Benz Arocs flatbed truck: the pneumatic crane on its own

**Agent: Claude Sonnet 5.5**
**Original model:** [42043-1_Flatbed-Trailer.mpd](data/models-annotated/42043-1_Flatbed-Trailer.mpd)
**Context:** The model was too large and complex for fully animating it, finally I accepted Sonnet's suggestion about animating the crane alone.

<a href="samples/42043-crane.png"><img src="samples/42043-crane.png" width="320" alt="42043 Mercedes-Benz Arocs flatbed truck"></a>

[▶ Video](https://anteloc.github.io/ldraw-mecha/samples/42043-crane.mp4) · [Summary](samples/42043-crane.md)

**Original**

<a href="img/42043-1_Flatbed-Trailer.png"><img src="img/42043-1_Flatbed-Trailer.png" width="320" alt="42043 Mercedes-Benz Arocs flatbed truck"></a>

## 3625 Fabuland plane: take-off, flight and landing

**Agent: Claude Sonnet 5.5**
**Original model:** [3625-1.mpd](data/models-annotated/3625-1.mpd)
**Context:** Asked for an in-place animation, to avoid the plane moving around.

<a href="samples/3625.png"><img src="samples/3625.png" width="320" alt="3625 Fabuland plane"></a>

[▶ Video](https://anteloc.github.io/ldraw-mecha/samples/3625.mp4) · [Summary](samples/3625.md)

## Minifig movement catalog: ten minifigs, three moves each

**Agent: Claude Opus 5.5**
**Original model:** None
**Context:** This one is actually a **generated composition**, from several **different minifigs**, to be used as a **"howto reference"** for other agents also animating minifigs.

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
