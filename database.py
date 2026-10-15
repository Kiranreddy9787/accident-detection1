"""MySQL helpers for the AI Accident Detection & Emergency Alert System.

Connection settings are read from environment variables so credentials never need
to be committed to source control. See README.md for setup instructions.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence

import mysql.connector
from mysql.connector import Error, MySQLConnection


def load_dotenv_file(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE pairs from a local .env file without any third-party package.

    Values already present in the real environment are never overwritten, so
    command-line ``set`` / ``$env:`` or the run_flask.bat launcher still win.
    """
    env_path = path or (Path(__file__).resolve().parent / ".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_dotenv_file()


DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "accident_detection"),
    "charset": "utf8mb4",
    "use_unicode": True,
}


def get_connection(include_database: bool = True) -> MySQLConnection:
    """Return a new MySQL connection using the environment configuration.

    Set ``include_database=False`` when connecting before the schema exists.
    The caller must close the returned connection, or use ``db_connection``.
    """
    config = DB_CONFIG.copy()
    if not include_database:
        config.pop("database")
    return mysql.connector.connect(**config)


@contextmanager
def db_connection() -> Iterator[MySQLConnection]:
    """Yield a connection and always close it afterwards."""
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def test_connection() -> tuple[bool, str]:
    """Check that MySQL is reachable and the configured database is available."""
    try:
        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE()")
            database_name = cursor.fetchone()[0]
            cursor.close()
        return True, f"Connected to MySQL database '{database_name}'."
    except Error as error:
        return False, f"MySQL connection failed: {error}"


def fetch_all(query: str, params: Optional[Sequence[Any]] = None) -> list[dict[str, Any]]:
    """Run a SELECT query and return rows as dictionaries."""
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        cursor.close()
    return rows


def execute_query(
    query: str,
    params: Optional[Sequence[Any] | Mapping[str, Any]] = None,
) -> int:
    """Execute an INSERT, UPDATE, or DELETE query and commit it.

    Returns the affected row ID for inserts, otherwise the affected row count.
    """
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(query, params or ())
        connection.commit()
        result = cursor.lastrowid or cursor.rowcount
        cursor.close()
    return result


def save_accident_event_from_video(
    severity: str,
    detection_confidence: float,
    description: str,
    source_video_path: Optional[str] = None,
    snapshot_path: Optional[str] = None,
) -> int:
    """Persist an unverified uploaded-video event and its MySQL severity level.

    A reusable ``Uploaded Video Source`` camera row is created only if needed so
    the event remains compatible with the camera-based relational schema.
    """
    if severity not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("severity must be LOW, MEDIUM, or HIGH")
    if not 0 <= detection_confidence <= 1:
        raise ValueError("detection_confidence must be between 0 and 1")

    with db_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT severity_level_id FROM severity_level WHERE UPPER(level_name) = %s LIMIT 1",
                (severity,),
            )
            severity_row = cursor.fetchone()
            if not severity_row:
                raise Error(f"The severity level '{severity}' is missing from the database.")
            severity_level_id = severity_row[0]

            cursor.execute("SELECT camera_id FROM cameras WHERE stream_url = %s LIMIT 1", ("uploaded-video://local",))
            camera_row = cursor.fetchone()
            if camera_row:
                camera_id = camera_row[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO cameras (camera_name, location_description, stream_url, status)
                    VALUES (%s, %s, %s, 'active')
                    """,
                    ("Uploaded Video Source", "User-uploaded video", "uploaded-video://local"),
                )
                camera_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO detection_log (camera_id, model_name, model_version, confidence_score, source_frame_path, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (camera_id, "YOLOv8n + incident assessment", "demo", detection_confidence, source_video_path, description),
            )
            detection_log_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO accident_event (detection_log_id, severity_level_id, event_status, snapshot_path, description)
                VALUES (%s, %s, 'detected', %s, %s)
                """,
                (detection_log_id, severity_level_id, snapshot_path, description),
            )
            accident_event_id = cursor.lastrowid
            connection.commit()
            return accident_event_id
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def find_recent_accident_event(source_video_path: str, cooldown_seconds: int = 120) -> Optional[int]:
    """Return a recent matching event ID so repeated frames are grouped."""
    with db_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT ae.accident_event_id
                FROM accident_event AS ae
                INNER JOIN detection_log AS dl ON dl.detection_log_id = ae.detection_log_id
                WHERE dl.source_frame_path = %s
                  AND TIMESTAMPDIFF(SECOND, ae.created_at, CURRENT_TIMESTAMP) BETWEEN 0 AND %s
                ORDER BY ae.created_at DESC
                LIMIT 1
                """,
                (source_video_path, cooldown_seconds),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()


def get_accident_history(severity: Optional[str] = None) -> list[dict[str, Any]]:
    """Fetch persisted accident events for the authenticated history view."""
    query = """
        SELECT ae.accident_event_id, ae.event_status, ae.occurred_at, ae.created_at,
               ae.snapshot_path, ae.description, sl.level_name AS severity,
               dl.source_frame_path AS source_video_path, dl.confidence_score,
               c.camera_name
        FROM accident_event AS ae
        INNER JOIN severity_level AS sl ON sl.severity_level_id = ae.severity_level_id
        INNER JOIN detection_log AS dl ON dl.detection_log_id = ae.detection_log_id
        INNER JOIN cameras AS c ON c.camera_id = dl.camera_id
    """
    params: tuple[Any, ...] = ()
    if severity:
        query += " WHERE UPPER(sl.level_name) = %s"
        params = (severity,)
    query += " ORDER BY ae.created_at DESC"
    return fetch_all(query, params)


def get_dashboard_summary() -> dict[str, Any]:
    """Return real persisted event counts and recent alert rows for the dashboard."""
    with db_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT COUNT(*) AS accident_count FROM accident_event")
            accident_count = cursor.fetchone()["accident_count"]
            cursor.execute(
                """
                SELECT a.alert_id, a.alert_status, a.alert_channel, a.alert_message, a.created_at,
                       sl.level_name AS severity
                FROM alerts AS a
                INNER JOIN accident_event AS ae ON ae.accident_event_id = a.accident_event_id
                INNER JOIN severity_level AS sl ON sl.severity_level_id = ae.severity_level_id
                ORDER BY a.created_at DESC
                LIMIT 5
                """
            )
            return {"database_available": True, "accident_count": accident_count, "recent_alerts": cursor.fetchall()}
        finally:
            cursor.close()


def create_alert(event_id: int, contact_id: Optional[int], channel: str, status: str, message: str) -> int:
    return execute_query(
        """INSERT INTO alerts (accident_event_id, emergency_contact_id, alert_channel, alert_status, alert_message, sent_at)
           VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END)""",
        (event_id, contact_id, channel, status, message, status),
    )


def update_alert_status(alert_id: int, status: str) -> int:
    return execute_query(
        "UPDATE alerts SET alert_status = %s, sent_at = CASE WHEN %s = 'pending' THEN sent_at ELSE CURRENT_TIMESTAMP END WHERE alert_id = %s",
        (status, status, alert_id),
    )


def log_notification_attempt(alert_id: int, contact_id: Optional[int], status: str, provider: str, response: str) -> int:
    return execute_query(
        """INSERT INTO notification_log (alert_id, emergency_contact_id, delivery_status, provider_message_id, provider_response, delivered_at)
           VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'sent' OR %s = 'delivered' THEN CURRENT_TIMESTAMP ELSE NULL END)""",
        (alert_id, contact_id, status, provider, response, status, status),
    )


def get_active_email_contacts() -> list[dict[str, Any]]:
    return fetch_all("SELECT emergency_contact_id, contact_name, email FROM emergency_contacts WHERE is_active = TRUE AND email IS NOT NULL AND email <> ''")


def get_emergency_contacts() -> list[dict[str, Any]]:
    return fetch_all("SELECT * FROM emergency_contacts ORDER BY is_active DESC, contact_type, contact_name")


def create_emergency_contact(name: str, organization: str, phone: str, email: Optional[str], contact_type: str, user_id: int) -> int:
    return execute_query(
        """INSERT INTO emergency_contacts (user_id, contact_name, organization, phone_number, email, contact_type)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (user_id, name, organization or None, phone, email or None, contact_type),
    )


def set_emergency_contact_active(contact_id: int, is_active: bool) -> int:
    return execute_query("UPDATE emergency_contacts SET is_active = %s WHERE emergency_contact_id = %s", (is_active, contact_id))


if __name__ == "__main__":
    connected, message = test_connection()
    print(message)
    raise SystemExit(0 if connected else 1)
