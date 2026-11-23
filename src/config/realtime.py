"""The real-time messages' settings (T11.4a, T11.4b, D24): the socket's path, the token, the limits.

The chat socket is mounted on Streamlit's own server (`serve.py`, `st.App`), so it has the page's
host and port. The token's secret is read in `environment` (`chat_token_secret()`), like every
other secret.
"""

# Where the chat app is mounted on Streamlit's server, and its one socket inside it: the browser
# opens `<mount><socket>` on the page's own host and port. The thread is in the token, never in the
# path or a query string.
# Not /chat: that is the coach's chat page, which a reload would then send to the socket's app.
CHAT_MOUNT_PATH = "/realtime"
CHAT_SOCKET_PATH = "/ws"
# The hosts a local page may be opened at. The socket's allowed origins are these hosts on the port
# Streamlit is serving (which it moves to 8502 when 8501 is taken), plus CHAT_PUBLIC_ORIGINS. A
# browser always sends the page's origin with a WebSocket handshake; one with another origin, or
# none, is refused, which also keeps out a page that rebinds its own name to this machine.
CHAT_LOCAL_HOSTS = ("localhost", "127.0.0.1")
# A public deployment's own https origin goes here, with the items in docs/DEPLOYMENT.md; none yet.
CHAT_PUBLIC_ORIGINS: frozenset[str] = frozenset()
# How long a token is valid (T11.4a): short, so a stolen one is soon useless, and the page renews it
# on an open socket long before it ends. Read at call time, so a test can patch it.
CHAT_TOKEN_TTL_SECONDS = 15 * 60
# How long before its token expires the page asks for a new one (a rerun of the thread's fragment).
# Two minutes leave room for a slow rerun; the server closes a socket whose token expired.
CHAT_TOKEN_RENEW_BEFORE_SECONDS = 2 * 60
# How long the page waits for a renewal's rerun on a live socket before it asks again: a quarter
# of the margin above, so a slow rerun is not asked for twice and the token still has time left.
CHAT_RENEW_RETRY_SECONDS = 30
# A token longer than this is refused before it is decoded (a real one is about 200 characters).
CHAT_TOKEN_MAX_CHARS = 1024
# The clock difference a token's expiry may show (the page and the socket read the same clock; one
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
# The fixed error a sender gets when the store refuses a message or cannot store it (never the
# reason).
CHAT_ERROR_NOT_SENT = "not_sent"
# The page's reconnect: the first wait after a close it did not ask for, doubled after each failed
# try up to the longest; and how many refusals in a row (each after a new token) it takes before it
# stops and says it is not connected.
CHAT_RECONNECT_FIRST_SECONDS = 1
CHAT_RECONNECT_MAX_SECONDS = 30
CHAT_RECONNECT_MAX_REFUSALS = 3
