#!/bin/bash
# run with ./benchmarks/pytorch/run_benchmarks.sh
# inspired by https://www.osc.edu/resources/getting_started/howto/howto_submit_multiple_jobs_using_parameters

TRAIN_JOB=/share/nas2/walml/repos/zoobot/benchmarks/pytorch/run_dataset_benchmark.sh
SEED=$RANDOM

# debug mode
sbatch --job-name=dr5_py_debug_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_decals_dr5,GPUS=1,SEED=$SEED,DEBUG_STRING='--debug' $TRAIN_JOB

# minimal hardware - 1 gpu, no mixed precision
# (not specifying a string will default to not doing it)
# sbatch --job-name=dr5_py_min_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_decals_dr5,GPUS=1,SEED=$SEED $TRAIN_JOB

# otherwise full hardware (standard setup) - 2 gpus, mixed precision
# sbatch --job-name=dr5_py_gr_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_decals_dr5,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB
# sbatch --job-name=dr5_py_co_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_decals_dr5,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,COLOR_STRING=--color,SEED=$SEED $TRAIN_JOB

# new - all galaxies
# sbatch --job-name=evo_py_gr_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_evo,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB

# and in color with resnet / no MP, for specific project
# might need batch size = 128 to allow for no MP
# sbatch --job-name=evo_py_gr_$SEED --export=ARCHITECTURE=resnet_torchvision,BATCH_SIZE=256,RESIZE_AFTER_CROP=224,DATASET=gz_evo,COLOR_STRING=--color,GPUS=2,SEED=$SEED $TRAIN_JOB

# sbatch --job-name=evo_py_gr_128px_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=128,DATASET=gz_evo,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB
# sbatch --job-name=evo_py_c_128px_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=128,DATASET=gz_evo,COLOR_STRING=--color,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB
# sbatch --job-name=evo_py_gr_64px_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=64,DATASET=gz_evo,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB
# sbatch --job-name=evo_py_c_64px_$SEED --export=ARCHITECTURE=efficientnet_b0,BATCH_SIZE=256,RESIZE_AFTER_CROP=64,DATASET=gz_evo,COLOR_STRING=--color,MIXED_PRECISION_STRING=--mixed-precision,GPUS=2,SEED=$SEED $TRAIN_JOB

echo 'PyTorch jobs submitted'
