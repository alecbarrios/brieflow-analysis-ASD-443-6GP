#!/bin/bash

# Run the SBS/phenotype rules
snakemake --use-conda --cores all \
    --snakefile "../brieflow/workflow/Snakefile" \
    --configfile "screen.yaml" \
    --rerun-triggers mtime code input software-env params \
    --until all_sbs all_phenotype #-n dry run
