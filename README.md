# Dream Company Analytics
### "Analyze Any Company. Your Way."

**Student:** Taranpreet Kaur | **Reg No:** 12506996 | **University:** Lovely Professional University (LPU)
**Demo Company:** IDBI Bank

A generic, professional analytics dashboard that accepts **any company's CSV file** (or a supported
public Screener.in company page) and instantly generates statistics and visualizations — built on
Flask, Pandas, NumPy, Seaborn and Matplotlib.

---

## 1. Setup on Windows (PyCharm)

Open a terminal inside the project folder (`dream-company-analytics/`) and run:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open your browser and go to:

```
http://127.0.0.1:5000
```

You should see the **Dream Company Analytics** landing page.

> **PyCharm tip:** Open the `dream-company-analytics` folder as a PyCharm project, let PyCharm
> create the virtual environment for you (or use the commands above in the built-in Terminal tab),
> then right-click `app.py` → **Run**.

---

## 2. How to Use

### Method 1 — CSV Upload
1. On the landing page, drag & drop a `.csv` file onto the **CSV Dataset** card, or click
   **Choose CSV File**.
2. The app detects the company name from the filename (editable via **Edit Company Name**).
3. Click **Analyze Dataset** to open the dashboard.

### Method 2 — Screener URL
1. Paste a public company page URL from `screener.in`, e.g. `https://www.screener.in/company/IDBI/`.
2. Click **Analyze URL**.
3. Choose which financial table (Profit & Loss, Balance Sheet, etc.) to analyze.
4. The dashboard opens using the same statistics/visualization engine as CSV uploads.

If a Screener page can't be reached or parsed, the app shows a friendly message and suggests using
CSV upload instead — it will never crash or show a Python traceback.

### Dashboard sections
- **Dashboard** — summary cards (rows, columns, numeric columns, missing values)
- **Dataset** — searchable, paginated data explorer
- **Statistics** — Mean, Median, Mode, Min, Max, Sum, Count, Variance, Std Dev, Skewness,
  Kurtosis, Describe — computed over all or selected numeric columns
- **Visualizations** — Box, Boxen, Strip, Swarm, Bar, Point, Violin plots and a correlation Heatmap
- **Reports** — download a statistics CSV, the last generated chart, or a plain-text summary report
- **Settings** — light/dark mode, current dataset info

Light/Dark mode is remembered across visits via `localStorage`.

---

## 3. Testing Checklist

- ✅ Upload `IDbi.csv` → detects **IDBI Bank**, dashboard header updates automatically
- ✅ Upload any other CSV (e.g. `Tesla.csv`, `HDFC.csv`) → same app, new company name, same
  analytics engine, **no code changes required**
- ✅ All 12 statistics work on any numeric column set
- ✅ All 8 chart types render as images inside the page (no separate Matplotlib windows)
- ✅ Screener URL flow gracefully falls back to a friendly error if the page can't be reached
- ✅ Invalid/empty/non-CSV files show friendly errors, never a traceback

---

## 4. Packaging as a Windows .exe (PyInstaller)

Once you've confirmed the app runs correctly with `python app.py`, you can package it into a
double-click executable.

**Step 1 — Install PyInstaller**
```
pip install pyinstaller
```

**Step 2 — Create a small launcher script** `run_desktop.py` in the project root:

```python
import threading
import webbrowser
import time
from app import app

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    threading.Thread(target=open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
```

**Step 3 — Build the executable**
```
pyinstaller --onefile --add-data "templates;templates" --add-data "static;static" run_desktop.py
```

**Step 4 — Run it**
The finished `.exe` will be inside the `dist/` folder as `run_desktop.exe`. Double-clicking it will:
1. Start the Flask server in the background
2. Automatically open your default browser to `http://127.0.0.1:5000`
3. Dream Company Analytics is ready to use — no terminal required

---

## 5. Project Structure

```
dream-company-analytics/
├── app.py                        # Flask routes / API endpoints
├── config.py                     # App configuration & security settings
├── requirements.txt
├── README.md
├── services/
│   ├── data_service.py           # Load / clean / profile any dataset (dynamic column detection)
│   ├── statistics_service.py     # All 12 statistical functions
│   ├── visualization_service.py  # All 8 Seaborn/Matplotlib charts
│   ├── company_detector.py       # Filename/URL -> readable company name
│   └── screener_service.py       # Screener.in URL fetch + table parsing (secure)
├── templates/
│   ├── index.html                # Landing page (CSV upload + Screener URL)
│   └── dashboard.html            # Sidebar dashboard (Statistics/Visualizations/Reports/etc.)
├── static/
│   ├── css/style.css             # Professional SaaS design system, light/dark mode
│   └── js/app.js                 # Upload, drag-drop, API calls, charts, pagination
├── uploads/                       # (runtime) uploaded CSVs land here temporarily
└── outputs/                       # (runtime) generated report/chart artifacts
```

---

## 6. Important Notes

- **No IDBI lock-in.** IDBI Bank is only the first demo dataset. Numeric columns are always
  detected dynamically via `df.select_dtypes(include="number")` — no company-specific column
  names are ever hard-coded into the analytics engine.
- **No API key required.** The "✨ Explain This Result" button currently returns a rule-based
  explanation. The `/explain-result` route in `app.py` is isolated so a real AI API call
  (Claude/OpenAI/Groq) can be dropped in later without touching the statistics or visualization
  engines.
- **Security.** Screener URL handling only allows `http(s)://screener.in` / `www.screener.in`
  company pages, rejects `file://`, `localhost`, and private/internal IP ranges, and uses request
  timeouts. Uploaded files are validated for type, size and content before being read.
