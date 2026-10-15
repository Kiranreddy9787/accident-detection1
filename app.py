import os
import uuid
import json
import threading
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash

import database as db
from alerts import generate_alert
from detection import DetectionError, process_video
from event_logging import AccidentEventGrouper, EventLoggingError, capture_accident_snapshot
from severity import estimate_severity
from video_processing import VideoProcessingError, read_video_metadata


# Phones commonly save recordings as MOV (iPhone), MP4 (Android/iPhone), or
# WebM (browser camera recording). OpenCV validates the actual video before it
# is accepted, so this list only controls the upload filename types we allow.
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "m4v", "webm"}
MAX_VIDEO_BYTES = 500 * 1024 * 1024
SERVER_SESSION_MARKER = uuid.uuid4().hex
VIDEO_MIME_TYPES = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "avi": "video/x-msvideo",
}
event_grouper = AccidentEventGrouper(cooldown_seconds=120)
analysis_progress: dict[str, dict[str, object]] = {}
analysis_progress_lock = threading.Lock()


def create_app():
    """Application factory for the Emergency Alert System."""
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "development-only-change-this-key"),
        # A server restart requires users to authenticate again. This is useful
        # for a local monitoring console and prevents an old browser cookie from
        # opening the dashboard automatically when the project is started.
        SERVER_SESSION_MARKER=SERVER_SESSION_MARKER,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Flask counts the multipart form headers and boundaries too, so leave
        # a small allowance above the advertised 500 MiB video-file limit.
        MAX_CONTENT_LENGTH=501 * 1024 * 1024,
        VIDEO_UPLOAD_FOLDER=str(Path(app.root_path) / "videos"),
        PROCESSED_VIDEO_FOLDER=str(Path(app.root_path) / "videos" / "processed"),
        MODEL_FOLDER=str(Path(app.root_path) / "models"),
        SNAPSHOT_FOLDER=str(Path(app.root_path) / "snapshots"),
    )
    Path(app.config["VIDEO_UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["PROCESSED_VIDEO_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["MODEL_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["SNAPSHOT_FOLDER"]).mkdir(parents=True, exist_ok=True)

    def has_current_login() -> bool:
        """Return whether this browser has signed in during this server run."""
        if "user_id" not in session:
            return False
        # Tests deliberately seed a session to exercise protected views without
        # needing a live MySQL login, so keep that narrow testing convenience.
        return app.testing or session.get("server_session_marker") == app.config["SERVER_SESSION_MARKER"]

    def login_required(view):
        """Redirect unauthenticated visitors to the login page."""
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not has_current_login():
                session.clear()
                flash("Please sign in to access the dashboard.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    def admin_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("user_role") != "admin":
                flash("Administrator access is required.", "error")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped_view

    @app.route("/")
    @login_required
    def home():
        try:
            dashboard_data = db.get_dashboard_summary()
        except Error:
            app.logger.warning("Dashboard database metrics are unavailable")
            dashboard_data = {"database_available": False, "accident_count": None, "recent_alerts": []}
        return render_template(
            "index.html",
            current_user={
                "name": session.get("user_name", "User"),
                "role": session.get("user_role", "operator"),
            },
            uploaded_video=session.get("uploaded_video"),
            processed_video=session.get("processed_video"),
            accident_classification=session.get("accident_classification"),
            severity_estimate=session.get("severity_estimate"),
            current_accident_event=session.get("current_accident_event"),
            current_alert=session.get("current_alert"),
            dashboard_data=dashboard_data,
        )

    @app.route("/upload-video", methods=["GET", "POST"])
    @login_required
    def upload_video():
        if request.method == "POST":
            video_file = request.files.get("video")
            if video_file is None or not video_file.filename:
                flash("Choose a video file to upload.", "error")
                return render_template("upload_video.html")

            safe_name = secure_filename(video_file.filename)
            extension = Path(safe_name).suffix.lower().lstrip(".")
            if not safe_name or extension not in ALLOWED_VIDEO_EXTENSIONS:
                flash("Use an MP4, MOV, M4V, WebM, or AVI video file.", "error")
                return render_template("upload_video.html"), 400

            stored_name = f"{uuid.uuid4().hex}_{safe_name}"
            target_path = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / stored_name
            try:
                video_file.save(target_path)
                file_size = target_path.stat().st_size
                if file_size == 0:
                    raise VideoProcessingError("The uploaded file is empty.")
                if file_size > MAX_VIDEO_BYTES:
                    raise VideoProcessingError("The video exceeds the 500 MB file size limit.")
                metadata = read_video_metadata(target_path)
            except (OSError, VideoProcessingError) as error:
                target_path.unlink(missing_ok=True)
                app.logger.info("Video upload rejected: %s", error)
                flash(f"Upload failed: {error}", "error")
                return render_template("upload_video.html"), 400

            session["uploaded_video"] = {
                "filename": stored_name,
                "original_name": safe_name,
                "mime_type": VIDEO_MIME_TYPES[extension],
                **metadata,
            }
            session.pop("processed_video", None)
            session.pop("accident_classification", None)
            session.pop("severity_estimate", None)
            session.pop("current_accident_event", None)
            session.pop("current_alert", None)
            flash("Video uploaded successfully. It is ready for preview.", "success")
            return redirect(url_for("home"))

        return render_template("upload_video.html")

    @app.route("/process-video", methods=["POST"])
    @login_required
    def process_uploaded_video():
        """Create an annotated copy of the selected upload with YOLO detection."""
        selected_video = session.get("uploaded_video")
        if not selected_video:
            flash("Upload a video before starting detection.", "warning")
            return redirect(url_for("upload_video"))

        source_path = Path(app.config["VIDEO_UPLOAD_FOLDER"]) / selected_video["filename"]
        processed_filename = f"detected_{Path(selected_video['filename']).stem}.webm"
        output_path = Path(app.config["PROCESSED_VIDEO_FOLDER"]) / processed_filename

        def record_progress(current_frame: int, total_frames: int) -> None:
            progress = round(current_frame * 100 / total_frames) if total_frames > 0 else 0
            with analysis_progress_lock:
                analysis_progress[selected_video["filename"]] = {
                    "status": "processing",
                    "progress": min(progress, 99),
                    "current_frame": current_frame,
                    "total_frames": total_frames,
                    "message": "Analyzing video frames with YOLO…",
                }

        with analysis_progress_lock:
            if len(analysis_progress) >= 64:
                for old_filename in list(analysis_progress)[:-63]:
                    analysis_progress.pop(old_filename, None)
            analysis_progress[selected_video["filename"]] = {
                "status": "starting", "progress": 0, "current_frame": 0,
                "total_frames": selected_video.get("frame_count", 0),
                "message": "Loading pretrained YOLO model…",
            }
        try:
            result = process_video(
                source_path,
                output_path,
                app.config["MODEL_FOLDER"],
                progress_callback=record_progress,
            )
        except (DetectionError, OSError, ValueError) as error:
            with analysis_progress_lock:
                analysis_progress[selected_video["filename"]] = {
                    "status": "failed", "progress": 0,
                    "message": f"Analysis failed: {error}",
                }
            app.logger.exception("Video detection processing failed")
            flash(f"Detection could not be completed: {error}", "error")
            return redirect(url_for("home"))

        with analysis_progress_lock:
            analysis_progress[selected_video["filename"]] = {
                "status": "complete", "progress": 100,
                "current_frame": result.get("frame_count", 0),
                "total_frames": result.get("frame_count", 0),
                "message": "Video analysis complete.",
            }

        session["processed_video"] = {"filename": processed_filename, **result}
        movement_incident = result.get("movement_incident", {"possible_incident": False})
        classification = {
            "status": "rule_based",
            "label": "Possible incident — manual review required" if movement_incident.get("possible_incident") else "No possible incident flagged",
            "possible_incident": bool(movement_incident.get("possible_incident")),
            "method": "proximity_and_motion_rules",
            "message": movement_incident.get("message", "Movement rules completed."),
            "rule_score": movement_incident.get("rule_score", 0.0),
            "peak_frame_index": movement_incident.get("frame_index"),
            "time_seconds": movement_incident.get("time_seconds"),
            "video_timestamp": movement_incident.get("video_timestamp"),
            "track_ids": movement_incident.get("track_ids", []),
            "involved_objects": movement_incident.get("involved_objects", []),
            "signals": movement_incident.get("signals", []),
        }

        session["accident_classification"] = classification
        if classification.get("possible_incident"):
            counts = result.get("object_counts", {})
            severity = estimate_severity(
                vehicle_detections=sum(counts.get(name, 0) for name in ("car", "motorcycle", "bus", "truck")),
                person_detections=counts.get("person", 0),
                collision_indicator=classification.get("accident_probability", classification.get("rule_score", 0.65)),
                detection_confidence=result.get("average_detection_confidence", 0.0),
            )
            if classification.get("method") == "proximity_and_motion_rules":
                severity["explanation"] = (
                    "A proximity-and-motion rule flagged a possible incident. "
                    "This is an unverified video warning, not a confirmed collision or severity assessment."
                )
            source_video_path = selected_video["filename"]
            grouped_event_id = None
            if not event_grouper.is_in_cooldown(source_video_path):
                try:
                    grouped_event_id = db.find_recent_accident_event(source_video_path)
                except Error as error:
                    app.logger.warning("Database cooldown check was unavailable: %s", error)
            if event_grouper.is_in_cooldown(source_video_path) or grouped_event_id:
                severity["database_saved"] = bool(grouped_event_id)
                severity["accident_event_id"] = grouped_event_id
                severity["database_message"] = "Grouped with a recent accident event; no duplicate event was created."
            else:
                frame_index = classification.get("peak_frame_index")
                if frame_index is None:
                    frame_index = selected_video["frame_count"] // 2
                try:
                    snapshot = capture_accident_snapshot(source_path, frame_index, app.config["SNAPSHOT_FOLDER"])
                    event_description = json.dumps({
                        "severity_explanation": severity["explanation"],
                        "detected_objects": counts,
                        "source_video": {"original_name": selected_video["original_name"], "stored_name": source_video_path},
                        "snapshot_frame_index": snapshot["frame_index"],
                        "assessment": classification,
                    })
                    # Mark immediately after the snapshot so a temporary MySQL
                    # outage cannot cause continuous duplicate captures.
                    event_grouper.mark_event(source_video_path)
                    session["current_accident_event"] = {
                        "event_id": None, "status": "detected", "severity": severity["severity"],
                        "snapshot": snapshot, "source_video": selected_video["original_name"], "detected_objects": counts,
                    }
                    event_id = db.save_accident_event_from_video(
                        severity["severity"],
                        result.get("average_detection_confidence", 0.0),
                        event_description,
                        source_video_path,
                        snapshot["filename"],
                    )
                    severity["database_saved"] = True
                    severity["accident_event_id"] = event_id
                    session["current_accident_event"]["event_id"] = event_id
                    try:
                        alert = generate_alert(
                            event_id,
                            classification.get("video_timestamp", "timestamp unavailable"),
                            severity["severity"],
                            "User-uploaded video",
                            snapshot["filename"],
                            incident_details=classification.get("message", ""),
                            allow_external_delivery=not app.testing,
                        )
                        session["current_alert"] = {"status": "sent", **alert}
                    except Error as error:
                        app.logger.warning("Alert could not be persisted: %s", error)
                        session["current_alert"] = {
                            "status": "failed",
                            "message": "Accident event was saved, but the dashboard alert could not be logged.",
                        }
                except EventLoggingError as error:
                    severity["database_saved"] = False
                    severity["database_message"] = f"Event could not be logged because the snapshot failed: {error}"
                except (Error, ValueError) as error:
                    app.logger.warning("Accident event could not be saved: %s", error)
                    severity["database_saved"] = False
                    severity["database_message"] = "Snapshot was captured, but the accident event could not be saved to MySQL."
            session["severity_estimate"] = severity
        else:
            session.pop("severity_estimate", None)
            session.pop("current_accident_event", None)
            session.pop("current_alert", None)
        if classification.get("possible_incident"):
            if session.get("current_alert"):
                flash(f"{classification['message']} Dashboard warning logged; no emergency message was sent.", "warning")
            else:
                flash(
                    "A possible incident was flagged, but its event or dashboard warning could not be saved. "
                    "Check MySQL availability and the database configuration.",
                    "error",
                )
        elif classification.get("status") == "rule_based":
            flash("YOLO and movement checks completed. No possible incident signal was found; this does not prove the video is accident-free.", "success")
        else:
            flash("Analysis completed. No possible incident was flagged.", "success")
        return redirect(url_for("home"))

    @app.route("/analysis-progress/<path:filename>")
    @login_required
    def get_analysis_progress(filename):
        """Return progress for this user's currently selected video only."""
        selected_video = session.get("uploaded_video", {})
        if filename != selected_video.get("filename") or Path(filename).name != filename:
            abort(404)
        with analysis_progress_lock:
            state = analysis_progress.get(filename)
        if state is None:
            state = {"status": "idle", "progress": 0, "message": "Analysis has not started."}
        return jsonify(state)

    @app.route("/videos/<path:filename>")
    @login_required
    def uploaded_video(filename):
        """Serve the current user's selected upload for the HTML5 video player."""
        selected_video = session.get("uploaded_video", {})
        if filename != selected_video.get("filename") or Path(filename).name != filename:
            abort(404)
        return send_from_directory(app.config["VIDEO_UPLOAD_FOLDER"], filename, as_attachment=False)

    @app.route("/processed-videos/<path:filename>")
    @login_required
    def processed_video(filename):
        selected_video = session.get("processed_video", {})
        if filename != selected_video.get("filename") or Path(filename).name != filename:
            abort(404)
        return send_from_directory(app.config["PROCESSED_VIDEO_FOLDER"], filename, as_attachment=False)

    @app.route("/snapshots/<path:filename>")
    @login_required
    def accident_snapshot(filename):
        if Path(filename).name != filename:
            abort(404)
        return send_from_directory(app.config["SNAPSHOT_FOLDER"], filename, as_attachment=False)

    @app.route("/accident-history")
    @login_required
    def accident_history():
        severity_filter = request.args.get("severity", "").upper()
        if severity_filter not in {"", "LOW", "MEDIUM", "HIGH"}:
            abort(400)
        try:
            events = db.get_accident_history(severity_filter or None)
            database_error = None
        except Error:
            app.logger.exception("Unable to load accident history")
            events = []
            database_error = "Accident history is unavailable because MySQL could not be reached."
        return render_template(
            "accident_history.html", events=events, selected_severity=severity_filter, database_error=database_error
        )

    @app.route("/emergency-contacts", methods=["GET", "POST"])
    @login_required
    @admin_required
    def emergency_contacts():
        if request.method == "POST":
            name = request.form.get("contact_name", "").strip()
            phone = request.form.get("phone_number", "").strip()
            email = request.form.get("email", "").strip().lower()
            organization = request.form.get("organization", "").strip()
            contact_type = request.form.get("contact_type", "other")
            if not name or not phone or contact_type not in {"police", "ambulance", "fire", "hospital", "administrator", "other"}:
                flash("Enter a name, phone number, and valid contact type.", "error")
            else:
                try:
                    db.create_emergency_contact(name, organization, phone, email, contact_type, session["user_id"])
                    flash("Emergency contact added. Email is never sent unless optional demo SMTP is enabled.", "success")
                    return redirect(url_for("emergency_contacts"))
                except Error:
                    app.logger.exception("Unable to create emergency contact")
                    flash("The emergency contact could not be saved.", "error")
        try:
            contacts = db.get_emergency_contacts()
            database_error = None
        except Error:
            contacts, database_error = [], "Contacts cannot be loaded until MySQL is available."
        return render_template("emergency_contacts.html", contacts=contacts, database_error=database_error)

    @app.route("/emergency-contacts/<int:contact_id>/toggle", methods=["POST"])
    @login_required
    @admin_required
    def toggle_emergency_contact(contact_id):
        try:
            db.set_emergency_contact_active(contact_id, request.form.get("active") == "true")
            flash("Contact notification status updated.", "success")
        except Error:
            flash("Contact status could not be updated.", "error")
        return redirect(url_for("emergency_contacts"))

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large(_error):
        flash("Video upload is too large. The maximum file size is 500 MB.", "error")
        return redirect(url_for("upload_video"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if has_current_login():
            return redirect(url_for("home"))
        # Remove a stale authenticated session, while preserving flash messages
        # created by logout, setup, or a protected-route redirect.
        if "user_id" in session:
            session.clear()

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not email or not password:
                flash("Enter both your email address and password.", "error")
                return render_template("login.html")

            try:
                users = db.fetch_all(
                    """
                    SELECT user_id, full_name, email, password_hash, role, is_active
                    FROM users
                    WHERE email = %s
                    LIMIT 1
                    """,
                    (email,),
                )
            except Error:
                app.logger.exception("Unable to query the user account during login")
                flash("The login service is temporarily unavailable. Please try again later.", "error")
                return render_template("login.html"), 503

            user = users[0] if users else None
            if not user or not user["is_active"] or not check_password_hash(user["password_hash"], password):
                flash("Invalid email address or password.", "error")
                return render_template("login.html"), 401

            session.clear()
            session["user_id"] = user["user_id"]
            session["user_name"] = user["full_name"]
            session["user_role"] = user["role"]
            session["server_session_marker"] = app.config["SERVER_SESSION_MARKER"]
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("home"))

        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @app.route("/setup-admin", methods=["GET", "POST"])
    def setup_admin():
        """Allow creation of the initial administrator account only."""
        try:
            admin_count = db.fetch_all("SELECT COUNT(*) AS total FROM users WHERE role = 'admin'")[0]["total"]
        except Error:
            app.logger.exception("Unable to check administrator setup status")
            flash("The database is unavailable. Configure MySQL and import the schema first.", "error")
            return render_template("setup_admin.html"), 503

        if admin_count:
            flash("An administrator account already exists. Please sign in.", "warning")
            return redirect(url_for("login"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not full_name or not email or not password:
                flash("Complete all required fields.", "error")
            elif len(password) < 8:
                flash("Use a password with at least 8 characters.", "error")
            elif password != confirm_password:
                flash("Passwords do not match.", "error")
            else:
                try:
                    db.execute_query(
                        """
                        INSERT INTO users (full_name, email, password_hash, role)
                        VALUES (%s, %s, %s, 'admin')
                        """,
                        (full_name, email, generate_password_hash(password)),
                    )
                except Error as error:
                    if error.errno == 1062:
                        flash("An account already uses that email address.", "error")
                    else:
                        app.logger.exception("Unable to create initial administrator account")
                        flash("The administrator account could not be created. Please try again.", "error")
                else:
                    flash("Administrator account created. Please sign in.", "success")
                    return redirect(url_for("login"))

        return render_template("setup_admin.html")

    return app


app = create_app()


if __name__ == "__main__":
    # Set FLASK_HOST=0.0.0.0 to let another device on the same network reach
    # the development server. A phone still needs HTTPS for in-page camera use.
    app.run(debug=True, host=os.getenv("FLASK_HOST", "127.0.0.1"))
