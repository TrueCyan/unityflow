import os

UNITY_BRIDGE_HOST = os.environ.get("UNITY_BRIDGE_HOST", "localhost")
UNITY_BRIDGE_PORT = int(os.environ.get("UNITY_BRIDGE_PORT", "29184"))
UNITY_BRIDGE_TIMEOUT = int(os.environ.get("UNITY_BRIDGE_TIMEOUT", "30"))


def base_url():
    return f"http://{UNITY_BRIDGE_HOST}:{UNITY_BRIDGE_PORT}"
