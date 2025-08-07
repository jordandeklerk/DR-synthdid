"""Utility functions for continuous treatment DiD estimators."""

from typing import NamedTuple

import numpy as np

from .numba import (
    check_full_rank_crossprod,
    compute_rsquared,
    create_nonzero_divisor,
    matrix_sqrt_eigendecomp,
)


class FullRankCheckResult(NamedTuple):
    """Result from full rank check."""

    is_full_rank: bool
    condition_number: float
    min_eigenvalue: float
    max_eigenvalue: float


def is_full_rank(x, tol=None):
    """Check if a matrix has full rank using eigenvalue decomposition.

    Tests whether a matrix has full rank by computing the condition number
    based on the ratio of maximum to minimum eigenvalues of :math:`X'X`.

    Parameters
    ----------
    x : ndarray
        Input matrix to check for full rank. Can be 1D or 2D.
    tol : float, optional
        Tolerance for the condition number check.

    Returns
    -------
    FullRankCheckResult
        NamedTuple containing:

        - is_full_rank: Whether the matrix has full rank
        - condition_number: The condition number (max_eigenvalue/min_eigenvalue)
        - min_eigenvalue: Minimum eigenvalue of :math:`X'X`
        - max_eigenvalue: Maximum eigenvalue of :math:`X'X`
    """
    x = np.atleast_2d(x)

    if x.shape[1] == 1:
        is_nonzero = np.any(x != 0)
        abs_vals = np.abs(x)
        max_val = np.max(abs_vals) if is_nonzero else 0.0
        min_val = np.min(abs_vals[abs_vals > 0]) if is_nonzero else 0.0

        return FullRankCheckResult(
            is_full_rank=bool(is_nonzero),
            condition_number=max_val / min_val if is_nonzero and min_val > 0 else np.inf,
            min_eigenvalue=min_val**2,
            max_eigenvalue=max_val**2,
        )

    is_full, cond_num, min_eig, max_eig = check_full_rank_crossprod(x, tol)

    return FullRankCheckResult(
        is_full_rank=bool(is_full), condition_number=cond_num, min_eigenvalue=min_eig, max_eigenvalue=max_eig
    )


def compute_r_squared(y, y_pred, weights=None):
    """Compute R-squared statistic for model fit.

    Parameters
    ----------
    y : ndarray
        Observed values.
    y_pred : ndarray
        Predicted values.
    weights : ndarray, optional
        Observation weights. If provided, computes weighted R-squared.

    Returns
    -------
    float
        R-squared value between 0 and 1.

    Notes
    -----
    The weighted R-squared is computed by scaling both y and y_pred
    by sqrt(weights) before the standard R-squared calculation.
    """
    y = np.asarray(y)
    y_pred = np.asarray(y_pred)

    if weights is not None:
        weights = np.asarray(weights)
        if len(weights) != len(y):
            raise ValueError("weights must have same length as y")

        sqrt_w = np.sqrt(weights)
        y = y * sqrt_w
        y_pred = y_pred * sqrt_w

    return float(compute_rsquared(y, y_pred))


def matrix_sqrt(x):
    """Compute matrix square root using eigen-decomposition.

    Computes the square root of a positive semi-definite matrix using
    eigenvalue decomposition. Negative eigenvalues are set to zero to
    ensure numerical stability.

    Uses the formula: :math:`sqrt(X) = V @ diag(sqrt(eigenvalues)) @ V.T`
    where :math:`V` contains the eigenvectors of :math:`X`.

    Parameters
    ----------
    x : ndarray
        Square positive semi-definite matrix.

    Returns
    -------
    ndarray
        Matrix square root such that :math:`result @ result.T ≈ x`.
    """
    x = np.asarray(x)

    if x.ndim != 2:
        raise ValueError("Input must be a 2D array")
    if x.shape[0] != x.shape[1]:
        raise ValueError("Input must be a square matrix")

    return matrix_sqrt_eigendecomp(x)


def avoid_zero_division(a, eps=None):
    """Ensure values are bounded away from zero for safe division.

    Parameters
    ----------
    a : ndarray or float
        Input values to bound away from zero.
    eps : float, optional
        Minimum absolute value. If None, uses machine epsilon.

    Returns
    -------
    ndarray or float
        Values bounded away from zero with preserved sign.
    """
    if eps is None:
        eps = np.finfo(float).eps

    a = np.asarray(a)
    return create_nonzero_divisor(a, eps)


def basis_dimension(basis="additive", degree=None, segments=None):
    """Compute dimension of multivariate basis without constructing it.

    Efficiently computes the dimension of additive, tensor product, or
    generalized linear product (GLP) bases without the memory overhead
    of constructing the full basis matrix.

    Parameters
    ----------
    basis : {"additive", "tensor", "glp"}, default="additive"
        Type of basis to use:

        - "additive": Sum of univariate bases
        - "tensor": Full tensor product
        - "glp": Generalized linear product
    degree : ndarray, optional
        Polynomial degrees for each variable. Must be provided with segments.
    segments : ndarray, optional
        Number of segments for each variable. Must be provided with degree.

    Returns
    -------
    int
        Dimension of the specified basis.
    """
    if basis not in ("additive", "tensor", "glp"):
        raise ValueError("basis must be one of: 'additive', 'tensor', 'glp'")

    if degree is None or segments is None:
        raise ValueError("Both degree and segments must be provided")

    degree = np.asarray(degree)
    segments = np.asarray(segments)

    if degree.shape != segments.shape:
        raise ValueError("degree and segments must have the same shape")

    K = np.column_stack([degree, segments])

    K_filtered = K[K[:, 0] > 0]

    if K_filtered.shape[0] == 0:
        return 0

    if basis == "additive":
        return int(np.sum(np.sum(K_filtered, axis=1) - 1))

    if basis == "tensor":
        return int(np.prod(np.sum(K_filtered, axis=1)))

    if basis == "glp":
        dimen = np.sum(K_filtered, axis=1) - 1
        dimen = dimen[dimen > 0]
        dimen = np.sort(dimen)[::-1]
        k = len(dimen)

        if k == 0:
            return 0

        nd1 = np.ones(dimen[0], dtype=int)
        nd1[dimen[0] - 1] = 0

        ncol_bs = dimen[0]

        if k > 1:
            for i in range(1, k):
                dim_rt = _compute_glp_dimension_step(dimen[0], dimen[i], nd1, ncol_bs)
                nd1 = dim_rt["nd1"]
                ncol_bs = dim_rt["d12"]
            ncol_bs += k - 1

        return int(ncol_bs)

    return 0


def _compute_glp_dimension_step(d1, d2, nd1, pd12):
    """Compute a step in the GLP dimension calculation."""
    if d2 == 1:
        return {"d12": pd12, "nd1": nd1}

    d12 = d2
    if d1 - d2 > 0:
        for i in range(1, d1 - d2 + 1):
            d12 += d2 * nd1[i - 1]

    if d2 > 1:
        for i in range(2, d2 + 1):
            d12 += i * nd1[d1 - i]

    d12 += nd1[d1 - 1]

    nd2 = nd1.copy()
    if d1 > 1:
        for j_idx in range(d1 - 1):
            j = j_idx + 1
            nd2[j_idx] = 0
            start_i = j
            end_i = max(0, j - d2 + 1)
            for i in range(start_i, end_i - 1, -1):
                if i > 0:
                    nd2[j_idx] += nd1[i - 1]
                else:
                    nd2[j_idx] += 1

    if d2 > 1:
        nd2[d1 - 1] = nd1[d1 - 1]
        for i in range(d1 - d2 + 1, d1):
            nd2[d1 - 1] += nd1[i - 1]
    else:
        nd2[d1 - 1] = nd1[d1 - 1]

    return {"d12": d12, "nd1": nd2}


def _quantile_basis(x, q):
    """Compute quantiles for uniform confidence bands."""
    x = np.asarray(x)
    x_sorted = np.sort(x)
    n = len(x_sorted)

    index = q * n + 0.5
    j = int(np.floor(index))
    j_clamped = max(0, min(j - 1, n - 1))

    return x_sorted[j_clamped]
