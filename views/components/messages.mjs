// The Messages page's browser component (T11.4b, D24): shows a coach-client thread and keeps its
// socket to the chat app mounted on Streamlit's server (src/realtime/).
//
// Our own code, with no library and no request to another host: Streamlit loads this file's text
// as the component's JavaScript (views/messages.py). `createClient` holds the socket logic and is
// unit-tested with Node's built-in test runner (tests/js/messages.test.mjs); the default export
// only wires it to the page.
//
// - The token comes in the component's `data` on every run of the thread's fragment and is kept in
//   memory only (never in localStorage, sessionStorage or the URL). It is the socket's first frame.
// - Before the token expires the component asks for a rerun of the fragment (a trigger), which
//   mints a new token; the new token and the last shown message's ID go on the open socket.
// - After a close it did not ask for (sleep, a server restart, a missed renewal) it reconnects,
//   waiting longer after each failed try; a refusal first asks for a new token, and after a few
//   refusals in a row it stops and says it is not connected.
// - Messages are kept by ID, so a message the page's store read and the socket both bring shows
//   once; text is shown as plain text (textContent), never as HTML.

const OPEN = 1;

/** Return a message's length in characters as Python counts them (code points). */
export function charCount(text) {
  return Array.from(text).length;
}

/** Create the socket client: `env` gives the socket, the clock, timers and the page's callbacks. */
export function createClient(env) {
  const messages = new Map();
  let status = "offline";
  let notice = null;
  let settings = null;
  let socketUrl = null;
  let token = null;
  let expiresAt = 0;
  let ws = null;
  let closingOnPurpose = false;
  let renewTimer = null;
  let reconnectTimer = null;
  let tokenTimer = null;
  let asks = 0;
  let backoffMs = 0;
  let refusals = 0;
  let lastSent = null;

  /** Return the highest message ID the page shows (0 for none). */
  function lastId() {
    let found = 0;
    for (const id of messages.keys()) found = Math.max(found, id);
    return found;
  }

  /** Tell the page what to draw now. */
  function changed() {
    const sorted = [...messages.values()].sort((a, b) => a.id - b.id);
    env.onChange({ messages: sorted, status, notice, lastSent });
  }

  /** Add messages by ID; one already shown is not added again. */
  function merge(items) {
    for (const item of items || []) {
      if (Number.isInteger(item.id) && typeof item.text === "string") {
        messages.set(item.id, {
          id: item.id,
          mine: item.mine === true,
          text: item.text,
          created_at: String(item.created_at || ""),
        });
      }
    }
  }

  /** Clear a timer if one is set; return null. */
  function cancel(timer) {
    if (timer !== null) env.clearTimer(timer);
    return null;
  }

  /** Ask the page for a new token (a rerun of the thread's fragment), and again until one comes. */
  function askForToken() {
    renewTimer = cancel(renewTimer);
    tokenTimer = cancel(tokenTimer);
    env.requestRenewal();
    // Streamlit drops a trigger sent while its own connection is down, and a rerun in the same
    // second mints the same token: so ask again, waiting longer each time, until update() brings
    // a different token. Refusals still end in "stopped"; this only keeps a lost ask from leaving
    // the page on "Connecting…" for good.
    asks += 1;
    // On a live socket the token still has time left, so a slow rerun gets longer before the next
    // ask; with no socket the page waits for the token, so it asks again sooner.
    const first =
      status === "live" ? settings.renew_retry * 1000 : settings.reconnect_first * 1000;
    const wait = Math.min(first * 2 ** (asks - 1), settings.reconnect_max * 1000);
    tokenTimer = env.setTimer(() => {
      tokenTimer = null;
      askForToken();
    }, wait);
  }

  /** Ask for a new token a little before this one expires. */
  function scheduleRenewal() {
    renewTimer = cancel(renewTimer);
    const delay = Math.max(0, expiresAt - settings.renew_before * 1000 - env.now());
    renewTimer = env.setTimer(() => {
      renewTimer = null;
      askForToken();
    }, delay);
  }

  /** Send the token and the last shown ID: the first frame, a renewal, or the answer to "more". */
  function sendAuth() {
    ws.send(JSON.stringify({ type: "auth", token, after_id: lastId() }));
  }

  /** Open a socket with the current token, or ask for a new one if it is about to expire. */
  function connect() {
    reconnectTimer = cancel(reconnectTimer);
    if (env.now() >= expiresAt - 1000) {
      askForToken();
      return;
    }
    status = "connecting";
    changed();
    closingOnPurpose = false;
    const socket = env.openSocket(socketUrl);
    ws = socket;
    socket.onopen = () => {
      if (ws === socket) sendAuth();
    };
    socket.onmessage = (event) => {
      if (ws === socket) receive(event.data);
    };
    socket.onclose = (event) => {
      if (ws === socket) closed(event.code);
    };
  }

  /** Handle one frame from the server. */
  function receive(text) {
    let frame;
    try {
      frame = JSON.parse(text);
    } catch {
      return;
    }
    if (frame.type === "messages") {
      merge(frame.items);
      // More messages wait on the server: ask for them with the new last ID.
      if (frame.more === true) sendAuth();
    } else if (frame.type === "ready") {
      status = "live";
      refusals = 0;
      backoffMs = 0;
    } else if (frame.type === "notification") {
      notice = "other_thread";
    } else if (frame.type === "error") {
      notice = "not_sent";
      // The store refused the message, most often because the other side ended the relationship:
      // a rerun of the fragment reads it again and turns the thread read-only if so.
      askForToken();
    } else {
      return;
    }
    changed();
  }

  /** Handle a close: stop if the page asked for it, else get a new token or reconnect later. */
  function closed(code) {
    ws = null;
    if (closingOnPurpose) return;
    if (code === settings.refused_code) {
      refusals += 1;
      if (refusals >= settings.max_refusals) {
        status = "stopped";
        renewTimer = cancel(renewTimer);
        tokenTimer = cancel(tokenTimer);
        changed();
        return;
      }
      status = "connecting";
      changed();
      askForToken();
      return;
    }
    status = "connecting";
    changed();
    const first = settings.reconnect_first * 1000;
    backoffMs = backoffMs === 0 ? first : Math.min(backoffMs * 2, settings.reconnect_max * 1000);
    reconnectTimer = cancel(reconnectTimer);
    reconnectTimer = env.setTimer(() => {
      reconnectTimer = null;
      connect();
    }, backoffMs);
  }

  /** Close the socket and stop every timer. */
  function close() {
    closingOnPurpose = true;
    renewTimer = cancel(renewTimer);
    reconnectTimer = cancel(reconnectTimer);
    tokenTimer = cancel(tokenTimer);
    if (ws !== null) {
      const socket = ws;
      ws = null;
      socket.close(1000);
    }
  }

  /** Take a run's data: the thread from the store, and the socket's settings with a new token. */
  function update(data) {
    merge(data.messages);
    const socket = data.socket || null;
    if (socket === null) {
      close();
      status = "offline";
      changed();
      return;
    }
    if (socket.token !== token) {
      settings = socket;
      socketUrl = data.socket_url;
      token = socket.token;
      expiresAt = env.now() + socket.expires_in * 1000;
      tokenTimer = cancel(tokenTimer);
      asks = 0;
      scheduleRenewal();
      if (ws !== null && ws.readyState === OPEN) {
        sendAuth();
      } else if (ws === null && reconnectTimer === null && status !== "stopped") {
        connect();
      } else if (status === "stopped") {
        // A new token after the page reran (for instance the user pressed a button): try again.
        refusals = 0;
        connect();
      }
    }
    changed();
  }

  /** Send a message; return true if it went on the socket, false if it is empty, too long or offline. */
  function send(text, maxChars) {
    const trimmed = text.trim();
    if (trimmed === "" || status !== "live" || ws === null || ws.readyState !== OPEN) return false;
    if (charCount(text) > maxChars) {
      notice = "too_long";
      changed();
      return false;
    }
    notice = null;
    lastSent = text;
    ws.send(JSON.stringify({ type: "send", text }));
    changed();
    return true;
  }

  /** Forget the notice the page has shown. */
  function clearNotice() {
    notice = null;
    changed();
  }

  return { update, send, close, clearNotice, lastId };
}

// --- The page ------------------------------------------------------------------------------------

const instances = new WeakMap();

/** Return the socket's URL on the page's own host and port (wss:// on an https page). */
function socketUrlFor(path) {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}${path}`;
}

/** Return a message's time in the browser's own time zone. */
function shownTime(created, locale) {
  const moment = new Date(created);
  if (Number.isNaN(moment.getTime())) return "";
  return moment.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}

/** Draw the thread, the status line and the notice; text only, never HTML. */
function draw(instance, snapshot) {
  const { labels, locale, other_name: otherName } = instance.data;
  const list = instance.list;
  const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 40;
  list.replaceChildren();
  if (snapshot.messages.length === 0) {
    const empty = document.createElement("p");
    empty.className = "fk-empty";
    empty.textContent = labels.empty;
    list.append(empty);
  }
  for (const message of snapshot.messages) {
    const item = document.createElement("div");
    item.className = message.mine ? "fk-message fk-mine" : "fk-message fk-theirs";
    const meta = document.createElement("div");
    meta.className = "fk-meta";
    const who = message.mine ? labels.you : otherName;
    meta.textContent = `${who} · ${shownTime(message.created_at, locale)}`;
    const body = document.createElement("div");
    body.className = "fk-text";
    body.textContent = message.text;
    item.append(meta, body);
    list.append(item);
  }
  if (atBottom || instance.firstDraw) list.scrollTop = list.scrollHeight;
  instance.firstDraw = false;
  const statusText = { connecting: labels.connecting, live: labels.live, stopped: labels.stopped };
  instance.status.textContent = statusText[snapshot.status] || "";
  instance.notice.textContent = snapshot.notice ? labels[snapshot.notice] : "";
  const live = snapshot.status === "live";
  instance.input.disabled = !live;
  instance.button.disabled = !live;
  if (snapshot.notice === "not_sent" && instance.input.value === "" && snapshot.lastSent) {
    instance.input.value = snapshot.lastSent;
  }
}

/** Mount or update the component: Streamlit calls this on every run whose data changed. */
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let instance = instances.get(parentElement);
  if (!instance) {
    const root = parentElement.querySelector(".fk-messages");
    instance = {
      list: root.querySelector(".fk-list"),
      status: root.querySelector(".fk-status"),
      notice: root.querySelector(".fk-notice"),
      form: root.querySelector(".fk-form"),
      input: root.querySelector(".fk-input"),
      button: root.querySelector(".fk-send"),
      firstDraw: true,
      data,
      renew: () => {},
    };
    instance.client = createClient({
      openSocket: (url) => new WebSocket(url),
      now: () => Date.now(),
      setTimer: (callback, ms) => window.setTimeout(callback, ms),
      clearTimer: (timer) => window.clearTimeout(timer),
      requestRenewal: () => instance.renew(),
      onChange: (snapshot) => draw(instance, snapshot),
    });
    instances.set(parentElement, instance);
  }
  instance.data = data;
  // The latest run's trigger: it reruns only the fragment around the thread.
  instance.renew = () => setTriggerValue("renew", Date.now());
  const canSend = data.can_send === true;
  instance.form.hidden = !canSend;
  instance.input.maxLength = data.max_chars;
  instance.input.placeholder = data.labels.placeholder;
  instance.button.textContent = data.labels.send;
  const sendNow = () => {
    if (instance.client.send(instance.input.value, data.max_chars)) instance.input.value = "";
  };
  instance.button.onclick = sendNow;
  instance.input.onkeydown = (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendNow();
    }
  };
  instance.input.oninput = () => instance.client.clearNotice();
  const socket = data.socket ? { ...data.socket } : null;
  instance.client.update({
    messages: data.messages,
    socket,
    socket_url: socket ? socketUrlFor(socket.path) : null,
  });
  return () => {
    instance.client.close();
    instances.delete(parentElement);
  };
}
