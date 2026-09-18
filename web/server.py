"""Flask web dashboard for GestureSlides."""

import cv2
import queue
from flask import Flask, Response, jsonify, render_template, request

from config import WEB_SERVER_HOST, WEB_SERVER_PORT, ENABLE_CAMERA_PREVIEW
from gesture_map import VALID_ACTIONS, VALID_GESTURES, load_gesture_map, save_gesture_map
from logger import get_log_dates, get_recent_logs
from profiles import delete_profile, get_profile_names, load_profile, save_profile
from recorder import delete_recording, get_recording_names, is_recording, load_recording, save_recording, start_recording, stop_recording
from runtime import config, state, frames
from trigger import exit_presentation, first_slide, last_slide, next_slide, pause_slide, prev_slide, start_presentation

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config.snapshot())

@app.route("/api/config", methods=["POST"])
def update_config():
    updates = request.json
    if not isinstance(updates, dict):
        return jsonify({"error": "Invalid config format"}), 400
    if updates:
        config.update(updates)
    return jsonify(config.snapshot())

@app.route("/api/state/stream")
def state_stream():
    """SSE endpoint for live gesture state."""
    def generate():
        q = state.subscribe()
        try:
            while True:
                try:
                    payload = q.get(timeout=2.0)
                    yield f"data: {payload}\n\n"
                except queue.Empty:
                    # Keep-alive
                    yield ": keep-alive\n\n"
        finally:
            state.unsubscribe(q)
    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/action", methods=["POST"])
def trigger_action():
    """Remote control endpoint to trigger slide actions."""
    data = request.json or {}
    action = data.get("action", "")

    action_map = {
        "next": next_slide,
        "prev": prev_slide,
        "pause": pause_slide,
        "first": first_slide,
        "last": last_slide,
        "start": start_presentation,
        "exit": exit_presentation,
    }

    if action not in action_map:
        return jsonify({"error": f"Unknown action: {action}"}), 400

    try:
        action_map[action]()
        return jsonify({"status": "ok", "action": action})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def get_logs():
    """Return recent gesture log entries."""
    limit = request.args.get("limit", 100, type=int)
    logs = get_recent_logs(limit=min(limit, 500))
    return jsonify({"logs": logs})

@app.route("/api/logs/dates")
def get_logs_dates():
    """Return dates with available log files."""
    dates = get_log_dates()
    return jsonify({"dates": dates})

@app.route("/api/gestures", methods=["GET"])
def get_gesture_map():
    """Return current gesture-to-action mapping."""
    gesture_map = load_gesture_map()
    return jsonify({
        "gesture_map": gesture_map,
        "valid_gestures": list(VALID_GESTURES),
        "valid_actions": list(VALID_ACTIONS),
    })

@app.route("/api/gestures", methods=["POST"])
def update_gesture_map():
    """Update gesture-to-action mapping."""
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request format"}), 400
    gesture_map = data.get("gesture_map", {})
    if not isinstance(gesture_map, dict):
        return jsonify({"error": "Invalid gesture_map format"}), 400
    try:
        saved = save_gesture_map(gesture_map)
        return jsonify({"status": "ok", "gesture_map": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/profiles", methods=["GET"])
def get_profiles():
    """Return list of available profiles."""
    names = get_profile_names()
    return jsonify({"profiles": names})

@app.route("/api/profiles/<name>", methods=["GET"])
def get_profile(name):
    """Return a specific profile."""
    profile = load_profile(name)
    return jsonify({"profile": profile})

@app.route("/api/profiles/<name>", methods=["POST"])
def create_or_update_profile(name):
    """Create or update a profile."""
    # Validate profile name
    if not name or not name.isalnum() and "_" not in name and "-" not in name:
        return jsonify({"error": "Invalid profile name"}), 400
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request format"}), 400
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        return jsonify({"error": "Invalid settings format"}), 400
    try:
        saved = save_profile(name, settings)
        return jsonify({"status": "ok", "profile": saved})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/profiles/<name>", methods=["DELETE"])
def remove_profile(name):
    """Delete a profile."""
    if delete_profile(name):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Cannot delete profile"}), 400

@app.route("/api/profiles/<name>/activate", methods=["POST"])
def activate_profile(name):
    """Activate a profile (apply its settings to runtime config)."""
    profile = load_profile(name)
    updates = {k: v for k, v in profile.items() if k != "name"}
    config.update(updates)
    return jsonify({"status": "ok", "profile": profile["name"]})

@app.route("/api/status")
def get_status():
    """Return current system status."""
    from runtime import state
    current_state = state.get_state()
    return jsonify({
        "status": "running",
        "hand_detected": current_state.get("hand_detected", False),
        "last_action": current_state.get("action"),
        "uptime": state.uptime(),
        "recording": is_recording(),
    })

@app.route("/api/recordings", methods=["GET"])
def get_recordings():
    """Return list of available recordings."""
    names = get_recording_names()
    return jsonify({"recordings": names})

@app.route("/api/recordings", methods=["POST"])
def create_recording():
    """Start or stop recording."""
    data = request.json or {}
    action = data.get("action", "")

    if action == "start":
        start_recording()
        return jsonify({"status": "ok", "recording": True})
    elif action == "stop":
        events = stop_recording()
        return jsonify({"status": "ok", "recording": False, "events": events})
    return jsonify({"error": "Invalid action"}), 400

@app.route("/api/recordings/<name>", methods=["GET"])
def get_recording(name):
    """Return a specific recording."""
    events = load_recording(name)
    return jsonify({"events": events})

@app.route("/api/recordings/<name>", methods=["POST"])
def save_named_recording(name):
    """Save the current recording with a name."""
    data = request.json or {}
    events = data.get("events", [])
    saved = save_recording(name, events)
    return jsonify({"status": "ok", "events": saved})

@app.route("/api/recordings/<name>", methods=["DELETE"])
def remove_recording(name):
    """Delete a recording."""
    if delete_recording(name):
        return jsonify({"status": "ok"})
    return jsonify({"error": "Recording not found"}), 404

@app.route("/api/latency")
def get_latency_stats():
    """Return gesture-to-action latency statistics."""
    stats = state.get_latency_stats()
    return jsonify(stats)

@app.route("/api/health")
def health_check():
    """Return system health status."""
    from runtime import state
    current_state = state.get_state()

    health = {
        "status": "healthy",
        "camera": current_state.get("paused", True) is False,
        "hand_detected": current_state.get("hand_detected", False),
        "uptime": state.uptime(),
    }

    if not health["camera"]:
        health["status"] = "degraded"

    return jsonify(health)

@app.route("/video_feed")
def video_feed():
    """MJPEG stream of the camera."""
    if not ENABLE_CAMERA_PREVIEW:
        return "Camera preview disabled", 403

    def generate_frames():
        while True:
            frame = frames.get()
            if frame is None:
                continue
            
            # Draw something lightweight maybe, but gesture.py doesn't annotate the base frame
            # if visualization is off. But we can just send the raw frame for the dashboard.
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            if not ret:
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            # Throttling a bit to save bandwidth to local interface
            cv2.waitKey(30)

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def run_server():
    """Start the dashboard server."""
    # Run silently
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=False, use_reloader=False)
