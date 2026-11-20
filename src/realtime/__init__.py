"""The chat server (T11.4a, D24): real-time messages between a coach and a client.

`tokens` mints and checks the signed, short-lived token the Streamlit page hands the browser;
`app` is the FastAPI app with the one WebSocket; `server` runs it with uvicorn on this machine.
"""
