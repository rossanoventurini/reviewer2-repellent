import os

CKPT = os.path.join("ckpt", "fastidx")
API_KEY = os.environ.get("WANDB_API_KEY")


def main():
    print(os.path.join(CKPT, "model.bin"))
