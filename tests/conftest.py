import os, sys, tempfile
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hansonglive-test-")
os.environ.pop("LIVE_PASSWORD", None)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
