"""Flask web dashboard for GestureSlides."""

import cv2
import queue
from flask import Flask, Response, jsonify, render_template, request

from config import WEB_SERVER_HOST, WEB_SERVER_PORT, ENABLE_CAMERA_PREVIEW
from runtime import config, state, frames

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
