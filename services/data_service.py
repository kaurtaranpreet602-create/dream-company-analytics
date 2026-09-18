"""
data_service.py
Central data engine. Loads a CSV ONCE into memory, cleans it, and
exposes dynamic type detection (numeric / categorical / date columns)
so the SAME engine works with any company's dataset.

The loaded dataset is cached in-process (DataStore) so the app does
NOT reload the CSV on every request.
"""

import os
import io
import pandas as pd
import numpy as np


class DataStore:
    """Very small in-memory single-dataset cache (per server process)."""

    def __init__(self):
        self.df = None
        self.company_name = None
        self.source_name = None
        self.source_type = None  # 'csv' or 'url'

    def is_loaded(self):
        return self.df is not None

    def set_dataset(self, df, company_name, source_name, source_type):
        self.df = df
        self.company_name = company_name
        self.source_name = source_name
        self.source_type = source_type

    def clear(self):
        self.df = None
        self.company_name = None
        self.source_name = None
        self.source_type = None


# Single global store instance used by the whole Flask app
store = DataStore()


class DataServiceError(Exception):
    """Raised for any user-facing, friendly data error."""
    pass


def load_csv_from_filestorage(file_storage):
    """
    Load a CSV from a Flask FileStorage object (uploaded file).
    Performs validation and returns a cleaned DataFrame.
    """
    filename = file_storage.filename or ""

    if not filename.lower().endswith(".csv"):
        raise DataServiceError("Only CSV files are supported. Please upload a .csv file.")

    raw_bytes = file_storage.read()

    if not raw_bytes or len(raw_bytes.strip()) == 0:
        raise DataServiceError("The uploaded file is empty. Please choose a valid CSV file.")

    df = _read_csv_bytes(raw_bytes)
    df = clean_dataframe(df)
    return df, filename


def load_csv_from_dataframe_source(df, source_label):
    """Used by the Screener service to hand off an already-built DataFrame."""
    df = clean_dataframe(df)
    return df, source_label


def _read_csv_bytes(raw_bytes):
    """Try a few common encodings before giving up with a friendly error."""
    encodings_to_try = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
    last_error = None

    for enc in encodings_to_try:
        try:
            text = raw_bytes.decode(enc)
            df = pd.read_csv(io.StringIO(text))
            if df.shape[1] == 0:
                raise DataServiceError("The CSV file does not contain any columns.")
            return df
        except DataServiceError:
            raise
        except Exception as e:  # noqa: BLE001
            last_error = e
            continue

    raise DataServiceError(
        "This CSV file could not be read. It may be corrupted or use an "
        "unsupported encoding. Please check the file and try again."
    )


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generic cleaning that works for ANY dataset:
      - drop fully-empty rows/columns
      - strip whitespace from column names
      - attempt to parse obvious date columns
      - coerce numeric-looking object columns to numeric
    """
    if df is None or df.empty:
        raise DataServiceError("The dataset is empty. Please upload a CSV file that contains data.")

    # Drop rows/columns that are entirely empty
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")

    if df.empty:
        raise DataServiceError("The dataset has no usable rows after cleaning.")

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]

    # Try to coerce object columns that look numeric (e.g. "1,234" or " 45 ")
    for col in df.columns:
        if df[col].dtype == object:
            cleaned = df[col].astype(str).str.replace(",", "", regex=False).str.strip()
            numeric_attempt = pd.to_numeric(cleaned, errors="coerce")
            # Only convert if the vast majority of non-null values parsed successfully
            non_null = df[col].notna().sum()
            if non_null > 0 and numeric_attempt.notna().sum() / non_null >= 0.8:
                df[col] = numeric_attempt

    # Try to detect date-like columns (object dtype, name suggests a date, or parses well)
    for col in df.columns:
        if df[col].dtype == object:
            col_lower = str(col).lower()
            looks_like_date = any(k in col_lower for k in ["date", "year", "month", "period"])
            if looks_like_date:
                parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
                if parsed.notna().sum() / max(len(df), 1) >= 0.5:
                    df[col] = parsed

    df = df.reset_index(drop=True)
    return df


def get_numeric_columns(df: pd.DataFrame):
    return list(df.select_dtypes(include="number").columns)


def get_categorical_columns(df: pd.DataFrame):
    return list(df.select_dtypes(include=["object", "category"]).columns)


def get_date_columns(df: pd.DataFrame):
    return list(df.select_dtypes(include=["datetime64[ns]", "datetime64"]).columns)


def get_dataset_profile(df: pd.DataFrame, company_name: str, source_name: str):
    numeric_cols = get_numeric_columns(df)
    categorical_cols = get_categorical_columns(df)
    date_cols = get_date_columns(df)

    missing_values = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    return {
        "company_name": company_name,
        "source_name": source_name,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "numeric_columns": numeric_cols,
        "numeric_column_count": len(numeric_cols),
        "categorical_columns": categorical_cols,
        "categorical_column_count": len(categorical_cols),
        "date_columns": date_cols,
        "date_column_count": len(date_cols),
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "all_columns": list(df.columns),
    }


def get_dataframe_preview(df: pd.DataFrame, page=1, page_size=10, search=""):
    """Return a paginated, optionally search-filtered preview of the dataframe."""
    working = df

    if search:
        mask = working.astype(str).apply(
            lambda row: row.str.contains(search, case=False, na=False)
        ).any(axis=1)
        working = working[mask]

    total_rows = len(working)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    page_df = working.iloc[start:end]

    # Replace NaN/NaT with None for clean JSON, and datetimes with strings
    page_df = page_df.copy()
    for col in page_df.columns:
        if pd.api.types.is_datetime64_any_dtype(page_df[col]):
            page_df[col] = page_df[col].dt.strftime("%Y-%m-%d")
    page_df = page_df.where(pd.notnull(page_df), None)

    return {
        "columns": list(df.columns),
        "rows": page_df.to_dict(orient="records"),
        "total_rows": total_rows,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_column_dtypes(df: pd.DataFrame):
    result = {}
    for col in df.columns:
        dtype = df[col].dtype
        if pd.api.types.is_numeric_dtype(dtype):
            result[col] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            result[col] = "date"
        else:
            result[col] = "categorical"
    return result
