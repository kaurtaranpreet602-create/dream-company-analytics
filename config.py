"""
Dream Company Analytics - Configuration
Student: Taranpreet Kaur | Reg No: 12506996
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "dream-company-analytics-secret-key-2025"

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")

    ALLOWED_EXTENSIONS = {"csv"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB max upload size

    # Screener.in URL handling
    SCREENER_ALLOWED_HOST = "www.screener.in"
    SCREENER_ALT_HOST = "screener.in"
    REQUEST_TIMEOUT = 10  # seconds

    # Blocked hosts / patterns for SSRF protection
    BLOCKED_HOST_PATTERNS = [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "169.254.",   # link-local
        "10.",        # private network
        "192.168.",   # private network
        "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
    ]
