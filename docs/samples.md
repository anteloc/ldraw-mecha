# Samples

`samples/` publishes past generated results as evidence of what agents produced.
Each sample is exactly four sibling items sharing one basename:

| Item | Content |
| --- | --- |
| `samples/NAME/` | Verbatim copy of the generated folder (e.g. `output/106/`). Never edited. |
| `samples/NAME.mp4` | Web-sized H.264 encode of the video the user supplied. |
| `samples/NAME.png` | A "home" still of the result, rendered from its `.blend` for web pages and the gallery. |
| `samples/NAME.md` | Summary for readers: what the sample shows, how it was made, and what each file is. |

Sometimes the evidence relies on other things the same run generated, for
example a derived source model in `output/NAME-source/`, an early study folder,
or new scripts that exist only in the checkout where the run happened. Pass each
folder or file with `--extra`. It is copied verbatim to
`samples/NAME/extra/<folder or file name>`. This keeps the four-item
convention, and the original evidence files stay byte-identical. Files already
committed to this repo, such as `data/models-annotated/` or existing `scripts/`,
are not extras. Neither are artifacts a webapp makes for other purposes, such as
gallery copies in `ldraw-mecha-docker/data/generated/`.

Only Blender backups (`*.blend1`, `*.blend2`, …), Python caches (`__pycache__/`,
`*.pyc`) and `.DS_Store` are left out of the copy; they are not evidence and
stay git-ignored. Everything else,
including logs and scripts, is committed as-is. Everything under `samples/` is
LFS-tracked except the `samples/NAME.md` summaries, which are plain git so
GitHub renders them.

## Adding a sample

The user supplies the evidence folder and a `.mov` or `.mp4` video:

```bash
./add-sample.sh output/106 path/to/video.mov          # NAME defaults to the folder name
./add-sample.sh output/106 path/to/video.mov --name 106-car
./add-sample.sh output/minifigs minifigs.mov --blend minifigs.blend   # when there are several
./add-sample.sh output/3625 3625.mov --extra output/3625-source
./add-sample.sh ../exp/output/42043-crane crane.mov --extra ../exp/scripts/build_crane_42043.py
```

Before you run it, search the evidence for paths outside its folder, such as
`grep -rhoE '(\.\./|output/)[A-Za-z0-9._-]+' output/NAME`. Also check the
source checkout for the run's other output folders and uncommitted scripts
(`git status` there). Pass each generated folder or file you find with `--extra`.

The script refuses to overwrite an existing sample. It then:

1. encodes the video to `samples/NAME.mp4` (max 1920 px wide, max 30 fps,
   CRF 24, no audio; override with `SAMPLE_MAX_WIDTH`, `SAMPLE_FPS`,
   `SAMPLE_CRF`);
2. renders `samples/NAME.png` from the evidence's `.blend` in background
   Blender. With several `.blend` files it stops and lists them: pick one with
   `--blend FILE` (relative to the evidence folder). The still shows the file's
   active scene at its saved frame, everything visible framed from a
   three-quarter view above the front-right, like Blender's Home (Frame All).
   Hidden objects, such as hidden bodywork, stay hidden. Every sample gets the
   same studio look: Cycles (denoised, on the GPU when there is one), soft key,
   fill and rim lights with shadows instead of the file's own lights, and a
   mid-grey backdrop with contact shadows, so white and dark parts both stand
   out. It is a 1600×1200 PNG of about 1.3–1.6 MB, and takes about 20–30 s on
   an Apple M4 GPU (override the size with `SAMPLE_IMAGE_SIZE=WxH`). The
   `.blend` is not changed. There is one image only: a gallery page shows it scaled down and
   links to the full size, e.g.
   `<a href="NAME.png"><img src="NAME.png" width="320"></a>`;
3. copies the folder, verifies it with `diff -r`, and checks every file is
   committable;
4. prints facts for the summary (evidence time range, `.blend` files, models
   referenced) and ranked chat candidates from Claude
   (`~/.claude/projects/`), Codex (`~/.codex/sessions/`) and the docker webapp
   (`../ldraw-mecha-docker/data/chats/`, override with `DOCKER_ROOT`). Claude
   and Codex chats are searched for this repo and for the git checkout that
   holds the source, such as an experiment clone.

Then write `samples/NAME.md` (see below) and add a section for the sample to
[GALLERY.md](../GALLERY.md), copying an existing one: the summary's title as a
`##` heading, the linked thumbnail, and the `▶ Video` and `Summary` links.

The video link points to GitHub Pages
(`https://anteloc.github.io/ldraw-mecha/samples/NAME.mp4`), because GitHub
serves LFS files from the repo as downloads. Pages publishes `samples/*.mp4`
and `pages/` when a version tag such as `v0.7.5` is pushed on a `master` commit
([.github/workflows/pages.yml](../.github/workflows/pages.yml)), so a new
sample's video plays once the next release tag is out.

## Choosing the chat

Candidates are ranked by how many distinct evidence files the chat refers to.
The chat that generated the files is usually the one that names most of them.
A chat flagged `after` first mentions the folder once the evidence was already
written, so it cannot have produced it. Later reviews land there, as do
multi-day sessions that only reached the folder afterwards and this sample's
own session. A docker `exact` match comes from the chat ID in the
evidence path. Read the top candidate and confirm that its turns created the
files before summarising it.

## Summary template

The summary is for people, not agents: someone who never saw the chat should
understand what the sample shows, when it was made, how long it took, why each
file exists and where it is. [samples/3625.md](../samples/3625.md) is the
reference example; follow its layout.

```markdown
# <Model number and name>: <what the animation shows>

<2-3 plain sentences: what you see in the video, which LEGO model, who made
it, and the outcome.>

[![<model name>](NAME.png)](NAME.png)

▶ [Watch the video](NAME.mp4)

## At a glance

| | |
|---|---|
| LEGO model | <number and name>; source file `data/models-annotated/<file>` |
| Made by | <agent> (<model>) |
| When | <YYYY-MM-DD>, <start>–<end> Madrid time |
| Working time | About <N> min of agent work<, plus the pauses worth noting> |
| Result | [NAME/<main>.blend](NAME/<main>.blend): <frames> frames at <fps> fps |

## How to view it

1. Open [NAME/<main>.blend](NAME/<main>.blend) in Blender 5.2 or later.
2. Press Play (Space).
3. <Where the controls are and what each one moves.>

## What was asked

> <the user's exact request>

## What happened

1. <5-8 short steps in time order: plan, user decisions, problems found and
   how they were fixed, delivery, follow-up questions.>

## Files

All paths are relative to `samples/`.

| File | What it is | Why it exists |
|---|---|---|
| [NAME.mp4](NAME.mp4) | <screen recording, made by whom> | To show the result |
| [NAME.png](NAME.png) | Still rendered from [NAME/<main>.blend](NAME/<main>.blend) by `add-sample.sh` | Preview for pages and the gallery |
| [NAME/<file>](NAME/<file>) | <...> | <...> |

## Known limits

- <3-6 limits the agent stated, in plain words.>

## Source

<Tool> chat `<session id>`, stored <where>. Times come from the chat log, not
from file dates.
```

Writing rules:

- **Plain words.** Avoid toolkit jargon (LDU, evaluator, coaxial, signals,
  shortcut parts). If a term is needed, explain it once in passing. Convert
  LDU to real-world size (1 LDU = 0.4 mm) when a size matters.
- **Each fact once,** in the section where a reader would look for it.
- **When:** Madrid time only, in one range from the first request to the last
  message. Times are approximate.
- **Working time:** agent activity only. `add-sample.sh` prints it for each
  chat candidate: the sum of gaps of 5 minutes or less between messages. Leave
  out longer gaps (waiting for the user, overnight pauses) and mention the ones
  a reader would wonder about.
- **What was asked:** the user's exact words in a blockquote. Leave out text
  the client added automatically, such as IDE or browser context. For a long
  request (more than about 10 lines), write a one-sentence gist and put the
  exact text in a collapsed `<details><summary>Full request</summary>` block.
  Replies that changed the work go in "What happened", quoted briefly. If
  another agent answered for the user, say so.
- **Where:** every file is a relative link whose text is its path, so the path
  is also its location. Use relative links only (`NAME.mp4`, `NAME/...`), never
  GitHub URLs or branch names, so merges and squashes never break them.
- **Why:** every file, or group of similar files (`NAME/xray/`), gets one row
  in the files table, and every row says why the file exists. Extras are
  listed with the path they were copied from.
- **Composite scenes** (several animations sharing one scene, like
  `minifigs` and `plants`): say so in the opening paragraph.
- **Claims:** report the agent's checks and limits as the agent stated them.
  Do not call motion collision-free or physically proven.

The summary adds context only. Never edit files in `samples/NAME/`.
