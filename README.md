# AI Accident Detection & Emergency Alert System

Flask dashboard for uploaded traffic-video analysis. It uses pretrained YOLOv8n for people and vehicle detection and experimental motion rules to flag possible incidents. It does not train a model or require `models/accident_classifier.pt`. A possible-incident warning is not a confirmed crash or a dependable emergency alert.

## Project structure

```
app.py                 Flask application entry point
database.py            MySQL connection and query helpers
templates/             HTML templates
static/css/            Stylesheets
static/js/             Browser JavaScript
static/images/         UI image assets
models/yolov8n.pt      Pretrained YOLOv8n weights (downloaded on first analysis if absent)
videos/                Input video files and processed output
snapshots/             Possible-incident snapshots
database/accident_detection.sql  Complete MySQL schema
tests/test_auth.py       Automated login-flow tests (uses mocked database calls)
video_processing.py      OpenCV video validation and frame-extraction helpers
detection.py             CPU-friendly YOLOv8n person/vehicle video processing
incident_rules.py        Training-free movement rules for possible-incident warnings
accident_model.py        Optional legacy CNN code; not used by the default app flow
```

## Setup on Windows

1. Open PowerShell in this project folder.
2. Create a virtual environment:
   ```powershell
   py -m venv .venv
   ```
3. Activate it:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that window, then activate again.
4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Run the Flask application:
   ```powershell
   python app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.

Press `Ctrl+C` in PowerShell to stop the server.

## Configure MySQL

1. Install and start **MySQL Server 8.0+**. During installation, remember the password you assign to the MySQL user (commonly `root`).
2. In PowerShell, from this project directory, create the database and tables. Replace `root` with your MySQL username if needed:
   ```powershell
   Get-Content .\database\accident_detection.sql | mysql -u root -p
   ```
   Enter the MySQL password when prompted. This creates the `accident_detection` database, all tables, relationships, indexes, and the four reference severity levels. It does not add accident, detection, alert, or notification records.

   The repository also includes `database/accident_detection_dump.sql`, a database snapshot with the schema and reference severity levels. It contains no user accounts; create the first administrator through the app setup flow. To restore the database in one step instead of the schema-only file above:
   ```powershell
   Get-Content .\database\accident_detection_dump.sql | mysql -u root -p
   ```
3. Configure this application's connection settings in the same PowerShell window. Replace the example values with your real MySQL credentials:
   ```powershell
   $env:MYSQL_HOST = "localhost"
   $env:MYSQL_PORT = "3306"
   $env:MYSQL_USER = "root"
   $env:MYSQL_PASSWORD = "your_mysql_password"
   $env:MYSQL_DATABASE = "accident_detection"
   ```
   These settings apply only to the current PowerShell window and keep the password out of source code.
4. Test the connection:
   ```powershell
   python database.py
   ```
   A successful connection prints `Connected to MySQL database 'accident_detection'.`
5. Start the web application as usual:
   ```powershell
   python app.py
   ```

If the `mysql` command is not recognized, run the SQL file from **MySQL Workbench**: open the file `database/accident_detection.sql`, then click the lightning-bolt Execute button. Ensure the MySQL `bin` folder is on your Windows PATH if you want to use the terminal command.

## First administrator account and login

1. Configure MySQL and import the schema as described above.
2. Set a non-default Flask session secret for the current PowerShell window:
   ```powershell
   $env:FLASK_SECRET_KEY = "replace-this-with-a-long-random-secret"
   ```
3. Start the app with `python app.py`, then open `http://127.0.0.1:5000`. You will be redirected to the sign-in page.
4. Select **Set up the first admin account**, complete the form, and use a password of at least 8 characters. The password is stored in `users.password_hash` using Werkzeug's secure hash function; it is never stored as plain text.
5. Sign in with the newly created account. The dashboard is protected, and use **Sign out** in the sidebar to end the session.

The setup page can only create the first administrator. After one exists, it redirects to the login page. Add later users directly through an admin-management feature or a controlled database process.

### Run the authentication tests

The included tests verify dashboard protection, invalid-login errors, secure first-admin password hashing, successful sign-in, logout, video upload validation, protected playback, and OpenCV frame extraction. They use mocked database calls, so they do not create any user accounts:

```powershell
python -m unittest discover -s tests -v
```

## Database tables

- `users` — administrator and operator accounts
- `cameras` — camera stream and location configuration
- `detection_log` — model detection output
- `accident_event` — unverified possible-incident records
- `severity_level` — severity reference values
- `alerts` — generated emergency alerts
- `emergency_contacts` — notification recipients
- `notification_log` — delivery attempts and provider responses

## Upload a video

After signing in, select **Upload Video** from the dashboard. The application accepts `.mp4`, `.avi`, `.mov`, `.m4v`, and `.webm` files up to 500 MB, sanitizes the original filename, assigns a unique stored filename, and saves it to `videos/`. OpenCV verifies that the uploaded file has readable video frames before it is accepted. The upload form shows transfer progress, and the dashboard shows frame-based analysis progress while YOLO processes the video. The dashboard then plays the original or annotated output without replacing the upload.

### Connect to a camera

The upload screen works with camera-enabled devices. Choose **Connect to camera** to open the device camera capture, or choose **Record from camera** to preview and record before uploading. Camera recordings may be MP4, MOV, M4V, or WebM; the server checks that OpenCV can read the recording before accepting it.

To open the app from a phone on the same Wi-Fi, start it with `run_flask.bat` and open `http://<your-computer-LAN-IP>:5000` on the phone. The native camera picker should work over that connection. For **Record in this page**, browsers require a secure HTTPS address (an HTTPS tunnel or a production HTTPS deployment); browsers intentionally block direct camera access on plain `http://` LAN addresses. Allow the camera permission when prompted.

`video_processing.extract_frames(video_path, output_directory, every_n_frames=30)` is available for later use. It reads the video through OpenCV and saves periodic JPEG frames; it does not perform accident detection.

## Vehicle and person detection

After uploading a video, select **Run YOLO vehicle & person detection** on the dashboard. The app uses the lightweight `yolov8n.pt` model and automatically downloads it to `models/` on the first processing run. Internet access is therefore needed only for the first run. The model runs on CPU, uses a 640px inference size, and filters detections to people, cars, motorcycles, buses, and trucks.

Detection produces a separate browser-friendly annotated WebM in `videos/processed/`; it never modifies the original upload. Bounding boxes show the class name, track ID, and confidence score. The app also checks for possible incidents using vehicle/person proximity and abrupt tracked-motion changes. These rules are only a demonstration warning and can miss incidents or flag normal traffic.

## Possible-incident assessment

YOLO detects people and vehicles; it does not recognize crashes. The app uses tracked center movement over time and flags only when vehicles come close while at least one shows a sharp slowdown or reversal, along with approach evidence or a motion change by both vehicles. Bounding-box overlap by itself never triggers an incident. A flag is worded **“Possible incident — manual review required”** and includes the clip timestamp and involved track classes/IDs. If these signals are absent, the app reports that no possible-incident signal was flagged; that does not prove the video is accident-free. No accident-classification model is trained or required. The legacy `accident_model.py` file is retained but is not used in the normal dashboard analysis.

These are fixed pixel-motion heuristics, not a validated crash detector. Camera angle, perspective, frame rate, occlusion, poor lighting, detector errors, abrupt normal braking, turns, and imperfect track matching can cause missed events or false positives. Review the source video manually; do not use the score as an emergency or safety decision.

## Severity estimation

When the movement rules flag a possible incident, the dashboard calculates a transparent, demonstration-only score and displays `LOW`, `MEDIUM`, or `HIGH`. It is **not medically, legally, or officially validated** and must not be used as an emergency-triage decision.

The score is capped at 100 and calculated from the following explainable signals:

| Factor | Maximum points | Pipeline source |
| --- | ---: | --- |
| Vehicle evidence | 30 | Unique tracked car, motorcycle, bus, and truck objects (capped at 5) |
| Person evidence | 15 | Unique tracked person objects (capped at 5) |
| Visual incident indicator | 35 | Movement-rule signal |
| Detection confidence | 20 | Mean YOLO confidence for the filtered objects |

Scores below 35 are `LOW`, 35–64.9 are `MEDIUM`, and 65 or above are `HIGH`. YOLO tracking assigns IDs across frames so the dashboard counts a tracked object once instead of once per frame. Track IDs are estimates: missed or interrupted tracking can split one real object into multiple counts, and counts are not verified identities. The movement rules look for close proximity plus abrupt slowdown or direction change; they do not prove a collision or injury.

For a possible incident flagged by the movement rules, the app attempts to save an unverified `accident_event` and its MySQL `severity_level`. It captures the rule-trigger frame when available, otherwise the video midpoint. It creates one reusable `Uploaded Video Source` camera row when needed to satisfy the relational schema. If MySQL is not configured or available, the warning remains visible and states that the event was not saved.

## Accident event logging

For a possible incident, the system saves a uniquely named JPEG under `snapshots/` and records the timestamp, `detected` status, heuristic severity estimate, YOLO object counts, source-video details, and snapshot filename in MySQL. These are unverified warnings, not confirmed accident records. The dashboard shows the latest logged event, and **Accident History** lists saved events with a `LOW`/`MEDIUM`/`HIGH` filter.

To prevent repeated logs from continuous detections, the app groups matching source-video events for 120 seconds. It uses both an in-memory cooldown and a MySQL recent-event lookup, so pressing processing repeatedly does not create a new event for the same uploaded source during the cooldown. Logged records are rule-flagged and unverified; they are not official reports.

## Automatic alert generation

When a possible incident event is saved, the app creates a **dashboard warning** in MySQL and logs its dashboard-delivery attempt in `notification_log`. The warning contains the event ID, snapshot timestamp, source/location (`User-uploaded video` for uploads), severity, and snapshot filename. It is prominently marked **unverified** for human review.

No SMS, phone call, or emergency-service message is sent. External email is disabled by default in alert generation, and Flask test mode suppresses it even if SMTP settings are present. Dashboard warnings can still be logged in MySQL. The optional demo email feature requires explicit opt-in in a non-test run.

### Optional demo email

Email is disabled by default. To opt in, configure a test SMTP mailbox and use only contacts you are authorized to notify. Set these values in the PowerShell window before starting Flask:

```powershell
$env:ENABLE_DEMO_EMAIL = "true"
$env:SMTP_HOST = "smtp.example.com"
$env:SMTP_PORT = "587"
$env:SMTP_USE_TLS = "true"
$env:SMTP_FROM = "demo-alerts@example.com"
$env:SMTP_USERNAME = "demo-alerts@example.com"
$env:SMTP_PASSWORD = "your_smtp_app_password"
python app.py
```

If email is disabled, missing configuration, or SMTP delivery fails, the app does not crash. It stores the alert as `failed` and records the provider response in `notification_log`. A successful SMTP handoff is stored as `sent`; actual delivery confirmation would require a provider webhook integration later. The `alerts.py` provider boundary is designed so SMS/email providers can be added without changing accident detection logic.

## Current limitations

- YOLOv8n is pretrained for general object detection, not accident recognition.
- The proximity and motion rules are experimental and have not been validated on representative road-accident videos.
- Event history and persisted dashboard alerts require a working MySQL database.
- SMS, calls, and emergency-service notifications are not sent. Email is an optional demo feature and is disabled by default.
