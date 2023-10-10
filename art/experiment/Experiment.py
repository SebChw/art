from typing import TYPE_CHECKING, Any, Dict, List, Optional

from collections import defaultdict
from dataclasses import dataclass

import lightning as L

from art.core.MetricCalculator import MetricCalculator, SkippedMetric
from art.experiment.experiment_state import ArtProjectState
from art.step.checks import Check

if TYPE_CHECKING:
    from art.step.step import Step


@dataclass
class StepStatus:
    status: str
    results: Dict[str, Any]

    def __repr__(self):
        result_repr = "\n".join(f"\t{k}: {v}" for k, v in self.results.items() if k != 'hash')
        return f"{self.status}. Results:\n{result_repr}"

class ArtProject:
    name: str
    steps: List
    logger: object  # probably lightning logger
    state: ArtProjectState

    def __init__(self, name, datamodule: L.LightningDataModule, **kwargs):
        # Potentially we can save file versions to show which model etc was used.
        self.name = name
        self.steps = []
        self.datamodule = datamodule
        self.state = ArtProjectState()
        self.metric_calculator = MetricCalculator(self)
        # self.update_dashboard(self.steps) # now from each step we take internal information it has remembered and save them to show on a dashboard

    def add_step(
        self,
        step: "Step",
        checks: List[Check],
        skipped_metrics: List[SkippedMetric] = [],
    ):
        self.steps.append(
            {
                "step": step,
                "checks": checks,
                "skipped_metrics": skipped_metrics,
            }
        )
        step.set_step_id(len(self.steps))

    def fill_step_states(self, step: "Step"):
        self.state.step_states[step.get_model_name()][
            step.get_name_with_id()
        ] = step.get_results()

    def check_checks(self, step: "Step", checks: List[Check]):
        for check in checks:
            result = check.check(step)
            if not result.is_positive:
                raise Exception(
                    f"Check failed for step: {step.name}. Reason: {result.error}"
                )

    def check_if_must_be_run(self, step: "Step", checks: List[Check]):
        if not step.was_run():
            return True
        else:
            step.load_results()
            try:
                self.check_checks(step, checks)
            except Exception as e:
                return True

        step_current_hash = step.get_hash()
        step_saved_hash = step.get_results()["hash"]
        model_changed = True if step_current_hash != step_saved_hash else False

        if model_changed:
            print(
                f"Code of the model in {step.get_full_step_name()} was changed. Rerun needed."
            )
            return True

        return False

    def run_all(self, force_rerun=False):
        steps_status = defaultdict(lambda: StepStatus("Not run", None))
        
        for step in self.steps:
            self.metric_calculator.compile(step["skipped_metrics"])
            step, checks = step["step"], step["checks"]

            self.state.current_step = step

            if not self.check_if_must_be_run(step, checks) and not force_rerun:
                steps_status[step.get_full_step_name()] = StepStatus("Skipped", step.get_results())
                self.fill_step_states(step)
                continue

            step.add_result("hash", step.get_hash())
            
            try:
                step(self.state.step_states, self.datamodule, self.metric_calculator)
                self.check_checks(step, checks)
                steps_status[step.get_full_step_name()] = StepStatus("Completed", step.get_results())
            except Exception as e:
                steps_status[step.get_full_step_name()] = StepStatus("Failed", step.get_results())
                print(f"Step {step.get_full_step_name()} failed with error: {str(e)}")

            self.fill_step_states(step)

        print("Steps status:")
        for step_name, step_status in steps_status.items():
            print(f"{step_name}: {step_status}")

    def get_steps(self):
        return self.steps

    def replace_step(self, step: "Step", step_id=-1):
        self.steps[step_id]["step"] = step
        if step_id == -1:
            step_id = len(self.steps)
        step.set_step_id(step_id)

    def register_metrics(
        self: Any,
        metrics: List[Any],
    ):
        self.metric_calculator.add_metrics(metrics)

    def to(self: Any, device: str):
        self.metric_calculator.to(device)

    def update_datamodule(self, datamodule: L.LightningDataModule):
        self.datamodule = datamodule
