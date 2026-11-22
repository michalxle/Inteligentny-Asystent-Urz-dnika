"""Explicit online provisioning; runtime never downloads models."""
import os
from pathlib import Path
from huggingface_hub import snapshot_download
root=Path(__file__).resolve().parents[1]
data=Path(os.environ.get('DATA_DIR',root/'.data'))
snapshot_download('intfloat/multilingual-e5-base',local_dir=data/'models/multilingual-e5-base',allow_patterns=['*.json','*.safetensors','*.model','*.txt','1_Pooling/*','*.py'],ignore_patterns=['onnx/*','openvino/*'])
print('Lokalny model wyszukiwania zapisany.')
