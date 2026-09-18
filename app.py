"""
Dream Company Analytics - "Analyze Any Company. Your Way."

Student: Taranpreet Kaur | Reg No: 12506996 | LPU
Demo Company: IDBI Bank

Main Flask application.

Run:
    python app.py

Open:
    http://127.0.0.1:5000
"""

import os
import io
import math
import numbers
import traceback
import base64

import pandas as pd

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file
)

from werkzeug.utils import secure_filename

from config import Config
from services import data_service
from services import statistics_service
from services import visualization_service
from services import company_detector
from services import screener_service


# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(
    Config.UPLOAD_FOLDER,
    exist_ok=True
)

os.makedirs(
    Config.OUTPUT_FOLDER,
    exist_ok=True
)


# ============================================================
# CACHE
# ============================================================

# Screener tables are kept in memory.
_screener_cache = {}

# Last generated chart
_last_chart = {
    "image": None,
    "title": None
}


# ============================================================
# JSON SAFETY HELPER
# ============================================================

def _make_json_safe(value):
    """
    Convert NaN, Infinity and other non-JSON values
    into values that JavaScript can safely parse.
    """

    # None
    if value is None:
        return None

    # Dictionary
    if isinstance(value, dict):
        return {
            str(key): _make_json_safe(val)
            for key, val in value.items()
        }

    # List / tuple
    if isinstance(value, (list, tuple)):
        return [
            _make_json_safe(item)
            for item in value
        ]

    # Strings / booleans / integers
    if isinstance(value, (str, bool, int)):
        return value

    # Python float
    if isinstance(value, float):

        if math.isnan(value):
            return None

        if math.isinf(value):
            return None

        return value

    # NumPy / Pandas numbers
    if isinstance(value, numbers.Number):

        try:
            value = value.item()
        except (AttributeError, ValueError, TypeError):
            pass

        if isinstance(value, float):

            if math.isnan(value):
                return None

            if math.isinf(value):
                return None

        return value

    # Pandas missing values
    try:

        missing = pd.isna(value)

        if isinstance(missing, bool) and missing:
            return None

    except (TypeError, ValueError):
        pass

    # NumPy scalar fallback
    if hasattr(value, "item"):

        try:
            converted = value.item()

            if converted is not value:
                return _make_json_safe(converted)

        except (AttributeError, ValueError, TypeError):
            pass

    return value


# ============================================================
# ERROR RESPONSE
# ============================================================

def _error_response(message, status=400):

    return jsonify({
        "success": False,
        "error": str(message)
    }), status


# ============================================================
# DATASET CHECK
# ============================================================

def _require_dataset():

    if not data_service.store.is_loaded():

        raise data_service.DataServiceError(
            "No dataset is currently loaded. "
            "Please upload a CSV or analyze a Screener URL first."
        )


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if not data_service.store.is_loaded():

        return render_template(
            "index.html",
            no_dataset=True
        )

    return render_template(
        "dashboard.html"
    )


# ============================================================
# CSV UPLOAD
# ============================================================

@app.route(
    "/upload",
    methods=["POST"]
)
def upload():

    try:

        # Check file
        if "file" not in request.files:

            return _error_response(
                "No file was included in the request."
            )

        file = request.files["file"]

        # Check filename
        if file.filename == "":

            return _error_response(
                "No file was selected."
            )

        # Check extension
        if not file.filename.lower().endswith(".csv"):

            return _error_response(
                "Only CSV files are supported. "
                "Please choose a .csv file."
            )

        safe_name = secure_filename(
            file.filename
        )

        # Load CSV
        df, source_name = (
            data_service.load_csv_from_filestorage(
                file
            )
        )

        # Detect company
        company_name = (
            company_detector.detect_company_name(
                safe_name
            )
        )

        # Store dataset
        data_service.store.set_dataset(
            df,
            company_name,
            safe_name,
            "csv"
        )

        # Create profile
        profile = (
            data_service.get_dataset_profile(
                df,
                company_name,
                safe_name
            )
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "message": "Dataset loaded successfully.",
                "profile": profile
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )

    except Exception:

        app.logger.error(
            traceback.format_exc()
        )

        return _error_response(
            "An unexpected error occurred while "
            "processing the file. Please try again.",
            500
        )


# ============================================================
# UPDATE COMPANY NAME
# ============================================================

@app.route(
    "/update-company-name",
    methods=["POST"]
)
def update_company_name():

    try:

        _require_dataset()

        payload = (
            request.get_json(
                silent=True
            ) or {}
        )

        new_name = (
            payload.get(
                "company_name"
            ) or ""
        ).strip()

        if not new_name:

            return _error_response(
                "Company name cannot be empty."
            )

        data_service.store.company_name = (
            new_name
        )

        return jsonify({
            "success": True,
            "company_name": new_name
        })

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )


# ============================================================
# SCREENER URL
# ============================================================

@app.route(
    "/analyze-url",
    methods=["POST"]
)
def analyze_url():

    try:

        payload = (
            request.get_json(
                silent=True
            ) or {}
        )

        url = (
            payload.get("url")
            or ""
        ).strip()

        if not url:

            return _error_response(
                "Please enter a Screener company URL."
            )

        # ----------------------------------------------------
        # Fetch Screener data
        # ----------------------------------------------------

        result = (
            screener_service.fetch_screener_tables(
                url
            )
        )

        # ----------------------------------------------------
        # Store DataFrames in memory
        # ----------------------------------------------------

        cache_key = url

        _screener_cache[
            cache_key
        ] = result["tables"]

        # ----------------------------------------------------
        # IMPORTANT FIX
        #
        # Screener tables can contain NaN.
        # JavaScript JSON.parse() does NOT accept NaN.
        #
        # Convert:
        #     NaN       -> null
        #     Infinity  -> null
        #     -Infinity -> null
        # ----------------------------------------------------

        response_data = {
            "success": True,
            "cache_key": cache_key,
            "company_name": result.get(
                "company_name",
                "Unknown Company"
            ),
            "sections": result.get(
                "sections",
                []
            )
        }

        response_data = _make_json_safe(
            response_data
        )

        return jsonify(
            response_data
        )

    except screener_service.ScreenerError as e:

        return _error_response(
            str(e)
        )

    except Exception:

        app.logger.error(
            traceback.format_exc()
        )

        return _error_response(
            "Unable to retrieve data from this "
            "Screener page. Please check the URL "
            "or use CSV upload instead.",
            500
        )


# ============================================================
# SELECT SCREENER TABLE
# ============================================================

@app.route(
    "/select-screener-table",
    methods=["POST"]
)
def select_screener_table():

    try:

        payload = (
            request.get_json(
                silent=True
            ) or {}
        )

        cache_key = payload.get(
            "cache_key"
        )

        table_key = payload.get(
            "table_key"
        )

        company_name = (
            payload.get(
                "company_name"
            ) or ""
        ).strip()

        if not company_name:
            company_name = "Unknown Company"

        # Check cache
        if cache_key not in _screener_cache:

            return _error_response(
                "This Screener session has expired. "
                "Please analyze the URL again."
            )

        tables = _screener_cache[
            cache_key
        ]

        # Check selected table
        if table_key not in tables:

            return _error_response(
                "The selected table could not be found."
            )

        raw_df = tables[
            table_key
        ]

        # Convert DataFrame into normal application dataset
        df, source_name = (
            data_service.load_csv_from_dataframe_source(
                raw_df,
                cache_key
            )
        )

        # Store dataset
        data_service.store.set_dataset(
            df,
            company_name,
            cache_key,
            "url"
        )

        # Profile
        profile = (
            data_service.get_dataset_profile(
                df,
                company_name,
                cache_key
            )
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "message": "Screener data loaded successfully.",
                "profile": profile
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )

    except Exception:

        app.logger.error(
            traceback.format_exc()
        )

        return _error_response(
            "An unexpected error occurred while "
            "loading this Screener table.",
            500
        )


# ============================================================
# DATASET PROFILE
# ============================================================

@app.route(
    "/dataset-profile",
    methods=["GET"]
)
def dataset_profile():

    try:

        _require_dataset()

        store = data_service.store

        profile = (
            data_service.get_dataset_profile(
                store.df,
                store.company_name,
                store.source_name
            )
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "profile": profile
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )


# ============================================================
# DATASET EXPLORER
# ============================================================

@app.route(
    "/dataset",
    methods=["GET"]
)
def dataset():

    try:

        _require_dataset()

        store = data_service.store

        page = request.args.get(
            "page",
            default=1,
            type=int
        )

        page_size = request.args.get(
            "page_size",
            default=10,
            type=int
        )

        search = request.args.get(
            "search",
            default="",
            type=str
        )

        preview = (
            data_service.get_dataframe_preview(
                store.df,
                page=page,
                page_size=page_size,
                search=search
            )
        )

        dtypes = (
            data_service.get_column_dtypes(
                store.df
            )
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "preview": preview,
                "dtypes": dtypes
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )


# ============================================================
# STATISTICS
# ============================================================

@app.route(
    "/statistics",
    methods=["POST"]
)
def statistics():

    try:

        _require_dataset()

        store = data_service.store

        payload = (
            request.get_json(
                silent=True
            ) or {}
        )

        function_name = payload.get(
            "function"
        )

        selected_columns = (
            payload.get(
                "columns"
            ) or None
        )

        numeric_columns = (
            data_service.get_numeric_columns(
                store.df
            )
        )

        result = (
            statistics_service.compute_statistic(
                store.df,
                numeric_columns,
                function_name,
                selected_columns
            )
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "result": result
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )

    except statistics_service.StatisticsError as e:

        return _error_response(
            str(e)
        )

    except Exception:

        app.logger.error(
            traceback.format_exc()
        )

        return _error_response(
            "An unexpected error occurred while "
            "computing statistics.",
            500
        )


# ============================================================
# VISUALIZATION
# ============================================================

@app.route(
    "/visualization",
    methods=["POST"]
)
def visualization():

    try:

        _require_dataset()

        store = data_service.store

        payload = (
            request.get_json(
                silent=True
            ) or {}
        )

        chart_type = payload.get(
            "chart_type"
        )

        x_column = payload.get(
            "x_column"
        )

        y_column = payload.get(
            "y_column"
        )

        columns = (
            payload.get(
                "columns"
            ) or None
        )

        numeric_columns = (
            data_service.get_numeric_columns(
                store.df
            )
        )

        categorical_columns = (
            data_service.get_categorical_columns(
                store.df
            )
        )

        chart = (
            visualization_service.generate_chart(
                store.df,
                numeric_columns,
                categorical_columns,
                chart_type,
                x_column=x_column,
                y_column=y_column,
                columns=columns
            )
        )

        # Save last chart
        _last_chart["image"] = (
            chart["image"]
        )

        _last_chart["title"] = (
            chart["title"]
        )

        return jsonify(
            _make_json_safe({
                "success": True,
                "chart": chart
            })
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )

    except visualization_service.VisualizationError as e:

        return _error_response(
            str(e)
        )

    except Exception:

        app.logger.error(
            traceback.format_exc()
        )

        return _error_response(
            "An unexpected error occurred while "
            "generating the chart.",
            500
        )


# ============================================================
# DOWNLOAD CHART
# ============================================================

@app.route(
    "/download-chart",
    methods=["GET"]
)
def download_chart():

    if not _last_chart["image"]:

        return _error_response(
            "No chart has been generated yet."
        )

    try:

        header, encoded = (
            _last_chart["image"].split(
                ",",
                1
            )
        )

        binary = base64.b64decode(
            encoded
        )

    except Exception:

        return _error_response(
            "The generated chart could not be downloaded.",
            500
        )

    filename = (
        (_last_chart["title"] or "chart")
        .replace(" ", "_")
        + ".png"
    )

    return send_file(
        io.BytesIO(binary),
        mimetype="image/png",
        as_attachment=True,
        download_name=filename
    )


# ============================================================
# DOWNLOAD STATISTICS
# ============================================================

@app.route(
    "/download-statistics",
    methods=["GET"]
)
def download_statistics():

    try:

        _require_dataset()

        store = data_service.store

        numeric_columns = (
            data_service.get_numeric_columns(
                store.df
            )
        )

        if not numeric_columns:

            return _error_response(
                "No numerical columns were found "
                "in this dataset."
            )

        summary = (
            store.df[
                numeric_columns
            ]
            .describe()
            .transpose()
        )

        summary.index.name = "Column"

        buffer = io.StringIO()

        summary.to_csv(
            buffer
        )

        memory = io.BytesIO(
            buffer.getvalue().encode(
                "utf-8"
            )
        )

        memory.seek(0)

        filename = (
            (store.company_name or "company")
            .replace(" ", "_")
            + "_statistics.csv"
        )

        return send_file(
            memory,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )


# ============================================================
# SUMMARY REPORT
# ============================================================

@app.route(
    "/generate-summary-report",
    methods=["GET"]
)
def generate_summary_report():

    try:

        _require_dataset()

        store = data_service.store

        profile = (
            data_service.get_dataset_profile(
                store.df,
                store.company_name,
                store.source_name
            )
        )

        numeric_columns = (
            profile["numeric_columns"]
        )

        lines = []

        lines.append(
            "DREAM COMPANY ANALYTICS - SUMMARY REPORT"
        )

        lines.append(
            f"Company: {profile['company_name']}"
        )

        lines.append(
            f"Source: {profile['source_name']}"
        )

        lines.append("")

        lines.append(
            f"Rows: {profile['rows']}"
        )

        lines.append(
            f"Columns: {profile['columns']}"
        )

        lines.append(
            f"Numeric Columns: "
            f"{profile['numeric_column_count']}"
        )

        lines.append(
            f"Categorical Columns: "
            f"{profile['categorical_column_count']}"
        )

        lines.append(
            f"Missing Values: "
            f"{profile['missing_values']}"
        )

        lines.append(
            f"Duplicate Rows: "
            f"{profile['duplicate_rows']}"
        )

        lines.append("")

        if numeric_columns:

            lines.append(
                "KEY STATISTICS "
                "(Mean / Std Dev per numeric column):"
            )

            means = (
                store.df[
                    numeric_columns
                ].mean(
                    numeric_only=True
                )
            )

            stds = (
                store.df[
                    numeric_columns
                ].std(
                    numeric_only=True
                )
            )

            for col in numeric_columns:

                mean_value = means[col]
                std_value = stds[col]

                mean_text = (
                    "N/A"
                    if pd.isna(mean_value)
                    else f"{mean_value:.2f}"
                )

                std_text = (
                    "N/A"
                    if pd.isna(std_value)
                    else f"{std_value:.2f}"
                )

                lines.append(
                    f"  - {col}: "
                    f"mean={mean_text}, "
                    f"std={std_text}"
                )

        else:

            lines.append(
                "No numerical columns were found "
                "in this dataset."
            )

        report_text = "\n".join(
            lines
        )

        memory = io.BytesIO(
            report_text.encode(
                "utf-8"
            )
        )

        memory.seek(0)

        filename = (
            (store.company_name or "company")
            .replace(" ", "_")
            + "_summary_report.txt"
        )

        return send_file(
            memory,
            mimetype="text/plain",
            as_attachment=True,
            download_name=filename
        )

    except data_service.DataServiceError as e:

        return _error_response(
            str(e)
        )


# ============================================================
# EXPLAIN RESULT
# ============================================================

@app.route(
    "/explain-result",
    methods=["POST"]
)
def explain_result():

    payload = (
        request.get_json(
            silent=True
        ) or {}
    )

    context = payload.get(
        "context",
        "this result"
    )

    explanation = (
        f"This is a rule-based explanation for "
        f"{context}. "
        "Higher values generally indicate larger "
        "magnitude for that metric relative to "
        "other columns or time periods in the "
        "dataset. For a deeper, AI-generated "
        "explanation, connect an AI API key in "
        "a future version of this application."
    )

    return jsonify({
        "success": True,
        "explanation": explanation
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(413)
def file_too_large(e):

    return _error_response(
        "The uploaded file is too large. "
        "Maximum size is 10 MB.",
        413
    )


@app.errorhandler(404)
def not_found(e):

    return _error_response(
        "The requested resource was not found.",
        404
    )


@app.errorhandler(500)
def server_error(e):

    app.logger.error(
        traceback.format_exc()
    )

    return _error_response(
        "An unexpected server error occurred. "
        "Please try again.",
        500
    )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print(" DREAM COMPANY ANALYTICS")
    print(" Analyze Any Company. Your Way.")
    print("=" * 60)

    print(
        " Open this URL in your browser: "
        "http://127.0.0.1:5000"
    )

    print("=" * 60)

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000,
        use_reloader=False
    )