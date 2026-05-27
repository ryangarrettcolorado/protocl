# Protocōl Design System

This folder contains the source of truth for the Protocōl brand and UI tokens.

## Files
- `protocol.tokens.json` — W3C-format design tokens (colors, type, space, motion).
- See `/app/styles/brand.py` for the Streamlit injector that consumes these tokens.

## Usage in Streamlit
```python
import streamlit as st
from app.styles.brand import inject_brand_css, render_header

st.set_page_config(
    page_title="Protocōl — Personal Health Intelligence OS",
    page_icon="assets/protocol-icon.svg",
    layout="wide",
)
inject_brand_css()
render_header()
```

## Updating tokens
1. Edit `design/protocol.tokens.json`.
2. Restart the Streamlit app — `inject_brand_css()` re-reads on each run.
3. Commit with a `style:` Conventional Commit prefix.
