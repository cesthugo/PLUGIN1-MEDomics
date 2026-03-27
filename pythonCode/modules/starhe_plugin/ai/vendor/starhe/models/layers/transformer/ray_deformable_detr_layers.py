# Copyright (c) OpenMMLab. All rights reserved.
from typing import Optional, Tuple, Union

import torch
from mmcv.cnn import build_norm_layer
from mmcv.cnn.bricks.transformer import FFN, MultiheadAttention
from mmcv.ops import MultiScaleDeformableAttention
from mmengine.model import ModuleList
from torch import Tensor, nn

from mmdet.models.layers.transformer.detr_layers import (DetrTransformerDecoder, DetrTransformerDecoderLayer,
                          DetrTransformerEncoder, DetrTransformerEncoderLayer)
from mmdet.models.layers.transformer.deformable_detr_layers import (DeformableDetrTransformerEncoder, DeformableDetrTransformerEncoderLayer)
from mmdet.models.layers.transformer.utils import inverse_sigmoid

class RayDetrTransformerEncoderLayer(DetrTransformerEncoderLayer):
    """Encoder layer of Ray DETR.
    deformable attention is not used as we want a dense attention intra ray.
    In addition, handling the reference points would be a pain.
    """
    def _init_layers(self) -> None:
        """Initialize self-attention, FFN, and normalization."""
        self.self_attn = MultiheadAttention(**self.self_attn_cfg)
        self.embed_dims = self.self_attn.embed_dims
        # self.ffn = FFN(**self.ffn_cfg)
        norms_list = [
            build_norm_layer(self.norm_cfg, self.embed_dims)[1]
            for _ in range(1)
        ]
        self.norms = ModuleList(norms_list)

    def forward(self, query: Tensor, query_pos: Tensor,
                key_padding_mask: Tensor, n_ray: int=6, **kwargs) -> Tensor:
        """Forward function of an encoder layer.

        Args:
            query (Tensor): The input query, has shape (bs, num_queries, dim).
            query_pos (Tensor): The positional encoding for query, with
                the same shape as `query`.
            key_padding_mask (Tensor): The `key_padding_mask` of `self_attn`
                input. ByteTensor. has shape (bs, num_queries).
        Returns:
            Tensor: forwarded results, has shape (bs, num_queries, dim).
        """
        # NOTE adapted ro rune per patch of same ray
        # 1. recover n_ray dim: (bs, num_queries, dim) -> (bs, num_queries, dim) -> (bs, num_queries/n_ray, n_ray, dim
        # 2. iter to do attenton per n_ray
        
        B, N, C = query.shape

        # 1. (bs, num_queries, dim) -> (bs, num_queries/n_ray, n_ray, dim)
        query = query.view(B, N//n_ray, n_ray, C)
        query_pos = query_pos.view(B, N//n_ray, n_ray, C)
        key_padding_mask = key_padding_mask.view(B, N//n_ray, n_ray)
        
        # 2. iter to do attenton per n_ray
        out = []
        for ray in range(n_ray):
            _query = self.self_attn(
                query=query[:, :, ray, :],
                key=query[:, :, ray, :],
                value=query[:, :, ray, :],
                query_pos=query_pos[:, :, ray, :],
                key_pos=query_pos[:, :, ray, :],
                key_padding_mask=key_padding_mask[:, :, ray],
                **kwargs)
            out.append(_query)
            
        # Stack the list of tensors along a new dimension and then flatten the last two dimensions
        query = torch.stack(out, dim=2).view(B, N, C)
        
        # stacked_query = torch.stack(out, dim=2)
        # query = stacked_query.permute(0, 2, 1, 3).contiguous().view(B, N, C)

        query = self.norms[0](query)

        return query

class RayDeformableDetrTransformerEncoder(DeformableDetrTransformerEncoder):
    """Transformer encoder of Ray Deformable DETR."""
    
    # mode = alternate, chained
    
    def _init_layers(self) -> None:
        """Initialize encoder layers."""
        layer_def_cfg = self.layer_cfg.deepcopy()
        layer_def_cfg["self_attn_cfg"]["num_levels"] = 1

        self.layers = ModuleList([
            RayDetrTransformerEncoderLayer(**self.layer_cfg)
            if i%2==0 else DeformableDetrTransformerEncoderLayer(**layer_def_cfg)
            for i in range(self.num_layers*2)
        ])
        self.embed_dims = self.layers[0].embed_dims
        
    # def forward(self, query: Tensor, query_pos: Tensor,
    #             key_padding_mask: Tensor, n_ray: int, **kwargs) -> Tensor:
    #     """Forward function of encoder.

    #     Args:
    #         query (Tensor): Input queries of encoder, has shape
    #             (bs, num_queries, dim).
    #         query_pos (Tensor): The positional embeddings of the queries, has
    #             shape (bs, num_queries, dim).
    #         key_padding_mask (Tensor): The `key_padding_mask` of `self_attn`
    #             input. ByteTensor, has shape (bs, num_queries).

    #     Returns:
    #         Tensor: Has shape (bs, num_queries, dim) if `batch_first` is
    #         `True`, otherwise (num_queries, bs, dim).
    #     """
    #     for layer in self.layers:
    #         query = layer(query, query_pos, key_padding_mask, **kwargs)
    #     return query