import logging

import torch
import torch.nn as nn

from .base import BaseRetriever
from .. import builder
from ..registry import RETRIEVER


@RETRIEVER.register_module
class RoIRetriever(BaseRetriever):

    def __init__(self,
                 backbone,
                 global_pool,
                 concat,
                 embed_extractor,
                 attr_predictor=dict(
                     type='AttrPredictor',
                     inchannels=4096,
                     outchannels=463,
                     loss_attr=dict(
                          type='BCEWithLogitsLoss',
                          weight=None,
                          size_average=None,
                          reduce=None,
                          reduction='mean')),
                 roi_pool=None,
                 pretrained=None):
        super(RoIRetriever, self).__init__()

        self.backbone = builder.build_backbone(backbone)
        self.global_pool = builder.build_global_pool(global_pool)
        
        if roi_pool is not None:
            self.roi_pool = builder.build_roi_pool(roi_pool)
        else:
            self.roi_pool = None

        self.concat = builder.build_concat(concat)
        self.embed_extractor = builder.build_embed_extractor(embed_extractor)
 
        if attr_predictor is not None:
           self.attr_predictor = builder.build_attr_predictor(attr_predictor)
        else:
           self.attr_predictor = None
   
        self.init_weights(pretrained=pretrained)


    def extract_feat(self, x, landmarks):
        x = self.backbone(x)
        global_x = self.global_pool(x)
        global_x = global_x.view(global_x.size(0), -1)

        if landmarks is not None:
            local_x = self.roi_pool(x, landmarks)
        else:
            local_x = None

        x = self.concat(global_x, local_x)
        return x


    def forward_train(self,
                      anchor,
                      id,
                      attr=None,
                      pos=None,
                      neg=None,
                      anchor_lm=None,
                      pos_lm=None,
                      neg_lm=None):
        
        losses = dict()
        
        # extract features
        anchor_feat = self.extract_feat(anchor, anchor_lm)
 
        if pos is not None:
           pos_feat = self.extract_feat(pos, pos_lm)
           neg_feat = self.extract_feat(neg, neg_lm)
           losses['loss_id'] = self.embed_extractor(anchor_feat, 
                                                    id,
                                                    train=True,
                                                    triplet=True,
                                                    pos=pos_feat, neg=neg_feat)
        
        else:
           losses['loss_id'] = self.embed_extractor(anchor_feat, id)

        if attr is not None:
           losses['loss_attr'] = self.attr_predictor(anchor_feat, attr)
        
        return losses


    def simple_test(self, x, landmarks=None):
        """Test single image"""
        x = x.unsqueeze(0)
        if landmarks is not None:
            landmarks = landmarks.unsqueeze(0)
        feat = self.extract_feat(x, landmarks)
        embed = self.embed_extractor(feat)
        return embed

    def aug_test(self, x, landmarks=None):
        """Test batch of images"""
        feat = self.extract_feat(x, landmarks)
        embed = self.embed_extractor(x)
        return embed

    def init_weights(self, pretrained=None):
        super(RoIRetriever, self).init_weights(pretrained)
        self.backbone.init_weights(pretrained=pretrained)
        self.global_pool.init_weights()

        if self.roi_pool is not None:
            self.roi_pool.init_weights()
          
        self.concat.init_weights()
        self.embed_extractor.init_weights()

        if self.attr_predictor is not None:
           self.attr_predictor.init_weights()   
         