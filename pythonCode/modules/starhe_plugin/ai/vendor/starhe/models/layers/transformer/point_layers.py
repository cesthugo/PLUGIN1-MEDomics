from mmengine.model import base_module
import torch
from torch import nn


class LabelEncoder(base_module):

    def __init__(self, num_feats: int = 256,
                 num_classes: int = 80):
        super().__init__()

        self.label_embed = nn.Embedding(num_classes, num_feats)


    def forward(self, labels: torch.Tensor) -> torch.Tensor:
        """
        Forward propagation method for the LabelEncoder. This method generates
        embeddings for the given labels using an embedding layer.

        Args:
            labels (torch.Tensor): The input labels for which embeddings need to
                be generated. It should be a tensor of shape (batch_size,) or 
                (batch_size, num_objects) where `batch_size` is the number of samples 
                in the current batch and `num_objects` is the number of objects 
                in each sample. Each element in the tensor is an integer representing 
                the class label of an object.

        Returns:
            torch.Tensor: The output embeddings for the input labels. The output 
            tensor has shape (batch_size, num_feats) or (batch_size, num_objects, num_feats)
            where `num_feats` is the embedding dimension and is determined by 
            the `num_feats` parameter in the constructor of this class.
        """
        emb = self.label_embed.weight[labels]
        return emb
