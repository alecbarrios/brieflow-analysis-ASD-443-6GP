#!/usr/bin/env python3

"""
Rename brieflow .nd2 files so metadata (plate, cycle/round, well, tile) is
embedded directly in the filename.

Current convention (SBS example, inside .../plate_1/input_sbs/c1/):
    P01_Wells-A1-A2-C2-C3-C4_Points-.nd2          -> point_idx 0
    P01_Wells-A1-A2-C2-C3-C4_Points-_0001.nd2     -> point_idx 1
    P01_Wells-A1-A2-C2-C3-C4_Points-_0349.nd2     -> point_idx 349
    ...

With tiles_per_well=349, point_idx 0..348 belong to wells_list[0] (A1, tiles 0..348),
point_idx 349..697 belong to wells_list[1] (A2, tiles 0..348), etc.

Output convention (easy to regex later):
    SBS:        plate-1_cycle-1_well-A1_tile-0.nd2
    Phenotype:  plate-1_round-1_well-A1_tile-0.nd2

Directory structure is preserved; only the filenames change.
"""

from pathlib import Path
import re
import random
import shutil
from collections import defaultdict

# ---------- filename parsing ----------

# Captures: plate number, wells list (raw), and the point suffix.
# Point suffix is either "" (means index 0) or "_NNNN" (means int(NNNN)).
FNAME_RE = re.compile(
    r"^P(?P<plate>\d+)_Wells-(?P<wells>[A-Z0-9\-]+)_Points-(?P<pt>(?:_\d+)?)\.nd2$"
)

# Cycle/round directory like "c1", "c10", "c13-no-primer"
CYCLE_DIR_RE = re.compile(r"^c(?P<n>\d+)(?P<suffix>.*)$")

def parse_filename(name: str):
    """Return (plate_int, wells_list, point_idx) or None if it doesn't match."""
    m = FNAME_RE.match(name)
    if not m:
        return None
    plate = int(m.group("plate"))
    wells = m.group("wells").split("-")

    # --- correction for human-error in acquisition naming ---
    # Files labeled A3-B1-C1-C3 should actually be A3-B1-C1-C2.
    if wells == ["A3", "B1", "C1", "C3"]:
        wells = ["A3", "B1", "C1", "C2"]
    # --------------------------------------------------------

    pt = m.group("pt")
    point_idx = 0 if pt == "" else int(pt.lstrip("_"))
    return plate, wells, point_idx

def parse_cycle_dir(dirname: str):
    """Return (cycle_int, suffix_str) or None. 'c13-no-primer' -> (13, '-no-primer')."""
    m = CYCLE_DIR_RE.match(dirname)
    if not m:
        return None
    return int(m.group("n")), m.group("suffix")


# ---------- new name construction ----------

def build_new_name(plate, kind_key, kind_val, well, tile, suffix=""):
    """
    kind_key: 'cycle' or 'round'
    suffix:   extra tag from dir name, e.g. '-no-primer' -> appended as '_no-primer'
    """
    tag = ""
    if suffix:
        tag = "_" + suffix.lstrip("-")
    return f"plate-{plate}_{kind_key}-{kind_val}_well-{well}_tile-{tile}{tag}.nd2"


# ---------- planning (no filesystem changes) ----------

def plan_renames(root_dir, kind, tiles_per_well=349, skip_dirs=()):
    """
    Walk root_dir (e.g. .../plate_1/input_sbs), build a list of planned renames.

    kind: 'sbs' -> uses 'cycle'; 'ph' -> uses 'round'
    Returns list of dicts: {old_path, new_path, plate, cycle_or_round, well, tile,
                            point_idx, wells_list, ok, reason}
    """
    assert kind in ("sbs", "ph")
    kind_key = "cycle" if kind == "sbs" else "round"

    root = Path(root_dir)
    plans = []

    # Each immediate subdir is a cycle/round folder (c1, c2, ...).
    # For phenotype data with only one round, you can pass the round folder
    # directly OR a parent that contains one subdir; both are handled.
    subdirs = [p for p in sorted(root.iterdir()) if p.is_dir()]
    subdirs = [p for p in subdirs if p.name not in set(skip_dirs)]
    if not subdirs:
        # treat root itself as a single cycle/round folder
        subdirs = [root]

    for sub in subdirs:
        parsed = parse_cycle_dir(sub.name)
        if parsed is None:
            # not a cycle-style dir; skip or treat as round 1
            cycle_val, suffix = (1, "")
        else:
            cycle_val, suffix = parsed

        for nd2 in sorted(sub.glob("*.nd2")):
            parsed_fn = parse_filename(nd2.name)
            if parsed_fn is None:
                plans.append({
                    "old_path": nd2, "new_path": None, "ok": False,
                    "reason": "filename did not match pattern",
                    "plate": None, kind_key: cycle_val, "well": None,
                    "tile": None, "point_idx": None, "wells_list": None,
                })
                continue

            plate, wells_list, point_idx = parsed_fn
            well_slot = point_idx // tiles_per_well
            tile = point_idx % tiles_per_well

            if well_slot >= len(wells_list):
                plans.append({
                    "old_path": nd2, "new_path": None, "ok": False,
                    "reason": f"point_idx {point_idx} -> well_slot {well_slot} "
                              f"out of range for wells {wells_list} "
                              f"(tiles_per_well={tiles_per_well})",
                    "plate": plate, kind_key: cycle_val, "well": None,
                    "tile": tile, "point_idx": point_idx, "wells_list": wells_list,
                })
                continue

            well = wells_list[well_slot]
            new_name = build_new_name(plate, kind_key, cycle_val, well, tile, suffix)
            plans.append({
                "old_path": nd2,
                "new_path": nd2.with_name(new_name),
                "ok": True,
                "reason": "",
                "plate": plate,
                kind_key: cycle_val,
                "well": well,
                "tile": tile,
                "point_idx": point_idx,
                "wells_list": wells_list,
            })

    return plans


# ---------- reporting ----------

def summarize(plans, kind, n_examples=200, seed=0):
    """Print summary stats + a sample of renames so you can sanity-check."""
    kind_key = "cycle" if kind == "sbs" else "round"
    ok = [p for p in plans if p["ok"]]
    bad = [p for p in plans if not p["ok"]]

    print(f"\n=== SUMMARY ({kind}) ===")
    print(f"Total files seen: {len(plans)}")
    print(f"  matched:        {len(ok)}")
    print(f"  unmatched/err:  {len(bad)}")

    # tiles-per-well-per-(cycle,plate,well) check
    counts = defaultdict(int)
    for p in ok:
        counts[(p["plate"], p[kind_key], p["well"])] += 1
    if counts:
        cnt_vals = list(counts.values())
        print(f"  tiles per (plate,{kind_key},well): "
              f"min={min(cnt_vals)} max={max(cnt_vals)} "
              f"unique={sorted(set(cnt_vals))}")

    # first/last tile per well per cycle, to verify boundaries
    print("\n-- per (plate, cycle/round, well) tile range (first 20 groups) --")
    grp = defaultdict(list)
    for p in ok:
        grp[(p["plate"], p[kind_key], p["well"])].append(p["tile"])
    for i, (key, tiles) in enumerate(sorted(grp.items())[:20]):
        print(f"  {key}: n={len(tiles)} min_tile={min(tiles)} max_tile={max(tiles)}")

    # show errors
    if bad:
        print("\n-- ERRORS (first 20) --")
        for p in bad[:20]:
            print(f"  {p['old_path'].name}  --  {p['reason']}")

    # sample of renames
    rng = random.Random(seed)
    sample = rng.sample(ok, min(n_examples, len(ok)))
    sample.sort(key=lambda p: (p["plate"], p[kind_key], p["well"], p["tile"]))
    print(f"\n-- SAMPLE OF {len(sample)} RENAMES --")
    for p in sample:
        print(f"  {p['old_path'].parent.name}/{p['old_path'].name}")
        print(f"    -> {p['new_path'].name}")
        print(f"     (point_idx={p['point_idx']}, wells_list={p['wells_list']})")


# ---------- execution ----------

def apply_renames(plans, copy_instead=False):
    """Actually rename (or copy) the files. Use only after you've verified the plan."""
    done = 0
    for p in plans:
        if not p["ok"]:
            continue
        src, dst = p["old_path"], p["new_path"]
        if dst.exists():
            print(f"SKIP (dst exists): {dst}")
            continue
        if copy_instead:
            shutil.copy2(src, dst)
        else:
            src.rename(dst)
        done += 1
    print(f"Applied {done} renames (copy={copy_instead}).")


# ---------- CLI / example usage ----------

if __name__ == "__main__":
    # EDIT THESE TWO PATHS, then run:
    #  rename_nd2_files.py #or 
    #  python rename_nd2_files.py #if no chmod
    # First it only PLANS and prints examples. Set DO_RENAME=True when ready.

    SBS_DIR = "/home/jovyan/spatial-technology-platform/AB/6GP002/6GP002/plate_1/input_sbs"
    PH_DIR  = "/home/jovyan/spatial-technology-platform/AB/6GP002/6GP002/plate_1/input_ph"
    SKIP_DIRS = ["c13-no-primer"] #dirs to entirely skip renaming that live inside input_* parent dir

    SBS_TILES_PER_WELL = 349
    PH_TILES_PER_WELL  = 349   # change to 764 etc. as needed

    DO_RENAME = True  # flip to True only after you've eyeballed the plan

    sbs_plans = plan_renames(SBS_DIR, kind="sbs", tiles_per_well=SBS_TILES_PER_WELL, skip_dirs=SKIP_DIRS)
    summarize(sbs_plans, kind="sbs", n_examples=300)

    ph_plans  = plan_renames(PH_DIR,  kind="ph",  tiles_per_well=PH_TILES_PER_WELL)
    summarize(ph_plans,  kind="ph",  n_examples=300)

    if DO_RENAME:
        apply_renames(sbs_plans)
        apply_renames(ph_plans)
