"""Real-time messages (T11.4a, T11.4b, D24) between a coach and a client.

`tokens` mints and checks the signed, short-lived token the Streamlit page hands the browser;
`app` is the FastAPI app with the one WebSocket; `server` mounts it on Streamlit's own server
(`serve.py`); `page` builds what the Messages page hands its browser component.
"""
