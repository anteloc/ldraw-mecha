# Samples

`samples/` publishes past generated results as evidence of what agents produced.
Each sample is exactly three sibling items sharing one basename:

| Item | Content |
| --- | --- |
| `samples/NAME/` | Verbatim copy of the generated folder (e.g. `output/106/`). Never edited. |
| `samples/NAME.mp4` | Web-sized H.264 encode of the video the user supplied. |
| `samples/NAME.md` | Agent-written summary: references and chat summary. |

Sometimes the evidence relies on other generated folders, for example a derived
source model in `output/NAME-source/`. Pass each one with `--extra`. It is copied
verbatim to `samples/NAME/extra/<folder>/`. This keeps the three-item convention,
and the original evidence files stay byte-identical. Folders that are already in
the repo, such as `data/models-annotated/` or `scripts/`, are not extras.

Only Blender backups (`*.blend1`, `*.blend2`, …) and `.DS_Store` are left out
of the copy; they are not evidence and stay git-ignored. Everything else,
including logs and scripts, is committed as-is. `.blend`, `.glb`, `.mp4` and
images are LFS-tracked.

## Adding a sample

The user supplies the evidence folder and a `.mov` or `.mp4` video:

```bash
./add-sample.sh output/106 path/to/video.mov          # NAME defaults to the folder name
./add-sample.sh output/106 path/to/video.mov --name 106-car
./add-sample.sh output/3625 3625.mov --extra output/3625-source
```

Before you run it, search the evidence for paths outside its folder, such as
`grep -rhoE '(\.\./|output/)[A-Za-z0-9._-]+' output/NAME`. Pass each generated
folder you find with `--extra`.

The script refuses to overwrite an existing sample. It then:

1. encodes the video to `samples/NAME.mp4` (max 1920 px wide, max 30 fps,
   CRF 24, no audio; override with `SAMPLE_MAX_WIDTH`, `SAMPLE_FPS`,
   `SAMPLE_CRF`);
2. copies the folder, verifies it with `diff -r`, and checks every file is
   committable;
3. prints facts for the summary (evidence time range, `.blend` files, models
   referenced) and ranked chat candidates from Claude
   (`~/.claude/projects/`), Codex (`~/.codex/sessions/`) and the docker webapp
   (`../ldraw-mecha-docker/data/chats/`, override with `DOCKER_ROOT`).

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

Write `samples/NAME.md` with relative links only (`NAME.mp4`, `NAME/`), so
merges and squashes never break them. Do not use GitHub URLs or branch names.

```markdown
# Animation: <animation title>, by <agent(s)>

## References

- **Date:** <approximate date, with timestamps and time zone if available>
- **Agent(s):** <agent, model, and effort if recorded>
- **Model:** <.mpd/.ldr filename used for the animation>
- **Animation video:** [NAME.mp4](NAME.mp4)
- **Evidences:** [NAME/](NAME/), plus each extra source folder,
  [NAME/extra/FOLDER/](NAME/extra/FOLDER/), and the original path it was copied from
- **Produced `.blend` files:**
    - `NAME/rigged.blend`: <one-line role>

## Chat summary

- **Prompt:** <exact text of the user request that triggered the work, in
  italics; for a long prompt, quote it as an italic block below this item.
  Leave out text the client added automatically, such as IDE context, and
  say so>
- **Most relevant:**
    - <brief decisions by the agent or user, issues found, how they were
      resolved; keep it short>
```

The summary adds context only. Never edit files in `samples/NAME/`.
