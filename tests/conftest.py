"""Pytest config — provides a minimal streamlit shim so modules that
import `streamlit` at the top level can be tested without the full library.

Tests for pure logic (sleep_score, sleep_need, alerts evaluators,
notifications.send_email) don't need real Streamlit — only attribute-access
no-ops on `st.cache_data`, `st.secrets`, etc.
"""
from __future__ import annotations

import sys
import types


def _install_streamlit_shim() -> None:
    if "streamlit" in sys.modules:
        return

    class _Cache:
        def __call__(self, *a, **kw):
            # @st.cache_data(...) → returns a decorator
            def deco(fn):
                fn.clear = lambda: None
                return fn
            return deco

        def clear(self): pass

    class _Secrets:
        def __contains__(self, key): return False
        def __getitem__(self, key): raise KeyError(key)
        def get(self, key, default=None): return default

    class _Session(dict):
        def __getattr__(self, k):
            return self.get(k)
        def __setattr__(self, k, v):
            self[k] = v

    st = types.ModuleType("streamlit")
    st.cache_data = _Cache()
    st.secrets = _Secrets()
    st.session_state = _Session()

    # Common no-op functions used at import time
    def _noop(*a, **kw): return None
    for name in (
        "title", "caption", "markdown", "subheader", "divider", "info",
        "warning", "error", "success", "stop", "rerun", "metric",
        "plotly_chart", "dataframe", "columns", "form", "form_submit_button",
        "expander", "tabs", "selectbox", "checkbox", "button", "text_input",
        "text_area", "number_input", "slider", "date_input", "radio", "Page",
        "navigation", "set_page_config", "page_link", "spinner", "json", "code",
    ):
        setattr(st, name, _noop)
    sys.modules["streamlit"] = st


_install_streamlit_shim()
