"""PAT soft-sensor integration for indirect measurement prediction.

Provides a protocol (ABC) for soft-sensor prediction models and a built-in
LinearSoftSensor for simple calibration curves. Predictions are stored
alongside direct measurements with a naming convention that distinguishes
predicted values (e.g., 'glucose_predicted') from measured values.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from sporedb.analytics.models import SoftSensorConfig  # noqa: F401


class SoftSensor(ABC):
    """Protocol for PAT soft-sensor prediction models.

    Implement this ABC to integrate any prediction model (linear, PLS, ML)
    into SporeDB's analytics pipeline. The predict() method must return
    arrays compatible with the telemetry schema.
    """

    @property
    @abstractmethod
    def output_variable(self) -> str:
        """Name of the predicted variable (should end with '_predicted')."""
        ...

    @property
    @abstractmethod
    def input_variables(self) -> list[str]:
        """Names of required input variables for prediction."""
        ...

    @abstractmethod
    def predict(
        self,
        inputs: dict[str, np.ndarray],
        timestamps: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Predict values and optional uncertainties.

        Parameters
        ----------
        inputs : dict[str, np.ndarray]
            Input variable name -> values array.
        timestamps : np.ndarray
            Timestamps corresponding to each input value.

        Returns
        -------
        tuple[np.ndarray, np.ndarray | None]
            (predicted_values, uncertainties_or_None)

        Raises
        ------
        ValueError
            If required input variables are missing from inputs dict.
        """
        ...


class LinearSoftSensor(SoftSensor):
    """Simple linear calibration model: y = slope * x + intercept.

    Parameters
    ----------
    input_variable : str
        Name of the input variable (single-input model).
    output_variable : str
        Name of the predicted output variable.
    slope : float
        Calibration slope.
    intercept : float
        Calibration intercept.
    prediction_std : float
        Constant prediction uncertainty (0.0 = no uncertainty).
    """

    def __init__(
        self,
        input_variable: str,
        output_variable: str,
        slope: float,
        intercept: float,
        prediction_std: float = 0.0,
    ) -> None:
        self._input_variable = input_variable
        self._output_variable = output_variable
        self._slope = slope
        self._intercept = intercept
        self._prediction_std = prediction_std

    @property
    def output_variable(self) -> str:
        return self._output_variable

    @property
    def input_variables(self) -> list[str]:
        return [self._input_variable]

    def predict(
        self,
        inputs: dict[str, np.ndarray],
        timestamps: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """Compute y = slope * x + intercept with optional constant uncertainty.

        Raises
        ------
        ValueError
            If the required input variable is not present in inputs.
        """
        if self._input_variable not in inputs:
            raise ValueError(
                f"Required input variable '{self._input_variable}' not found "
                f"in inputs. Available: {sorted(inputs.keys())}"
            )

        x = inputs[self._input_variable]
        y = self._slope * x + self._intercept

        if self._prediction_std > 0:
            uncertainties = np.full_like(y, self._prediction_std)
            return y, uncertainties

        return y, None


def apply_soft_sensor(
    sensor: SoftSensor,
    telemetry_df: pd.DataFrame,
) -> pd.DataFrame:
    """Apply a soft sensor to a telemetry DataFrame.

    Extracts input variables from the DataFrame, runs predict(),
    and returns a new DataFrame of predicted rows with:
    - same 'ts' column as input
    - 'variable' = sensor.output_variable
    - 'value' = predicted values
    - 'uncertainty' = prediction uncertainties (NaN if None)
    - 'source' = 'soft_sensor'

    The returned DataFrame can be concatenated with the original telemetry.

    Parameters
    ----------
    sensor : SoftSensor
        The soft-sensor model to apply.
    telemetry_df : pd.DataFrame
        Must contain columns: 'ts', 'variable', 'value'.

    Returns
    -------
    pd.DataFrame
        New rows with predicted values.

    Raises
    ------
    ValueError
        If required input variables are not found in the telemetry DataFrame.
    """
    available_vars = set(telemetry_df["variable"].unique())

    # Check all required inputs are present
    missing = set(sensor.input_variables) - available_vars
    if missing:
        raise ValueError(
            f"Required input variable(s) {sorted(missing)} not found in "
            f"telemetry DataFrame. Available: {sorted(available_vars)}"
        )

    # Extract input arrays, aligned by timestamp
    # Use the first input variable's timestamps as reference
    first_var = sensor.input_variables[0]
    ref_df = (
        telemetry_df[telemetry_df["variable"] == first_var]
        .sort_values("ts")
        .reset_index(drop=True)
    )
    timestamps = ref_df["ts"].to_numpy()

    inputs: dict[str, np.ndarray] = {}
    for var_name in sensor.input_variables:
        var_df = (
            telemetry_df[telemetry_df["variable"] == var_name]
            .sort_values("ts")
            .reset_index(drop=True)
        )
        inputs[var_name] = var_df["value"].to_numpy(dtype=float)

    # Run prediction (T-05-02: catch exceptions from user models)
    try:
        predicted_values, uncertainties = sensor.predict(inputs, timestamps)
    except ValueError:
        raise  # Re-raise ValueError (expected validation errors)
    except Exception as exc:
        raise RuntimeError(f"Soft-sensor prediction failed: {exc}") from exc

    # Validate output shape (T-05-02 mitigation)
    if len(predicted_values) != len(timestamps):
        raise ValueError(
            f"Predicted values length ({len(predicted_values)}) does not match "
            f"input timestamps length ({len(timestamps)})"
        )

    # Build result DataFrame
    result = pd.DataFrame(
        {
            "ts": timestamps,
            "variable": sensor.output_variable,
            "value": predicted_values,
            "uncertainty": uncertainties if uncertainties is not None else np.nan,
            "source": "soft_sensor",
        }
    )

    return result
