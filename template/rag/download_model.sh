#! /bin/bash

set -x

pip install -U huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple

export HF_ENDPOINT=https://hf-mirror.com

huggingface-cli download --resume-download sentence-transformers/all-MiniLM-L6-v2 --local-dir all-MiniLM-L6-v2