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

class RayTransformerEncoderLayer(TransformerEncoderLayer):
    
    # def forward(self, x):
    #     x = x + self.attn(self.ln1(x))
    #     print(x.shape)
    #     x = self.ffn(self.ln2(x), identity=x)
    #     return x
    def forward(self, x, H, W):
        B, _, C = x.shape

        # Reshape x to (B, W, H, C)
        x = x.view(B, H, W, C).transpose(1, 2)

        # NOTE should be vectorized in a dedicated self attention module..
        # Apply transformer to each column independently
        out = []
        for i in range(W):
            x_ = x[:, i] + self.attn(self.ln1(x[:, i]))
            x_ = self.ffn(self.ln2(x_), identity=x_)
            out.append(x_)
            
        x = torch.stack(out)
        
        # (W, B, H, C)
        # Reshape x back to (B, H*W, C)
        x = x.transpose(0, 1).transpose(1, 2).reshape(B, H*W, C)
        return x

@MODELS.register_module()
class RayVisionTransformer(VisionTransformer):
    """Vision Transformer for Ultrasound image.
    
    computer intra and inter-ray attention
    """
    def __init__(self,
                 arch=dict(
                     embed_dims=256,
                     num_layers=6,
                     num_heads=8,
                     feedforward_channels=2048,
                 ),
                 img_size=224,
                 patch_size=(128, 3),
                 in_channels=1,
                 out_indices=-1,
                 drop_rate=0.,
                 drop_path_rate=0.,
                 qkv_bias=True,
                 norm_cfg=dict(type='LN', eps=1e-6),
                 final_norm=True,
                 out_type='featmap',
                 with_cls_token=False,
                 frozen_stages=-1,
                 interpolate_mode='bicubic',
                 layer_scale_init_value=0.,
                 patch_cfg=dict(),
                 layer_cfgs=dict(),
                 pre_norm=False,
                 init_cfg=None):
        BaseBackbone.__init__(self, init_cfg)
        
        essential_keys = {
            'embed_dims', 'num_layers', 'num_heads', 'feedforward_channels'
        }
        assert isinstance(arch, dict) and essential_keys <= set(arch), \
            f'Custom arch needs a dict with keys {essential_keys}'
        self.arch_settings = arch
        
        self.embed_dims = self.arch_settings['embed_dims']
        self.num_layers = self.arch_settings['num_layers']
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
        num_patches = self.patch_resolution[0] * self.patch_resolution[1]
        
        # Set out type
        if out_type not in self.OUT_TYPES:
            raise ValueError(f'Unsupported `out_type` {out_type}, please '
                             f'choose from {self.OUT_TYPES}')
        self.out_type = out_type

        # Set cls token
        if with_cls_token:
            self.cls_token = nn.Parameter(torch.zeros(1, 1, self.embed_dims))
        elif out_type != 'cls_token':
            self.cls_token = None
            self.num_extra_tokens = 0
        else:
            raise ValueError(
                'with_cls_token must be True when `out_type="cls_token"`.')
            
        # Set position embedding
        self.interpolate_mode = interpolate_mode
        self.pos_embed = nn.Parameter(
            torch.zeros(1, num_patches + self.num_extra_tokens,
                        self.embed_dims))
        self._register_load_state_dict_pre_hook(self._prepare_pos_embed)

        self.drop_after_pos = nn.Dropout(p=drop_rate)
        
        if isinstance(out_indices, int):
            out_indices = [out_indices]
        assert isinstance(out_indices, Sequence), \
            f'"out_indices" must by a sequence or int, ' \
            f'get {type(out_indices)} instead.'
        for i, index in enumerate(out_indices):
            if index < 0:
                out_indices[i] = self.num_layers + index
            assert 0 <= out_indices[i] <= self.num_layers, \
                f'Invalid out_indices {index}'
        self.out_indices = out_indices
            
        # stochastic depth decay rule
        dpr = np.linspace(0, drop_path_rate, self.num_layers)

        self.layers = ModuleList()
        if isinstance(layer_cfgs, dict):
            layer_cfgs = [layer_cfgs] * self.num_layers
        for i in range(self.num_layers):
            _layer_cfg = dict(
                embed_dims=self.embed_dims,
                num_heads=self.arch_settings['num_heads'],
                feedforward_channels=self.
                arch_settings['feedforward_channels'],
                layer_scale_init_value=layer_scale_init_value,
                drop_rate=drop_rate,
                drop_path_rate=dpr[i],
                qkv_bias=qkv_bias,
                norm_cfg=norm_cfg)
            _layer_cfg.update(layer_cfgs[i])
            self.layers.append(RayTransformerEncoderLayer(**_layer_cfg))
            self.layers.append(TransformerEncoderLayer(**_layer_cfg))
            
        self.frozen_stages = frozen_stages
        if pre_norm:
            self.pre_norm = build_norm_layer(norm_cfg, self.embed_dims)
        else:
            self.pre_norm = nn.Identity()

        self.final_norm = final_norm
        if final_norm:
            self.ln1 = build_norm_layer(norm_cfg, self.embed_dims)
        if self.out_type == 'avg_featmap':
            self.ln2 = build_norm_layer(norm_cfg, self.embed_dims)

        # freeze stages only when self.frozen_stages > 0
        if self.frozen_stages > 0:
            self._freeze_stages()
            
    def init_weights(self):
        super(VisionTransformer, self).init_weights()

        if not (isinstance(self.init_cfg, dict)
                and self.init_cfg['type'] == 'Pretrained'):
            if self.pos_embed is not None:
                print(self.pos_embed)
                quit()
                trunc_normal_(self.pos_embed, std=0.02)
            
            
    def forward(self, x):
        B = x.shape[0]
        x, patch_resolution = self.patch_embed(x)

        if self.cls_token is not None:
            # stole cls_tokens impl from Phil Wang, thanks
            cls_token = self.cls_token.expand(B, -1, -1)
            x = torch.cat((cls_token, x), dim=1)

        x = x + resize_pos_embed(
            self.pos_embed,
            self.patch_resolution,
            patch_resolution,
            mode=self.interpolate_mode,
            num_extra_tokens=self.num_extra_tokens)
        x = self.drop_after_pos(x)

        x = self.pre_norm(x)
        print(x.shape)
        print(self.pos_embed.shape)

        outs = []
        for i, layer in enumerate(self.layers):
            if isinstance(layer, RayTransformerEncoderLayer):
                x = layer(x, patch_resolution[0], patch_resolution[1])
                print(i, x.shape)
            else:
                x = layer(x)
                print(i, x.shape)

            if i == len(self.layers) - 1 and self.final_norm:
                x = self.ln1(x)

            if i in self.out_indices:
                outs.append(self._format_output(x, patch_resolution))

        return tuple(outs)


def test_transformer_encoder_layer():
    
    
    
    import torch

    # embed_dims = 256
    # num_heads = 8
    # feedforward_channels = 1024
    # batch_size = 2
    # seq_length = 128
    
    img_tensor = torch.rand(2, 1, 768, 768)
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
    
    transformer = RayVisionTransformer(img_size=768)
    y = transformer(img_tensor)
    print(y[-1].shape)
    print(transformer)

if __name__ == '__main__':
    test_transformer_encoder_layer()
