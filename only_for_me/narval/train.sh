#!/bin/bash
#SBATCH --mem-per-cpu 4G
#SBATCH --nodes=1
#SBATCH --time=2:50:0  
#SBATCH --tasks-per-node=4
#SBATCH --cpus-per-task=12
#SBATCH --gres=gpu:a100:4

nvidia-smi

PYTHON=/home/walml/envs/zoobot39_dev/bin/python
# source ~/envs/zoobot39_dev/bin/activate

# mkdir $SLURM_TMPDIR/cache
mkdir /tmp/cache

export NCCL_BLOCKING_WAIT=1  #Set this environment variable if you wish to use the NCCL backend for inter-GPU communication.
# export MASTER_ADDR=$(hostname) #Store the master node’s IP address in the MASTER_ADDR environment variable.
# echo "r$SLURM_NODEID master: $MASTER_ADDR"
# echo "r$SLURM_NODEID Launching python script"

REPO_DIR=/project/def-bovy/walml/zoobot
srun $PYTHON $REPO_DIR/only_for_me/narval/train.py \
    --save-dir $REPO_DIR/only_for_me/narval/debug_models \
    --batch-size 256 \
    --color --wandb --mixed-precision
# srun python $SLURM_TMPDIR/zoobot/only_for_me/narval/finetune.py

    # --architecture maxvit_small_tf_224 \
