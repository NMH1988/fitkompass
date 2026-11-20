"""Opening the store: a SQLite connection with foreign keys on, migrated to its schema (T9.6).

The connection is opened in autocommit mode, so the module's `transaction()` is the only place a
transaction starts or ends: every store function that writes (an audit row counts) runs inside one,
and an error rolls the whole of it back. Open a connection per unit of work with `connect()`;
Streamlit runs each session in its own thread, and a connection is not shared between threads.
Every transaction takes the write lock (`BEGIN IMMEDIATE`), reads included, so sessions use the
file one at a time: fine for a local app, and it keeps a read and its audit row together.

The file is in write-ahead log mode (WAL), so a second process (the chat server, D24) uses it next
to Streamlit. As every store transaction takes the write lock, two of them still take turns (up to
the busy timeout) in either mode; what WAL adds is that a commit never waits for a reader, so a
statement run outside a transaction (a migration check, a role lookup, a long-lived connection's
own read) never makes a write fail, and a reader never sees a write half done. WAL is a setting of
the file, so the first connection of this version moves an existing store to it.
"""

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src import config
from src.store.schema import MIGRATIONS

logger = logging.getLogger(__name__)

_FOREIGN_KEYS_ON = "PRAGMA foreign_keys = ON"
# Deleted rows are overwritten with zeros instead of left in the file's free pages, so a deleted
# entry cannot be read back from a copy of the file (docs/SECURITY.md).
_SECURE_DELETE_ON = "PRAGMA secure_delete = ON"
# Temporary tables and indices stay in memory, so no temporary file holds stored values
# (the write-ahead log still holds the pages written since its last checkpoint).
_TEMP_STORE_MEMORY = "PRAGMA temp_store = MEMORY"
# Owner-only permissions on POSIX, so other accounts on a shared computer cannot read the
# store; Windows applies the user profile's access rules instead (docs/SECURITY.md).
_PRIVATE_FOLDER = 0o700
_PRIVATE_FILE = 0o600
# A second process reads and writes the file (D24). The mode is kept in the file; the pragma
# returns the mode in force, which stays the old one when the switch could not be made.
_WAL_ON = "PRAGMA journal_mode = WAL"
_WAL = "wal"
# Copies the log's pages into the file and empties the log, so a deleted row's earlier copies
# are no longer in the `-wal` file (docs/SECURITY.md). It returns (busy, log pages, pages copied);
# busy is 1 when another connection's read kept it from finishing.
_CHECKPOINT = "PRAGMA wal_checkpoint(TRUNCATE)"
# When the log is reset after a completed checkpoint SQLite reuses it from the start and would
# leave older pages behind the new ones; with a limit of 0 it truncates the file then, so a
# deleted row's copies go once a later checkpoint completes (docs/SECURITY.md).
_JOURNAL_SIZE_LIMIT = "PRAGMA journal_size_limit = 0"
# The connection's file, so the checkpoint runs on a connection of its own (checkpoint()).
_DATABASES = "PRAGMA database_list"
_MAIN = "main"
_SCHEMA_VERSION = "PRAGMA user_version"
# IMMEDIATE takes the write lock at once, so two sessions migrating (or writing) at the same time
# wait for each other (up to the busy timeout) instead of failing halfway.
_BEGIN = "BEGIN IMMEDIATE"
_COMMIT = "COMMIT"
_ROLLBACK = "ROLLBACK"


# The one message for a store file that cannot be prepared: an OS error's text names the path.
_CANNOT_PREPARE = "The data file's folder or permissions could not be set."
_NO_WAL = "The data file could not be set up for a second process to use it."


class StoreError(RuntimeError):
    """Raised when the store file cannot be used, e.g. it has a newer schema than this code."""


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the block in one transaction: commit at the end, roll back on any error."""
    if conn.in_transaction:
        # SQLite would only say "cannot start a transaction within a transaction".
        raise StoreError("A store transaction was opened inside another one.")
    conn.execute(_BEGIN)
    try:
        yield conn
        conn.execute(_COMMIT)
    except BaseException:
        # SQLite may have rolled back already (a full disk, an I/O error); a second ROLLBACK
        # would raise and hide the real error. A failed COMMIT leaves the transaction open.
        if conn.in_transaction:
            conn.execute(_ROLLBACK)
        raise


def schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version the database is at (0 for a new file)."""
    return conn.execute(_SCHEMA_VERSION).fetchone()[0]


def migrate(conn: sqlite3.Connection) -> None:
    """Run the migrations the database has not had yet, all in one transaction."""
    with transaction(conn):
        version = schema_version(conn)
        if version > len(MIGRATIONS):
            raise StoreError("The data file was written by a newer version of the app.")
        for script in MIGRATIONS[version:]:
            conn.executescript(script)


def _make_folder(folder: Path) -> bool:
    """Make the store's folder (owner-only where the OS applies the mode); False if refused."""
    try:
        folder.mkdir(mode=_PRIVATE_FOLDER, parents=True, exist_ok=True)
    except OSError:  # e.g. the folder's name is taken by a file, or its parent is read-only
        return False
    return True


def _make_owner_only(target: Path, own_folder: bool) -> bool:
    """On POSIX, make the folder 0700 and the file 0600 before SQLite opens it; False if refused."""
    # mkdir's mode is masked by the umask and leaves an existing folder as it was, so the folder
    # is set first (only the app's own, never a folder a caller passed). A new file is created
    # with 0600 (O_EXCL), so no other account can open it before the chmod. An existing file never
    # gets a descriptor here (O_EXCL refuses it before one exists), as closing any descriptor of a
    # file drops every POSIX lock this process holds on it, SQLite's included
    # (sqlite.org/howtocorrupt.html, 2.2). The chmod then fixes a file made by an older version, or
    # one the owner made read-only. One window is left, accepted as negligible: while one thread
    # creates the file, another thread of the same process may open it through SQLite and lock it
    # before the first closes its descriptor, dropping that lock; it only matters if a second
    # process writes to the brand-new, empty store at that moment.
    try:
        if own_folder:
            os.chmod(target.parent, _PRIVATE_FOLDER)
        try:
            new_file = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, _PRIVATE_FILE)
        except FileExistsError:
            pass
        else:
            os.close(new_file)
        os.chmod(target, _PRIVATE_FILE)
    except OSError:
        return False
    return True


def prepare_file(target: Path, *, own_folder: bool) -> None:
    """Make the file's folder and, on POSIX, make both owner-only; StoreError if refused."""
    # Fail closed with one fixed message: a folder that cannot be made, or a file that cannot be
    # made owner-only, is never used. StoreError is raised outside the `except`, so the OS error
    # (whose text and filename name the path) is not even its __context__ (T9.5 catches StoreError).
    # The review workflow's checkpointer file beside the store is prepared the same way (T9.16).
    if not _make_folder(target.parent):
        raise StoreError(_CANNOT_PREPARE)
    if os.name == "posix" and not _make_owner_only(target, own_folder=own_folder):
        raise StoreError(_CANNOT_PREPARE)


def _use_wal(conn: sqlite3.Connection) -> None:
    """Put the file in write-ahead log mode, or raise StoreError so it is never used without it."""
    # Fail closed: in its old mode a commit waits for every reader, so a long-lived read (the chat
    # server's) could make Streamlit's writes fail with "database is locked". StoreError is raised
    # outside the `except`, so the SQLite error is not even its __context__.
    try:
        mode = conn.execute(_WAL_ON).fetchone()[0]
    except sqlite3.OperationalError:  # e.g. another connection held the file past the timeout
        mode = None
    if mode != _WAL:
        raise StoreError(_NO_WAL)


def _checkpoint_now(conn: sqlite3.Connection) -> int:
    """Run the checkpoint on its own connection with a short wait; return SQLite's busy flag."""
    # The checkpoint first takes the write lock (waiting for another store call, as each holds it)
    # and then waits for readers while holding it. With the store's busy timeout every other store
    # call would wait behind it for seconds; with a short wait it outlasts a short store call and
    # answers busy soon when a read goes on.
    file = next(row[2] for row in conn.execute(_DATABASES) if row[1] == _MAIN)
    if not Path(file).is_file():
        # Renamed or removed while open (POSIX): never create a new file outside prepare_file().
        raise sqlite3.OperationalError("the store file is not where it was opened")
    own = sqlite3.connect(file, timeout=config.STORE_CHECKPOINT_WAIT_SECONDS, autocommit=True)
    try:
        return own.execute(_CHECKPOINT).fetchone()[0]
    finally:
        own.close()


def checkpoint(conn: sqlite3.Connection) -> bool:
    """Copy the write-ahead log into the file and empty it; False if it could not finish."""
    # Run after a delete has committed, so it never raises: the delete stands either way, and a
    # failure here must not be shown as a failed delete. Another connection's transaction that
    # outlasts the short wait (a read, or any store call, as each takes the write lock; in this
    # process or the chat server's) keeps it from finishing; the deleted rows' copies then stay in
    # the log until a later checkpoint completes (the next delete's, SQLite's automatic one after
    # about 1000 pages, or the last connection's close). A fixed event with a status, never the
    # error's text (docs/SECURITY.md).
    try:
        busy = _checkpoint_now(conn)
    except sqlite3.Error:
        logger.warning("store_checkpoint", extra={"status": "error"})
        return False
    if busy:
        logger.warning("store_checkpoint", extra={"status": "busy"})
        return False
    return True


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open the store (config.STORE_PATH by default), migrate it, and close it after the block."""
    target = config.STORE_PATH if path is None else path
    prepare_file(target, own_folder=path is None)
    conn = sqlite3.connect(target, timeout=config.STORE_BUSY_TIMEOUT_SECONDS, autocommit=True)
    try:
        conn.row_factory = sqlite3.Row
        # Off by default in SQLite, and set per connection: without it no reference is checked.
        conn.execute(_FOREIGN_KEYS_ON)
        conn.execute(_SECURE_DELETE_ON)
        conn.execute(_TEMP_STORE_MEMORY)
        conn.execute(_JOURNAL_SIZE_LIMIT)
        _use_wal(conn)  # outside a transaction, where SQLite allows the switch
        migrate(conn)
        yield conn
    finally:
        conn.close()
