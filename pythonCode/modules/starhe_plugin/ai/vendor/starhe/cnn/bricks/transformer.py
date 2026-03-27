from mmengine.model import BaseModule, ModuleList, Sequential

from mmcv.cnn import (Linear, build_activation_layer, build_conv_layer,
                      build_norm_layer)

from mmcv.cnn.bricks.transformer import AdaptivePadding
from mmengine.utils import to_2tuple

class NonSquarePatchEmbed(BaseModule):
    """Image to Patch Embedding.

    We use a conv layer to implement PatchEmbed.

    Args:
        in_channels (int): The num of input channels. Default: 3
        embed_dims (int): The dimensions of embedding. Default: 768
        conv_type (str): The type of convolution
            to generate patch embedding. Default: "Conv2d".
        kernel_size (int): The kernel_size of embedding conv. Default: 16.
        stride (int): The slide stride of embedding conv.
            Default: 16.
        padding (int | tuple | string): The padding length of
            embedding conv. When it is a string, it means the mode
            of adaptive padding, support "same" and "corner" now.
            Default: "corner".
        dilation (int): The dilation rate of embedding conv. Default: 1.
        bias (bool): Bias of embed conv. Default: True.
        norm_cfg (dict, optional): Config dict for normalization layer.
            Default: None.
        input_size (int | tuple | None): The size of input, which will be
            used to calculate the out size. Only works when `dynamic_size`
            is False. Default: None.
        init_cfg (`mmcv.ConfigDict`, optional): The Config for initialization.
            Default: None.
    """

    def __init__(self,
                 in_channels=1,
                 embed_dims=256,
                 conv_type='Conv2d',
                 kernel_size=(16,1), # (height, width)
                 stride=None,
                 padding='corner',
                 dilation=1,
                 bias=True,
                 norm_cfg=None,
                 input_size=None,
                 init_cfg=None):
        super().__init__(init_cfg=init_cfg)
        self.embed_dims = embed_dims
        if stride is None:
            stride = kernel_size
            
        dilation = to_2tuple(dilation)

        if isinstance(padding, str):
            self.adaptive_padding = AdaptivePadding(
                kernel_size=kernel_size,
                stride=stride,
                dilation=dilation,
                padding=padding)
            # disable the padding of conv
            padding = 0
        else:
            self.adaptive_padding = None
        padding = to_2tuple(padding)

        self.projection = build_conv_layer(
            dict(type=conv_type),
            in_channels=in_channels,
            out_channels=embed_dims,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=bias)

        if norm_cfg is not None:
            self.norm = build_norm_layer(norm_cfg, embed_dims)[1]
        else:
            self.norm = None

        if input_size:
            print(input_size)
            input_size = to_2tuple(input_size)
            print(input_size)
            # `init_out_size` would be used outside to
            # calculate the num_patches
            # e.g. when `use_abs_pos_embed` outside
            self.init_input_size = input_size
            if self.adaptive_padding:
                pad_h, pad_w = self.adaptive_padding.get_pad_shape(input_size)
                input_h, input_w = input_size
                input_h = input_h + pad_h
                input_w = input_w + pad_w
                input_size = (input_h, input_w)

            # https://pytorch.org/docs/stable/generated/torch.nn.Conv2d.html
            h_out = (input_size[0] + 2 * padding[0] - dilation[0] *
                     (kernel_size[0] - 1) - 1) // stride[0] + 1
            w_out = (input_size[1] + 2 * padding[1] - dilation[1] *
                     (kernel_size[1] - 1) - 1) // stride[1] + 1
            self.init_out_size = (h_out, w_out)
        else:
            self.init_input_size = None
            self.init_out_size = None

    def forward(self, x, ray_grouping=False):
        """
        Args:
            x (Tensor): Has shape (B, C, H, W). In most case, C is 3.

        Returns:
            tuple: Contains merged results and its spatial shape.

            - x (Tensor): Has shape (B, out_h * out_w, embed_dims)
                or (B, embed_dims, out_h, out_w) if ray_grouping is True
            - out_size (tuple[int]): Spatial shape of x, arrange as
              (out_h, out_w).
        """

        if self.adaptive_padding:
            x = self.adaptive_padding(x)

        x = self.projection(x)
        out_size = (x.shape[2], x.shape[3])
        
        if not ray_grouping:
            # (B, C, H, W) -> (B, embed_dims, out_h*out_w) -> (B, out_h*out_w, embed_dims)        
            x = x.flatten(2).transpose(1, 2)

        if self.norm is not None:
            x = self.norm(x)
        return x, out_size



def test_NonSquarePatchEmbed(img_tensor, in_channels=1, embed_dims=256, kernel_size=(32, 3)):
    
    import torch
    
    # Initialize an instance of NonSquarePatchEmbed
    embedder = NonSquarePatchEmbed(in_channels=in_channels,
                                   embed_dims=embed_dims, kernel_size=kernel_size)

    

    # Forward pass through the embedder
    out, out_size = embedder(img_tensor, ray_grouping=True)

    # Print the output size and the output tensor shape
    print("Output size: ", out_size)
    print("Output tensor shape: ", out.shape)
    return out, out_size


if __name__ == "__main__":
    import torch
    # Create a random grayscale image tensor (B, C, H, W) = (1, 1, 16, 16)
    img_tensor = torch.rand(2, 1, 756, 756)
    test_NonSquarePatchEmbed(img_tensor)