import os
import logging
import contextlib
from sklearn.model_selection import train_test_split

import tensorflow as tf

from zoobot.tensorflow.training import training_config, losses, custom_metrics
from zoobot.tensorflow.estimators import define_model
from galaxy_datasets.tensorflow import get_image_dataset, add_transforms_to_dataset
from galaxy_datasets.transforms import default_transforms


def train(
    # absolutely crucial arguments
    save_dir,  # save model here
    schema,  # answer these questions
    # input data - specify *either* catalog (to be split) or the splits themselves
    catalog=None,
    train_catalog=None,
    val_catalog=None,
    test_catalog=None,
    # model training parameters
    architecture_name='efficientnet',  # only EfficientNet is currenty implemented
    batch_size=128,
    dropout_rate=0.2,
    # TODO drop_connect_rate not implemented
    epochs=1000,
    patience=8,
    # augmentation parameters
    color=False,
    requested_img_size=None,
    crop_scale_bounds=(0.7, 0.8),
    crop_ratio_bounds=(0.9, 1.1),
    resize_after_crop=224,
    always_augment=False,
    # hardware parameters
    mixed_precision=True,
    gpus=2,
    eager=False,  # tf-specific. Enable eager mode. Set True for easier debugging but slower training
    # replication parameters
    random_state=42  # TODO not yet implemented except for catalog split (not used in benchmarks)
) -> tf.keras.Model:

    # get the image paths, divide into train/val/test if not explicitly passed above
    if catalog is not None:
        assert train_catalog is None
        assert val_catalog is None
        assert test_catalog is None
        train_catalog, hidden_catalog = train_test_split(catalog, train_size=0.7, random_state=random_state)
        val_catalog, test_catalog = train_test_split(hidden_catalog, train_size=1./3., random_state=random_state)
    else:
        assert catalog is None
        assert len(train_catalog) > 0
        assert len(val_catalog) > 0
        assert len(test_catalog) > 0

    # a bit awkward, but I think it is better to have to specify you def. want color than that you def want greyscale
    greyscale = not color
    if greyscale:
        logging.info('Converting images to greyscale before training')
        channels = 1
    else:
        logging.warning(
            'Training on color images, not converting to greyscale')
        channels = 3

    assert save_dir is not None
    if not os.path.isdir(save_dir):
        os.mkdir(save_dir)

    if gpus > 1:
        logging.info('Using distributed mirrored strategy')
        strategy = tf.distribute.MirroredStrategy()  # one machine, one or more GPUs
        # strategy = tf.distribute.MultiWorkerMirroredStrategy()  # one or more machines. Not tested - you'll need to set this up for your own cluster.
        context_manager = strategy.scope()
        logging.info('Replicas: {}'.format(strategy.num_replicas_in_sync))
        # each GPU will calculate loss (hence gradients) for that device's sub-batch
        # within that sub-batch, loss uses tf.keras.reduction setting, which was SUM
        # so per-device loss would be 2x smaller with 2 devices (smaller b)
        # unclear if loss is averaged or summed?
        # gradients are summed across devices
        #

          # MirroredStrategy causes loss to decrease by factor of num_gpus.
          # Multiply by gpu_loss_factor to keep loss consistent.
        assert strategy.num_replicas_in_sync == gpus
        # gpu_loss_factor = strategy.num_replicas_in_sync
    else:
        logging.info('Using single or no GPU, not distributed')
        # does nothing, just a convenience for clean code
        context_manager = contextlib.nullcontext()
        # gpu_loss_factor = 1  # do nothing

    train_image_paths = list(train_catalog['file_loc'])
    val_image_paths = list(val_catalog['file_loc'])
    test_image_paths = list(test_catalog['file_loc'])

    # format is [{label_col: 0, label_col: 12}, {label_col: 3, label_col: 14}, ...]
    # train_labels = train_catalog[schema.label_cols].to_dict(orient='records')
    # val_labels = val_catalog[schema.label_cols].to_dict(orient='records')
    # test_labels = test_catalog[schema.label_cols].to_dict(orient='records')
    train_labels = train_catalog[schema.label_cols].values
    val_labels = val_catalog[schema.label_cols].values
    test_labels = test_catalog[schema.label_cols].values

    logging.info('Example path: {}'.format(train_image_paths[0]))
    logging.info('Example labels: {}'.format(train_labels[0]))

    train_dataset = get_image_dataset(
        train_image_paths, labels=train_labels, requested_img_size=requested_img_size, check_valid_paths=True, greyscale=greyscale
    )
    val_dataset = get_image_dataset(
        val_image_paths, labels=val_labels, requested_img_size=requested_img_size, check_valid_paths=True, greyscale=greyscale
    )
    test_dataset = get_image_dataset(
        test_image_paths, labels=test_labels, requested_img_size=requested_img_size, check_valid_paths=True, greyscale=greyscale
    )

    # specify augmentations
    train_transforms = default_transforms(
        # no need to specify greyscale here
        # tensorflow will greyscale in get_image_dataset i.e. on load, while pytorch doesn't so needs specifying here
        # may refactor to avoid inconsistency 
        crop_scale_bounds=crop_scale_bounds,
        crop_ratio_bounds=crop_ratio_bounds,
        resize_after_crop=resize_after_crop
    )
    # TODO should be clearer, not magic 1's (e.g. default_train_transforms, etc.)
    # TODO if always_augment, use train augments at test time (TODO rename this too)
    inference_transforms = default_transforms(
        crop_scale_bounds=(1., 1.),
        crop_ratio_bounds=(1., 1.),
        resize_after_crop=resize_after_crop
    )
    # apply augmentations
    train_dataset = add_transforms_to_dataset(train_dataset, train_transforms)
    # if always_augment:
        # logging.warning('always_augment=True, applying augmentations to val and test datasets')
    val_dataset = add_transforms_to_dataset(val_dataset, inference_transforms)
    test_dataset = add_transforms_to_dataset(test_dataset, inference_transforms)

    # batch, shuffle, prefetch
    train_dataset = train_dataset.shuffle(5000).batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)
    val_dataset = val_dataset.batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)
    test_dataset = test_dataset.batch(batch_size)

    with context_manager:

        if mixed_precision:
            logging.info(
                'Using mixed precision. \
                Note that this is a global setting (why, tensorflow, why...) \
                and so may affect any future code'
            )
            tf.keras.mixed_precision.set_global_policy('mixed_float16')

        # TODO use architecture_name here

        model = define_model.get_model(
            output_dim=len(schema.label_cols),
            input_size=resize_after_crop,
            channels=channels,
            dropout_rate=dropout_rate
        )

        # reduction=None will give per-example loss. Still summed (probability-multiplied) across questions.
        multiquestion_loss = losses.get_multiquestion_loss(
            schema.question_index_groups,
            reduction=tf.keras.losses.Reduction.NONE
        )
        # SUM reduction over loss, cannot divide by batch size on replicas when distributed training
        # so do it here instead
        # def loss(x, y): return gpu_loss_factor * multiquestion_loss(x, y) / batch_size

        # TF actually has a built-in for this which just automatically gets num_replicas and does 
        """
        per_replica_batch_size = per_example_loss.shape[0]
        global_batch_size = per_replica_batch_size * num_replicas
        return reduce_sum(per_example_loss) / global_batch_size
        """
        def loss(x, y): return tf.nn.compute_average_loss(per_example_loss=multiquestion_loss(x, y))  


        # be careful to define this within the context_manager, so it is also mirrored if on multi-gpu
        extra_metrics = [
            # custom_metrics.LossPerQuestion(
            #     name='loss_per_question',
            #     question_index_groups=schema.question_index_groups
            # )
        ]

    model.compile(
        loss=loss,
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001, beta_1=0.9, beta_2=0.999),
        metrics=extra_metrics
    )
    model.summary()

    trainer = training_config.Trainer(
        # parameters for how to train e.g. epochs, patience
        log_dir=save_dir,
        epochs=epochs,
        patience=patience
    )

    best_trained_model = trainer.fit(
        model,
        train_dataset,
        val_dataset,
        eager=eager,
        verbose=1
    )

    # unsure if this will work
    best_trained_model.evaluate(test_dataset)

    return best_trained_model
