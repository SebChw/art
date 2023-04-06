from torch.utils.data import DataLoader
import lightning as L

import torch
import datasets
from torch.utils.data.sampler import BatchSampler, RandomSampler

from art.data.collate import create_waveform_collate, create_sourceseparation_collate


class GoogleCommandDataModule(L.LightningDataModule):
    def __init__(self, batch_size=64, spectrogram=False):
        super().__init__()

        self.batch_size = batch_size
        self.spectrogram = spectrogram
        if self.spectrogram:
            self.collate = lambda x: x
        else:
            self.collate = create_waveform_collate()
        self.dataset = None

    def prepare_data(self):
        # If you don't write anything here Lightning will try to use prepare_data_per_node
        print("Nothing to download")

    def setup(self, stage):
        # This separation between assignment and donwloading may be usefull for multi-node training
        if self.dataset is None:
            self.dataset = datasets.load_dataset("speech_commands", "v0.02")
            self.dataset = self.dataset.remove_columns(
                ["file", "is_unknown", "speaker_id", "utterance_id"]
            )

            # This is very inefficient it stores stuff on 64 bits by default. HF doesn't support 16 bits.
            # self.dataset = self.dataset.map(
            #     lambda example: {"data": np.expand_dims(example["audio"]["array"], 0)}, remove_columns="audio")

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.dataset = self.dataset.with_format("torch", device=device)

    def train_dataloader(self):
        # Why  Iremoved samplers
        # https://huggingface.co/docs/datasets/use_with_pytorch
        return DataLoader(
            self.dataset["train"].shuffle(),
            shuffle=True,
            batch_size=self.batch_size,
            collate_fn=self.collate,
        )

    def val_dataloader(self):
        return DataLoader(
            self.dataset["validation"],
            batch_size=self.batch_size,
            collate_fn=self.collate,
        )

    def test_dataloader(self):
        return DataLoader(
            self.dataset["test"], batch_size=self.batch_size, collate_fn=self.collate
        )


class SourceSeparationDataModule(L.LightningDataModule):
    def __init__(
        self,
        dataset_kwargs,
        batch_size=64,
        train_size=None,
        max_length=-1,
        num_workers=4,
    ):
        super().__init__()

        self.train_size = train_size
        self.dataset_kwargs = dataset_kwargs

        self.batch_size = batch_size
        self.num_workers = num_workers

        self.collate = create_sourceseparation_collate(max_length)
        self.dataset = None

    def prepare_data(self):
        print("Nothing to download")

    def setup(self, stage):
        if self.dataset is None:
            self.dataset = datasets.load_dataset(**self.dataset_kwargs)
            if self.dataset_kwargs["path"] == "sebchw/sound_demixing_challenge":
                self.dataset_train = self.dataset["train"]
                self.dataset_valid = datasets.load_dataset(
                    "sebchw/musdb18", split="test"
                )
            else:
                self.dataset_train = self.dataset["train"]
                self.dataset_valid = self.dataset["test"]

            # We don't shuffle not to mix up song between sets
            #! It is suggested by DB to use clean set as validation
            # if self.train_size:
            #     self.dataset = self.dataset.train_test_split(
            #         train_size=self.train_size, shuffle=False
            #     )

            self.dataset_train = self.dataset_train.with_format("torch", device="cpu")
            self.dataset_valid = self.dataset_valid.with_format("torch", device="cpu")

    def dataloader_batch_sampler(self, ds, batch_size):
        batch_sampler = BatchSampler(
            RandomSampler(ds), batch_size=batch_size, drop_last=False
        )
        return DataLoader(
            ds,
            batch_sampler=batch_sampler,
            collate_fn=self.collate,
            num_workers=self.num_workers,
        )

    def train_dataloader(self):
        return self.dataloader_batch_sampler(self.dataset_train, self.batch_size)

    def val_dataloader(self):
        return self.dataloader_batch_sampler(self.dataset_valid, self.batch_size)

    def test_dataloader(self):
        return self.dataloader_batch_sampler(self.dataset_valid, self.batch_size)
