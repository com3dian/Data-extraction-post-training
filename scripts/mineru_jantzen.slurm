#!/bin/bash
#SBATCH --job-name=mineru-jantzen
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --chdir=/home/WUR/lu087/Github/Data-extraction-post-training
#SBATCH --output=outputs/mineru-%j.out
#SBATCH --error=outputs/mineru-%j.err

# Submit from the project root: sbatch scripts/mineru_jantzen.slurm
# Optionally process one folder: sbatch scripts/mineru_jantzen.slurm data/papers/jantzen
set -euo pipefail

input_dir="${1:-data/papers}"
output_dir="data/ready/jantzen_species_interaction"

if [[ ! -d "$input_dir" ]]; then
    printf 'Input directory does not exist: %s\n' "$input_dir" >&2
    exit 1
fi

# MinerU 2.7.6 does not recurse: batch each directory containing PDFs separately.
mapfile -d '' -t paper_dirs < <(
    find "$input_dir" -type f -iname '*.pdf' -printf '%h\0' | sort -zu
)

if (( ${#paper_dirs[@]} == 0 )); then
    printf 'No PDFs found under %s. Add or download the papers before submitting.\n' "$input_dir" >&2
    exit 1
fi

source /home/WUR/lu087/miniconda3/etc/profile.d/conda.sh
conda activate minerU

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export PYTHONUNBUFFERED=1

python - <<'PY'
import torch

if not torch.cuda.is_available():
    raise SystemExit("No CUDA GPU available. Submit this script to the GPU partition with sbatch.")
print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
PY

mkdir -p "$output_dir"

for paper_dir in "${paper_dirs[@]}"; do
    printf 'Processing PDFs in %s\n' "$paper_dir"
    srun --ntasks=1 mineru \
        -p "$paper_dir" \
        -o "$output_dir" \
        -b hybrid-auto-engine \
        -l en
done

printf 'MinerU run finished. Output: %s\n' "$output_dir"
