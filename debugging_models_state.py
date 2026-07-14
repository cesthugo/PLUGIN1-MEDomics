import torch

#model = torch.load("/Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/pythonCode/modules/starhe_plugin/models/best_acc_mean_cls_f1_epoch_14.pth")

model2 = torch.load("/Users/hugo/Desktop/STAGE/PLUGIN1-MEDomics/pythonCode/modules/starhe_plugin/models/best_acc_mean_cls_f1_epoch_14.pth", weights_only=False)

print("done")