#!/bin/bash

# Run the SBS/phenotype rules
snakemake --use-conda --cores all \
    --snakefile "../brieflow/workflow/Snakefile" \
    --configfile "screen.yaml" \
    --rerun-triggers mtime \
    --until all_sbs -n #all_phenotype 
