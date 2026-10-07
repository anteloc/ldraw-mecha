# Choosing part information

Use `data/categories` for **browsing families and selecting named components**.
It is a useful offline alternative to description search for those tasks, and a
complement to the database for inventory classification. It does not establish
connections, axes or motion. The [minifig builder](../scripts/build_minifigs.py)
already uses it to choose separate arms, hands, legs and accessories.

## Which source to use

| Question | First source | What still needs checking |
| --- | --- | --- |
| Which individual parts belong to a family? | [Category tables](../data/categories/parts): `technic.py`, `hinges.py`, `animals.py`, `minifig/`, etc. | Availability, aliases, assembly versus separate piece |
| Which part best matches a description? | `./ldraw-mecha search parts 'worm gear' --engine fts` | Ranking is not compatibility; inspect the selected DAT |
| Where is a mechanism used in an actual model? | `search submodels`, `submodels MODEL`, then the annotated MPD | Occurrences, transforms and interfaces in that model |
| What is a part called, without SQLite? | [Full description TSV](../data/part-descriptions-full.tsv) or [category parts.lst](../data/categories/parts.lst) | Snapshot freshness; neither gives connectivity |
| Rough local size for filtering or framing? | [get_dimensions](../data/categories/dimensions.py), or database `PART_BBOXES` | Extents include geometry such as studs; they are not nominal sizes or joint centres |
| Where and how could two parts connect? | pyldraw3 with LDraw geometry and `data/offLibShadow`, exposed by `connectors` and `contacts` | Engagement, retention, rigid/free meaning and clearance |
| How should that assembly move? | [Curated references](reference/README.md), measured geometry and a motion plan | Remeasure the target and test its motion |

There is **no set/model taxonomy in this directory**: its tables describe part
families, colours and dimensions. Set-level categories/themes and model/submodel
descriptions are in `ldraw-info.db`; actual assemblies are in `models-annotated`.
The category folder is not an alternative to the MPD model catalog.

## Fast local lookups

From the repository root, search the relevant small table before dumping a
whole catalog. Names are CamelCase Python constants; values are LDraw references
without `.dat`:

```sh
rg -n 'WormGear|TechnicAxle9' data/categories/parts/technic.py
rg -n 'ArmLeft|ArmRight|Hand =|Hips =' data/categories/parts/minifig
rg -n 'Crocodile|Clam' data/categories/parts/animals.py
# Reverse lookup: where is this reference classified?
rg -n '"3815b"' data/categories/parts
```

Named imports and dimensions need no Blender, SQLite or network:

```python
from data.categories.parts.minifig import arms, hands
from data.categories import get_dimensions

arm = arms.ArmLeft       # "3819"
hand = hands.Hand        # "3820"
size = get_dimensions(arm)  # ldu_x, ldu_y, ldu_z; grid-rounded size hints
assert get_dimensions("not-a-part") == {}
```

Pass a bare, lowercase reference to `get_dimensions`; `"3819.dat"` is not a
dictionary key. Do not mutate its returned dictionaries. For large inventories,
parse the tables as data (for example with `ast`) and retain the category,
constant name and reference. Avoid flattening them with `import *`: names recur
across files and some names are assigned more than once within a file. A Python
import keeps only the last such assignment; raw text/AST preserves that evidence.
`build_minifigs.tables()` is a small, minifig-specific lookup, not a general
taxonomy API. The CLI's `search` still queries SQLite, not these tables.

For database metadata not exposed by `search`, use read-only SQL. In the current
database the key for these two tables includes `.dat`:

```python
from pathlib import Path
import sqlite3

with sqlite3.connect(Path("data/ldraw-info.db").resolve().as_uri() + "?mode=ro", uri=True) as db:
    category = db.execute("SELECT categories FROM PART_CATEGORIES WHERE alias=?", ("3819.dat",)).fetchone()
    bbox = db.execute("SELECT min_x, min_y, min_z, max_x, max_y, max_z, complete "
                      "FROM PART_BBOXES WHERE alias=?", ("3819.dat",)).fetchone()
```

Check for a missing row and the box's `complete` value before relying on it.
This example returns no `PART_CATEGORIES` row for `3819.dat` in the audited
snapshot, although the Python taxonomy names it and its bounding box is present.
Unlike the dimensions dictionary, these boxes include bounds and centre fields;
neither source substitutes for evaluated mesh clearance.

## Useful applications and traps

**Character construction:** select a plain/patterned torso and separate limbs
when each must move. The minifig case deliberately avoids combined torso/arm/hand
DATs that import as a single physical occurrence. The taxonomy also distinguishes
complete crocodiles from bodies, heads and tails. This makes it a good candidate
list for future articulated-animal studies, not an already verified animal rig.

**Mechanism inventory:** family membership can help shortlist gears, hinges,
axles, doors, turntables or articulated figure components. Join by part reference
to the model's occurrence inventory; keep every occurrence and its transform.
An unknown family means unclassified, not static. Do not merge patterned variants
or strip suffixes to guess geometry. “Complete”, “Open” and “Closed” can describe
assembly or fixed-pose DAT variants rather than an available motion control.

**Approximate dimensions:** `get_dimensions("3001")` gives 80 × 28 × 40 LDU
and `plates_y=4`. That Y extent includes the stud; it is not a four-plate-high
brick body. For `3819` the extents are about 17.065 × 28.936 × 19.936 LDU;
they do not locate the shoulder pivot. Read connectors/geometry for pivots,
grips, shaft axes, pitch radii and mounting offsets. The dictionary has no
min/max coordinates, so an off-centre part cannot be positioned from it alone.

**Coverage and naming:** basic hips `3815b` are in `minifig/accessories.py`,
not the almost empty `hips.py`; many hats are also in accessories. Expand a
failed search to the whole folder. Underscore names, obsolete tables and moved
parts need review. Check the actual library file/header before conversion;
`build_minifigs.library_title()` demonstrates existence and moved/obsolete
checks. Keep upstream attribution and the supplied notices when reusing data.

## Evaluation of this snapshot

The [2026-10-07 audit](../output/minifigs-reference-review/taxonomy-audit.json)
counts 62 leaf tables (64 Python files), 23,551 string assignments and 20,589
distinct references. `dimensions.py` has 22,588 entries. These are snapshot
counts, not a promise of current LDraw coverage.

The database has 35,257 part descriptions and 35,256 bounding boxes. Of the
taxonomy's references, 20,429 are in both the database and dimensions dictionary;
160 are absent from the installed parts library as well as the description
table. Conversely, 14,828 database references are absent from the category
tables. Database `PART_CATEGORIES` covers only 5,418 rows, so the directory adds
useful family labels even though its part coverage is smaller than descriptions.
The audit also found 20 repeated constant-name assignments within individual
files. The sources are related snapshots, not independent corroboration of fit.

The generic `parts/` ignore rule previously hid the entire category-table tree
from Git and ordinary recursive `rg` searches. A narrow exception now makes
those existing source tables available for version control and future checkouts.
No taxonomy regeneration, new dependency or automatic mechanism inference is
required to use them.
