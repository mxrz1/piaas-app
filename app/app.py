"""
How to run:
1. Set required environment variable APP_CATEGORY to one of: land, air, sea, land_air.
2. Optional environment variables: DB_PATH (default observations.db), DEFAULT_TZ (fallback display timezone).
3. Install requirements: pip install flask.
4. Start the server: python app.py
5. Visit http://localhost:5000/ in your browser to use the app.
"""
import csv
import math
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


CATEGORY_LABELS = {
    "land": {
        "label": "Land Animals",
        "observation_singular": "Land Observation",
        "observation_plural": "Land Observations",
    },
    "air": {
        "label": "Air Animals",
        "observation_singular": "Air Observation",
        "observation_plural": "Air Observations",
    },
    "sea": {
        "label": "Sea Animals",
        "observation_singular": "Sea Observation",
        "observation_plural": "Sea Observations",
    },
    "land_air": {
        "label": "Land & Air Animals",
        "observation_singular": "Land & Air Observation",
        "observation_plural": "Land & Air Observations",
    },
}

COMMON_TIMEZONES = [
    "UTC",
    "Europe/London",
    "Europe/Vienna",
    "Europe/Paris",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Sao_Paulo",
    "Africa/Nairobi",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Tokyo",
    "Asia/Singapore",
    "Australia/Sydney",
]

APP_CATEGORY = os.environ.get("APP_CATEGORY")
if APP_CATEGORY not in CATEGORY_LABELS:
    raise RuntimeError(
        "APP_CATEGORY environment variable must be set to one of: land, air, sea, land_air"
    )

DB_PATH = os.environ.get("DB_PATH", "observations.db")
DEFAULT_TZ_NAME = os.environ.get("DEFAULT_TZ")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")


def category_context(category_key: str) -> Dict[str, str]:
    label_data = CATEGORY_LABELS[category_key]
    return {
        "key": category_key,
        "label": label_data["label"],
        "observation_singular": label_data["observation_singular"],
        "observation_plural": label_data["observation_plural"],
    }


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exception: Optional[BaseException]) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def initialize_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL CHECK(category IN ('land','air','sea','land_air')),
        stream_name TEXT NOT NULL,
        animal TEXT NOT NULL,
        start_time_utc TEXT NOT NULL,
        end_time_utc TEXT,
        notes TEXT,
        observer TEXT,
        created_at_utc TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_observations_category_start ON observations (category, start_time_utc);
    CREATE INDEX IF NOT EXISTS idx_observations_category_stream ON observations (category, stream_name);
    """
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executescript(schema)
        conn.commit()


def ensure_db_initialized() -> None:
    if not hasattr(app, "_db_initialized"):
        initialize_db()
        app._db_initialized = True  # type: ignore[attr-defined]


def insert_observation(data: Dict[str, Optional[str]]) -> int:
    db = get_db()
    db.execute(
        """
        INSERT INTO observations (
            category, stream_name, animal, start_time_utc, end_time_utc, notes, observer, created_at_utc
        ) VALUES (:category, :stream_name, :animal, :start_time_utc, :end_time_utc, :notes, :observer, :created_at_utc)
        """,
        data,
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def update_observation(obs_id: int, data: Dict[str, Optional[str]]) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE observations
        SET stream_name = :stream_name,
            animal = :animal,
            start_time_utc = :start_time_utc,
            end_time_utc = :end_time_utc,
            notes = :notes,
            observer = :observer
        WHERE id = :id AND category = :category
        """,
        {**data, "id": obs_id, "category": APP_CATEGORY},
    )
    db.commit()


def delete_observation(obs_id: int) -> None:
    db = get_db()
    db.execute(
        "DELETE FROM observations WHERE id = ? AND category = ?",
        (obs_id, APP_CATEGORY),
    )
    db.commit()


def fetch_one(obs_id: int) -> Optional[sqlite3.Row]:
    db = get_db()
    return db.execute(
        "SELECT * FROM observations WHERE id = ? AND category = ?",
        (obs_id, APP_CATEGORY),
    ).fetchone()


def build_filters(query_params: Dict[str, str]) -> Tuple[str, Dict[str, object]]:
    conditions = ["category = :category"]
    params: Dict[str, object] = {"category": APP_CATEGORY}

    stream_name = query_params.get("stream_name", "").strip()
    if stream_name:
        conditions.append("LOWER(stream_name) LIKE LOWER(:stream_name)")
        params["stream_name"] = f"%{stream_name}%"

    animal = query_params.get("animal", "").strip()
    if animal:
        conditions.append("LOWER(animal) LIKE LOWER(:animal)")
        params["animal"] = f"%{animal}%"

    start_date = query_params.get("start_date", "").strip()
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            conditions.append("start_time_utc >= :start_time")
            params["start_time"] = start_dt.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            flash("Invalid start date filter. Use YYYY-MM-DD.", "warning")

    end_date = query_params.get("end_date", "").strip()
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            conditions.append("start_time_utc <= :end_time")
            params["end_time"] = end_dt.strftime("%Y-%m-%dT23:59:59Z")
        except ValueError:
            flash("Invalid end date filter. Use YYYY-MM-DD.", "warning")

    where_clause = " WHERE " + " AND ".join(conditions)
    return where_clause, params


def fetch_observations(
    query_params: Dict[str, str],
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Tuple[List[sqlite3.Row], int]:
    where_clause, params = build_filters(query_params)
    order_clause = " ORDER BY start_time_utc DESC, id DESC"
    limit_clause = ""
    params_with_bounds = dict(params)
    if limit is not None:
        limit_clause = " LIMIT :limit"
        params_with_bounds["limit"] = limit
    if offset is not None:
        limit_clause += " OFFSET :offset" if limit_clause else " LIMIT -1 OFFSET :offset"
        params_with_bounds["offset"] = offset

    db = get_db()
    rows = db.execute(
        "SELECT * FROM observations" + where_clause + order_clause + limit_clause,
        params_with_bounds,
    ).fetchall()

    count = db.execute(
        "SELECT COUNT(*) FROM observations" + where_clause,
        params,
    ).fetchone()[0]
    return rows, count


def fetch_recent(limit: int = 25) -> List[sqlite3.Row]:
    db = get_db()
    return db.execute(
        """
        SELECT * FROM observations
        WHERE category = ?
        ORDER BY start_time_utc DESC, id DESC
        LIMIT ?
        """,
        (APP_CATEGORY, limit),
    ).fetchall()


def parse_datetime_to_utc(value: str, user_tz: Optional[ZoneInfo] = None) -> datetime:
    """
    Parse a datetime string to UTC.

    Args:
        value: The datetime string (typically from datetime-local input)
        user_tz: The user's timezone. If provided and the datetime is naive,
                 it will be interpreted as being in this timezone.

    Returns:
        A datetime object in UTC
    """
    value = value.strip()
    if not value:
        raise ValueError("Datetime value is required")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        # If no timezone info and user timezone provided, interpret as user's local time
        if user_tz:
            dt = dt.replace(tzinfo=user_tz)
        else:
            # Fallback to UTC if no user timezone
            dt = dt.replace(tzinfo=timezone.utc)
    # Convert to UTC
    dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0)


def parse_optional_datetime_to_utc(value: str, user_tz: Optional[ZoneInfo] = None) -> Optional[datetime]:
    """Parse an optional datetime string to UTC."""
    value = value.strip()
    if not value:
        return None
    return parse_datetime_to_utc(value, user_tz)


def utc_to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc_string(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_for_form(value: str, user_tz: Optional[ZoneInfo] = None) -> str:
    """
    Format a UTC datetime string for display in a datetime-local input.

    Args:
        value: UTC datetime string
        user_tz: User's timezone for conversion. If None, uses UTC.

    Returns:
        Formatted string for datetime-local input
    """
    dt = parse_utc_string(value)
    if user_tz:
        dt = dt.astimezone(user_tz)
    return dt.strftime("%Y-%m-%dT%H:%M")


def get_display_timezone() -> ZoneInfo:
    tz_name = session.get("display_timezone")
    if not tz_name and DEFAULT_TZ_NAME:
        tz_name = DEFAULT_TZ_NAME
    if not tz_name:
        tz_name = datetime.now().astimezone().tzinfo.key if hasattr(datetime.now().astimezone().tzinfo, "key") else "UTC"  # type: ignore[attr-defined]
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def get_display_timezone_name() -> str:
    tz = session.get("display_timezone")
    if tz:
        return tz
    if DEFAULT_TZ_NAME:
        return DEFAULT_TZ_NAME
    tzinfo = datetime.now().astimezone().tzinfo
    if tzinfo and hasattr(tzinfo, "key"):
        return tzinfo.key  # type: ignore[attr-defined]
    return "UTC"


def serialize_observation(row: sqlite3.Row, display_tz: ZoneInfo) -> Dict[str, object]:
    start_dt = parse_utc_string(row["start_time_utc"])
    end_dt = None
    if row["end_time_utc"]:
        end_dt = parse_utc_string(row["end_time_utc"])

    def fmt(dt: datetime) -> str:
        return dt.astimezone(display_tz).strftime("%Y-%m-%d %H:%M %Z")

    return {
        "id": row["id"],
        "stream_name": row["stream_name"],
        "animal": row["animal"],
        "notes": row["notes"],
        "observer": row["observer"],
        "start_time_utc": row["start_time_utc"],
        "end_time_utc": row["end_time_utc"],
        "start_time_display": fmt(start_dt),
        "end_time_display": fmt(end_dt) if end_dt else None,
        "created_at_utc": row["created_at_utc"],
    }


@app.before_request
def before_request() -> None:
    ensure_db_initialized()
    g.category = category_context(APP_CATEGORY)


@app.context_processor
def inject_globals() -> Dict[str, object]:
    return {
        "category": category_context(APP_CATEGORY),
        "display_timezone_name": get_display_timezone_name(),
    }


@app.route("/", methods=["GET", "POST"])
def home() -> Response:
    display_tz = get_display_timezone()

    if request.method == "POST":
        stream_name = request.form.get("stream_name", "").strip()
        animal = request.form.get("animal", "").strip()
        start_time_raw = request.form.get("start_time", "")
        end_time_raw = request.form.get("end_time", "")
        notes = request.form.get("notes", "").strip() or None
        observer = request.form.get("observer", "").strip() or None

        if not stream_name or not animal:
            flash("Stream name and animal are required.", "danger")
            return redirect(url_for("home"))
        try:
            # Parse datetime inputs using user's timezone
            start_dt = parse_datetime_to_utc(start_time_raw, display_tz)
            end_dt = parse_optional_datetime_to_utc(end_time_raw, display_tz)
            if end_dt and end_dt < start_dt:
                flash("End time cannot be earlier than start time.", "danger")
                return redirect(url_for("home"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("home"))

        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        insert_observation(
            {
                "category": APP_CATEGORY,
                "stream_name": stream_name,
                "animal": animal,
                "start_time_utc": utc_to_iso(start_dt),
                "end_time_utc": utc_to_iso(end_dt) if end_dt else None,
                "notes": notes,
                "observer": observer,
                "created_at_utc": utc_to_iso(created_at),
            }
        )
        flash(f"{g.category['observation_singular']} created.", "success")
        return redirect(url_for("home"))

    recent_rows = [serialize_observation(row, display_tz) for row in fetch_recent()]
    # Default start time in user's timezone
    default_start = datetime.now(display_tz).strftime("%Y-%m-%dT%H:%M")
    return render_template(
        "home.html",
        recent_observations=recent_rows,
        default_start=default_start,
        display_timezone=display_tz,
    )


@app.route("/log")
def log() -> Response:
    per_page = 25
    page = max(int(request.args.get("page", 1)), 1)
    offset = (page - 1) * per_page
    rows, total = fetch_observations(request.args, limit=per_page, offset=offset)
    display_tz = get_display_timezone()
    serialized = [serialize_observation(row, display_tz) for row in rows]
    total_pages = max(math.ceil(total / per_page), 1)
    query_args = request.args.to_dict()
    query_args.pop("page", None)
    page_links = [
        (p, url_for("log", **{**query_args, "page": p})) for p in range(1, total_pages + 1)
    ]
    prev_url = url_for(
        "log", **{**query_args, "page": page - 1 if page > 1 else 1}
    )
    next_url = url_for(
        "log", **{**query_args, "page": page + 1 if page < total_pages else total_pages}
    )
    export_url = url_for("export_csv", **request.args.to_dict())
    return render_template(
        "log.html",
        observations=serialized,
        total=total,
        page=page,
        total_pages=total_pages,
        per_page=per_page,
        query=request.args,
        query_args=query_args,
        page_links=page_links,
        prev_url=prev_url,
        next_url=next_url,
        export_url=export_url,
    )


@app.route("/observations/<int:obs_id>/edit", methods=["GET", "POST"])
def edit(obs_id: int) -> Response:
    row = fetch_one(obs_id)
    if row is None:
        flash("Observation not found for this category.", "danger")
        return redirect(url_for("log"))

    display_tz = get_display_timezone()

    if request.method == "POST":
        stream_name = request.form.get("stream_name", "").strip()
        animal = request.form.get("animal", "").strip()
        start_time_raw = request.form.get("start_time", "")
        end_time_raw = request.form.get("end_time", "")
        notes = request.form.get("notes", "").strip() or None
        observer = request.form.get("observer", "").strip() or None

        if not stream_name or not animal:
            flash("Stream name and animal are required.", "danger")
            return redirect(url_for("edit", obs_id=obs_id))
        try:
            # Parse datetime inputs using user's timezone
            start_dt = parse_datetime_to_utc(start_time_raw, display_tz)
            end_dt = parse_optional_datetime_to_utc(end_time_raw, display_tz)
            if end_dt and end_dt < start_dt:
                flash("End time cannot be earlier than start time.", "danger")
                return redirect(url_for("edit", obs_id=obs_id))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("edit", obs_id=obs_id))

        update_observation(
            obs_id,
            {
                "stream_name": stream_name,
                "animal": animal,
                "start_time_utc": utc_to_iso(start_dt),
                "end_time_utc": utc_to_iso(end_dt) if end_dt else None,
                "notes": notes,
                "observer": observer,
            },
        )
        flash(f"{g.category['observation_singular']} updated.", "success")
        return redirect(url_for("log"))

    # Format times in user's timezone for the form
    start_form = format_for_form(row["start_time_utc"], display_tz)
    end_form = format_for_form(row["end_time_utc"], display_tz) if row["end_time_utc"] else ""
    return render_template(
        "edit.html",
        observation=row,
        start_form=start_form,
        end_form=end_form,
    )


@app.route("/observations/<int:obs_id>/delete", methods=["POST"])
def delete(obs_id: int) -> Response:
    row = fetch_one(obs_id)
    if row is None:
        flash("Observation not found for this category.", "danger")
    else:
        delete_observation(obs_id)
        flash(f"{g.category['observation_singular']} deleted.", "success")
    return redirect(url_for("log"))


@app.route("/export.csv")
def export_csv() -> Response:
    rows, _ = fetch_observations(request.args)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "category",
            "stream_name",
            "animal",
            "start_time_utc",
            "end_time_utc",
            "notes",
            "observer",
            "created_at_utc",
            "display_time_zone",
        ]
    )
    display_tz_name = get_display_timezone_name()
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["category"],
                row["stream_name"],
                row["animal"],
                row["start_time_utc"],
                row["end_time_utc"],
                row["notes"],
                row["observer"],
                row["created_at_utc"],
                display_tz_name,
            ]
        )
    output.seek(0)
    filename = f"{APP_CATEGORY}_observations.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/settings/timezone", methods=["GET", "POST"])
def timezone_settings() -> Response:
    if request.method == "POST":
        tz_name = request.form.get("timezone")
        if tz_name and tz_name in COMMON_TIMEZONES:
            session["display_timezone"] = tz_name
            flash(f"Display timezone set to {tz_name}.", "success")
            return redirect(url_for("timezone_settings"))
        flash("Please select a valid timezone.", "danger")
    return render_template("timezone.html", timezones=COMMON_TIMEZONES)


@app.route("/api/set-timezone", methods=["POST"])
def set_timezone() -> Response:
    """API endpoint to set user's timezone from browser detection."""
    data = request.get_json()
    if data and "timezone" in data:
        tz_name = data["timezone"]
        # Only set if not already set by user preference
        if "display_timezone" not in session:
            try:
                # Validate timezone
                ZoneInfo(tz_name)
                session["display_timezone"] = tz_name
                return jsonify({"success": True, "timezone": tz_name})
            except Exception:
                return jsonify({"success": False, "error": "Invalid timezone"}), 400
    return jsonify({"success": False, "error": "No timezone provided"}), 400


@app.route("/healthz")
def healthcheck() -> str:
    return "ok"


if __name__ == "__main__":
    ensure_db_initialized()
    app.run(debug=False)
