import os

CKPT = "/home/aburrow/ckpt/fastidx"
FAISS = "https://github.com/facebookresearch/faiss"  # third-party
wandb_api_key = "a1b2c3d4e5f6a7b8c9d0"


def main():
    print(os.path.join(CKPT, "model.bin"))
