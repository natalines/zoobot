#!/bin/bash
#SBATCH --job-name=dr5-rep                     # Job name
#SBATCH --output=dr5-rep_%A.log 
#SBATCH --mem=0                                     # "reserve all the available memory on each node assigned to the job"
#SBATCH --no-requeue                                    # Do not resubmit a failed job
#SBATCH --time=23:00:00                                # Time limit hrs:min:sec
#SBATCH --constraint=A100 
#SBATCH --exclusive   # only one task per node
#SBATCH --ntasks 1
#SBATCH --cpus-per-task=24
#SBATCH --exclude compute-0-7,compute-0-5
pwd; hostname; date

nvidia-smi

# export WANDB_CACHE_DIR=/share/nas2/walml/WANDB_CACHE_DIR

ZOOBOT_DIR=/share/nas2/walml/repos/zoobot
PYTHON=/share/nas2/walml/miniconda3/envs/zoobot/bin/python

RESULTS_DIR=/share/nas2/walml/repos/gz-decals-classifiers/results

ARCHITECTURE='efficientnet'
BATCH_SIZE=512
GPUS=2
# requires --mixed-precision to be set on A100s

# ARCHITECTURE='resnet_detectron'
# BATCH_SIZE=256
# GPUS=2
# # doesn't need mixed precision, but can use anyway for consistency

# ARCHITECTURE='resnet_torchvision'
# BATCH_SIZE=256
# GPUS=2
## doesn't need mixed precision, but can use anyway for consistency

# be sure to add _color if appropriate
EXPERIMENT_DIR=$RESULTS_DIR/pytorch/dr5/${ARCHITECTURE}_dr5_pytorch_color

$PYTHON /share/nas2/walml/repos/zoobot/replication/pytorch/train_model_on_decals_dr5_splits.py \
    --experiment-dir $EXPERIMENT_DIR \
    --architecture $ARCHITECTURE \
    --resize-size 224 \
    --batch-size 512 \
    --gpus 2 \
    --mixed-precision \
    --color

