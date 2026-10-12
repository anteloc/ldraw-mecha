"""Read-only curation of the selected minifig bundle; writes fresh evidence here."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from reference_assets import load_plan
from ldraw_mechanisms import plan as contract
from ldraw_mechanisms.source import library_path
import build_minifigs as builder
import minifig_clips as clips

OUT = ROOT / "output/reference-rechecks/minifigs"
OUT.mkdir(parents=True, exist_ok=True)
BUNDLE = ROOT / 'examples/reference/minifigs'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def taxonomy():
    root = ROOT / 'data/categories'
    files = sorted((root / 'parts').rglob('*.py'))
    entries, duplicates = [], []
    for path in files:
        seen = {}
        for node in ast.parse(path.read_text()).body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                name, ref = node.targets[0].id, node.value.value
                if name in seen:
                    duplicates.append([str(path.relative_to(root)), name, seen[name], ref])
                seen[name] = ref
                entries.append(dict(file=str(path.relative_to(root)), name=name, ref=ref))
    refs = {e['ref'].lower() for e in entries}
    dims = next(ast.literal_eval(n.value) for n in ast.parse((root / 'dimensions.py').read_text()).body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PartsDimensions'
                                                    for t in n.targets))
    tables = ['PARTS_DESCRIPTIONS', 'MODELS_DESCRIPTIONS', 'SUBMODELS_DESCRIPTIONS',
              'PART_CATEGORIES', 'PART_BBOXES']
    with sqlite3.connect((ROOT / 'data/ldraw-info.db').as_uri() + '?mode=ro', uri=True) as db:
        db_refs = {r[0].lower().removesuffix('.dat') for r in db.execute('select part from PARTS_DESCRIPTIONS')}
        rows = {t: db.execute(f'select count(*) from {t}').fetchone()[0] for t in tables}
        boxes = db.execute("select alias, dim_x, dim_y, dim_z, complete from PART_BBOXES "
                           "where alias in ('3001.dat','3819.dat')").fetchall()
    return dict(
        date='2026-10-07', python_files=len(files), leaf_tables=sum(p.name != '__init__.py' for p in files),
        string_assignments=len(entries), distinct_refs=len(refs), dimensions=len(dims),
        table_bytes=sum(p.stat().st_size for p in files),
        private_aliases=sum(e['name'].startswith('_') for e in entries),
        category_counts=dict(Counter(e['file'] for e in entries)),
        duplicate_names_within_file=duplicates, db_rows=rows,
        taxonomy_refs_in_db=len(refs & db_refs), taxonomy_refs_not_in_db=sorted(refs - db_refs),
        db_refs_not_in_taxonomy=len(db_refs - refs), dimensions_covering_taxonomy=len(refs & dims.keys()),
        missing_in_installed_library=[r for r in sorted(refs) if not (library_path() / 'parts' / f'{r}.dat').is_file()],
        dimension_samples={r: dims.get(r) for r in ['3001', '3005', '3819', '3820', '3817c', '4716']},
        database_bbox_samples=boxes,
        hashes={str(p.relative_to(ROOT)): digest(p) for p in files + [root / 'dimensions.py']},
    )


def figures():
    result = {}
    for fig in builder.ROSTER:
        folder = BUNDLE / fig['key']
        plan = load_plan(folder / 'plan.json')
        contract.validate(plan)
        role_map = read(folder / 'source/parts.json')
        parts, evidence = builder.assemble(fig)
        authored, semantics = builder.author_plan(fig, read(folder / 'study/plan.json'), role_map['parts'], evidence)
        fields = ('controls', 'signals', 'bodies', 'anchors', 'checks')
        matched = all(plan[k] == authored[k] for k in fields)
        assert matched, fig['key']
        assert digest(folder / 'source/minifig.mpd') == plan['source']['sha256']
        values = dict(neck=0.8, shoulder_l=1.2, shoulder_r=-0.7, wrist_l=-0.4, wrist_r=0.9,
                      hip_l=0.5, hip_r=-0.3)
        contract.evaluate(plan, values)
        lifecycle = read(folder / 'lifecycle.json')
        clear = read(folder / 'clearance.json')['clip_poses']
        result[fig['key']] = dict(
            parts=len(role_map['parts']), bodies=len(plan['bodies']), builder_motion_matches=matched,
            source_hash_matches=True, semantics=semantics, asymmetric_values=values,
            lifecycle_report_passed=lifecycle['passed'], own_clip_crossings=clear['crossings_by_clip'],
            hashes={p: digest(folder / p) for p in ('source/minifig.mpd', 'source/parts.json', 'plan.json',
                                                    'lifecycle.json', 'clearance.json')})
    return result


def main():
    library = clips.library()
    assert all(not clips.check(c) for c in library)
    for clip in library:
        assert read(BUNDLE / 'clips' / f'{clip.id}.json')['baked'] == clips.baked(clip)
    report = dict(date='2026-10-07', figures=figures(), clips=len(library),
                  clip_rules_passed=True, exported_baked_clips_match=True,
                  hashes={str(p.relative_to(ROOT)): digest(p) for p in [BUNDLE / 'minifigs.blend',
                          ROOT / 'scripts/build_minifigs.py', ROOT / 'scripts/minifig_clips.py',
                          ROOT / 'scripts/blender/animate_minifigs.py']},
                  coverage='Source hashes, builder motion, portable evaluation, semantic signs and clip data. '
                           'Existing clearance/lifecycle results read, not rerun. No physical proof.')
    (OUT / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    (OUT / 'taxonomy-audit.json').write_text(json.dumps(taxonomy(), indent=2) + '\n')
    print(f"Reviewed {len(report['figures'])} figures and {len(library)} clips")


if __name__ == '__main__':
    main()
