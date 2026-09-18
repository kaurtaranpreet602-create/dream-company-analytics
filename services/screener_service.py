"""
screener_service.py

Fetches publicly accessible Screener.in company pages,
extracts financial HTML tables, and converts them into
Pandas DataFrames for Dream Company Analytics.
"""

import re
from io import StringIO
from urllib.parse import urlparse

import pandas as pd
import requests

from config import Config


class ScreenerError(Exception):
    """User-friendly Screener error."""
    pass


# ============================================================
# URL VALIDATION
# ============================================================

def _validate_url(url: str) -> str:
    """Validate Screener company URL."""

    if not url or not isinstance(url, str):
        raise ScreenerError(
            "Please provide a Screener company URL."
        )

    url = url.strip()

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ScreenerError(
            "Only http:// and https:// URLs are supported."
        )

    host = (parsed.hostname or "").lower()

    if not host:
        raise ScreenerError(
            "This does not look like a valid URL."
        )

    # Allowed Screener domains
    allowed_hosts = {
        "screener.in",
        "www.screener.in"
    }

    if host not in allowed_hosts:
        raise ScreenerError(
            "Only Screener.in company pages are supported."
        )

    # Company page required
    if "/company/" not in parsed.path.lower():
        raise ScreenerError(
            "Please enter a valid Screener company URL.\n"
            "Example: https://www.screener.in/company/IDBI/"
        )

    return url


# ============================================================
# FETCH SCREENER DATA
# ============================================================

def fetch_screener_tables(url: str):
    """
    Fetch a Screener company page and extract HTML tables.

    Returns:
        {
            "company_name": str,
            "sections": list,
            "tables": dict
        }
    """

    url = _validate_url(url)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    # --------------------------------------------------------
    # Request page
    # --------------------------------------------------------

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=getattr(
                Config,
                "REQUEST_TIMEOUT",
                20
            ),
            allow_redirects=True
        )

    except requests.exceptions.Timeout as exc:
        raise ScreenerError(
            "Screener took too long to respond. "
            "Please try again."
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise ScreenerError(
            "Unable to connect to Screener.in. "
            "Please check your internet connection."
        ) from exc

    # --------------------------------------------------------
    # HTTP errors
    # --------------------------------------------------------

    if response.status_code == 404:
        raise ScreenerError(
            "The Screener company page was not found. "
            "Please check the URL."
        )

    if response.status_code in (401, 403):
        raise ScreenerError(
            "Screener has restricted access to this page. "
            "Please use CSV upload instead."
        )

    if response.status_code == 429:
        raise ScreenerError(
            "Screener is temporarily limiting requests. "
            "Please wait and try again."
        )

    if response.status_code != 200:
        raise ScreenerError(
            f"Screener returned HTTP {response.status_code}."
        )

    html = response.text

    if not html.strip():
        raise ScreenerError(
            "Screener returned an empty page."
        )

    # --------------------------------------------------------
    # Parse HTML tables
    #
    # IMPORTANT:
    # pandas 3.x requires StringIO here.
    # --------------------------------------------------------

    try:
        tables = pd.read_html(
            StringIO(html),
            flavor="lxml"
        )

    except ValueError as exc:
        raise ScreenerError(
            "No financial tables were found on this "
            "Screener page."
        ) from exc

    except Exception as exc:
        raise ScreenerError(
            f"Could not parse Screener data: {exc}"
        ) from exc

    if not tables:
        raise ScreenerError(
            "No usable financial tables were found."
        )

    # --------------------------------------------------------
    # Company name
    # --------------------------------------------------------

    company_name = _extract_company_name(
        html,
        url
    )

    # --------------------------------------------------------
    # Prepare tables
    # --------------------------------------------------------

    sections = []
    cleaned_tables = {}

    for index, table in enumerate(tables):

        if table is None or table.empty:
            continue

        if table.shape[1] < 2:
            continue

        try:
            cleaned = _clean_table(table)
        except Exception:
            continue

        if cleaned.empty:
            continue

        key = f"table_{index}"

        label = _detect_table_type(cleaned)

        cleaned_tables[key] = cleaned

        sections.append({
            "key": key,
            "label": label,
            "columns": [
                str(column)
                for column in cleaned.columns
            ],
            "row_count": int(
                cleaned.shape[0]
            ),
            "preview_rows": (
                cleaned
                .head(5)
                .astype(str)
                .to_dict(
                    orient="records"
                )
            )
        })

    if not cleaned_tables:
        raise ScreenerError(
            "Screener page was found, but no usable "
            "financial tables could be extracted."
        )

    return {
        "company_name": company_name,
        "sections": sections,
        "tables": cleaned_tables
    }


# ============================================================
# CLEAN DATAFRAME
# ============================================================

def _clean_table(table: pd.DataFrame) -> pd.DataFrame:
    """Clean a Screener HTML table."""

    table = table.copy()

    # --------------------------------------------------------
    # Handle MultiIndex columns
    # --------------------------------------------------------

    if isinstance(
        table.columns,
        pd.MultiIndex
    ):
        columns = []

        for column in table.columns:

            parts = []

            for value in column:

                value = str(value).strip()

                if (
                    value
                    and value.lower() != "nan"
                    and value not in parts
                ):
                    parts.append(value)

            columns.append(
                " ".join(parts)
                if parts
                else "Column"
            )

        table.columns = columns

    else:
        table.columns = [
            str(column).strip()
            for column in table.columns
        ]

    # --------------------------------------------------------
    # Remove empty rows and columns
    # --------------------------------------------------------

    table = table.dropna(
        axis=0,
        how="all"
    )

    table = table.dropna(
        axis=1,
        how="all"
    )

    if table.empty:
        return table

    # --------------------------------------------------------
    # Clean column names
    # --------------------------------------------------------

    new_columns = []

    for column in table.columns:

        column = re.sub(
            r"\s+",
            " ",
            str(column)
        ).strip()

        if not column:
            column = "Column"

        new_columns.append(column)

    table.columns = new_columns

    # --------------------------------------------------------
    # Convert numeric columns
    # --------------------------------------------------------

    for column in table.columns:

        # Keep first column as text because it normally
        # contains names such as Sales, Expenses, etc.
        if column == table.columns[0]:
            continue

        values = (
            table[column]
            .astype(str)
            .str.strip()
            .str.replace(
                ",",
                "",
                regex=False
            )
            .str.replace(
                "%",
                "",
                regex=False
            )
            .str.replace(
                "₹",
                "",
                regex=False
            )
            .str.replace(
                "Rs.",
                "",
                regex=False
            )
            .str.replace(
                "Rs",
                "",
                regex=False
            )
        )

        values = values.replace(
            {
                "-": None,
                "—": None,
                "–": None,
                "": None,
                "nan": None,
                "NaN": None
            }
        )

        numeric_values = pd.to_numeric(
            values,
            errors="coerce"
        )

        # Convert if at least 40% of non-empty values
        # are numeric.
        non_empty = values.notna().sum()
        numeric_count = numeric_values.notna().sum()

        if (
            non_empty > 0
            and numeric_count >= max(
                1,
                int(non_empty * 0.40)
            )
        ):
            table[column] = numeric_values

    return table.reset_index(drop=True)


# ============================================================
# COMPANY NAME
# ============================================================

def _extract_company_name(
    html: str,
    url: str
) -> str:
    """Extract company name from page title or URL."""

    # Try title
    match = re.search(
        r"<title[^>]*>(.*?)</title>",
        html,
        flags=re.IGNORECASE | re.DOTALL
    )

    if match:

        title = match.group(1)

        # Remove HTML tags
        title = re.sub(
            r"<[^>]+>",
            " ",
            title
        )

        # Remove extra spaces
        title = re.sub(
            r"\s+",
            " ",
            title
        ).strip()

        # Remove Screener suffix
        title = re.sub(
            r"\s*[-|]\s*Screener.*$",
            "",
            title,
            flags=re.IGNORECASE
        ).strip()

        if title:
            return title

    # Try URL
    parsed = urlparse(url)

    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    try:
        company_index = parts.index(
            "company"
        )

        if company_index + 1 < len(parts):

            slug = parts[
                company_index + 1
            ]

            return slug.replace(
                "-",
                " "
            ).title()

    except ValueError:
        pass

    return "Unknown Company"


# ============================================================
# TABLE TYPE DETECTION
# ============================================================

def _detect_table_type(
    table: pd.DataFrame
) -> str:
    """Identify the type of Screener financial table."""

    try:
        text = " ".join(
            table.astype(str)
            .fillna("")
            .values
            .flatten()
        ).lower()

    except Exception:
        return "Financial Table"

    # Profit & Loss
    if (
        "operating profit" in text
        or "net profit" in text
        or "expenses" in text
        or "sales" in text
    ):
        return "Profit & Loss"

    # Balance Sheet
    if (
        "total assets" in text
        or "total liabilities" in text
        or "equity capital" in text
        or "reserves" in text
    ):
        return "Balance Sheet"

    # Cash Flow
    if (
        "cash from operating activity" in text
        or "cash from investing activity" in text
        or "cash from financing activity" in text
        or "net cash flow" in text
    ):
        return "Cash Flow"

    # Ratios
    if (
        "debtor days" in text
        or "inventory days" in text
        or "days payable" in text
        or "roce" in text
        or "roe" in text
    ):
        return "Ratios"

    # Shareholding
    if (
        "promoters" in text
        or "fii" in text
        or "dii" in text
    ):
        return "Shareholding Pattern"

    # Quarterly
    if (
        "mar 202" in text
        or "jun 202" in text
        or "sep 202" in text
        or "dec 202" in text
    ):
        return "Quarterly Results"

    return "Financial Table"