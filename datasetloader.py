### this is a 2D dataset loader ###
from configparser import Interpolation
from matplotlib import transforms
from torch.utils.data import Dataset
import nibabel as nib
import matplotlib.pyplot as plt
import os
import re
import numpy as np
import torch
import torch.tensor as ts
import torchvision
import torch.nn as nn
import torchio as tio
import torch.nn.functional as F
import torchvision.transforms.functional as TF
import torch.optim as optim
from mpl_toolkits.mplot3d import Axes3D
from PIL import Image
import SimpleITK as sitk
import albumentations as A
import random

# 5-Channel Loader
class train_ISLES2018_loader(Dataset):
    def __init__(self, file_dir, modalities=None,validate=False):
        super().__init__()
        
        self.samples = []
        

        for case_name in os.listdir(file_dir):
            case_path = os.path.join(file_dir, case_name)
            case = {} # dict which will store all the images for each modality, this is later used to iterate through all the slices etc

            for path in os.listdir(case_path):
                modality = re.search(r'SMIR.Brain.XX.O.(\w+).\d+',path).group(1)
                if modality != 'CT_4DPWI': # leave DWI images out for now, can be trained with later
                    nii_path_name = os.path.join(case_path,path,path+'.nii')
                    img = nib.load(nii_path_name)
                    case[modality] = img
            
            normalize = torchvision.transforms.Normalize([0.0],[1.0])

            for i in range(case['CT'].shape[2]):        # go through each case dimension (2-22)
                slices = []                                # create array for each image slice
                for modality in modalities:             # loop through the modalities
                    if modality != 'OT':                # ignore the ground truth

                        # add image augmentations here 
                        #print(np.max(case[modality].get_fdata()), np.min(case[modality].get_fdata()))

                        
                        
                        slice=case[modality].get_fdata()
                        img_array = np.array(slice).astype('float64')
                        img_2d = img_array[:,:,i].transpose((1,0))
                        img_2d = np.uint8(img_2d[None,:])
                        img_2d = torch.from_numpy(img_2d)


                        slices.append(img_2d) # add the slice to the array
                
                
                #gt_slice = torch.from_numpy(case['OT'].get_fdata()[:,:,i]).float().unsqueeze(0) # slice of the corresponding ground_truths

                
                gt_slice=case['OT'].get_fdata()
                gt_array = np.array(gt_slice).astype('float64')
                gt_2d = gt_array[:,:,i].transpose((1,0))

                gt_2d = np.uint8(gt_2d[None,:])

                

        
                
                gt_2d = torch.from_numpy(gt_2d)

                

                slices, gt_slice = self.transform(slices,gt_2d)
                
                #print(slices[0].shape)

                #plt.imshow(gt.squeeze(0), cmap="gray")
                #plt.colorbar(label='intensity')
                #plt.show()
                
                #gt_slice = normalize(gt_slice)
                #plt.imshow(gt_slice.squeeze(0), cmap="gray")
                #plt.show()
                # now transform all the slices in the array before concatenating them:
                # slices, gt_slice = self.transform(slices,gt_slice)

                combined = torch.cat(tuple(slices), dim=0) # concatenate all the slices to form 5 channel, input has to be a set
                
                """
                f, axarr = plt.subplots(2,2)
                axarr[0,0].imshow(combined[0, :, :], cmap="gray")
                axarr[0,1].imshow(combined[1, :, :], cmap="gray")
                axarr[1,0].imshow(combined[2, :, :], cmap="gray")
                
                axarr[1,1].imshow(gt_slice[0, :, :], cmap="gray")
                plt.show()
                """
                self.samples.append((combined, gt_slice))  # append tuples of combined slices and ground truth masks, this makes it easier to later compare the pred/actual
        
        
        
                        
    def __getitem__(self, idx):
        return self.samples[idx]   # return the dataset corresponding to the input modality
    
    def __len__(self):      # return length of dataset for each modality
        return len(self.samples)

    def transform(self, slices, gt):

        # convert each slice into a pil image
        for i in range(len(slices)):
            image = slices[i]
            image = TF.to_pil_image(image)
            slices[i] = image
        
        gt = TF.to_pil_image(gt)

        resize = torchvision.transforms.Resize(size=(256, 256))
        image = resize(image)
        gt=  resize(gt)
        
        
        # flip horizontally randomly
        if random.random() > 0.5:
            for i in range(len(slices)):
                image = slices[i]
                image = TF.hflip(image)
                slices[i] = image
            
            gt = TF.hflip(gt)
        
        # flip vertically randomly
        if random.random() > 0.5:
            for i in range(len(slices)):
                image = slices[i]
                image = TF.vflip(image)
                slices[i] = image
            
            gt = TF.vflip(gt)
        
        # rotate at random
        if random.random() > 0.5:
            angle = random.randint(-30, 30)
            for i in range(len(slices)):
                image = slices[i]
                image = TF.rotate(image, angle, fill=(0,))
                slices[i] = image
            
            gt = TF.rotate(gt, angle, fill=(0,))

        # convert back to tensor/normalize
        for i in range(len(slices)):
            image = slices[i]
            image = TF.to_tensor(image)
            slices[i] = image
        
        gt = TF.to_tensor(gt)

        
        return slices, gt
    
    def normalizeIntensityRange(self,data):
        
        return (data - np.min(data)) / (np.max(data) - np.min(data))
    
    # this bit is a huge bottleneck
    def n4BiasCorrection(self, img):
        
        img = sitk.GetImageFromArray(img)
        image = sitk.Cast(img, sitk.sitkFloat32)
        corrected_img = sitk.N4BiasFieldCorrection(image)
        img = sitk.GetArrayFromImage(corrected_img)

        return img
    
    # returns the modality and ground truth image
    def getData(self,modality):
        return self.data[modality], self.data['OT']


class val_ISLES2018_loader(Dataset):
    def __init__(self, file_dir, modalities=None,validate=False):
        super().__init__()
        
        self.samples = []

        for case_name in os.listdir(file_dir):
            
            case_path = os.path.join(file_dir, case_name)
            case = {} # dict which will store all the images for each modality, this is later used to iterate through all the slices etc

            for path in os.listdir(case_path):
                modality = re.search(r'SMIR.Brain.XX.O.(\w+).\d+',path).group(1)
                if modality != 'CT_4DPWI': # leave DWI images out for now, can be trained with later
                    nii_path_name = os.path.join(case_path,path,path+'.nii')
                    img = nib.load(nii_path_name)
                    case[modality] = img
            
            

            for i in range(case['CT'].shape[2]):        # go through each case dimension (2-22)
                slices = []                                # create array for each image slice
                for modality in modalities:             # loop through the modalities
                    if modality != 'OT':                # ignore the ground truth
    
                 
                        slice=case[modality].get_fdata()
                        img_array = np.array(slice).astype('float64')
                        img_2d = img_array[:,:,i].transpose((1,0))
                        img_2d = np.uint8(img_2d[None,:])
                        img_2d = torch.from_numpy(img_2d)

                        image = TF.to_pil_image(img_2d)
                        image = TF.to_tensor(image)

                        slices.append(image) # add the slice to the array
                
                

                
                gt_slice=case['OT'].get_fdata()
                gt_array = np.array(gt_slice).astype('float32')
                gt_2d = gt_array[:,:,i].transpose((1,0))

                gt_2d = np.uint8(gt_2d[None,:])
                gt_2d = torch.from_numpy(gt_2d)

                gt = TF.to_pil_image(gt_2d)
                gt = TF.to_tensor(gt)
                
                #plt.imshow(gt.squeeze(0), cmap="gray")
                #plt.show()
                

                combined = torch.cat(tuple(slices), dim=0) # concatenate all the slices to form 5 channel, input has to be a set
                
                  
                self.samples.append((combined, gt))  # append tuples of combined slices and ground truth masks, this makes it easier to later compare the pred/actual
        
            
        
                        
    def __getitem__(self, idx):
        return self.samples[idx]   # return the dataset corresponding to the input modality
    
    def __len__(self):      # return length of dataset for each modality
        return len(self.samples)

    def transform(self, slices, gt):
        
        # flip horizontally randomly
        if random.random() > 0.5:
            for i in range(len(slices)):
                image = slices[i]
                image = TF.hflip(image)
                slices[i] = image
            
            gt = TF.hflip(image)

        
        return slices, gt
    
    
    
    
    

            
            

#directory = "ISLES/TRAINING"
#modalities = ['OT', 'CT', 'CT_CBV', 'CT_CBF', 'CT_Tmax' , 'CT_MTT']
#dataset = ISLES2018_loader(directory, modalities)
#print(dataset.__len__())



