// Tests for the Messages component's socket client (T11.4b), run with Node's built-in test runner:
// `node --test tests/js/messages.test.mjs` (tests/test_messages_component.py runs it). The socket,
// the clock and the timers are fakes, so hours of token renewals run in milliseconds.

import assert from "node:assert/strict";
import { test } from "node:test";

import { charCount, createClient } from "../../views/components/messages.mjs";

const OPEN = 1;
const CLOSED = 3;
const REFUSED = 4401;
const SETTINGS = {
  path: "/realtime/ws",
  expires_in: 900,
  renew_before: 120,
  renew_retry: 30,
  reconnect_first: 1,
  reconnect_max: 30,
  max_refusals: 3,
  refused_code: REFUSED,
};

/** A fake WebSocket: records what the client sends; the test opens, pushes and closes it. */
class FakeSocket {
  /** Start in the connecting state. */
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
  }

  /** Record a frame the client sends. */
  send(text) {
    assert.equal(this.readyState, OPEN, "sent on a socket that is not open");
    this.sent.push(JSON.parse(text));
  }

  /** Close as the client asks. */
  close(code) {
    this.readyState = CLOSED;
    this.closedWith = code;
  }

  /** Finish the handshake. */
  open() {
    this.readyState = OPEN;
    this.onopen();
  }

  /** Push a frame from the server. */
  push(frame) {
    this.onmessage({ data: JSON.stringify(frame) });
  }

  /** Close from the server's side (or the network's). */
  drop(code) {
    this.readyState = CLOSED;
    this.onclose({ code });
  }
}

/** Return a client wired to fakes, and the handles a test drives it with. */
function harness() {
  const world = { now: 1_000_000, timers: [], sockets: [], renewals: 0, snapshot: null };
  world.client = createClient({
    openSocket: (url) => {
      const socket = new FakeSocket(url);
      world.sockets.push(socket);
      return socket;
    },
    now: () => world.now,
    setTimer: (callback, ms) => {
      const timer = { at: world.now + ms, callback, done: false };
      world.timers.push(timer);
      return timer;
    },
    clearTimer: (timer) => {
      timer.done = true;
    },
    requestRenewal: () => {
      world.renewals += 1;
    },
    onChange: (snapshot) => {
      world.snapshot = snapshot;
    },
  });
  /** Move the clock forward, running every timer that falls due on the way, in order. */
  world.advance = (ms) => {
    const end = world.now + ms;
    for (;;) {
      const due = world.timers
        .filter((timer) => !timer.done && timer.at <= end)
        .sort((a, b) => a.at - b.at)[0];
      if (!due) break;
      world.now = Math.max(world.now, due.at); // a late timer fires at the current time
      due.done = true;
      due.callback();
    }
    world.now = end;
  };
  /** Move the clock forward with no timer running, as when the machine sleeps. */
  world.sleep = (ms) => {
    world.now += ms;
  };
  /** Hand the client a run's data, as the page does on each run of the fragment. */
  world.run = (token, messages = []) => {
    world.client.update({
      messages,
      socket: { ...SETTINGS, token },
      socket_url: "ws://localhost:8501/realtime/ws",
    });
  };
  /** Return the socket opened last. */
  world.last = () => world.sockets[world.sockets.length - 1];
  return world;
}

/** Return a message as the server or the page sends it. */
function message(id, text = `message ${id}`, mine = false) {
  return { id, mine, text, created_at: "2026-11-23T10:00:00+00:00" };
}

/** Open the latest socket and answer its first frame with ready. */
function accept(world) {
  world.last().open();
  world.last().push({ type: "ready" });
}

test("the token is the socket's first frame, with the last ID the page shows", () => {
  const world = harness();
  world.run("token-a", [message(3), message(5)]);
  assert.equal(world.sockets.length, 1);
  assert.equal(world.last().url, "ws://localhost:8501/realtime/ws");
  world.last().open();
  assert.deepEqual(world.last().sent, [{ type: "auth", token: "token-a", after_id: 5 }]);
  world.last().push({ type: "ready" });
  assert.equal(world.snapshot.status, "live");
});

test("messages keep arriving on an untouched page after the first token's lifetime", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  const socket = world.last();
  // Two minutes before the token's 15 minutes run out, the component asks for a new one.
  world.advance((SETTINGS.expires_in - SETTINGS.renew_before) * 1000 - 1);
  assert.equal(world.renewals, 0);
  world.advance(1);
  assert.equal(world.renewals, 1);
  // The fragment reruns and hands a new token: it goes on the open socket, no new socket.
  socket.push({ type: "messages", items: [message(1)], more: false });
  world.run("token-b");
  assert.deepEqual(socket.sent.at(-1), { type: "auth", token: "token-b", after_id: 1 });
  socket.push({ type: "ready" });
  // Long past the first token's expiry, and through several more renewals, messages still come.
  for (let round = 0; round < 5; round += 1) {
    world.advance(SETTINGS.expires_in * 1000);
    world.run(`token-${round + 3}`);
    socket.push({ type: "ready" });
    socket.push({ type: "messages", items: [message(round + 2)], more: false });
  }
  assert.equal(world.sockets.length, 1);
  assert.deepEqual(
    world.snapshot.messages.map((item) => item.id),
    [1, 2, 3, 4, 5, 6],
  );
  assert.equal(world.snapshot.status, "live");
  assert.ok(world.renewals >= 6);
});

test("after a close it did not ask for, it reconnects with the token and its last ID", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.last().push({ type: "messages", items: [message(7)], more: false });
  world.last().drop(1006); // a server restart or the machine sleeping
  assert.equal(world.snapshot.status, "connecting");
  assert.equal(world.sockets.length, 1);
  world.advance(SETTINGS.reconnect_first * 1000);
  assert.equal(world.sockets.length, 2);
  world.last().open();
  assert.deepEqual(world.last().sent, [{ type: "auth", token: "token-a", after_id: 7 }]);
});

test("failed reconnects wait longer each time, up to the longest wait", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  const waits = [];
  for (let attempt = 0; attempt < 7; attempt += 1) {
    world.last().drop(1006);
    const before = world.now;
    const count = world.sockets.length;
    while (world.sockets.length === count) world.advance(100);
    waits.push((world.now - before) / 1000);
  }
  assert.deepEqual(waits, [1, 2, 4, 8, 16, 30, 30]);
});

test("a reconnect after the token ran out asks for a new token first", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.last().drop(1006); // the machine goes to sleep: the socket drops...
  world.sleep(SETTINGS.expires_in * 1000); // ...and wakes after the token's expiry
  world.advance(0); // the late timers fire: the renewal and the reconnect
  assert.equal(world.sockets.length, 1); // no socket with an expired token
  assert.ok(world.renewals >= 1);
  world.run("token-fresh");
  assert.equal(world.sockets.length, 2);
  world.last().open();
  assert.equal(world.last().sent[0].token, "token-fresh");
});

test("a refusal asks for a new token, and refusals in a row end in 'stopped'", () => {
  const world = harness();
  world.run("token-a");
  world.last().open();
  world.last().drop(REFUSED);
  assert.equal(world.renewals, 1);
  world.run("token-b");
  world.last().open();
  world.last().drop(REFUSED);
  world.run("token-c");
  world.last().open();
  world.last().drop(REFUSED);
  assert.equal(world.snapshot.status, "stopped");
  const count = world.sockets.length;
  world.advance(3_600_000);
  assert.equal(world.sockets.length, count);
});

test("'more' is answered with the token and the new last ID", () => {
  const world = harness();
  world.run("token-a");
  world.last().open();
  world.last().push({ type: "messages", items: [message(1), message(2)], more: true });
  assert.deepEqual(world.last().sent.at(-1), { type: "auth", token: "token-a", after_id: 2 });
});

test("a message from the store read and from the socket shows once, in ID order", () => {
  const world = harness();
  world.run("token-a", [message(2), message(1)]);
  accept(world);
  world.last().push({ type: "messages", items: [message(2), message(3)], more: false });
  world.run("token-b", [message(1)]); // a store read older than what the socket pushed
  assert.deepEqual(
    world.snapshot.messages.map((item) => item.id),
    [1, 2, 3],
  );
  // The renewal never rewinds: its after_id is the highest ID shown.
  assert.equal(world.last().sent.at(-1).after_id, 3);
});

test("a send goes on the socket only when live, not empty and not too long", () => {
  const world = harness();
  world.run("token-a");
  assert.equal(world.client.send("too early", 10), false);
  accept(world);
  assert.equal(world.client.send("   ", 10), false);
  assert.equal(world.client.send("x".repeat(11), 10), false);
  assert.equal(world.snapshot.notice, "too_long");
  // Characters as Python counts them: four emoji are four, not eight UTF-16 units.
  assert.equal(charCount("💪💪💪💪"), 4);
  assert.equal(world.client.send("💪💪💪💪", 4), true);
  assert.deepEqual(world.last().sent.at(-1), { type: "send", text: "💪💪💪💪" });
});

test("a refused message and a notification are shown as notices", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.client.send("hello", 100);
  world.last().push({ type: "error", code: "not_sent" });
  assert.equal(world.snapshot.notice, "not_sent");
  assert.equal(world.snapshot.lastSent, "hello");
  world.last().push({ type: "notification", kind: "message_received", thread: 9 });
  assert.equal(world.snapshot.notice, "other_thread");
});

test("a run with no socket (the relationship ended) closes it for good", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  const socket = world.last();
  world.client.update({ messages: [], socket: null, socket_url: null });
  assert.equal(socket.closedWith, 1000);
  assert.equal(world.snapshot.status, "offline");
  world.advance(3_600_000);
  assert.equal(world.sockets.length, 1);
  assert.equal(world.renewals, 0);
});

test("a close the page asked for is not followed by a reconnect", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.client.close();
  world.advance(3_600_000);
  assert.equal(world.sockets.length, 1);
});

test("a frame that is not JSON or of no known type changes nothing", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.last().onmessage({ data: "<img src=x>" });
  world.last().push({ type: "something" });
  assert.equal(world.snapshot.status, "live");
  assert.deepEqual(world.snapshot.messages, []);
});

test("a token request that gets no answer is asked again, waiting longer each time", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.last().drop(1006);
  world.sleep(SETTINGS.expires_in * 1000); // the token ran out while the page could not rerun
  world.advance(0);
  const first = world.renewals;
  assert.ok(first >= 1);
  assert.equal(world.snapshot.status, "connecting");
  // Each ask that brings no new token is followed by another: 1, 2, 4, ... up to 30 seconds.
  const times = [];
  for (let ask = 0; ask < 7; ask += 1) {
    const before = world.renewals;
    const start = world.now;
    for (let step = 0; world.renewals === before; step += 1) {
      assert.ok(step < 1000, "no new ask within 100 seconds");
      world.advance(100);
    }
    times.push(Math.round((world.now - start) / 1000));
  }
  assert.deepEqual(times, [1, 2, 4, 8, 16, 30, 30]);
  // When the page reruns at last, the new token opens a socket and the asks stop.
  world.run("token-late");
  assert.equal(world.sockets.length, 2);
  const asked = world.renewals;
  world.last().open();
  world.last().push({ type: "ready" });
  world.advance(60_000);
  assert.equal(world.renewals, asked);
});

test("after a refusal, a rerun that gives back the same token is followed by another ask", () => {
  const world = harness();
  world.run("token-a");
  world.last().open();
  world.last().drop(REFUSED);
  assert.equal(world.renewals, 1);
  world.run("token-a"); // minted in the same second: the same token, so nothing to send
  assert.equal(world.sockets.length, 1);
  world.advance(SETTINGS.reconnect_first * 1000);
  assert.equal(world.renewals, 2);
  world.run("token-b");
  assert.equal(world.sockets.length, 2);
  world.last().open();
  assert.equal(world.last().sent[0].token, "token-b");
});

test("a refused message asks the page to look again, which can turn the thread read-only", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  const socket = world.last();
  world.client.send("still there?", 100);
  socket.push({ type: "error", code: "not_sent" });
  assert.equal(world.renewals, 1);
  // The other side had ended the relationship: the fragment's rerun gives no socket.
  world.client.update({ messages: [], socket: null, socket_url: null });
  assert.equal(socket.closedWith, 1000);
  assert.equal(world.snapshot.status, "offline");
  world.advance(3_600_000);
  assert.equal(world.renewals, 1);
});

test("a renewal on a live socket waits longer before asking again", () => {
  const world = harness();
  world.run("token-a");
  accept(world);
  world.advance((SETTINGS.expires_in - SETTINGS.renew_before) * 1000);
  assert.equal(world.renewals, 1);
  world.advance(SETTINGS.renew_retry * 1000 - 1); // a slow rerun: no second ask yet
  assert.equal(world.renewals, 1);
  world.advance(1);
  assert.equal(world.renewals, 2);
});
