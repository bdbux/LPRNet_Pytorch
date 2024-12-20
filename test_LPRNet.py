# -*- coding: utf-8 -*-
# /usr/bin/env/python3

'''
test pretrained model.
Author: aiboy.wei@outlook.com .
'''

from data.load_data import CHARS, CHARS_DICT, LPRDataLoader
from PIL import Image, ImageDraw, ImageFont
from model.LPRNet import build_lprnet
# import torch.backends.cudnn as cudnn
from torch.autograd import Variable
import torch.nn.functional as F
from torch.utils.data import *
from torch import optim
import torch.nn as nn
import numpy as np
import argparse
import torch
import time
import cv2
import os
import matplotlib.pyplot as plt

def get_parser():
    # if script is imported provide default args
    if __name__ != 'main':
        class Args:
            img_size = [94, 24]
            test_img_dirs = "LPRNet_Pytorch/data/test"
            dropout_rate = 0
            lpr_max_len = 8
            test_batch_size = 100
            phase_train = False
            num_workers = 2
            cuda = False
            show = False
            pretrained_model = "LPRNet_Pytorch/weights/Final_LPRNet_model.pth"
        return Args()

    # else run as normal
    parser = argparse.ArgumentParser(description='parameters to train net')
    parser.add_argument('--img_size', default=[94, 24], help='the image size')
    parser.add_argument('--test_img_dirs', default="LPRNet_Pytorch/data/test", help='the test images path')
    parser.add_argument('--dropout_rate', default=0, help='dropout rate.')
    parser.add_argument('--lpr_max_len', default=8, help='license plate number max length.')
    parser.add_argument('--test_batch_size', default=100, help='testing batch size.')
    parser.add_argument('--phase_train', default=False, type=bool, help='train or test phase flag.')
    parser.add_argument('--num_workers', default=2, type=int, help='Number of workers used in dataloading')
    parser.add_argument('--cuda', default=False, type=bool, help='Use cuda to train model')
    parser.add_argument('--show', default=False, type=bool, help='show test image and its predict result or not.')
    parser.add_argument('--pretrained_model', default='LPRNet_Pytorch/weights/Final_LPRNet_model.pth', help='pretrained base model')

    args = parser.parse_args()

    return args

def collate_fn(batch):
    imgs = []
    labels = []
    lengths = []
    for _, sample in enumerate(batch):
        img, label, length = sample
        imgs.append(torch.from_numpy(img))
        labels.extend(label)
        lengths.append(length)
    labels = np.asarray(labels).flatten().astype(np.float32)

    return (torch.stack(imgs, 0), torch.from_numpy(labels), lengths)

def test(args, model=None):
    if model != None:
        device = torch.device("cuda:0" if args.cuda else "cpu")
        model.to(device)
        print("Build successful with provided model!")
    else:
        lprnet = build_lprnet(lpr_max_len=args.lpr_max_len, phase=args.phase_train, class_num=len(CHARS), dropout_rate=args.dropout_rate)
        device = torch.device("cuda:0" if args.cuda else "cpu")
        lprnet.to(device)
        print("Successful to build network!")

        # load pretrained model
        if args.pretrained_model:
            lprnet.load_state_dict(torch.load(args.pretrained_model))
            print("load pretrained model successful!")
        else:
            print("[Error] Can't found pretrained mode, please check!")
            return False
        model = lprnet

    test_img_dirs = os.path.expanduser(args.test_img_dirs)
    test_dataset = LPRDataLoader(test_img_dirs.split(','), args.img_size, args.lpr_max_len)
    try:
        Greedy_Decode_Eval(model, test_dataset, args)
    finally:
        cv2.destroyAllWindows()

def Greedy_Decode_Eval(Net, datasets, args):
    # TestNet = Net.eval()
    epoch_size = len(datasets) // args.test_batch_size
    batch_iterator = iter(DataLoader(datasets, args.test_batch_size, shuffle=True, num_workers=args.num_workers, collate_fn=collate_fn))

    Tp = 0
    Tn_1 = 0
    Tn_2 = 0
    t1 = time.time()
    for i in range(epoch_size):
        # load train data
        images, labels, lengths = next(batch_iterator)
        start = 0
        targets = []
        for length in lengths:
            label = labels[start:start+length]
            targets.append(label)
            start += length
        targets = np.array([el.numpy() for el in targets])
        imgs = images.numpy().copy()

        if args.cuda:
            images = Variable(images.cuda())
        else:
            images = Variable(images)

        # forward
        prebs = Net(images)
        # greedy decode
        prebs = prebs.cpu().detach().numpy()
        preb_labels = list()
        for i in range(prebs.shape[0]):
            preb = prebs[i, :, :]
            preb_label = list()
            for j in range(preb.shape[1]):
                preb_label.append(np.argmax(preb[:, j], axis=0))
            no_repeat_blank_label = list()
            pre_c = preb_label[0]
            if pre_c != len(CHARS) - 1:
                no_repeat_blank_label.append(pre_c)
            for c in preb_label: # dropout repeate label and blank label
                if (pre_c == c) or (c == len(CHARS) - 1):
                    if c == len(CHARS) - 1:
                        pre_c = c
                    continue
                no_repeat_blank_label.append(c)
                pre_c = c
            preb_labels.append(no_repeat_blank_label)
        for i, label in enumerate(preb_labels):
            # show image and its predict label
            if args.show:
                show(imgs[i], label, targets[i])
            if len(label) != len(targets[i]):
                Tn_1 += 1
                continue
            if (np.asarray(targets[i]) == np.asarray(label)).all():
                Tp += 1
            else:
                Tn_2 += 1
    Acc = Tp * 1.0 / (Tp + Tn_1 + Tn_2)
    print("[Info] Test Accuracy: {} [{}:{}:{}:{}]".format(Acc, Tp, Tn_1, Tn_2, (Tp+Tn_1+Tn_2)))
    t2 = time.time()
    print("[Info] Individual Test Speed: {}s 1/{}]".format((t2 - t1) / len(datasets), len(datasets)))
    print("Total time: " + str(t2 - t1) + " seconds")

def show_image_in_colab(img, title=""):
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    plt.title(title)
    plt.axis("off")
    plt.show()

def show(img, label, target):
    img = np.transpose(img, (1, 2, 0))  # Rearrange channels for visualization
    img *= 128.
    img += 127.5
    img = img.astype(np.uint8)

    lb = ""
    for i in label:
        lb += CHARS[i]
    tg = ""
    for j in target.tolist():
        tg += CHARS[int(j)]

    flag = "F"
    if lb == tg:
        flag = "T"

    # Add text to the image
    img = cv2ImgAddText(img, lb, (0, 0))

    # Display the image in Colab
    show_image_in_colab(img, title=f"Target: {tg} | Predict: {lb} | Match: {flag}")

    print("target: ", tg, " ### {} ### ".format(flag), "predict: ", lb)

def cv2ImgAddText(img, text, pos, textColor=(255, 0, 0), textSize=12):
    if isinstance(img, np.ndarray):  # Check if the image is OpenCV format
        img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img)

    # Load the font file
    font_path = "LPRNet_Pytorch/data/NotoSansCJK-Regular.ttc"  # Update to the correct path
    fontText = ImageFont.truetype(font_path, textSize, encoding="utf-8")

    # Draw the text on the image
    draw.text(pos, text, textColor, font=fontText)

    # Convert back to OpenCV format
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)

def get_model(args):
    model = build_lprnet(
        lpr_max_len=args.lpr_max_len,
        phase=args.phase_train,
        class_num=len(CHARS),
        dropout_rate=args.dropout_rate
    )
    device = torch.device("cuda:0" if args.cuda and torch.cuda.is_available() else "cpu")
    model.to(device)

    # Load pretrained model
    if args.pretrained_model:
        model.load_state_dict(torch.load(args.pretrained_model, map_location=device))
        print("Loaded pretrained model successfully!")
    else:
        print("[Warning] Pretrained model not found. Returning untrained model.")
    return model


def main():
    args = get_parser()
    test(args)
    
if __name__ == "__main__":
    main()
