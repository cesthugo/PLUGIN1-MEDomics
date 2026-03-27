import torch.nn as nn
import torch
import numpy as np
from typing import Sequence
from mmpretrain.models.utils.helpers import is_tracing, to_2tuple, to_3tuple, to_4tuple, to_ntuple

from mmengine.model import BaseModule, ModuleList

from mmpretrain.registry import MODELS
from mmpretrain.models.backbones.base_backbone import BaseBackbone

from mmpretrain.models.backbones.vision_transformer import TransformerEncoderLayer, VisionTransformer
from mmpretrain.models.utils import (MultiheadAttention, SwiGLUFFNFused, build_norm_layer,
                     resize_pos_embed, to_2tuple)

from starhe.cnn.bricks.transformer import test_NonSquarePatchEmbed, NonSquarePatchEmbed

@MODELS.register_module()
class RayProjector(BaseBackbone):
    """Non square patch projector
    Vision Transformer for Ultrasound image.
    
    used to compute intra and inter-ray attention in encoder
    """
    def __init__(self,
                 embed_dims: int = 256,
                 img_size: int = 224,
                 patch_size=(128, 3),
                 in_channels=1,
                 patch_cfg=dict(),
                 pre_norm=False,
                 init_cfg=None):
        BaseBackbone.__init__(self, init_cfg)
        
        self.embed_dims = embed_dims
        self.img_size = to_2tuple(img_size)

        # Set patch embedding
        _patch_cfg = dict(
            in_channels=in_channels,
            input_size=img_size,
            embed_dims=self.embed_dims,
            conv_type='Conv2d',
            kernel_size=patch_size,
            stride=patch_size,
            bias=not pre_norm,  # disable bias if pre_norm is used(e.g., CLIP)
        )
        _patch_cfg.update(patch_cfg)
        self.patch_embed = NonSquarePatchEmbed(**_patch_cfg)
        self.patch_resolution = self.patch_embed.init_out_size

    def forward(self, x, spatial_reshape=True):
        x, patch_resolution = self.patch_embed(x, ray_grouping=spatial_reshape)
        return (x,)
    
def test_transformer_encoder_layer():
    
    
    
    import torch

    # embed_dims = 256
    # num_heads = 8
    # feedforward_channels = 1024
    # batch_size = 2
    # seq_length = 128
    
    img_tensor = torch.rand(2, 1, 128*10, 128*10)
    # out, out_size = test_NonSquarePatchEmbed(img_tensor)

    # # initialize TransformerEncoderLayer
    # intraRayEncoder_layer = RayTransformerEncoderLayer(
    #     embed_dims=embed_dims,
    #     num_heads=num_heads,
    #     feedforward_channels=feedforward_channels
    # )
    # RayEncoder_layer = TransformerEncoderLayer(
    #     embed_dims=embed_dims,
    #     num_heads=num_heads,
    #     feedforward_channels=feedforward_channels
    # )

    # # forward pass
    # x = intraRayEncoder_layer(out, out_size[0], out_size[1])
    # print('intraRayEncoder Output shape:', x.shape)
    
    
    # y = RayEncoder_layer(x)

    # # print the output shape
    # print('RayEncoder Output shape:', y.shape)
    
    transformer = RayProjector(img_size=128*10)
    x, patch_resolution = transformer(img_tensor)
    print(x.shape)
    print(patch_resolution)
    print(transformer)

if __name__ == '__main__':
    test_transformer_encoder_layer()