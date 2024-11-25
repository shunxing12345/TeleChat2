# Copyright 2024 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""run row parallel linear"""
import argparse
import os
import numpy as np

import mindspore.nn as nn
import mindspore as ms
from mindspore import Tensor
from mindspore.communication import init
from mindspore.ops import operations as P

from mindformers.experimental.graph.transformer.transformer_config import TransformerConfig
from mindformers.experimental.graph.tensor_parallel.layers import RowParallelLinear
from mindformers.experimental.utils import init_method_normal

parser = argparse.ArgumentParser()
parser.add_argument(
    '--dp',
    default=1,
    required=True,
    type=int,
    help='data_parallel')
parser.add_argument(
    '--cp',
    default=1,
    required=True,
    type=int,
    help='context_parallel')
parser.add_argument(
    '--tp',
    default=1,
    required=True,
    type=int,
    help='tensor_parallel')
parser.add_argument(
    '--has_bias',
    action='store_true',
    help='has_bias'
)
args_, rest_args_ = parser.parse_known_args()

ms.set_context(mode=ms.GRAPH_MODE)
rank_id = os.environ.get('RANK_ID')
if rank_id is not None:
    ms.set_auto_parallel_context(parallel_mode=ms.ParallelMode.SEMI_AUTO_PARALLEL, full_batch=True)
    init()

seed_value = 42
ms.set_seed(seed_value)
np.random.seed(seed_value)


class MyNet(nn.Cell):
    """MyNet for row parallel linear"""
    def __init__(self, config: TransformerConfig, input_size, output_size, bias=True):
        super(MyNet, self).__init__()

        self.linear = RowParallelLinear(input_size=input_size, output_size=output_size,
                                        config=config, compute_dtype=ms.dtype.float32,
                                        init_method=init_method_normal(), bias=bias)
        dp = config.data_parallel
        cp = config.context_parallel
        tp = config.tensor_parallel
        self.add = P.Add().shard(((dp, cp, tp), (tp,)))

    def construct(self, x):
        output_, output_bias = self.linear(x)
        if output_bias is not None:
            output_ = self.add(output_, output_bias)
        return output_


config_ = TransformerConfig()
config_.data_parallel = args_.dp
config_.tensor_parallel = args_.tp
config_.context_parallel = args_.cp

has_bias = args_.has_bias

bs = 2
seq_len = 4096
dim = 8192
input_shape = (bs, seq_len, dim)
output_size_ = dim * 2

net = MyNet(config_, dim, output_size_, has_bias)
input_ = Tensor(np.random.standard_normal(input_shape).astype(np.float32))
output = net(input_)