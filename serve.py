"""Run FitKompass with real-time messages: `streamlit run serve.py` (T11.4b, D24).

The pages are app.py's; this wrapper mounts the chat socket on the same server, port and process
(`src/realtime/server.py`), reading and writing the same store as the pages: in demo mode the
temporary one the pages make. `streamlit run app.py` alone runs the pages without the socket.
`streamlit run` finds the ASGI app by reading this file for `app = st.App(...)`, so the call stays
here, written out.
"""

from pathlib import Path

import streamlit as st

from src.realtime import server
from views import account

app = st.App(
    str(Path(__file__).with_name("app.py")),
    routes=server.chat_routes(store_path=account.store_path),
    lifespan=server.quiet_library_logs,
)
