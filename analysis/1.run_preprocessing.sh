#!/bin/bash

# Run only the preprocess rules 
# For a dry run: bash 1.run_preprocessing.sh -n
snakemake --use-conda --cores all \
    --snakefile "../brieflow/workflow/Snakefile" \
    --configfile "screen.yaml" \
    --rerun-triggers mtime code input params software-env \
    --until all_preprocess 