"""Fallback UniProt fetch for the barcode-standardization step.

Used when the live get_uniprot_data() REST call fails (UniProt's edge has been
dropping the default python-requests client signature since their 12-June-2026
deployment). Downloads the same reviewed dataset via curl -- a client signature
UniProt currently accepts -- keeps a persistent raw master copy, and writes a
post-processed file matching get_uniprot_data()'s output schema so that
standardize_barcode_design() can consume it unchanged.
"""

import subprocess
from pathlib import Path

import pandas as pd

# Identical query/fields to get_uniprot_data(), so the columns line up.
FIELDS = "accession,gene_names,cc_function,xref_kegg,xref_complexportal,xref_string"


def download_raw_uniprot(raw_path, species_id="9606"):
    """Download reviewed UniProt entries for `species_id` to `raw_path` via curl."""
    raw_path = Path(raw_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    url = (
        "https://rest.uniprot.org/uniprotkb/stream"
        f"?query=organism_id:{species_id}+AND+reviewed:true"
        f"&fields={FIELDS}&format=tsv"
    )
    # -L follow redirects, --fail error on HTTP>=400, --compressed for speed.
    result = subprocess.run(
        ["curl", "-sSL", "--fail", "--compressed", url, "-o", str(raw_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"curl download failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        raise RuntimeError(f"curl produced no data at {raw_path}")
    return raw_path


def postprocess_uniprot(raw_path):
    """Replicate get_uniprot_data()'s post-processing on a raw UniProt TSV."""
    df = pd.read_csv(raw_path, sep="\t", dtype=str, keep_default_na=False)

    # Build the entry link while the column is still named "Entry".
    df["Link"] = "https://www.uniprot.org/uniprotkb/" + df["Entry"] + "/entry"

    # Standardize column names, then rename/clean the function column.
    df.columns = df.columns.str.lower().str.replace(" ", "_")
    if "function_[cc]" in df.columns:
        df = df.rename(columns={"function_[cc]": "function"})
    if "function" in df.columns:
        df["function"] = df["function"].str.replace("FUNCTION: ", "", regex=False)

    return df


def fetch_uniprot_fallback(processed_path, raw_master_path, species_id="9606"):
    """curl-download + post-process UniProt data.

    Writes the persistent raw master to `raw_master_path` and the post-processed,
    schema-compatible table to `processed_path` (deletable). Returns the DataFrame.
    """
    download_raw_uniprot(raw_master_path, species_id=species_id)
    df = postprocess_uniprot(raw_master_path)
    Path(processed_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(processed_path, sep="\t", index=False)
    print(f"Fallback fetched {len(df)} entries -> {processed_path}")
    return df


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Fallback UniProt fetch via curl.")
    p.add_argument("--processed-out", required=True, help="Post-processed TSV path (UNIPROT_DATA_FP).")
    p.add_argument("--raw-out", required=True, help="Persistent raw master TSV path.")
    p.add_argument("--species", default="9606", help="NCBI taxonomy ID (default 9606).")
    args = p.parse_args()
    fetch_uniprot_fallback(args.processed_out, args.raw_out, species_id=args.species)