"""The chat server's settings (T11.4a, D24): its address, the token's lifetime and its limits.

The token's secret is read in `environment` (`chat_token_secret()`), like every other secret.
"""

# Bound to this machine only: the server is never reachable from another host.
CHAT_SERVER_HOST = "127.0.0.1"
# Not 8502: Streamlit moves to the next free port when 8501 is taken.
CHAT_SERVER_PORT = 8510
# The socket's one path; the thread is in the token, never in the path or a query string.
CHAT_SOCKET_PATH = "/ws"
# The pages allowed to open a socket: the Streamlit app opened on this machine. A browser always
# sends the page's origin with a WebSocket handshake; one with another origin, or none, is refused.
CHAT_ALLOWED_ORIGINS = frozenset({"http://localhost:8501", "http://127.0.0.1:8501"})
# How long a token is valid (T11.4a): short, so a stolen one is soon useless, and the page renews it
# on an open socket long before it ends. Read at call time, so a test can patch it.
CHAT_TOKEN_TTL_SECONDS = 15 * 60
# A token longer than this is refused before it is decoded (a real one is about 200 characters).
CHAT_TOKEN_MAX_CHARS = 1024
# The clock difference a token's expiry may show (both processes read this machine's clock; one
# second covers rounding to whole seconds).
CHAT_TOKEN_SKEW_SECONDS = 1
# How long the server waits for a new socket's first message (the token) before closing it.
CHAT_AUTH_WAIT_SECONDS = 10.0
# The most messages one frame of catch-up holds; a frame with more to come says so ("more").
CHAT_CATCH_UP_LIMIT = 100
# The largest frame the server reads: a message of MESSAGE_MAX_CHARS characters, each up to four
# bytes in UTF-8, in its JSON envelope, with room to spare.
CHAT_MAX_FRAME_BYTES = 8 * 1024
# The close codes. One code for every refusal (a bad, expired or foreign token, a missing token, a
# late token, a frame that is not one the server knows), so a close never says which check failed;
# another for an error inside the server.
CHAT_CLOSE_REFUSED = 4401
CHAT_CLOSE_ERROR = 1011
# The fixed error a sender gets when the store refuses a message (never the reason).
CHAT_ERROR_NOT_SENT = "not_sent"
