# Annotate an unannotated model

Studies and plans rely on an **annotated** model:
- a submodel hierarchy that a builder would recognise;
- a one-line description of every submodel;
- a `0 // <part> (<colour>)` comment above every part.

When a user supplies an unannotated `.ldr` or `.mpd`, offer to annotate it in this
session with [ldraw-annotator](https://github.com/anteloc/ldraw-annotator-nova).
The tool prepares the model and verifies the result; you, the agent, structure
and describe it. If the user declines, **stop**: ask for an annotated model
instead. Don't prepare, plan or animate an unannotated model.

A model is unannotated when most part lines have no `0 //` comment above them,
or its sections carry only names (`0 car`, `0 main`) instead of descriptions. A
file or folder name proves nothing either way. Already annotated models, such as
those in `data/models-annotated/`, are used as they are: don't rewrite or regroup
them unless asked to.

`setup-*.sh` installs the tool as `bin/ldraw-annotator`; if that is missing, use
`ldraw-annotator` from `PATH`. Its commands read `data/ldraw-info.db`, through
`--db` or `$LDRAW_ANNOTATOR_DB`. The commands below pass `--db`, so they don't
depend on your shell profile.

## 1. Prepare the copy, then make the offer

`prep` costs no tokens and takes under a second, even for a 50 MB model. It writes
a separate copy with part comments added and flexible parts (hoses, cables,
chains…) moved into their own submodels. The original is never changed.

```sh
bin/ldraw-annotator prep MODEL.mpd --mpd output/annotated/MODEL.mpd --db data/ldraw-info.db
```

Its JSON gives the `prefix` for new section names, the section counts and
`items`, the number of parts. Base the offer on these numbers and on the copy's
size:
- Say what annotation adds.
- Give a rough token estimate: about **size in bytes ÷ 2.5** tokens to read the
  copy once. Regrouping rewrites the moved part lines, and each `check` round
  adds more, so the whole job costs several times that.
- Warn plainly when the model is large (roughly 1000 parts or 100 KB and up),
  then let the user decide.

| Example (prep output) | Parts | Sections | Size | One read, approx. |
| --- | --- | --- | --- | --- |
| 1029 Milk Delivery Truck | 102 | 6 | 12 KB | 5k tokens |
| 10174 AT-ST | 833 | 15 | 87 KB | 35k tokens |
| 10248 Ferrari F40 | 1944 | 74 | 190 KB | 75k tokens |
| 10251 Brick Bank | 2417 | 26 (+19 embedded parts) | 917 KB | 370k tokens |

The token figures are estimates from file size, not measured sessions. Embedded
`.dat` sections don't need reading, so a model that consists mostly of them (like
the Brick Bank) costs less than its size suggests.

If the user declines, stop there. They can also annotate the model outside this
session with `ldraw-annotator run`, which uses an LLM provider and its API key
(see the tool's README).

## 2. Annotate

```sh
bin/ldraw-annotator prompt
```

`prompt` prints the task, the rules and the annotation guide as Markdown. Follow
it, editing `output/annotated/MODEL.mpd`. In short:
- describe every model section on the line right after its `0 FILE`;
- split sections that hold distinct assemblies into new submodels, as deep as
  each branch needs. Moved part lines are kept verbatim, and each new submodel
  is referenced with colour 16 and the identity matrix;
- keep every part occurrence exactly once.

Then verify the copy against the original, and fix every error until the result
says `"ok": true`:

```sh
bin/ldraw-annotator check MODEL.mpd output/annotated/MODEL.mpd --db data/ldraw-info.db
```

`check` proves the copy is lossless: every part occurrence keeps its world
placement and effective colour. It also checks the format rules and that pyldraw3
reads the file as intended. The format is specified in the tool's
[output contract](https://github.com/anteloc/ldraw-annotator-nova/blob/master/docs/output-contract.md).
Semantic groups describe the model. They don't declare rigid bodies or prove
mechanics.

## 3. Use the annotated copy

From here on, `output/annotated/MODEL.mpd` *is* the model. Treat it as if the
user had supplied it, and use it for every later step: study, extraction,
conversion and plans.

```sh
./ldraw-mecha prepare output/annotated/MODEL.mpd --output output/model-study
```

Finish annotating before you create a plan or GLB. Annotation changes section
names and occurrence paths, so plans and bindings made from another file don't
carry over.
