import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("FRED_API_KEY", "test-key")
os.environ.setdefault("ESTAT_APP_ID", "test-app-id")
os.environ.setdefault("INSEE_API_KEY", "test-token")
