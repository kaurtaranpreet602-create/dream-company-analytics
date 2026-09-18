"""
statistics_service.py
Implements all statistical functions dynamically against whichever
numeric columns exist in the currently loaded dataset. No column
names are ever hard-coded.
"""

import pandas as pd
import numpy as np

# Human-readable, generic explanations for each statistic
EXPLANATIONS = {
    "mean": "The mean is the average of all values in a column, found by adding them up and dividing by the count.",
    "median": "The median is the middle value when all values in a column are sorted in order.",
    "mode": "The mode is the value (or values) that occur most frequently in a column.",
    "min": "The minimum is the smallest value found in a column.",
    "max": "The maximum is the largest value found in a column.",
    "sum": "The sum is the total of all values in a column added together.",
    "count": "The count is the number of non-missing values in a column.",
    "variance": "Variance measures how spread out the values are from the mean. A higher variance means more spread.",
    "std": "Standard deviation is the square root of variance, showing how much values typically differ from the mean, in the same units as the data.",
    "skew": "Skewness measures the asymmetry of a distribution. Positive skew means a longer tail on the right; negative skew means a longer tail on the left.",
    "kurt": "Kurtosis measures how heavy-tailed or light-tailed a distribution is compared to a normal distribution.",
    "describe": "Describe gives a full statistical summary: count, mean, standard deviation, min, quartiles and max, all in one table.",
}

VALID_FUNCTIONS = {
    "mean", "median", "mode", "min", "max", "sum",
    "count", "variance", "std", "skew", "kurt", "describe",
}


class StatisticsError(Exception):
    pass


def _select_columns(df: pd.DataFrame, numeric_columns, selected_columns):
    """Validate and resolve the columns to run statistics against."""
    if not numeric_columns:
        raise StatisticsError("No numerical columns were found in this dataset.")

    if selected_columns:
        invalid = [c for c in selected_columns if c not in numeric_columns]
        if invalid:
            raise StatisticsError(
                f"These columns are not numeric and cannot be used for statistics: {', '.join(invalid)}"
            )
        cols = selected_columns
    else:
        cols = numeric_columns

    return cols


def compute_statistic(df: pd.DataFrame, numeric_columns, function_name, selected_columns=None):
    """
    Compute a single statistic across the given (or all numeric) columns.
    Returns a JSON-friendly dict.
    """
    if function_name not in VALID_FUNCTIONS:
        raise StatisticsError(f"Unknown statistical function: {function_name}")

    cols = _select_columns(df, numeric_columns, selected_columns)
    subset = df[cols]

    if function_name == "describe":
        result_df = subset.describe()
        table = _df_to_table(result_df, index_label="Metric")
        return {
            "function": function_name,
            "label": "Describe",
            "explanation": EXPLANATIONS["describe"],
            "table_type": "matrix",
            "table": table,
        }

    if function_name == "mode":
        result_df = subset.mode()
        table = _df_to_table(result_df, index_label="Row")
        return {
            "function": function_name,
            "label": "Mode",
            "explanation": EXPLANATIONS["mode"],
            "table_type": "matrix",
            "table": table,
        }

    func_map = {
        "mean": subset.mean,
        "median": subset.median,
        "min": subset.min,
        "max": subset.max,
        "sum": subset.sum,
        "count": subset.count,
        "variance": subset.var,
        "std": subset.std,
        "skew": subset.skew,
        "kurt": subset.kurt,
    }

    series_result = func_map[function_name](numeric_only=True) if function_name not in ("count",) else func_map[function_name]()

    rows = []
    for col, val in series_result.items():
        rows.append({
            "column": col,
            "value": None if pd.isna(val) else round(float(val), 4),
        })

    label_map = {
        "mean": "Mean", "median": "Median", "min": "Minimum", "max": "Maximum",
        "sum": "Sum", "count": "Count", "variance": "Variance", "std": "Standard Deviation",
        "skew": "Skewness", "kurt": "Kurtosis",
    }

    return {
        "function": function_name,
        "label": label_map[function_name],
        "explanation": EXPLANATIONS[function_name],
        "table_type": "simple",
        "rows": rows,
    }


def _df_to_table(result_df: pd.DataFrame, index_label="Index"):
    """Convert a wide statistics DataFrame (e.g. from describe/mode) into a JSON table."""
    result_df = result_df.reset_index()
    result_df = result_df.rename(columns={"index": index_label})
    result_df = result_df.where(pd.notnull(result_df), None)

    columns = list(result_df.columns)
    rows = []
    for _, row in result_df.iterrows():
        row_dict = {}
        for col in columns:
            val = row[col]
            if isinstance(val, (np.floating, float)) and val is not None:
                try:
                    val = round(float(val), 4)
                except (TypeError, ValueError):
                    pass
            row_dict[col] = val
        rows.append(row_dict)

    return {"columns": columns, "rows": rows}
