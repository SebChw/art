from abc import ABC, abstractmethod
from typing import Any, Dict
import hashlib
import inspect
import lightning as L

from art.core.base_components.base_model import ArtModule
from art.core.MetricCalculator import MetricCalculator
from art.step.step_savers import JSONStepSaver
from art.utils.enums import TrainingStage


class Step(ABC):
    """
    An abstract base class representing a generic step in a project.
    """

    def __init__(self):
        """
        Initialize the step with an empty results dictionary.
        """
        self.results = {}

    def __call__(
        self,
        previous_states: Dict,
        datamodule: L.LightningDataModule,
        metric_calculator: MetricCalculator,
    ):
        """
        Call the step and save its results.

        Args:
            previous_states (Dict): Dictionary containing the previous step states.
            datamodule (L.LightningDataModule): Data module to be used.
            metric_calculator (MetricCalculator): Metric calculator for this step.
        """
        self.datamodule = datamodule
        self.do(previous_states)
        JSONStepSaver().save(
            self.results, self.get_step_id(), self.name, "results.json"
        )

    def set_step_id(self, idx: int):
        """
        Set the step ID.

        Args:
            idx (int): Index to set as step ID.
        """
        self.idx = idx

    def get_step_id(self) -> str:
        """
        Retrieve the step ID.

        Returns:
            str: The step ID.
        """
        return f"{self.idx}"

    def get_name_with_id(self) -> str:
        """
        Retrieve the step name combined with its ID.

        Returns:
            str: Name combined with ID.
        """
        return f"{self.idx}_{self.name}"

    def get_full_step_name(self) -> str:
        """
        Retrieve the full name of the step, which is a combination of its ID and name.

        Returns:
            str: The full step name.
        """
        return f"{self.get_step_id()}_{self.name}"

    def get_hash(self) -> str:
        """
        Compute a hash based on the source code of the step's class.

        Returns:
            str: MD5 hash of the step's source code.
        """
        return hashlib.md5(
            inspect.getsource(self.__class__).encode("utf-8")
        ).hexdigest()

    def add_result(self, name: str, value: Any):
        """
        Add a result to the step's results dictionary.

        Args:
            name (str): Name of the result.
            value (Any): Value of the result.
        """
        self.results[name] = value

    def get_results(self) -> Dict:
        """
        Retrieve the results of the step.

        Returns:
            Dict: Dictionary containing step results.
        """
        return self.results

    def load_results(self):
        """
        Load results for the step from saved storage.
        """
        self.results = JSONStepSaver().load(self.get_step_id(), self.name)

    def was_run(self) -> bool:
        """
        Check if the step was already executed based on the existence of saved results.

        Returns:
            bool: True if the step was run, otherwise False.
        """
        path = JSONStepSaver().get_path(
            self.get_step_id(), self.name, JSONStepSaver.RESULT_NAME
        )
        return path.exists()

    def get_model_name(self) -> str:
        """
        Retrieve the model name associated with the step. By default, it's empty.

        Returns:
            str: Model name.
        """
        return ""


class ModelStep(Step):
    """
    A specialized step in the project, representing a model-based step.
    """

    def __init__(self, model: ArtModule, trainer: L.Trainer):
        """
        Initialize a model-based step.

        Args:
            model (ArtModule): The model associated with this step.
            trainer (L.Trainer): Trainer to train and validate the model.
        """
        super().__init__()
        self.model = model
        self.trainer = trainer

    def __call__(
        self,
        previous_states: Dict,
        datamodule: L.LightningDataModule,
        metric_calculator: MetricCalculator,
    ):
        """
        Call the model step, set the metric calculator for the model, and save the results.

        Args:
            previous_states (Dict): Dictionary containing the previous step states.
            datamodule (L.LightningDataModule): Data module to be used.
            metric_calculator (MetricCalculator): Metric calculator for this step.
        """
        self.datamodule = datamodule
        self.model.set_metric_calculator(metric_calculator)
        self.do(previous_states)
        JSONStepSaver().save(
            self.results, self.get_step_id(), self.name, "results.json"
        )

    @abstractmethod
    def do(self, previous_states: Dict):
        """
        Abstract method to execute the step. Must be implemented by child classes.

        Args:
            previous_states (Dict): Dictionary containing the previous step states.
        """
        pass

    def train(self, trainer_kwargs: Dict):
        """
        Train the model using the provided trainer arguments.

        Args:
            trainer_kwargs (Dict): Arguments to be passed to the trainer for training the model.
        """
        self.trainer.fit(model=self.model, **trainer_kwargs)
        logged_metrics = {k: v.item() for k, v in self.trainer.logged_metrics.items()}
        self.results.update(logged_metrics)

    def validate(self, trainer_kwargs: Dict):
        """
        Validate the model using the provided trainer arguments.

        Args:
            trainer_kwargs (Dict): Arguments to be passed to the trainer for validating the model.
        """
        print(f"Validating model {self.get_model_name()}")
        result = self.trainer.validate(model=self.model, **trainer_kwargs)
        self.results.update(result[0])

    def test(self, trainer_kwargs: Dict):
        """
        Test the model using the provided trainer arguments.

        Args:
            trainer_kwargs (Dict): Arguments to be passed to the trainer for testing the model.
        """
        result = self.trainer.test(model=self.model, **trainer_kwargs)
        self.results.update(result[0])

    def get_model_name(self) -> str:
        """
        Retrieve the name of the model associated with the step.

        Returns:
            str: Name of the model.
        """
        return self.model.__class__.__name__

    def get_step_id(self) -> str:
        """
        Retrieve the step ID, combining model name (if available) with the index.

        Returns:
            str: The step ID.
        """
        return (
            f"{self.get_model_name()}_{self.idx}"
            if self.get_model_name() != ""
            else f"{self.idx}"
        )

    def get_hash(self) -> str:
        """
        Compute a hash for the model associated with the step.

        Returns:
            str: Hash of the model.
        """
        return self.model.get_hash()

    def get_current_stage(self) -> str:
        """
        Retrieve the current training stage of the trainer.

        Returns:
            str: Current training stage.
        """
        return self.trainer.state.stage.value

    def get_check_stage(self) -> str:
        """
        Get the validation stage value from the TrainingStage enum.

        Returns:
            str: Validation stage value.
        """
        return TrainingStage.VALIDATION.value
