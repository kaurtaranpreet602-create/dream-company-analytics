"""
visualization_service.py
Generates charts dynamically for whichever dataset is loaded. Charts
are rendered server-side with Matplotlib/Seaborn (Agg backend, no
GUI windows) and returned as base64 PNG so they can be embedded
directly inside the web page.
"""

import io
import base64

import matplotlib
matplotlib.use("Agg")  # never open a GUI window
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

sns.set_theme(style="whitegrid")

VALID_CHARTS = {
    "box", "boxen", "strip", "swarm", "bar", "point", "violin", "heatmap"
}

CHART_LABELS = {
    "box": "Box Plot",
    "boxen": "Boxen Plot",
    "strip": "Strip Plot",
    "swarm": "Swarm Plot",
    "bar": "Bar Plot",
    "point": "Point Plot",
    "violin": "Violin Plot",
    "heatmap": "Heatmap",
}


class VisualizationError(Exception):
    pass


def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def generate_chart(df: pd.DataFrame, numeric_columns, categorical_columns,
                    chart_type, x_column=None, y_column=None, columns=None):
    """
    Generate one chart and return {image (base64), title, chart_type}.

    - box / boxen / strip / swarm / violin -> operate on selected numeric column(s)
    - bar / point -> use a categorical x-axis (or index) and a numeric y-axis
    - heatmap -> correlation matrix across all/selected numeric columns
    """
    if chart_type not in VALID_CHARTS:
        raise VisualizationError(f"Unknown chart type: {chart_type}")

    if chart_type == "heatmap":
        return _heatmap(df, numeric_columns, columns)

    if chart_type in ("bar", "point"):
        return _categorical_numeric_chart(df, chart_type, numeric_columns, categorical_columns, x_column, y_column)

    # box / boxen / strip / swarm / violin -> distribution charts on numeric columns
    return _distribution_chart(df, chart_type, numeric_columns, columns)


def _validate_numeric_selection(numeric_columns, columns):
    if not numeric_columns:
        raise VisualizationError("No numerical columns were found in this dataset for this chart.")
    if columns:
        invalid = [c for c in columns if c not in numeric_columns]
        if invalid:
            raise VisualizationError(
                f"These columns are not numeric and cannot be plotted: {', '.join(invalid)}"
            )
        return columns
    return numeric_columns


def _distribution_chart(df, chart_type, numeric_columns, columns):
    cols = _validate_numeric_selection(numeric_columns, columns)

    # Limit to a reasonable number of columns for legibility
    cols = cols[:8]

    data = df[cols].melt(var_name="Column", value_name="Value").dropna()

    if data.empty:
        raise VisualizationError("Not enough numeric data to build this chart.")

    fig, ax = plt.subplots(figsize=(8, 5))

    try:
        if chart_type == "box":
            sns.boxplot(data=data, x="Column", y="Value", ax=ax, hue="Column", legend=False)
        elif chart_type == "boxen":
            sns.boxenplot(data=data, x="Column", y="Value", ax=ax, hue="Column", legend=False)
        elif chart_type == "strip":
            sns.stripplot(data=data, x="Column", y="Value", ax=ax, hue="Column", legend=False)
        elif chart_type == "swarm":
            sns.swarmplot(data=data, x="Column", y="Value", ax=ax, hue="Column", legend=False)
        elif chart_type == "violin":
            sns.violinplot(data=data, x="Column", y="Value", ax=ax, hue="Column", legend=False)
    except Exception as e:  # noqa: BLE001
        plt.close(fig)
        raise VisualizationError(f"This chart could not be generated for the selected columns.") from e

    ax.set_title(f"{CHART_LABELS[chart_type]} of Selected Columns")
    ax.set_xlabel("Column")
    ax.set_ylabel("Value")
    plt.xticks(rotation=30, ha="right")
    fig.tight_layout()

    image = _fig_to_base64(fig)
    return {
        "image": image,
        "title": f"{CHART_LABELS[chart_type]} of Selected Columns",
        "chart_type": chart_type,
    }


def _categorical_numeric_chart(df, chart_type, numeric_columns, categorical_columns, x_column, y_column):
    if not numeric_columns:
        raise VisualizationError("No numerical columns were found in this dataset for this chart.")

    # Resolve y (must be numeric)
    if y_column and y_column not in numeric_columns:
        raise VisualizationError(f"'{y_column}' is not a numeric column and cannot be used on the value axis.")
    y = y_column or numeric_columns[0]

    # Resolve x: prefer a categorical/date column, else fall back to row index
    use_index = False
    if x_column:
        if x_column not in df.columns:
            raise VisualizationError(f"Column '{x_column}' was not found in this dataset.")
        x = x_column
    elif categorical_columns:
        x = categorical_columns[0]
    else:
        use_index = True
        x = "Row"

    plot_df = df.copy()
    if use_index:
        plot_df["Row"] = [str(i) for i in range(len(plot_df))]

    plot_df = plot_df[[x, y]].dropna()

    # Too many unique categories makes bar/point charts unreadable - limit to top 25
    if plot_df[x].nunique() > 25:
        plot_df = plot_df.iloc[:25]

    if plot_df.empty:
        raise VisualizationError("Not enough data to build this chart with the selected columns.")

    fig, ax = plt.subplots(figsize=(9, 5))

    try:
        plot_df[x] = plot_df[x].astype(str)
        if chart_type == "bar":
            sns.barplot(data=plot_df, x=x, y=y, ax=ax, hue=x, legend=False)
        elif chart_type == "point":
            sns.pointplot(data=plot_df, x=x, y=y, ax=ax)
    except Exception as e:  # noqa: BLE001
        plt.close(fig)
        raise VisualizationError("This chart could not be generated for the selected columns.") from e

    ax.set_title(f"{CHART_LABELS[chart_type]}: {y} by {x}")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    plt.xticks(rotation=40, ha="right")
    fig.tight_layout()

    image = _fig_to_base64(fig)
    return {
        "image": image,
        "title": f"{CHART_LABELS[chart_type]}: {y} by {x}",
        "chart_type": chart_type,
    }


def _heatmap(df, numeric_columns, columns):
    cols = _validate_numeric_selection(numeric_columns, columns)

    if len(cols) < 2:
        raise VisualizationError("At least two numeric columns are required to build a correlation heatmap.")

    corr = df[cols].corr()

    fig, ax = plt.subplots(figsize=(max(6, len(cols) * 0.9), max(5, len(cols) * 0.8)))
    sns.heatmap(corr, annot=True, cmap="coolwarm", fmt=".2f", ax=ax, square=True, cbar_kws={"shrink": 0.8})
    ax.set_title("Correlation Heatmap of Numeric Columns")
    fig.tight_layout()

    image = _fig_to_base64(fig)
    return {
        "image": image,
        "title": "Correlation Heatmap of Numeric Columns",
        "chart_type": "heatmap",
    }
