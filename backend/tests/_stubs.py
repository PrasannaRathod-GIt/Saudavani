"""Import helper: lets the tests import main.py even where fastapi/httpx/pydantic/groq are not installed.
Real packages are always preferred; stubs are installed only when an import fails."""
import importlib
import sys
import types


def install_stubs_if_needed() -> None:
    def missing(name: str) -> bool:
        try:
            importlib.import_module(name)
            return False
        except Exception:
            return True

    if missing("httpx") and "httpx" not in sys.modules:
        sys.modules["httpx"] = types.ModuleType("httpx")
    if missing("pydantic"):
        m = types.ModuleType("pydantic")

        class BaseModel:  # minimal stand-in
            pass

        m.BaseModel = BaseModel
        m.Field = lambda *a, **k: None
        sys.modules["pydantic"] = m
    if missing("fastapi"):
        fa = types.ModuleType("fastapi")

        class _App:
            def __init__(self, *a, **k):
                pass

            def _deco(self, *a, **k):
                return lambda fn: fn

            get = post = put = delete = websocket = on_event = _deco

            def add_middleware(self, *a, **k):
                pass

        class _Exc(Exception):
            def __init__(self, *a, **k):
                super().__init__(*a)

        fa.FastAPI = _App
        fa.File = fa.Form = lambda *a, **k: None
        fa.HTTPException = _Exc
        fa.UploadFile = object
        fa.WebSocket = object
        fa.WebSocketDisconnect = _Exc
        sys.modules["fastapi"] = fa
        cm = types.ModuleType("fastapi.middleware.cors")
        cm.CORSMiddleware = object
        mw = types.ModuleType("fastapi.middleware")
        sys.modules["fastapi.middleware"] = mw
        sys.modules["fastapi.middleware.cors"] = cm