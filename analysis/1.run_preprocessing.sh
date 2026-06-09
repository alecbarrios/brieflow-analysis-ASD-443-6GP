#!/bin/bash

# Run only the preprocess rules
snakemake --use-conda --cores all \
    --snakefile "../brieflow/workflow/Snakefile" \
    --configfile "screen.yaml" \
    --rerun-triggers mtime \
    --until all_preprocess #-n flag for dry run



