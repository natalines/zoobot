import logging

import torch
from torch import nn
import pytorch_lightning as pl
from torchmetrics import Accuracy

from zoobot.pytorch.estimators import efficientnet_standard, efficientnet_custom, resnet_torchvision_custom, custom_layers
from zoobot.pytorch.training import losses


class GenericLightningModule(pl.LightningModule):
    """
    All Zoobot models use the lightningmodule API and so share this structure
    The funcs below this class define e.g. the model itself, the loss function, etc.

    Use like
        lightning_model = GenericLightningModule(plain_pytorch_model, loss_func)
    """

    def __init__(
        self,
        *args,  # to be saved as hparams
        ):
        super().__init__()
        self.save_hyperparameters()  # saves all args by default

        self.setup_metrics()


    def setup_metrics(self):
        # these are ignored unless output dim = 2
        self.train_accuracy = Accuracy()
        self.val_accuracy = Accuracy()
        self.log_on_step = False
        # self.log_on_step is useful for debugging, but slower - best when log_every_n_steps is fairly large


    def forward(self, x):
        return self.model.forward(x)
    
    def make_step(self, batch, batch_idx, step_name):
        x, labels = batch
        predictions = self(x)  # by default, these are Dirichlet concentrations

        # true, pred convention as with sklearn
        # self.loss_func returns shape of (galaxy, question), mean to ()
        multiq_loss = self.loss_func(predictions, labels, sum_over_questions=False)
        # if hasattr(self, 'schema'):
        self.log_loss_per_question(multiq_loss, prefix=step_name)

        # sum over questions and take a per-device mean
        # for DDP strategy, batch size is constant (batches are not divided, data pool is divided)
        # so this will be the global per-example mean
        loss = torch.mean(torch.sum(multiq_loss, axis=1))
      
        return {'loss': loss, 'predictions': predictions, 'labels': labels}

    def training_step(self, batch, batch_idx):
        return self.make_step(batch, batch_idx, step_name='train')

    def training_step_end(self, outputs):
        self.log_outputs(outputs, step_name='train')

    def validation_step(self, batch, batch_idx):
        return self.make_step(batch, batch_idx, step_name='validation')

    def validation_step_end(self, outputs):
        self.log_outputs(outputs, step_name='validation')

    def test_step(self, batch, batch_idx):
        return self.make_step(batch, batch_idx, step_name='test')

    def test_step_end(self, outputs):
         self.log_outputs(outputs, step_name='test')

    
    def predict_step(self, batch, batch_idx, dataloader_idx=0):
        # https://pytorch-lightning.readthedocs.io/en/stable/common/lightning_module.html#inference
        # this calls forward, while avoiding the need for e.g. model.eval(), torch.no_grad()
        # x, y = batch  # would be usual format, but here, batch does not include labels
        return self(batch)


    def configure_optimizers(self):
        return torch.optim.Adam(self.parameters(), lr=self.learning_rate, betas=self.betas)  


    def log_outputs(self, outputs, step_name):
        self.log("{}/epoch_loss".format(step_name), outputs['loss'], on_epoch=True, on_step=False,prog_bar=True, logger=True)
        if self.log_on_step:
            # seperate call to allow for different name, to allow for consistency with TF.keras auto-names
            self.log(
                "{}/step_loss".format(step_name), outputs['loss'], on_epoch=False, on_step=True, prog_bar=True, logger=True)
        if outputs['predictions'].shape[1] == 2:  # will only do for binary classifications
            # logging.info(predictions.shape, labels.shape)
            self.log(
                "{}_accuracy".format(step_name), self.train_accuracy(outputs['predictions'], torch.argmax(outputs['labels'], dim=1, keepdim=False)), prog_bar=True)


    def log_loss_per_question(self, multiq_loss, prefix):
        # log questions individually
        # TODO need schema attribute or similar to have access to question names, this will do for now
        for question_n in range(multiq_loss.shape[1]):
            self.log(f'{prefix}/epoch_questions/question_{question_n}_loss:0', torch.mean(multiq_loss[:, question_n]), on_epoch=True, on_step=False)


class ZoobotLightningModule(GenericLightningModule):

    # lightning only supports checkpoint loading / hparams which are not fancy classes
    # therefore, can't nicely wrap these arguments. So it goes.
    # override GenericLightningModule above, only this init
    def __init__(
        self,
        output_dim,
        question_index_groups,
        weights_loc=None,
        include_top=True,
        channels=1,
        use_imagenet_weights=False,
        always_augment=True,
        dropout_rate=0.2,
        drop_connect_rate=0.2,
        architecture_name="efficientnet",  # recently changed from model_architecture
        learning_rate=5e-4,
        betas=(0.9, 0.999)
        ):

        # now, finally, can pass only standard variables as hparams to save
        super().__init__(
            output_dim,
            question_index_groups,
            channels,
            always_augment,
            dropout_rate,
            drop_connect_rate,
            architecture_name  # TODO can add any more specific params if needed
        )

        logging.info('Generic __init__ complete - moving to Zoobot __init__')

        # set attributes for learning rate, betas, used by self.configure_optimizers()
        self.learning_rate = learning_rate
        self.betas = betas

        # define model architecture
        get_architecture, representation_dim = select_base_architecture_func_from_name(architecture_name)

        self.loss_func = get_loss_func(question_index_groups)

        self.model = get_plain_pytorch_zoobot_model(
            output_dim=output_dim,
            weights_loc=weights_loc,
            include_top=include_top,
            channels=channels,
            use_imagenet_weights=use_imagenet_weights,
            always_augment=always_augment,
            dropout_rate=dropout_rate,
            drop_connect_rate=drop_connect_rate,
            get_architecture=get_architecture,
            representation_dim=representation_dim
        )

        logging.info('Zoobot __init__ complete')


    

def get_loss_func(question_index_groups):
    # This just adds schema.question_index_groups as an arg to the usual (labels, preds) loss arg format
    # Would use lambda but multi-gpu doesn't support as lambda can't be pickled

    # accept (labels, preds), return losses of shape (batch, question)
    def loss_func(preds, labels, sum_over_questions=False):
        # pytorch convention is preds, labels for loss func
        # my and sklearn convention is labels, preds for loss func

        # multiquestion_loss returns loss of shape (batch, question)
        # torch.sum(multiquestion_loss, axis=1) gives loss of shape (batch). Equiv. to non-log product of question likelihoods.
        multiq_loss = losses.calculate_multiquestion_loss(labels, preds, question_index_groups)
        if sum_over_questions:
            return torch.sum(multiq_loss, axis=1)
        else:
            return multiq_loss
    return loss_func


def select_base_architecture_func_from_name(base_architecture):
    # efficientnet variants are designed for specific resolutions
    # they will work with any reasonable res, though
    # https://github.com/tensorflow/tpu/issues/390#issuecomment-1237211990
    if base_architecture == 'efficientnet':  # 224px
        logging.info('Efficientnet variant not specified - using b0 by default')
        get_architecture = efficientnet_standard.efficientnet_b0
        representation_dim = 1280
    elif base_architecture == 'efficientnet_b2' or base_architecture == 'efficientnetb2':  # 260px
        get_architecture = efficientnet_standard.efficientnet_b2
        representation_dim = 1408
    elif base_architecture == 'efficientnet_b4' or base_architecture == 'efficientnetb4':  # 380px
        get_architecture = efficientnet_standard.efficientnet_b4
        representation_dim = 1792
    elif base_architecture == 'resnet_detectron':
        # only import if needed, as requires gpu version of pytorch or throws cuda errors e.g.
        # from detectron2 import _C -> ImportError: libtorch_cuda_cu.so: cannot open shared object file: No such file or directory
        from zoobot.pytorch.estimators import resnet_detectron2_custom
        get_architecture = resnet_detectron2_custom.get_resnet
        representation_dim = 2048
    elif base_architecture == 'resnet_torchvision':
        get_architecture = resnet_torchvision_custom.get_resnet  # only supports color
        representation_dim = 2048
    else:
        raise ValueError(
            'Model architecture not recognised: got model={}, expected one of [efficientnet, efficinetnet_b2, resnet_detectron, resnet_torchvision]'.format(base_architecture))

    return get_architecture,representation_dim



def get_plain_pytorch_zoobot_model(
    output_dim,
    weights_loc=None,
    include_top=True,
    channels=1,
    use_imagenet_weights=False,
    always_augment=True,
    dropout_rate=0.2,
    drop_connect_rate=0.2,
    get_architecture=efficientnet_standard.efficientnet_b0,
    representation_dim=1280  # or 2048 for resnet
    ) -> nn.Sequential:
    """
    Create a trainable efficientnet model.
    First layers are galaxy-appropriate augmentation layers - see :meth:`zoobot.estimators.define_model.add_augmentation_layers`.
    Expects single channel image e.g. (300, 300, 1), likely with leading batch dimension.

    Optionally (by default) include the head (output layers) used for GZ DECaLS.
    Specifically, global average pooling followed by a dense layer suitable for predicting dirichlet parameters.
    See ``efficientnet_custom.custom_top_dirichlet``

    Args:
        output_dim (int): Dimension of head dense layer. No effect when include_top=False.
        input_size (int): Length of initial image e.g. 300 (asmeaned square)
        crop_size (int): Length to randomly crop image. See :meth:`zoobot.estimators.define_model.add_augmentation_layers`.
        resize_size (int): Length to resize image. See :meth:`zoobot.estimators.define_model.add_augmentation_layers`.
        weights_loc (str, optional): If str, load weights from efficientnet checkpoint at this location. Defaults to None.
        include_top (bool, optional): If True, include head used for GZ DECaLS: global pooling and dense layer. Defaults to True.
        expect_partial (bool, optional): If True, do not raise partial match error when loading weights (likely for optimizer state). Defaults to False.
        channels (int, default 1): Number of channels i.e. C in NHWC-dimension inputs. 

    Returns:
        torch.nn.Sequential: trainable efficientnet model including augmentations and optional head
    """

    modules_to_use = []

    effnet = get_architecture(
        input_channels=channels,
        # TODO this arg will break resnet, at the moment - needs tweaking
        # don't adjust dropout_rate= here, that's the effnet head, which I replace below anyway. Use below instead.
        stochastic_depth_prob=drop_connect_rate,  # this is used though! It's about skipping *layers* inside the main model.
        use_imagenet_weights=use_imagenet_weights,
        include_top=False,  # no final three layers: pooling, dropout and dense
    )
    modules_to_use.append(effnet)

    if include_top:
        assert output_dim is not None
        # modules_to_use.append(tf.keras.layers.GlobalAveragePooling2D())  # included already in standard effnet in pytorch version - "AdaptiveAvgPool2d"
        # if always_augment:  # TODO this is terrible naming, need to change!
        # logging.info('Using test-time dropout')
        # dropout_layer = custom_layers.PermaDropout
        # else:
        logging.info('Not using test-time dropout')
        dropout_layer = torch.nn.Dropout
        modules_to_use.append(dropout_layer(dropout_rate))
        # TODO could optionally add a bottleneck layer here
        modules_to_use.append(efficientnet_custom.custom_top_dirichlet(representation_dim, output_dim))

    if weights_loc is not None:
        raise NotImplementedError
    #     load_weights(model, weights_loc, expect_partial=expect_partial)

    model = nn.Sequential(*modules_to_use)

    return model
