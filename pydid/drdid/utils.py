"""Utility functions for the DRDiD package."""

import warnings

import numpy as np


def _validate_inputs(arrays_dict, x, n_bootstrap, trim_level, check_intercept=False):
    """Validate inputs for bootstrap functions."""
    for name, arr in arrays_dict.items():
        if not isinstance(arr, np.ndarray):
            raise TypeError(f"{name} must be a NumPy array.")

    if not isinstance(x, np.ndarray):
        raise TypeError("x must be a NumPy array.")

    for name, arr in arrays_dict.items():
        if arr.ndim != 1:
            raise ValueError(f"{name} must be 1-dimensional.")

    if x.ndim != 2:
        raise ValueError("x must be a 2-dimensional array.")

    first_array = next(iter(arrays_dict.values()))
    n_units = first_array.shape[0]

    for name, arr in arrays_dict.items():
        if arr.shape[0] != n_units:
            raise ValueError("All arrays must have the same number of observations.")

    if x.shape[0] != n_units:
        raise ValueError("All arrays must have the same number of observations.")

    if not isinstance(n_bootstrap, int) or n_bootstrap <= 0:
        raise ValueError("n_bootstrap must be a positive integer.")

    if not 0 < trim_level < 1:
        raise ValueError("trim_level must be between 0 and 1.")

    if check_intercept and not np.all(x[:, 0] == 1.0):
        warnings.warn(
            "The first column of the covariate matrix 'x' does not appear to be an intercept (all ones). "
            "IPT propensity score estimation typically requires an intercept.",
            UserWarning,
        )

    return n_units


def _validate_wols_arrays(arrays_dict: dict[str, np.ndarray], x: np.ndarray, function_name: str = "wols") -> int:
    """Validate input arrays for WOLS functions."""
    all_arrays = list(arrays_dict.values()) + [x]
    if not all(isinstance(arr, np.ndarray) for arr in all_arrays):
        raise TypeError("All inputs must be NumPy arrays.")

    if function_name == "wols_panel":
        dim_error_msg = "delta_y, d, ps, and i_weights must be 1-dimensional."
    else:  # wols_rc
        dim_error_msg = "y, post, d, ps, and i_weights must be 1-dimensional."

    for arr in arrays_dict.values():
        if arr.ndim != 1:
            raise ValueError(dim_error_msg)

    if x.ndim != 2:
        raise ValueError("x must be a 2-dimensional array.")

    n_units = next(iter(arrays_dict.values())).shape[0]
    for arr in list(arrays_dict.values()) + [x]:
        if arr.shape[0] != n_units:
            raise ValueError("All arrays must have the same number of observations (first dimension).")

    return n_units


def _check_extreme_weights(weights: np.ndarray, threshold: float = 1e6) -> None:
    """Check for extreme weight ratios and warn if found."""
    if len(weights) > 1:
        positive_mask = weights > 0
        if np.any(positive_mask):
            min_positive = np.min(weights[positive_mask])
            max_weight = np.max(weights)
            if max_weight / min_positive > threshold:
                warnings.warn("Extreme weight ratios detected. Results may be numerically unstable.", UserWarning)


def _check_wls_condition_number(results, threshold_error: float = 1e15, threshold_warn: float = 1e10) -> None:
    """Check condition number of WLS results and handle accordingly."""
    try:
        condition_number = results.condition_number
        if condition_number > threshold_error:
            raise ValueError(
                f"Failed to solve linear system: The covariate matrix may be singular or ill-conditioned "
                f"(condition number: {condition_number:.2e})."
            )
        if condition_number > threshold_warn:
            warnings.warn(
                f"Potential multicollinearity detected (condition number: {condition_number:.2e}). "
                "Consider removing or combining covariates.",
                UserWarning,
            )
    except AttributeError:
        pass


def _check_coefficients_validity(coefficients: np.ndarray) -> None:
    """Check if coefficients contain invalid values."""
    if np.any(np.isnan(coefficients)) or np.any(np.isinf(coefficients)):
        raise ValueError(
            "Failed to solve linear system. Coefficients contain NaN/Inf values, "
            "likely due to multicollinearity or singular matrix."
        )
