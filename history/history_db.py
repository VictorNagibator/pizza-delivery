import os
import sqlite3
from datetime import datetime, timezone

# History database path. Inside Docker it is the /data volume
DEFAULT_DATABASE_PATH = '/data/history.db'

SCHEMA = '''
    CREATE TABLE IF NOT EXISTS order_status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE,
        order_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        courier TEXT,
        reason TEXT,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_history_order_id
        ON order_status_history (order_id, id);
'''


# Returns the history database path (the environment variable is read on every call)
def get_database_path():
    return os.getenv('HISTORY_DB_PATH', DEFAULT_DATABASE_PATH)


# Opens a database connection
def get_connection(path=None):
    path = path or get_database_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# Creates the schema (table only, no data)
def init_db(path=None):
    with get_connection(path) as connection:
        connection.executescript(SCHEMA)


# Appends one status event. Returns False when the event was already stored.
# The event_id makes the consumer idempotent: a redelivered message is ignored.
def append_event(event, path=None):
    event_id = event.get('event_id')
    order_id = event['order_id']
    status = event['status']
    created_at = event.get('created_at') or _now()

    with get_connection(path) as connection:
        cursor = connection.execute('''
            INSERT OR IGNORE INTO order_status_history
                (event_id, order_id, status, courier, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (event_id, order_id, status, event.get('courier'), event.get('reason'), created_at))
        return cursor.rowcount > 0


# Returns the status history of an order (oldest first)
def get_history(order_id, path=None):
    with get_connection(path) as connection:
        rows = connection.execute('''
            SELECT status, courier, reason, created_at
            FROM order_status_history
            WHERE order_id = ?
            ORDER BY id
        ''', (order_id,)).fetchall()
    return [dict(row) for row in rows]


# Returns the last status event of an order or None
def get_latest_status(order_id, path=None):
    with get_connection(path) as connection:
        row = connection.execute('''
            SELECT status, courier, reason, created_at
            FROM order_status_history
            WHERE order_id = ?
            ORDER BY id DESC
            LIMIT 1
        ''', (order_id,)).fetchone()
    return dict(row) if row else None


# Returns recent events, optionally filtered by status
def list_events(limit=50, offset=0, status=None, path=None):
    sql = '''
        SELECT order_id, status, courier, reason, created_at
        FROM order_status_history
    '''
    params = []
    if status is not None:
        sql += ' WHERE status = ?'
        params.append(status)
    sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])

    with get_connection(path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


# Returns aggregate statistics for the status log
def get_stats(path=None):
    with get_connection(path) as connection:
        rows = connection.execute('''
            SELECT status, COUNT(*) AS count
            FROM order_status_history
            GROUP BY status
            ORDER BY status
        ''').fetchall()
        totals = connection.execute('''
            SELECT COUNT(*) AS total_events, COUNT(DISTINCT order_id) AS total_orders
            FROM order_status_history
        ''').fetchone()

    return {
        'total_events': totals['total_events'],
        'total_orders': totals['total_orders'],
        'by_status': {row['status']: row['count'] for row in rows},
    }
