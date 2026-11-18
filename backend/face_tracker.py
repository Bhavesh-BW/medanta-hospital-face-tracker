import os
import sys
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass
import time
import math
import uuid
import json
import base64
import sqlite3
import collections
import copy
import threading
import queue
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timedelta, timezone

# ── IST Timezone Configuration (+05:30) ─────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30), name='IST')

def get_ist_now():
    """Returns current datetime in IST."""
    return datetime.now(IST)

def get_ist_iso():
    """Returns ISO 8601 string in IST: YYYY-MM-DDTHH:MM:SS.ffffff"""
    return datetime.now(IST).strftime('%Y-%m-%dT%H:%M:%S.%f')

def get_ist_str(fmt="%I:%M:%S %p IST"):
    """Returns formatted string in IST."""
    return datetime.now(IST).strftime(fmt)

import cv2
import numpy as np

# ── Paths & Configuration ───────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / 'dist'
MODELS = ROOT / 'models'

LIVE_DB_PATH = os.environ.get('FACE_TRACKER_DB', str(ROOT / 'face_tracker.db'))
DEMO_DB_PATH = '/data/face_tracker_demo.db' if os.path.exists('/data') else str(ROOT / 'face_tracker_demo.db')
RECORDINGS_DIR = Path('/data/recordings') if os.path.exists('/data/recordings') else (ROOT / 'recordings' if (ROOT / 'recordings').exists() else Path(r"d:\Python Projects\recordings"))

def get_playlist(path_or_dir):
    if not path_or_dir:
        return []
    p = str(path_or_dir)
    if os.path.isdir(p):
        files = sorted([
            os.path.join(p, f) for f in os.listdir(p)
            if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.ts'))
        ])
        if files:
            return files
    if not os.path.exists(p) and os.path.isdir(os.path.dirname(p)):
        parent = os.path.dirname(p)
        prefix = os.path.basename(p)
        matched = sorted([
            os.path.join(parent, f) for f in os.listdir(parent)
            if f.lower().startswith(prefix.lower()) and f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.ts'))
        ])
        if matched:
            return matched
    if os.path.isfile(p):
        return [p]
    return [p]

DEMO_RECORDINGS_MAP = {
    'main': str(RECORDINGS_DIR / "main"),
    'cam_cd9e9a': str(RECORDINGS_DIR / "cam_cd9e9a"),
    'recep1': str(RECORDINGS_DIR / "recep1"),
    'outside': str(RECORDINGS_DIR / "outside")
}
MODE_STATE_FILE = ROOT / "feed_mode.json"
CURRENT_FEED_MODE = 'live'
if os.path.exists(MODE_STATE_FILE):
    try:
        with open(MODE_STATE_FILE, 'r') as fp:
            CURRENT_FEED_MODE = json.load(fp).get('mode', 'live')
    except Exception:
        pass

DB_PATH = DEMO_DB_PATH if CURRENT_FEED_MODE == 'demo' else LIVE_DB_PATH
RTSP_BASE = os.environ.get('RTSP_BASE', 'rtsp://124.123.89.162:31554/live')
PORT = int(os.environ.get('PORT', '8198'))
HOST = os.environ.get('HOST', '0.0.0.0')

def init_demo_db():
    global DB_PATH
    old_db = DB_PATH
    DB_PATH = DEMO_DB_PATH
    init_db()
    DB_PATH = old_db
    conn_live = sqlite3.connect(LIVE_DB_PATH)
    conn_demo = sqlite3.connect(DEMO_DB_PATH)
    try:
        cur_d = conn_demo.cursor()
        cur_d.execute("SELECT COUNT(*) FROM cameras")
        if cur_d.fetchone()[0] == 0:
            cur_l = conn_live.cursor()
            cur_l.execute("SELECT id, name, location, rtsp, created_at, role FROM cameras")
            for row in cur_l.fetchall():
                cur_d.execute("INSERT OR REPLACE INTO cameras VALUES (?, ?, ?, ?, ?, ?)", row)
        cur_d.execute("SELECT COUNT(*) FROM blacklist_watchlist")
        if cur_d.fetchone()[0] == 0:
            cur_l = conn_live.cursor()
            cur_l.execute("SELECT * FROM blacklist_watchlist")
            cols = [c[0] for c in cur_l.description]
            ph = ','.join(['?'] * len(cols))
            for row in cur_l.fetchall():
                cur_d.execute(f"INSERT OR REPLACE INTO blacklist_watchlist VALUES ({ph})", row)
        conn_demo.commit()
    except Exception as e:
        print("Demo DB sync note:", e)
    finally:
        conn_demo.close()
        conn_live.close()

def load_cameras_from_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            rtsp TEXT NOT NULL,
            created_at TEXT
        )
    ''')
    try:
        cur.execute("ALTER TABLE cameras ADD COLUMN role TEXT DEFAULT 'entry'")
    except Exception:
        pass
    cur.execute("UPDATE cameras SET role = 'entry' WHERE role IS NULL OR role = ''")
    conn.commit()

    cur.execute('SELECT id, name, location, rtsp, role FROM cameras ORDER BY rowid ASC')
    rows = cur.fetchall()
    if not rows:
        default_cams = [
            ('main', 'Main Porch Entry — Inbound', 'Gate 01 Main Entry', f'{RTSP_BASE}/main', 'entry'),
            ('cam_cd9e9a', 'Main porch exit', 'porch exit', f'{RTSP_BASE}/main_exit', 'exit'),
            ('recep1', 'Main Reception & OPD Lobby', 'Tower A Ground Lobby', f'{RTSP_BASE}/recep1', 'internal'),
            ('outside', 'Hospital Outside Perimeter / Gates', 'Exterior Perimeter', f'{RTSP_BASE}/outside', 'perimeter')
        ]
        now_ts = get_ist_iso()
        for cid, cname, cloc, crtsp, crole in default_cams:
            cur.execute('INSERT OR IGNORE INTO cameras (id, name, location, rtsp, created_at, role) VALUES (?, ?, ?, ?, ?, ?)',
                        (cid, cname, cloc, crtsp, now_ts, crole))
        conn.commit()
        cur.execute('SELECT id, name, location, rtsp, role FROM cameras ORDER BY rowid ASC')
        rows = cur.fetchall()
    conn.close()

    cams = {}
    for r in rows:
        crole = r[4] if len(r) > 4 and r[4] else 'entry'
        cams[r[0]] = {
            'id': r[0],
            'name': r[1],
            'location': r[2],
            'rtsp': r[3],
            'role': crole
        }
    return cams

CAMERA_SOURCES = load_cameras_from_db()

MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
}

# ── SQLite Database Setup ──────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    cur = conn.cursor()
    try:
        cur.execute('PRAGMA journal_mode = WAL;')
        cur.execute('PRAGMA busy_timeout = 5000;')
    except Exception:
        pass
    cur.execute('''
        CREATE TABLE IF NOT EXISTS unique_visitors (
            id TEXT PRIMARY KEY,
            gender TEXT,
            gender_confidence REAL,
            age INTEGER,
            embedding_json TEXT,
            photo_b64 TEXT,
            crops_json TEXT,
            first_seen TEXT,
            last_seen TEXT,
            total_sightings INTEGER DEFAULT 1,
            last_camera TEXT,
            is_blacklisted INTEGER DEFAULT 0,
            blacklist_reason TEXT
        )
    ''')
    for col in [
        ('crops_json', 'TEXT'),
        ('gender_locked', 'INTEGER DEFAULT 0'),
        ('previous_camera', 'TEXT'),
        ('previous_camera_name', 'TEXT')
    ]:
        try:
            cur.execute(f'ALTER TABLE unique_visitors ADD COLUMN {col[0]} {col[1]}')
        except Exception:
            pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS visitor_sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id TEXT,
            camera_id TEXT,
            timestamp TEXT,
            gender TEXT,
            confidence REAL,
            photo_b64 TEXT,
            is_blacklisted INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_watchlist (
            id TEXT PRIMARY KEY,
            name TEXT,
            alias TEXT,
            category TEXT DEFAULT 'visitor',
            reason TEXT,
            embedding_json TEXT,
            photo_b64 TEXT,
            crops_json TEXT,
            enrolled_at TEXT,
            enrolled_by TEXT DEFAULT 'admin',
            active INTEGER DEFAULT 1
        )
    ''')
    try:
        cur.execute('ALTER TABLE blacklist_watchlist ADD COLUMN crops_json TEXT')
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS security_alerts (
            id TEXT PRIMARY KEY,
            watchlist_id TEXT,
            person_name TEXT,
            reason TEXT,
            camera_id TEXT,
            camera_name TEXT,
            confidence REAL,
            photo_b64 TEXT,
            timestamp TEXT,
            status TEXT DEFAULT 'open'
        )
    ''')
    for col in [('location', 'TEXT'), ('created_at', 'TEXT')]:
        try:
            cur.execute(f'ALTER TABLE security_alerts ADD COLUMN {col[0]} {col[1]}')
        except Exception:
            pass

    # High-Performance Indexes for 0ms Query Resolution
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_visitor_id ON visitor_sightings (visitor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_camera_id ON visitor_sightings (camera_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_vs_timestamp ON visitor_sightings (timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uv_last_seen ON unique_visitors (last_seen DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_uv_is_blacklisted ON unique_visitors (is_blacklisted)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bl_active ON blacklist_watchlist (active)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON security_alerts (status)")

    cur.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('auto_enroll_enabled', '1')")
    cur.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('dwell_window_hours', '4.0')")

    conn.commit()
    conn.close()

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a_f = np.asarray(a).flatten()
    b_f = np.asarray(b).flatten()
    dot = np.dot(a_f, b_f)
    norm = (np.linalg.norm(a_f) * np.linalg.norm(b_f)) + 1e-9
    return float(dot / norm)

def bbox_iou(boxA, boxB) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    interW = max(0, xB - xA)
    interH = max(0, yB - yA)
    interArea = interW * interH
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    unionArea = boxAArea + boxBArea - interArea
    if unionArea <= 0:
        return 0.0
    return interArea / float(unionArea)


# ── Camera Stream Pipeline (Concurrent Multi-Camera Worker) ────────────────

class CameraStreamPipeline:
    def __init__(self, camera_id: str, name: str, location: str, rtsp_url: str, engine, role: str = 'entry'):
        self.camera_id = camera_id
        self.name = name
        self.location = location
        self.rtsp_url = rtsp_url
        self.engine = engine
        self.role = role or 'entry'

        self.lock = threading.Condition()
        self.running = True
        self.generation = 0
        self.latest_frame = None
        self.latest_jpeg = None
        self.frame_id = 0
        self.last_processed_frame_id = -1
        self.sequence = 0
        self.fps = 0.0
        self.last_frame_ts = 0
        self.is_rtsp_connected = False
        self.error_msg = None
        self.active_tracks = {}
        self.recently_closed_tracks = collections.deque(maxlen=25)
        self.next_track_id = 1

        # Start capture and processing threads for this camera
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.capture_thread.start()
        self.process_thread.start()

    def stop(self):
        self.running = False
        with self.lock:
            self.lock.notify_all()

    def switch_source(self, new_url):
        with self.lock:
            self.rtsp_url = new_url
            self.generation += 1
            self.active_tracks.clear()
            if hasattr(self, 'recently_closed_tracks'):
                self.recently_closed_tracks.clear()
            self.latest_frame = None
            self.latest_jpeg = None
            self.frame_id += 1
            self.last_processed_frame_id = -1
            self.lock.notify_all()
        print(f"[PIPELINE SWITCHED] Camera {self.camera_id} -> {new_url}")

    def handle_feed_click(self, norm_x: float, norm_y: float, action: str = 'toggle_blacklist'):
        """Process an interactive click on the live CCTV stream to instantly flag or manage targets,
        supporting high-speed walking visitors through trajectory matching and proximity search."""
        W, H = 1280, 720
        if self.latest_frame is not None:
            H, W = self.latest_frame.shape[:2]

        fx = norm_x * W
        fy = norm_y * H

        now_t = time.time()
        best_track = None
        min_dist = float('inf')

        with self.lock:
            all_candidate_tracks = list(self.active_tracks.values()) + list(getattr(self, 'recently_closed_tracks', []))

        # 1. Exact or Padded Bounding Box Hit Test (checks current position and walking trajectory over last 2.8s)
        for trk in all_candidate_tracks:
            bx, by, bw, bh = trk['bbox']
            # Allow generous padding (75% or min 40px) for moving faces
            pad_w = max(40, int(bw * 0.75))
            pad_h = max(40, int(bh * 0.75))
            if (bx - pad_w) <= fx <= (bx + bw + pad_w) and (by - pad_h) <= fy <= (by + bh + pad_h):
                cx = bx + bw / 2.0
                cy = by + bh / 2.0
                dist = (fx - cx) ** 2 + (fy - cy) ** 2
                if dist < min_dist:
                    min_dist = dist
                    best_track = trk

            # Check recent trajectory points (where the person walked 0.2s - 2.8s ago)
            history = trk.get('history') or []
            for h_item in history:
                h_ts, h_cx, h_cy, h_bw, h_bh, h_bbox = h_item
                if (now_t - h_ts) > 2.8:
                    continue
                h_pad_w = max(45, int(h_bw * 0.85))
                h_pad_h = max(45, int(h_bh * 0.85))
                h_bx, h_by = h_bbox[0], h_bbox[1]
                if (h_bx - h_pad_w) <= fx <= (h_bx + h_bw + h_pad_w) and (h_by - h_pad_h) <= fy <= (h_by + h_bh + h_pad_h):
                    dist = (fx - h_cx) ** 2 + (fy - h_cy) ** 2
                    if dist < min_dist:
                        min_dist = dist
                        best_track = trk

        # 2. Proximity Fallback: If user clicked near a moving person (within 180px or 3.2x face dimension)
        if not best_track:
            for trk in all_candidate_tracks:
                bx, by, bw, bh = trk['bbox']
                cx = bx + bw / 2.0
                cy = by + bh / 2.0
                d = math.hypot(fx - cx, fy - cy)
                max_radius = max(180, max(bw, bh) * 3.2)
                if d <= max_radius and (d ** 2) < min_dist:
                    min_dist = (d ** 2)
                    best_track = trk

                history = trk.get('history') or []
                for h_item in history:
                    h_ts, h_cx, h_cy, h_bw, h_bh, _ = h_item
                    if (now_t - h_ts) > 2.8:
                        continue
                    hd = math.hypot(fx - h_cx, fy - h_cy)
                    h_max_radius = max(180, max(h_bw, h_bh) * 3.2)
                    if hd <= h_max_radius and (hd ** 2) < min_dist:
                        min_dist = (hd ** 2)
                        best_track = trk

        if not best_track:
            return {'success': False, 'error': 'No face detected near clicked coordinates'}

        visitor_id = best_track.get('visitor_id')
        if not visitor_id or visitor_id.startswith('UNTRACKED') or visitor_id.startswith('UNENROLLED'):
            return {'success': False, 'error': 'Face has no registered visitor profile to blacklist'}

        is_bl = best_track.get('is_blacklisted', False)

        if action == 'toggle_blacklist':
            if not hasattr(self, '_last_click_times'):
                self._last_click_times = {}
            last_t = self._last_click_times.get(visitor_id, 0)
            if (now_t - last_t) < 0.8:
                return {
                    'success': True,
                    'action': 'blacklisted' if is_bl else 'removed',
                    'visitor_id': visitor_id,
                    'message': f"Target {visitor_id} status updated"
                }
            self._last_click_times[visitor_id] = now_t

            if is_bl:
                self.engine.remove_from_blacklist_by_alias(visitor_id)
                best_track['is_blacklisted'] = False
                best_track['threat_name'] = None
                best_track['reason'] = None
                return {
                    'success': True,
                    'action': 'removed',
                    'visitor_id': visitor_id,
                    'message': f"Target {visitor_id} removed from security watchlist"
                }
            else:
                target_name = best_track.get('threat_name') or f"Target {visitor_id}"
                reason = "Flagged instantly via Live HUD Click"
                ok, res = self.engine.add_to_blacklist(visitor_id, name=target_name, reason=reason)
                if ok:
                    best_track['is_blacklisted'] = True
                    best_track['threat_name'] = target_name
                    best_track['reason'] = reason

                    # Get primary photo from cache or best_track
                    vis_photo = None
                    if visitor_id in self.engine.unique_cache_by_id:
                        vis_photo = self.engine.unique_cache_by_id[visitor_id].get('photo_b64')
                    if not vis_photo:
                        vis_photo = best_track.get('photo_b64')

                    # Create and persist threat alert into SQLite immediately
                    alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
                    now_iso = get_ist_iso()
                    try:
                        conn = sqlite3.connect(DB_PATH, timeout=20.0)
                        cur = conn.cursor()
                        cur.execute('''
                            INSERT INTO security_alerts (id, watchlist_id, person_name, reason, camera_id, camera_name, confidence, photo_b64, timestamp, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                        ''', (alert_id, res, target_name, reason, self.camera_id, self.name, 0.99, vis_photo, now_iso))
                        conn.commit()
                        conn.close()
                    except Exception as err:
                        print(f"[SECURITY ALERT INSERT ERROR]: {err}")

                    # Trigger instantaneous cinematic threat broadcast
                    alert_payload = {
                        'id': alert_id,
                        'watchlist_id': res,
                        'person_name': target_name,
                        'reason': reason,
                        'camera_id': self.camera_id,
                        'camera_name': self.name,
                        'confidence': 0.99,
                        'timestamp': get_ist_str("%I:%M:%S %p IST"),
                        'photo_b64': vis_photo
                    }
                    self.engine._broadcast_alert(alert_payload)
                    return {
                        'success': True,
                        'action': 'blacklisted',
                        'visitor_id': visitor_id,
                        'watchlist_id': res,
                        'name': target_name,
                        'alert': alert_payload,
                        'message': f"Target {visitor_id} blacklisted instantly on live feed!"
                    }
                return {'success': False, 'error': str(res)}

        return {'success': False, 'error': f"Unknown action: {action}"}

    def _generate_synthetic_frame(self, t: float):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :] = [18, 22, 28]  # Sleek dark slate CCTV background
        for gx in range(0, 1280, 160):
            cv2.line(frame, (gx, 0), (gx, 720), (28, 35, 45), 1)
        for gy in range(0, 720, 120):
            cv2.line(frame, (0, gy), (1280, gy), (28, 35, 45), 1)

        cw, ch = 760, 290
        cx1, cy1 = (1280 - cw) // 2, (720 - ch) // 2
        cx2, cy2 = cx1 + cw, cy1 + ch
        cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), (28, 34, 44), -1)
        cv2.rectangle(frame, (cx1, cy1), (cx2, cy2), (45, 60, 80), 2)

        cv2.rectangle(frame, (cx1 + 30, cy1 + 25), (cx1 + 430, cy1 + 65), (25, 90, 210), -1)
        cv2.putText(frame, "RTSP CAMERA SIGNAL OFFLINE (404)", (cx1 + 45, cy1 + 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 2)

        clean_name = self.name.replace('—', '-').replace('–', '-')
        cv2.putText(frame, f"CHANNEL: {clean_name.upper()}", (cx1 + 30, cy1 + 105),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (240, 245, 250), 2)
        cv2.putText(frame, f"LOCATION: {self.location.upper()}", (cx1 + 30, cy1 + 138),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 215, 230), 1)
        cv2.putText(frame, f"SOURCE:  {self.rtsp_url}", (cx1 + 30, cy1 + 168),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160, 175, 195), 1)
        
        cv2.putText(frame, "REASON:  Hospital edge camera / stream publisher is currently disconnected.", 
                    (cx1 + 30, cy1 + 205), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (140, 160, 210), 1)
        
        dots = "." * (int(t * 2) % 4)
        cv2.putText(frame, f"STATUS:  Auto-reconnecting to stream relay every 3 seconds{dots}", 
                    (cx1 + 30, cy1 + 242), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (60, 210, 120), 2)
        cv2.putText(frame, "Live video will resume automatically as soon as camera stream pushes frames.", 
                    (cx1 + 30, cy1 + 270), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 135, 150), 1)

        scan_x = int(cx1 + ((t * 240) % cw))
        cv2.line(frame, (scan_x, cy1), (scan_x, cy2), (60, 180, 240), 1)

        ts_str = get_ist_str("%Y-%m-%d %H:%M:%S IST")
        cv2.rectangle(frame, (0, 0), (1280, 50), (12, 15, 20), -1)
        cv2.putText(frame, f"MEDANTA HOSPITAL - {clean_name.upper()} | {ts_str}", 
                    (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 215, 230), 2)
        cv2.putText(frame, "[STANDBY RELAY]", (1100, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 160, 240), 2)
        return frame

    def _capture_loop(self):
        t0 = time.time()
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
        while self.running:
            gen = self.generation
            playlist = get_playlist(self.rtsp_url)
            p_idx = 0
            current_source = playlist[p_idx] if playlist else self.rtsp_url
            is_file = (playlist and len(playlist) > 0 and os.path.isfile(playlist[0])) or os.path.isfile(current_source)

            cap = cv2.VideoCapture(current_source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000
            ])
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                with self.lock:
                    self.is_rtsp_connected = False
                    self.error_msg = f"Connecting to RTSP relay ({self.name})..."
                cap.release()

                retry_start = time.time()
                while self.running and self.generation == gen and (time.time() - retry_start) < 3.0:
                    frame = self._generate_synthetic_frame(time.time() - t0)
                    with self.lock:
                        self.latest_frame = frame
                        self.lock.notify_all()
                    time.sleep(0.04)
                continue

            with self.lock:
                self.is_rtsp_connected = True
                self.error_msg = None

            video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_delay = 1.0 / max(10.0, min(60.0, video_fps)) if is_file else 0.0

            while self.running and self.generation == gen:
                ok, frame = cap.read()
                if not ok:
                    if is_file and playlist:
                        p_idx = (p_idx + 1) % len(playlist)
                        current_source = playlist[p_idx]
                        cap.release()
                        cap = cv2.VideoCapture(current_source, cv2.CAP_FFMPEG)
                        time.sleep(0.02)
                        continue
                    with self.lock:
                        self.is_rtsp_connected = False
                    break
                with self.lock:
                    self.is_rtsp_connected = True
                    self.latest_frame = frame
                    self.frame_id += 1
                    self.lock.notify_all()
                if is_file and frame_delay > 0:
                    time.sleep(frame_delay)

            cap.release()
            time.sleep(0.5)

    def _process_loop(self):
        last_alert_time = {}
        while self.running:
            try:
                self._process_single_frame(last_alert_time)
            except Exception as err:
                print(f"[CAM {self.camera_id} LOOP RECOVERED]:", err)
                time.sleep(0.04)

    def _process_single_frame(self, last_alert_time):
        with self.lock:
            # Wait for a fresh frame or timeout
            while self.running and (self.latest_frame is None or self.frame_id == self.last_processed_frame_id):
                self.lock.wait(timeout=0.04)
                if not self.running:
                    return
                # If camera is offline/standby, let it through periodically to update the standby HUD animation
                if not self.is_rtsp_connected and self.latest_frame is not None:
                    break

            if not self.running or self.latest_frame is None:
                return

            frame = self.latest_frame.copy()
            current_fid = self.frame_id
            is_rtsp = self.is_rtsp_connected

        self.last_processed_frame_id = current_fid

        # Fast unblocked path when camera signal is offline
        if not is_rtsp:
            # Adaptive JPEG Compression: dynamically throttle size on crowded scenes
            num_active = len(self.active_tracks)
            if num_active >= 4:
                jpeg_quality = 68
            elif num_active >= 2:
                jpeg_quality = 74
            else:
                jpeg_quality = 80
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
            if ok:
                with self.lock:
                    self.latest_jpeg = jpeg.tobytes()
                    self.sequence += 1
                    pub_time = time.monotonic()
                    if self.last_frame_ts:
                        fps = 1.0 / max(pub_time - self.last_frame_ts, 0.001)
                        self.fps = round(self.fps * 0.8 + fps * 0.2, 1)
                    self.last_frame_ts = pub_time
                    self.lock.notify_all()
            time.sleep(0.04)
            return

        now = time.monotonic()
        now_iso = get_ist_iso()
        now_epoch = time.time()
        faces = self.engine._detect_faces(frame)
        annotated = frame.copy()

        matched_track_ids = set()

        is_exit_camera = (getattr(self, 'role', 'entry') == 'exit')

        for face in faces:
            x, y, w, h = [int(v) for v in face[:4]]
            det_score = float(face[-1])
            min_det = 0.70 if is_exit_camera else 0.60
            if det_score < min_det or w < 20 or h < 24:
                continue

            # False Positive Filter 1: Exit camera sitting guard lap/knees/hands exclusion
            if is_exit_camera and x > 1200 and y > 650:
                continue

            # False Positive Filter 2: Anatomical 5-point landmark geometry (rejects hands, cuffs, buttons, clothing folds)
            if len(face) >= 8 and face[4] > 0 and face[6] > 0:
                re_x, re_y = face[4], face[5]
                le_x, le_y = face[6], face[7]
                eye_dist = math.hypot(le_x - re_x, le_y - re_y)
                if (eye_dist / max(w, 1)) < 0.12:
                    continue

            cx = x + w / 2.0
            cy = y + h / 2.0

            # Crop face thumbnail (tight facial crop for biometrics & gallery filmstrip)
            H_f, W_f = frame.shape[:2]
            y1 = max(0, y)
            y2 = min(H_f, y + h)
            x1 = max(0, x)
            x2 = min(W_f, x + w)
            face_crop = frame[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else None

            # False Positive Filter 3: Dark clothing / trousers contrast check
            # Hands resting on black trousers have >42% pitch-black pixels. Real faces have <5%.
            if face_crop is not None and face_crop.size > 0:
                hsv_v = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)[:, :, 2]
                if np.mean(hsv_v < 40) > 0.42:
                    continue

            # Assess frontality & sharpness for crop saving / enrollment (used downstream)
            is_sharp, quality_score = self.engine._is_sharp_face_crop(face_crop, face, det_score)

            # Expanded Upper Body / Torso crop for realistic outfit/person identification on visitor card
            pad_x = int(w * 0.90)
            pad_top = int(h * 0.30)
            pad_bot = int(h * 2.80)
            bx1 = max(0, x - pad_x)
            bx2 = min(W_f, x + w + pad_x)
            by1 = max(0, y - pad_top)
            by2 = min(H_f, y + h + pad_bot)
            body_crop = frame[by1:by2, bx1:bx2] if by2 > by1 and bx2 > bx1 else face_crop

            # Lazy Crop & Photo base64 encoding (only computed on-demand when saving to DB / broadcast)
            _cached_face_b64 = [None]
            _cached_photo_b64 = [None]

            def get_face_b64():
                if _cached_face_b64[0] is None:
                    if face_crop is not None and face_crop.size > 0:
                        ok, buf = cv2.imencode('.jpg', face_crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
                        if ok:
                            _cached_face_b64[0] = f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode()}"
                    if not _cached_face_b64[0]:
                        _cached_face_b64[0] = ""
                return _cached_face_b64[0]

            def get_photo_b64():
                if _cached_photo_b64[0] is None:
                    if body_crop is not None and body_crop.size > 0:
                        ok, buf = cv2.imencode('.jpg', body_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ok:
                            _cached_photo_b64[0] = f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode()}"
                    if not _cached_photo_b64[0]:
                        _cached_photo_b64[0] = get_face_b64()
                return _cached_photo_b64[0]

            # Fast Spatial Track Association (O(1) IoU & Proximity Geometry)
            best_track_id = None
            best_iou = 0.0
            for tid, trk in self.active_tracks.items():
                if tid in matched_track_ids:
                    continue
                iou = bbox_iou((x, y, w, h), trk['bbox'])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = tid

            if best_track_id is None:
                min_dist = 140.0
                for tid, trk in self.active_tracks.items():
                    if tid in matched_track_ids:
                        continue
                    tcx = trk['bbox'][0] + trk['bbox'][2] / 2.0
                    tcy = trk['bbox'][1] + trk['bbox'][3] / 2.0
                    dist = math.hypot(cx - tcx, cy - tcy)
                    if dist < min_dist:
                        min_dist = dist
                        best_track_id = tid

            matched_visitor = None
            is_transit = False
            prev_cam_name = None

            # Priority A: Spatial track continuity (O(1) in-memory lookup)
            if best_track_id is not None:
                tid_vis_id = self.active_tracks[best_track_id].get('visitor_id')
                if tid_vis_id and tid_vis_id in self.engine.unique_cache_by_id:
                    matched_visitor = self.engine.unique_cache_by_id[tid_vis_id]

            # Check recently closed tracks (within last 2.5 seconds)
            if matched_visitor is None and best_track_id is None and getattr(self, 'recently_closed_tracks', None):
                for trk in self.recently_closed_tracks:
                    if (now_epoch - trk.get('last_seen_epoch', 0)) <= 2.5:
                        tcx = trk['bbox'][0] + trk['bbox'][2] / 2.0
                        tcy = trk['bbox'][1] + trk['bbox'][3] / 2.0
                        if math.hypot(cx - tcx, cy - tcy) < 140.0:
                            tid_vis = trk.get('visitor_id')
                            if tid_vis and tid_vis in self.engine.unique_cache_by_id:
                                matched_visitor = self.engine.unique_cache_by_id[tid_vis]
                                break

            # Track-First, Infer-On-Demand Gate:
            # Check if this face needs full AI embedding & recognition
            need_embedding = False
            if matched_visitor is None:
                # Untracked face or new arrival: MUST extract embedding to identify or enroll
                need_embedding = True
            elif not is_exit_camera and is_sharp and quality_score > (matched_visitor.get('best_quality', 0.0) + 4.0) and det_score >= 0.76:
                # Tracked visitor, but face is significantly sharper (+4 quality): periodic quality upgrade
                trk_obj = self.active_tracks.get(best_track_id, {})
                if (now_epoch - trk_obj.get('last_embedding_epoch', 0)) >= 2.0:
                    need_embedding = True

            if need_embedding:
                emb = self.engine._extract_embedding(frame, face)
                instant_gender, gender_conf, age = self.engine._estimate_gender_and_age(frame, face, face_crop, self.camera_id, body_crop)
                if best_track_id is not None and best_track_id in self.active_tracks:
                    self.active_tracks[best_track_id]['last_embedding_epoch'] = now_epoch
                # 1. Watchlist Screening via Vector Matrix with High-Confidence Filter
                matched_blacklist, max_bl_sim = self.engine.search_watchlist(emb)
            else:
                # Fast Path: reuse established identity from active spatial track (O(1))
                emb = None
                instant_gender = matched_visitor.get('gender')
                gender_conf = 0.90
                age = matched_visitor.get('age', 28)
                matched_blacklist = None
                max_bl_sim = 0.0

            # Watchlist Confirmation Logic (Prevents innocent followers from flickering red)
            bl_confirmed = False
            if matched_blacklist is not None:
                is_known_non_bl = (matched_visitor is not None and not matched_visitor.get('is_blacklisted'))
                if is_known_non_bl:
                    # Established non-blacklisted visitor: require high bar (0.62+) to avoid false positive
                    if max_bl_sim >= 0.62:
                        bl_confirmed = True
                else:
                    if max_bl_sim >= 0.58:
                        bl_confirmed = True
                    elif max_bl_sim >= 0.50:
                        prev_bl_hits = self.active_tracks[best_track_id].get('bl_consecutive_hits', 0) if best_track_id is not None else 0
                        if (prev_bl_hits + 1) >= 3:
                            bl_confirmed = True

            if not bl_confirmed:
                matched_blacklist = None

            # Priority B: Watchlist alias binding (O(1))
            if matched_visitor is None and matched_blacklist is not None:
                alias = matched_blacklist.get('alias')
                if alias and alias in self.engine.unique_cache_by_id:
                    matched_visitor = self.engine.unique_cache_by_id[alias]

            is_exit_camera = (getattr(self, 'role', 'entry') == 'exit')

            # Priority C: Vector Matrix Search (<0.3ms across thousands of faces)
            if matched_visitor is None and emb is not None:
                max_active_sec = getattr(self.engine, 'max_active_seconds', 14400.0)
                matched_visitor, max_vis_sim = self.engine.search_gallery(
                    emb,
                    query_gender=instant_gender, gender_conf=gender_conf,
                    is_exit=is_exit_camera,
                    max_active_seconds=max_active_sec
                )
                # Secondary verification: confirm match against stored embeddings of this visitor
                if matched_visitor is not None:
                    vis_embs = matched_visitor.get('embeddings', [matched_visitor.get('embedding')])
                    vis_embs = [ve for ve in vis_embs if ve is not None]
                    if vis_embs:
                        all_sims = [cosine_sim(emb, ve) for ve in vis_embs]
                        max_indiv_sim = max(all_sims)
                        min_match_indiv = 0.58 if getattr(self.engine, 'arcface_sess', None) is not None else 0.48
                        if max_indiv_sim < min_match_indiv:
                            matched_visitor = None
                            max_vis_sim = 0.0

            # Registration or Update
            if matched_visitor is None:
                if is_exit_camera:
                    # EXIT CAMERA: Do NOT register new visitor profile or save embeddings!
                    # Treat as anonymous / untracked departure to keep database and counts clean.
                    visitor_id = "UNTRACKED_EXIT"
                    gender = instant_gender or 'male'
                    age = age or 28
                elif not getattr(self.engine, 'auto_enroll_enabled', True):
                    # AUTO ENROLL IS PAUSED:
                    # Do NOT create unique visitor profile, do NOT save embeddings, do NOT write to DB.
                    # Show live HUD box with UNENROLLED / CAPTURE PAUSED tag.
                    visitor_id = "UNENROLLED"
                    gender = instant_gender or 'male'
                    age = age or 28
                else:
                    # ENTRY / CHECKPOINT CAMERA: Normal New Visitor Registration
                    track_obj = self.active_tracks.get(best_track_id) if best_track_id is not None else None
                    track_len = len(track_obj.get('history', [])) if track_obj is not None else 1

                    # Enrollment eligibility:
                    # Isolated crop must confirm as a valid frontal face, with sharp features and good confidence.
                    can_enroll = (
                        is_sharp 
                        and quality_score >= 18.0 
                        and det_score >= 0.64
                        and self.engine.is_valid_face_crop(face_crop)
                    )

                    corridor_dup = False
                    if can_enroll and hasattr(self.engine, 'recent_auto_enrolled_locs'):
                        for past_epoch, past_vid, past_emb, past_cam, past_cx, past_cy in self.engine.recent_auto_enrolled_locs:
                            if (now_epoch - past_epoch) < 6.0 and past_cam == self.camera_id:
                                dist = np.hypot(cx - past_cx, cy - past_cy)
                                if dist < 180:
                                    corridor_dup = True
                                    break
                            if (now_epoch - past_epoch) < 60.0 and past_emb is not None:
                                bio_sim = cosine_sim(emb, past_emb)
                                min_bio_thresh = 0.40 if getattr(self.engine, 'arcface_sess', None) is not None else 0.38
                                if bio_sim >= min_bio_thresh:
                                    corridor_dup = True
                                    break

                    if (not can_enroll) or corridor_dup:
                        # Not yet ready for permanent database profile:
                        # Continue live tracking on HUD with ANALYZING tag without polluting database
                        visitor_id = track_obj.get('visitor_id', 'ANALYZING...') if track_obj else 'ANALYZING...'
                        gender = instant_gender or 'male'
                        age = age or 28
                    else:
                        if matched_blacklist is not None and matched_blacklist.get('alias'):
                            visitor_id = matched_blacklist['alias']
                        else:
                            visitor_id = f"VIS-{uuid.uuid4().hex[:8].upper()}"

                        init_gender = instant_gender or 'male'
                        init_conf = gender_conf if instant_gender else 0.70
                        self.engine.gender_votes[visitor_id] = collections.deque([(init_gender, init_conf)], maxlen=30)
                        gender = init_gender
                        gender_locked_flag = False
                        reg_face_b64 = get_face_b64()
                        reg_photo_b64 = get_photo_b64()
                        crops_list = [reg_face_b64] if reg_face_b64 else ([reg_photo_b64] if reg_photo_b64 else [])

                        matched_visitor = {
                            'id': visitor_id,
                            'gender': gender,
                            'gender_locked': False,
                            'age': age or 28,
                            'embedding': emb,
                            'embeddings': [emb] if emb is not None else [],
                            'first_seen': now_iso,
                            'last_seen': now_iso,
                            'last_seen_epoch': now_epoch,
                            'last_db_sync_epoch': now_epoch,
                            'last_sighting_epoch': now_epoch,
                            'photo_b64': reg_photo_b64,
                            'crops': crops_list,
                            'best_quality': quality_score,
                            'last_camera': self.camera_id,
                            'is_blacklisted': False,
                            'blacklist_reason': None,
                            'db_committed': True
                        }
                        self.engine.unique_cache.append(matched_visitor)
                        self.engine.unique_cache_by_id[visitor_id] = matched_visitor
                        if emb is not None:
                            self.engine.add_to_gallery(matched_visitor, emb)
                            self.engine.recent_auto_enrolled.append((now_epoch, visitor_id, emb))
                            if not hasattr(self.engine, 'recent_auto_enrolled_locs'):
                                self.engine.recent_auto_enrolled_locs = collections.deque(maxlen=40)
                            self.engine.recent_auto_enrolled_locs.append((now_epoch, visitor_id, emb, self.camera_id, cx, cy))
                        if gender_locked_flag:
                            self.engine.locked_genders.add(visitor_id)

                        # Persist verified visitor to database immediately
                        self.engine.async_db_execute("""
                            INSERT INTO unique_visitors (id, gender, gender_confidence, age, embedding_json, photo_b64, crops_json, first_seen, last_seen, last_camera, is_blacklisted, blacklist_reason, gender_locked)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                        """, (visitor_id, gender, gender_conf, age, json.dumps(emb.tolist()) if emb is not None else '[]', reg_photo_b64, json.dumps(crops_list), now_iso, now_iso, self.camera_id, 1 if gender_locked_flag else 0))
                        self.engine.async_db_execute("""
                            INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                            VALUES (?, ?, ?, ?, ?, ?, 0)
                        """, (visitor_id, self.camera_id, now_iso, gender, det_score, reg_photo_b64))
            else:
                # Existing Visitor Matched
                visitor_id = matched_visitor['id']
                if not matched_visitor.get('db_committed') and matched_visitor.get('pending_db_record'):
                    matched_visitor['db_committed'] = True
                    p_rec = matched_visitor.pop('pending_db_record', None)
                    p_sig = matched_visitor.pop('pending_sighting_record', None)
                    if p_rec:
                        self.engine.async_db_execute("""
                            INSERT INTO unique_visitors (id, gender, gender_confidence, age, embedding_json, photo_b64, crops_json, first_seen, last_seen, last_camera, is_blacklisted, blacklist_reason, gender_locked)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                        """, p_rec)
                    if p_sig:
                        self.engine.async_db_execute("""
                            INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                            VALUES (?, ?, ?, ?, ?, ?, 0)
                        """, p_sig)

                # Check Cross-Camera Transit
                last_cam = matched_visitor.get('last_camera')
                if last_cam and last_cam != self.camera_id:
                    prev_seen_epoch = matched_visitor.get('last_seen_epoch', 0)
                    transit_elapsed = now_epoch - prev_seen_epoch
                    prev_seen_date = (matched_visitor.get('first_seen') or now_iso).split('T')[0]
                    curr_date = now_iso.split('T')[0]

                    # Physical walking transit between cameras requires at least 12 seconds.
                    # If seen on another camera less than 12s ago, it is concurrent/overlapping view
                    dwell_limit = getattr(self.engine, 'max_active_seconds', 14400.0)
                    if transit_elapsed < 12.0:
                        matched_visitor['last_seen'] = now_iso
                        matched_visitor['last_seen_epoch'] = now_epoch
                    elif transit_elapsed <= dwell_limit and prev_seen_date == curr_date:
                        # Genuine Active Cross-Camera Transit (12s to configured stay window on the same calendar day)
                        is_transit = True
                        prev_cam_name = CAMERA_SOURCES.get(last_cam, {}).get('name', last_cam)
                        curr_name = self.name

                        # Calculate transit duration
                        duration_mins = max(1, int(transit_elapsed / 60))

                        matched_visitor['previous_camera'] = last_cam
                        matched_visitor['previous_camera_name'] = prev_cam_name
                        matched_visitor['last_camera'] = self.camera_id
                        matched_visitor['last_seen'] = now_iso
                        matched_visitor['last_seen_epoch'] = now_epoch
                        matched_visitor['last_sighting_epoch'] = now_epoch
                        matched_visitor['last_db_sync_epoch'] = now_epoch

                        # Broadcast transit event
                        transit_event = {
                            'visitor_id': visitor_id,
                            'name': matched_visitor.get('name') or visitor_id,
                            'gender': matched_visitor.get('gender', 'unknown'),
                            'from_camera': prev_cam_name,
                            'to_camera': curr_name,
                            'duration_mins': duration_mins,
                            'photo_b64': matched_visitor.get('photo_b64') or get_photo_b64(),
                            'timestamp': get_ist_str("%I:%M:%S %p IST")
                        }
                        self.engine._broadcast_transit(transit_event)

                        self.engine.async_db_execute("""
                            UPDATE unique_visitors
                            SET previous_camera = ?, previous_camera_name = ?, last_camera = ?, last_seen = ?
                            WHERE id = ?
                        """, (last_cam, prev_cam_name, self.camera_id, now_iso, visitor_id))
                        self.engine.async_db_execute("""
                            INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (visitor_id, self.camera_id, now_iso, matched_visitor['gender'], det_score, matched_visitor.get('photo_b64') or get_photo_b64(), 1 if matched_visitor.get('is_blacklisted') else 0))
                    else:
                        # Returning visit or historical passage (>4 hours or across days):
                        # Update current camera position, but do NOT chain as a single continuous multi-camera journey
                        matched_visitor['previous_camera'] = None
                        matched_visitor['previous_camera_name'] = None
                        matched_visitor['last_camera'] = self.camera_id
                        matched_visitor['last_seen'] = now_iso
                        matched_visitor['last_seen_epoch'] = now_epoch
                        matched_visitor['last_sighting_epoch'] = now_epoch
                        matched_visitor['last_db_sync_epoch'] = now_epoch

                        self.engine.async_db_execute("""
                            UPDATE unique_visitors
                            SET last_camera = ?, last_seen = ?
                            WHERE id = ?
                        """, (self.camera_id, now_iso, visitor_id))
                        self.engine.async_db_execute("""
                            INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (visitor_id, self.camera_id, now_iso, matched_visitor['gender'], det_score, matched_visitor.get('photo_b64') or get_photo_b64(), 1 if matched_visitor.get('is_blacklisted') else 0))
                else:
                    matched_visitor['last_camera'] = self.camera_id

                # Dynamic Gender Consensus & Multi-Sample Correction
                # Priority order: manual UI lock > auto-lock > vote consensus
                # Once gender_locked=True (by user OR auto), it is NEVER overwritten by votes again
                if visitor_id in self.engine.locked_genders or matched_visitor.get('gender_locked'):
                    # LOCKED: respect the stored gender unconditionally — no vote processing at all
                    consensus_gender = matched_visitor.get('gender', 'male')
                else:
                    if visitor_id not in self.engine.gender_votes:
                        self.engine.gender_votes[visitor_id] = collections.deque([(matched_visitor.get('gender', instant_gender or 'male'), 0.85)], maxlen=30)
                    if instant_gender is not None and gender_conf >= 0.50:
                        self.engine.gender_votes[visitor_id].append((instant_gender, gender_conf))

                    male_score = sum(c for g, c in self.engine.gender_votes[visitor_id] if g == 'male')
                    female_score = sum(c for g, c in self.engine.gender_votes[visitor_id] if g == 'female')

                    # Consensus based on cumulative multi-sample evidence
                    if female_score >= male_score:
                        consensus_gender = 'female'
                    else:
                        consensus_gender = 'male'

                    # Only write to DB when consensus differs AND visitor is definitely NOT manually locked
                    if consensus_gender != matched_visitor['gender'] and not matched_visitor.get('gender_locked'):
                        matched_visitor['gender'] = consensus_gender
                        self.engine.async_db_execute('UPDATE unique_visitors SET gender = ?, age = ?, last_seen = ? WHERE id = ?',
                                                     (consensus_gender, age, now_iso, visitor_id))

                    # AUTO-LOCK: Only auto-lock if winning gender holds >= 80% of total score over 25+ votes
                    # Never auto-lock aggressively on close calls
                    total_votes = len(self.engine.gender_votes[visitor_id])
                    total_score = male_score + female_score
                    if total_votes >= 25 and total_score > 0 and not matched_visitor.get('gender_locked'):
                        win_score = max(male_score, female_score)
                        if win_score / total_score >= 0.80:
                            self.engine.locked_genders.add(visitor_id)
                            matched_visitor['gender_locked'] = True
                            self.engine.async_db_execute(
                                'UPDATE unique_visitors SET gender = ?, gender_locked = 1, last_seen = ? WHERE id = ?',
                                (consensus_gender, now_iso, visitor_id)
                            )

                gender = matched_visitor['gender']

                # EXIT CAMERA: Do NOT append exit embeddings or overwrite avatar with exit frames!
                if not is_exit_camera:
                    # Dynamic clear crop accumulation with STRICT BIOMETRIC PURITY GATE
                    crops = matched_visitor.get('crops', [])
                    if not isinstance(crops, list):
                        crops = [crops] if crops else []
                    existing_quality = matched_visitor.get('best_quality', 0.0)

                    vis_embs = matched_visitor.get('embeddings', [matched_visitor.get('embedding')])
                    vis_embs = [ve for ve in vis_embs if ve is not None]
                    anchor_emb = vis_embs[0] if vis_embs else matched_visitor.get('embedding')

                    # STRICT BIOMETRIC PURITY GATE:
                    # Any new crop or avatar upgrade MUST match the visitor's anchor embedding >= 0.65!
                    biometric_pure = (emb is not None and anchor_emb is not None and cosine_sim(emb, anchor_emb) >= 0.65)

                    if biometric_pure and is_sharp and quality_score > (existing_quality + 4.0) and det_score >= 0.76:
                        if self.engine.is_valid_face_crop(face_crop):
                            up_photo = get_photo_b64()
                            up_face = get_face_b64()
                            matched_visitor['photo_b64'] = up_photo  # Upper body / torso photo
                            matched_visitor['best_quality'] = quality_score
                            if up_face and up_face in crops:
                                crops.remove(up_face)
                            if up_face:
                                crops.insert(0, up_face)
                            matched_visitor['crops'] = crops[:8]
                            self.engine.async_db_execute('UPDATE unique_visitors SET photo_b64 = ?, crops_json = ?, last_seen = ? WHERE id = ?',
                                                         (up_photo, json.dumps(crops[:8]), now_iso, visitor_id))
                    elif biometric_pure and len(crops) < 8 and quality_score >= 26.0 and det_score >= 0.72:
                        last_crop_epoch = matched_visitor.get('last_crop_epoch', 0)
                        crop_cooldown_ok = (now_epoch - last_crop_epoch) >= 20.0
                        sims = [cosine_sim(emb, ve) for ve in vis_embs]
                        max_sim = max(sims) if sims else 0.0
                        gallery_emb_count = len(vis_embs)
                        if crop_cooldown_ok and 0.62 <= max_sim <= 0.88 and gallery_emb_count < 5:
                            if self.engine.is_valid_face_crop(face_crop):
                                up_face = get_face_b64()
                                up_photo = get_photo_b64()
                                if up_face:
                                    crops.append(up_face)
                                else:
                                    crops.append(up_photo)
                                matched_visitor['crops'] = crops[:8]
                                matched_visitor['embeddings'].append(emb)
                                self.engine.add_to_gallery(matched_visitor, emb)
                                matched_visitor['last_crop_epoch'] = now_epoch
                                self.engine.async_db_execute('UPDATE unique_visitors SET crops_json = ?, last_seen = ? WHERE id = ?',
                                                             (json.dumps(crops[:8]), now_iso, visitor_id))

                matched_visitor['last_seen'] = now_iso
                matched_visitor['last_seen_epoch'] = now_epoch

                # Periodic database sync of last_seen and sightings count for known visitor in camera view (throttled to once per 8s)
                last_db_epoch = matched_visitor.get('last_db_sync_epoch', 0)
                if (now_epoch - last_db_epoch) >= 8.0:
                    matched_visitor['last_db_sync_epoch'] = now_epoch
                    matched_visitor['total_sightings'] = matched_visitor.get('total_sightings', 1) + 1
                    self.engine.async_db_execute("""
                        UPDATE unique_visitors 
                        SET last_seen = ?, last_camera = ?, total_sightings = total_sightings + 1
                        WHERE id = ?
                    """, (now_iso, self.camera_id, visitor_id))

                # Per-face same-camera arrival cooldown (60 seconds)
                # Prevents fast duplicate records within milliseconds or repeatedly while waiting in view
                last_sighting_epoch = matched_visitor.get('last_sighting_epoch', 0)
                if (now_epoch - last_sighting_epoch) >= 60.0:
                    matched_visitor['last_sighting_epoch'] = now_epoch
                    vis_sighting_photo = matched_visitor.get('photo_b64') or get_photo_b64()
                    self.engine.async_db_execute("""
                        INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (visitor_id, self.camera_id, now_iso, matched_visitor.get('gender', 'male'), det_score, vis_sighting_photo, 1 if matched_visitor.get('is_blacklisted') else 0))

            # Final Blacklist Evaluation
            is_blacklisted = False
            threat_name = None
            threat_reason = None
            threat_id = None

            if matched_blacklist is not None:
                is_blacklisted = True
                threat_name = matched_blacklist['name']
                threat_reason = matched_blacklist['reason']
                threat_id = matched_blacklist['id']
            elif visitor_id in self.engine.blacklisted_visitor_ids or (matched_visitor and matched_visitor.get('is_blacklisted')):
                is_blacklisted = True
                threat_name = (matched_visitor.get('name') if matched_visitor else None) or visitor_id
                threat_reason = (matched_visitor.get('blacklist_reason') if matched_visitor else None) or "Security Watchlist"
                threat_id = visitor_id

            if is_blacklisted:
                target_key = (threat_id or visitor_id).strip().lower()
                # Target MUST REMAIN RED on CCTV HUD! Never reset is_blacklisted = False
                now_ep = time.time()
                hist_key = (target_key, self.camera_id)
                last_logged = self.engine.blacklist_sighting_history.get(hist_key, 0)
                if (now_ep - last_logged) > 20.0:
                    self.engine.blacklist_sighting_history[hist_key] = now_ep
                    bl_sighting_photo = (matched_visitor.get('photo_b64') if matched_visitor else None) or get_photo_b64()
                    self.engine.async_db_execute("""
                        INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    """, (visitor_id, self.camera_id, now_iso, gender, det_score, bl_sighting_photo))

                # dismissed_targets ONLY suppresses repeating audio/modal popup notifications
                is_dismissed = (target_key in self.engine.dismissed_targets) or (threat_name and threat_name.strip().lower() in self.engine.dismissed_targets)
                last_alert_ts = last_alert_time.get(target_key, 0)
                if not is_dismissed and (now_ep - last_alert_ts) > 15.0:
                        last_alert_time[target_key] = now_ep
                        alert_photo = (matched_visitor.get('photo_b64') if matched_visitor else None) or get_photo_b64()
                        alert_payload = {
                            'id': f"ALT-{uuid.uuid4().hex[:8].upper()}",
                            'watchlist_id': threat_id or visitor_id,
                            'person_name': threat_name or visitor_id,
                            'reason': threat_reason or "Barred from Hospital Premises",
                            'camera_id': self.camera_id,
                            'camera_name': self.name,
                            'confidence': det_score,
                            'photo_b64': alert_photo,
                            'timestamp': get_ist_str("%I:%M:%S %p IST")
                        }
                        self.engine._broadcast_alert(alert_payload)
                        self.engine.async_db_execute("""
                            INSERT INTO security_alerts (id, watchlist_id, person_name, reason, camera_id, camera_name, confidence, photo_b64, timestamp, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                        """, (
                            alert_payload['id'],
                            alert_payload['watchlist_id'],
                            alert_payload['person_name'],
                            alert_payload['reason'],
                            alert_payload['camera_id'],
                            alert_payload['camera_name'],
                            alert_payload['confidence'],
                            alert_payload['photo_b64'],
                            now_iso
                        ))

            # Spatial Track Update: instant responsive lock with zero trailing lag
            if best_track_id is not None:
                track_id = best_track_id
                trk = self.active_tracks[track_id]
                px, py, pw, ph = trk['bbox']
                sx = int(0.95 * x + 0.05 * px)
                sy = int(0.95 * y + 0.05 * py)
                sw = int(0.95 * w + 0.05 * pw)
                sh = int(0.95 * h + 0.05 * ph)
                trk['bbox'] = (sx, sy, sw, sh)
                trk['last_seen'] = now
                trk['missed'] = 0
                if 'history' not in trk:
                    trk['history'] = collections.deque(maxlen=45)
                trk['history'].append((now_epoch, sx + sw / 2.0, sy + sh / 2.0, sw, sh, (sx, sy, sw, sh)))
                if is_blacklisted:
                    trk['bl_consecutive_hits'] = trk.get('bl_consecutive_hits', 0) + 1
                else:
                    trk['bl_consecutive_hits'] = 0
                trk['is_blacklisted'] = is_blacklisted
                trk['threat_name'] = threat_name
                trk['reason'] = threat_reason
                trk['is_transit'] = is_transit
                trk['prev_camera_name'] = prev_cam_name
                trk['gender'] = gender
                trk['age'] = age
                trk['visitor_id'] = visitor_id
            else:
                track_id = self.next_track_id
                self.next_track_id += 1
                hist = collections.deque(maxlen=45)
                hist.append((now_epoch, cx, cy, w, h, (x, y, w, h)))
                self.active_tracks[track_id] = {
                    'bbox': (x, y, w, h),
                    'history': hist,
                    'bl_consecutive_hits': 1 if is_blacklisted else 0,
                    'last_seen': now,
                    'missed': 0,
                    'visitor_id': visitor_id,
                    'is_blacklisted': is_blacklisted,
                    'threat_name': threat_name,
                    'reason': threat_reason,
                    'is_transit': is_transit,
                    'prev_camera_name': prev_cam_name,
                    'gender': gender,
                    'age': age
                }
            matched_track_ids.add(track_id)

        # Age out stale tracks: allow up to 2.5 seconds (or 25 missed frames) for stable walking continuity
        stale_ids = []
        for tid, trk in list(self.active_tracks.items()):
            if tid not in matched_track_ids:
                trk['missed'] = trk.get('missed', 0) + 1
                if trk['missed'] > 25 or (now - trk['last_seen']) > 2.5:
                    stale_ids.append(tid)

        for tid in stale_ids:
            popped = self.active_tracks.pop(tid, None)
            if popped:
                popped['last_seen_epoch'] = now_epoch
                self.recently_closed_tracks.append(popped)
                # If an uncommitted transient track died without confirmation, discard from cache
                p_vid = popped.get('visitor_id')
                if p_vid and p_vid in self.engine.unique_cache_by_id:
                    v_obj = self.engine.unique_cache_by_id[p_vid]
                    if not v_obj.get('db_committed') and v_obj.get('pending_db_record'):
                        # If any pending record exists, commit it now instead of dropping it
                        v_obj['db_committed'] = True
                        p_rec = v_obj.pop('pending_db_record', None)
                        p_sig = v_obj.pop('pending_sighting_record', None)
                        if p_rec:
                            self.engine.async_db_execute("""
                                INSERT INTO unique_visitors (id, gender, gender_confidence, age, embedding_json, photo_b64, crops_json, first_seen, last_seen, last_camera, is_blacklisted, blacklist_reason, gender_locked)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                            """, p_rec)
                        if p_sig:
                            self.engine.async_db_execute("""
                                INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                                VALUES (?, ?, ?, ?, ?, ?, 0)
                            """, p_sig)

        # Render Bounding Boxes & HUD from Active Tracks (Zero Lag: only draw currently detected faces)
        for tid, trk in self.active_tracks.items():
            if trk.get('missed', 0) > 0:
                continue
            bx, by, bw, bh = trk['bbox']
            t_blacklisted = trk.get('is_blacklisted')
            t_transit = trk.get('is_transit')
            t_gender = trk.get('gender', 'male')
            t_age = trk.get('age', 28)
            t_vid = trk.get('visitor_id', '')
            t_threat = trk.get('threat_name')
            t_prev = trk.get('prev_camera_name')

            if t_blacklisted:
                color = (30, 30, 235)  # Crimson Red
                tag = f"BLACKLISTED: {t_threat or t_vid}"
                tag_bg = (20, 20, 180)
            elif t_vid == 'UNTRACKED_EXIT':
                color = (130, 150, 170)  # Cool Slate Gray
                tag = f"EXIT ~{t_age}y [DEPARTURE]"
                tag_bg = (35, 45, 55)
            elif t_vid == 'UNENROLLED':
                color = (140, 160, 180)  # Neutral Cyan / Steel Slate
                tag = f"{t_gender.upper()} ~{t_age}y [CAPTURE PAUSED]"
                tag_bg = (30, 45, 60)
            elif t_transit:
                color = (46, 204, 113)  # Emerald Green (Verified Transit)
                short_prev = (t_prev or 'Entry').replace('Main Porch Entry — Inbound', 'Entry').replace('Main porch exit', 'Exit')
                tag = f"{t_gender.upper()} ~{t_age}y | {t_vid} [TRANSIT FROM {short_prev.upper()}]"
                tag_bg = (35, 140, 75)
            elif t_gender == 'female':
                color = (203, 118, 236)  # Rose Pink
                tag = f"FEMALE ~{t_age}y | {t_vid}"
                tag_bg = (140, 45, 160)
            else:
                color = (255, 178, 50)  # Cyan Blue
                tag = f"MALE ~{t_age}y | {t_vid}"
                tag_bg = (30, 90, 160)

            # Box & Corner Brackets
            cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), color, 2)
            d_len = max(8, int(min(bw, bh) * 0.22))
            cv2.line(annotated, (bx, by), (bx + d_len, by), color, 3)
            cv2.line(annotated, (bx, by), (bx, by + d_len), color, 3)
            cv2.line(annotated, (bx + bw, by), (bx + bw - d_len, by), color, 3)
            cv2.line(annotated, (bx + bw, by), (bx + bw, by + d_len), color, 3)
            cv2.line(annotated, (bx, by + bh), (bx + d_len, by + bh), color, 3)
            cv2.line(annotated, (bx, by + bh), (bx, by + bh - d_len), color, 3)
            cv2.line(annotated, (bx + bw, by + bh), (bx + bw - d_len, by + bh), color, 3)
            cv2.line(annotated, (bx + bw, by + bh), (bx + bw, by + bh - d_len), color, 3)

            # Tag Header Pill
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.44
            thickness = 1
            (tw, th), baseline = cv2.getTextSize(tag, font, font_scale, thickness)
            tag_y = max(by - 8, th + 8)
            cv2.rectangle(annotated, (bx, tag_y - th - 5), (bx + tw + 10, tag_y + 3), tag_bg, -1)
            cv2.putText(annotated, tag, (bx + 5, tag_y - 2), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # Fast unblocked JPEG encoding & publishing
        ok, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self.lock:
                self.latest_jpeg = jpeg.tobytes()
                self.sequence += 1
                pub_time = time.monotonic()
                if self.last_frame_ts:
                    fps = 1.0 / max(pub_time - self.last_frame_ts, 0.001)
                    self.fps = round(self.fps * 0.8 + fps * 0.2, 1)
                self.last_frame_ts = pub_time
                self.lock.notify_all()

        time.sleep(0.005)



# ── Main Face Tracker Intelligence Engine ───────────────────────────────────

class FaceTrackerEngine:
    def __init__(self):
        init_db()
        self.running = True
        self.active_camera = next(iter(CAMERA_SOURCES.keys()), 'main')
        self.alert_queues = []
        self.recent_transits = collections.deque(maxlen=50)
        self._fallback_lock = threading.Condition()
        self.inference_lock = threading.Lock()
        self.detector_lock = threading.Lock()

        # High-Performance Caches for Traffic Trend & KPIs
        self._trend_cache = {}  # { (ist_date, period): (data, timestamp) }
        self._kpi_cache = {}    # { (ist_date, period): (data, timestamp) }
        self._cache_lock = threading.Lock()
        self.auto_enroll_enabled = self._load_setting('auto_enroll_enabled', '1') in ('1', 'true', 'yes', 'on', 'True')
        try:
            self.dwell_window_hours = float(self._load_setting('dwell_window_hours', '4.0'))
        except Exception:
            self.dwell_window_hours = 4.0
        self.max_active_seconds = self.dwell_window_hours * 3600.0

        # Load AI models
        det_path = str(MODELS / 'face_detection_yunet_2023mar.onnx')
        rec_path = str(MODELS / 'face_recognition_sface_2021dec.onnx')
        arcface_path = str(MODELS / 'w600k_mbf.onnx')
        gender_path = str(MODELS / 'genderage.onnx')

        self.detector = cv2.FaceDetectorYN_create(det_path, '', (720, 405), 0.55, 0.3, 1000)
        self.recognizer = cv2.FaceRecognizerSF_create(rec_path, '')

        # GPU ONNX Runtime for ArcFace 512-d (RTX / CUDA acceleration)
        self.arcface_sess = None
        self.arcface_input_name = None
        if os.path.exists(arcface_path):
            try:
                import onnxruntime as ort
                avail = ort.get_available_providers()
                providers = []
                if 'CUDAExecutionProvider' in avail:
                    providers.append('CUDAExecutionProvider')
                providers.append('CPUExecutionProvider')
                self.arcface_sess = ort.InferenceSession(arcface_path, providers=providers)
                self.arcface_input_name = self.arcface_sess.get_inputs()[0].name
                active_p = self.arcface_sess.get_providers()[0]
                print(f"ArcFace 512-d (w600k_mbf.onnx) loaded successfully into ONNX Runtime on [{active_p}]!")
            except Exception as e:
                print("Failed to load ArcFace ONNX model:", e)

        # GPU ONNX Runtime for GenderAge
        self.gender_sess = None
        self.gender_input_name = None
        self.gender_net = None
        if os.path.exists(gender_path):
            try:
                import onnxruntime as ort
                avail = ort.get_available_providers()
                providers = []
                if 'CUDAExecutionProvider' in avail:
                    providers.append('CUDAExecutionProvider')
                providers.append('CPUExecutionProvider')
                self.gender_sess = ort.InferenceSession(gender_path, providers=providers)
                self.gender_input_name = self.gender_sess.get_inputs()[0].name
                active_p = self.gender_sess.get_providers()[0]
                print(f"InsightFace genderage.onnx loaded into ONNX Runtime on [{active_p}]!")
            except Exception as e:
                print("Failed to load genderage into ONNX Runtime:", e)
                try:
                    self.gender_net = cv2.dnn.readNetFromONNX(gender_path)
                    print("InsightFace genderage.onnx loaded into OpenCV DNN fallback!")
                except Exception as e2:
                    print("Failed fallback to OpenCV DNN:", e2)

        self.recent_auto_enrolled = collections.deque(maxlen=30)
        self.recent_auto_enrolled_locs = collections.deque(maxlen=40)

        # In-memory caches
        self.unique_cache = []
        self.unique_cache_by_id = {}
        self.watchlist_cache = []
        self.blacklisted_visitor_ids = set()
        self.locked_genders = set()
        self.dismissed_targets = set()
        self.gender_votes = {}
        self.blacklist_sighting_history = {}

        # Vectorized acceleration matrices
        self.gallery_matrix = None
        self.gallery_index = []
        self.watchlist_matrix = None
        self.watchlist_index = []
        self.matrix_lock = threading.Lock()

        # Background async DB worker
        self.db_queue = queue.Queue(maxsize=4000)
        self.db_thread = threading.Thread(target=self._db_writer_loop, daemon=True)
        self.db_thread.start()

        self._load_caches_from_db()

        # Initialize multi-camera concurrent stream pipelines
        self.pipelines = {}
        for cam_id, cam_info in CAMERA_SOURCES.items():
            try:
                stream_src = cam_info['rtsp']
                if CURRENT_FEED_MODE == 'demo':
                    stream_src = DEMO_RECORDINGS_MAP.get(cam_id, os.path.join(RECORDINGS_DIR, "MainPorchEntry_20261113_190525_60s.mp4"))
                self.pipelines[cam_id] = CameraStreamPipeline(
                    cam_id, cam_info['name'], cam_info['location'], stream_src, self,
                    role=cam_info.get('role', 'entry')
                )
                print(f"[PIPELINE STARTED] {cam_id} -> {cam_info['name']} ({stream_src})")
            except Exception as e:
                print(f"Failed to start pipeline for {cam_id}:", e)

    def _load_setting(self, key: str, default: str = '1') -> str:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            conn.close()
            if row and row[0] is not None:
                return str(row[0])
        except Exception:
            pass
        return default

    def set_setting(self, key: str, value: str):
        val_str = str(value)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO system_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ''', (key, val_str))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[SETTING ERROR] Failed to save {key}={val_str}:", e)
        if key == 'auto_enroll_enabled':
            self.auto_enroll_enabled = val_str in ('1', 'true', 'yes', 'on', 'True')
            print(f"[FACE TRACKER] auto_enroll_enabled updated to: {self.auto_enroll_enabled}")
        elif key == 'dwell_window_hours':
            try:
                self.dwell_window_hours = float(val_str)
                self.max_active_seconds = self.dwell_window_hours * 3600.0
                print(f"[FACE TRACKER] dwell_window_hours updated to: {self.dwell_window_hours}h ({self.max_active_seconds}s)")
            except Exception as e:
                print(f"[SETTING ERROR] Failed to parse dwell_window_hours={val_str}:", e)

    def get_feed_mode(self):
        global CURRENT_FEED_MODE
        return CURRENT_FEED_MODE

    def set_feed_mode(self, mode=None):
        global CURRENT_FEED_MODE, DB_PATH
        if not mode:
            mode = 'demo' if CURRENT_FEED_MODE == 'live' else 'live'
        mode = 'demo' if str(mode).lower() == 'demo' else 'live'
        
        if mode == CURRENT_FEED_MODE:
            return {'ok': True, 'mode': mode, 'active_db': os.path.basename(DB_PATH)}
            
        print(f"[FACE TRACKER] Switching feed mode: {CURRENT_FEED_MODE} -> {mode}")
        CURRENT_FEED_MODE = mode
        
        try:
            with open(MODE_STATE_FILE, 'w') as f:
                json.dump({'mode': mode}, f)
        except Exception:
            pass

        # Drain any pending DB writes before switching database
        drain_t0 = time.time()
        while not self.db_queue.empty() and (time.time() - drain_t0) < 0.8:
            time.sleep(0.04)

        if mode == 'demo':
            init_demo_db()
            DB_PATH = DEMO_DB_PATH
            for cam_id, pipe in self.pipelines.items():
                rec_file = DEMO_RECORDINGS_MAP.get(cam_id, str(RECORDINGS_DIR / "main"))
                pipe.switch_source(rec_file)
        else:
            DB_PATH = LIVE_DB_PATH
            for cam_id, pipe in self.pipelines.items():
                cam_info = CAMERA_SOURCES.get(cam_id, {})
                rtsp_url = cam_info.get('rtsp', f'{RTSP_BASE}/{cam_id}')
                pipe.switch_source(rtsp_url)

        self._load_caches_from_db()
        self.auto_enroll_enabled = self._load_setting('auto_enroll_enabled', '1') in ('1', 'true', 'yes', 'on', 'True')
        try:
            self.dwell_window_hours = float(self._load_setting('dwell_window_hours', '4.0'))
        except Exception:
            self.dwell_window_hours = 4.0
        self.max_active_seconds = self.dwell_window_hours * 3600.0
        return {'ok': True, 'mode': mode, 'active_db': os.path.basename(DB_PATH)}

    def get_pipeline(self, camera_id=None):
        if camera_id and camera_id in self.pipelines:
            return self.pipelines[camera_id]
        if self.active_camera in self.pipelines:
            return self.pipelines[self.active_camera]
        if self.pipelines:
            return next(iter(self.pipelines.values()))
        return None

    @property
    def latest_jpeg(self):
        pipe = self.get_pipeline()
        return pipe.latest_jpeg if pipe else None

    @property
    def latest_frame(self):
        pipe = self.get_pipeline()
        return pipe.latest_frame if pipe else None

    @property
    def sequence(self):
        pipe = self.get_pipeline()
        return pipe.sequence if pipe else 0

    @property
    def fps(self):
        pipe = self.get_pipeline()
        return pipe.fps if pipe else 0.0

    @property
    def is_rtsp_connected(self):
        pipe = self.get_pipeline()
        return pipe.is_rtsp_connected if pipe else False

    @property
    def error_msg(self):
        pipe = self.get_pipeline()
        return pipe.error_msg if pipe else None

    @property
    def lock(self):
        pipe = self.get_pipeline()
        return pipe.lock if pipe else self._fallback_lock

    def dismiss_alert(self, target_id: str):
        if target_id:
            self.dismissed_targets.add(str(target_id).strip().lower())
        return True

    def _broadcast_alert(self, alert_payload: dict):
        dead_queues = []
        for q in self.alert_queues:
            try:
                q.put_nowait(alert_payload)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            if dq in self.alert_queues:
                self.alert_queues.remove(dq)

    def _broadcast_transit(self, transit_payload: dict):
        self.recent_transits.appendleft(transit_payload)
        t_payload = dict(transit_payload)
        t_payload['_event_type'] = 'transit'
        dead_queues = []
        for q in self.alert_queues:
            try:
                q.put_nowait(t_payload)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            if dq in self.alert_queues:
                self.alert_queues.remove(dq)

    def _detect_faces(self, frame: np.ndarray):
        h, w = frame.shape[:2]
        target_w, target_h = 720, 405
        small = cv2.resize(frame, (target_w, target_h))
        with self.detector_lock:
            self.detector.setInputSize((target_w, target_h))
            _, faces = self.detector.detect(small)
        if faces is None:
            return []
        faces = faces.copy()
        scale_x = w / float(target_w)
        scale_y = h / float(target_h)
        for i in range(len(faces)):
            faces[i][0] *= scale_x
            faces[i][1] *= scale_y
            faces[i][2] *= scale_x
            faces[i][3] *= scale_y
            for landmark_idx in range(4, 14, 2):
                faces[i][landmark_idx] *= scale_x
                faces[i][landmark_idx + 1] *= scale_y
        return faces

    ARCFACE_DST = np.array([
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041]
    ], dtype=np.float32)

    def _extract_embedding(self, frame: np.ndarray, face: np.ndarray):
        if self.arcface_sess is not None and len(face) >= 14:
            try:
                # Five facial landmarks: right_eye, left_eye, nose_tip, right_mouth, left_mouth
                landmarks = np.array([
                    [face[4], face[5]],
                    [face[6], face[7]],
                    [face[8], face[9]],
                    [face[10], face[11]],
                    [face[12], face[13]]
                ], dtype=np.float32)
                tform, _ = cv2.estimateAffinePartial2D(landmarks, self.ARCFACE_DST, method=cv2.LMEDS)
                if tform is not None:
                    aligned = cv2.warpAffine(frame, tform, (112, 112), borderValue=0.0)
                else:
                    with self.inference_lock:
                        aligned = self.recognizer.alignCrop(frame, face)
                    aligned = cv2.resize(aligned, (112, 112))

                # InsightFace 112x112 ArcFace standard preprocessing: (BGR - 127.5) / 128.0
                blob = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)
                blob = (blob - 127.5) / 128.0
                blob = np.transpose(blob, (2, 0, 1))  # (3, 112, 112)
                blob = np.expand_dims(blob, axis=0)  # (1, 3, 112, 112)

                outputs = self.arcface_sess.run(None, {self.arcface_input_name: blob})
                feat = outputs[0][0].astype(np.float32)
                norm = np.linalg.norm(feat)
                if norm > 1e-6:
                    feat /= norm
                return feat
            except Exception as e:
                pass  # Fallback to SFace if any error

        # Fallback to OpenCV SFace (128-d)
        with self.inference_lock:
            aligned = self.recognizer.alignCrop(frame, face)
            feature = self.recognizer.feature(aligned)
        feat = feature.astype(np.float32)
        if feat.ndim > 1:
            feat = feat.flatten()
        norm = np.linalg.norm(feat)
        if norm > 1e-6:
            feat /= norm
        return feat

    def _is_sharp_face_crop(self, face_crop: np.ndarray, face_coords: np.ndarray, det_score: float):
        if face_crop is None or face_crop.size == 0:
            return False, 0.0

        # Minimum detection confidence: reject low-confidence noise, arms, clothing patterns
        if det_score < 0.68:
            return False, 0.0

        x, y, w, h = [int(v) for v in face_coords[:4]]
        # Minimum resolution: balanced middle value for doorway arrivals
        if w < 26 or h < 30:
            return False, 0.0

        aspect = float(w) / max(float(h), 1.0)
        # Face aspect ratio: must be reasonably upright (rejects horizontal ear/neck slices)
        if aspect < 0.55 or aspect > 1.35:
            return False, 0.0

        # Facial landmark validation (eliminates ears, necks, hair, back of head, arms)
        if len(face_coords) < 14:
            return False, 0.0  # No landmark data → cannot verify frontality → reject

        re_x, re_y = face_coords[4], face_coords[5]
        le_x, le_y = face_coords[6], face_coords[7]
        nt_x, nt_y = face_coords[8], face_coords[9]
        rcm_x, rcm_y = face_coords[10], face_coords[11]
        lcm_x, lcm_y = face_coords[12], face_coords[13]

        # In image coords, subject right eye is on the left (re_x < le_x)
        eye_dx = le_x - re_x
        if eye_dx <= 3.5:
            # Inverted, horizontal ear, or collapsed points
            return False, 0.0

        eye_dy = abs(le_y - re_y)
        # Head tilt / roll check (allows natural tilt up to ~38 degrees)
        if eye_dy > eye_dx * 0.80:
            return False, 0.0

        eye_dist = math.hypot(eye_dx, eye_dy)
        # Eye separation vs face width: accommodates overhead camera angle & glasses
        eye_ratio = eye_dist / max(float(w), 1.0)
        if eye_ratio < 0.16 or eye_ratio > 0.72:
            return False, 0.0

        # Mouth width / landmark validation: mouth corners must have horizontal separation
        mouth_dx = lcm_x - rcm_x
        if mouth_dx <= 2.0:
            # Collapsed mouth points, ear contours, back of head
            return False, 0.0

        mouth_dy = abs(lcm_y - rcm_y)
        if mouth_dy > max(mouth_dx * 0.85, 8.0):
            # Extreme vertical distortion / false landmark
            return False, 0.0

        # Yaw symmetry check (ensures face is facing camera, rejects profile ears and back of head)
        d_re_nose = math.hypot(nt_x - re_x, nt_y - re_y)
        d_le_nose = math.hypot(nt_x - le_x, nt_y - le_y)
        yaw_sym = min(d_re_nose, d_le_nose) / max(d_re_nose, d_le_nose, 1e-4)
        if yaw_sym < 0.28:
            return False, 0.0

        # Vertical facial topology (accommodates downward CCTV overhead perspective):
        # 1. Nose MUST be below the eye line
        eye_avg_y = (re_y + le_y) / 2.0
        eye_to_nose_dy = nt_y - eye_avg_y
        if eye_to_nose_dy < (0.08 * eye_dist):
            return False, 0.0

        # 2. Mouth MUST be below the nose
        mouth_y = (rcm_y + lcm_y) / 2.0
        nose_to_mouth_dy = mouth_y - nt_y
        if nose_to_mouth_dy < (0.08 * eye_dist):
            return False, 0.0

        # 3. Total vertical face height (eye line to mouth)
        total_face_h = mouth_y - eye_avg_y
        h_ratio = total_face_h / max(float(h), 1.0)
        if h_ratio < 0.26 or h_ratio > 0.86:
            return False, 0.0

        try:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            mean_v = float(np.mean(gray))
            if mean_v < 19.0 or mean_v > 241.0:
                return False, 0.0

            ch, cw = gray.shape[:2]
            inner_gray = gray[int(ch * 0.15):int(ch * 0.85), int(cw * 0.15):int(cw * 0.85)]
            if inner_gray.size == 0:
                inner_gray = gray

            inner_lap = float(cv2.Laplacian(inner_gray, cv2.CV_64F).var())
            # Sharpness threshold: balanced middle value (filters out blurry samples while keeping valid faces)
            if inner_lap < 22.0:
                return False, 0.0

            # Eye region texture check: upper half must contain eye/eyebrow gradients
            if ch >= 28 and cw >= 28:
                upper_eye_region = inner_gray[:int(inner_gray.shape[0] * 0.50), :]
                if upper_eye_region.size > 0:
                    eye_lap = float(cv2.Laplacian(upper_eye_region, cv2.CV_64F).var())
                    if eye_lap < 16.0:
                        return False, 0.0

            quality_score = inner_lap * (float(w) / 40.0)
            return True, max(quality_score, 11.0)
        except Exception:
            return False, 0.0

    def _estimate_gender_and_age(self, frame: np.ndarray, face: np.ndarray, face_crop: np.ndarray, camera_id: str, body_crop: np.ndarray = None):
        if getattr(self, 'gender_sess', None) is not None or self.gender_net is not None:
            try:
                x, y, w, h = [int(v) for v in face[:4]]
                if w < 28 or h < 28:
                    return None, 0.0, 30

                H, W = frame.shape[:2]
                # Direct face crop (zero margin padding):
                fc = frame[max(0, y):min(H, y + h), max(0, x):min(W, x + w)]
                if fc is None or fc.size == 0:
                    fc = face_crop
                if fc is None or fc.size == 0:
                    return None, 0.0, 30

                def _eval_net(img_crop):
                    if img_crop is None or img_crop.size == 0:
                        return 0.5, 0.5, 30
                    if getattr(self, 'gender_sess', None) is not None:
                        try:
                            resized = cv2.resize(img_crop, (96, 96))
                            blob = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
                            blob = np.transpose(blob, (2, 0, 1))
                            blob = np.expand_dims(blob, axis=0)
                            outputs = self.gender_sess.run(None, {self.gender_input_name: blob})
                            if len(outputs) >= 2:
                                gender_preds, age_preds = outputs[0], outputs[1]
                            else:
                                out0 = outputs[0]
                                gender_preds = out0[:, :2]
                                age_preds = out0[:, 2] if out0.shape[1] > 2 else [[30]]
                            exp_g = np.exp(gender_preds[0] - np.max(gender_preds[0]))
                            probs = exp_g / np.sum(exp_g)
                            age_val = int(round(float(age_preds[0][0]) * 100)) if hasattr(age_preds[0], '__len__') else int(round(float(age_preds[0]) * 100))
                            age_val = max(18, min(80, age_val))
                            return float(probs[0]), float(probs[1]), age_val
                        except Exception:
                            pass
                    if self.gender_net is not None:
                        blob = cv2.dnn.blobFromImage(cv2.resize(img_crop, (96, 96)), 1.0, (96, 96), (0, 0, 0), swapRB=True)
                        with self.inference_lock:
                            self.gender_net.setInput(blob)
                            preds = self.gender_net.forward()
                        if isinstance(preds, (list, tuple)) and len(preds) >= 2:
                            gender_preds, age_preds = preds[0], preds[1]
                        else:
                            gender_preds = preds[:, :2]
                            age_preds = preds[:, 2] if preds.shape[1] > 2 else [[30]]
                        exp_g = np.exp(gender_preds[0] - np.max(gender_preds[0]))
                        probs = exp_g / np.sum(exp_g)
                        age_val = int(round(float(age_preds[0][0]) * 100)) if hasattr(age_preds[0], '__len__') else int(round(float(age_preds[0]) * 100))
                        age_val = max(18, min(80, age_val))
                        return float(probs[0]), float(probs[1]), age_val
                    return 0.5, 0.5, 30

                # 1. Face crop evaluation
                f_face, m_face, a_face = _eval_net(fc)

                # 2. Head / Hair crop evaluation (silhouette, haircut, ears, sideburns, neck)
                head_crop = None
                if body_crop is not None and body_crop.size > 0:
                    head_crop = body_crop[0:int(body_crop.shape[0] * 0.48), :]
                else:
                    pad_side = int(w * 0.40)
                    pad_top = int(h * 0.25)
                    pad_bot = int(h * 0.70)
                    head_crop = frame[max(0, y - pad_top):min(H, y + h + pad_bot), max(0, x - pad_side):min(W, x + w + pad_side)]

                f_head, m_head, a_head = _eval_net(head_crop)

                # 3. Detect surgical mask / medical face covering on lower half of face
                mask_r = 0.0
                if fc is not None and fc.size > 0:
                    h_fc = fc.shape[0]
                    lower = fc[int(h_fc * 0.5):, :]
                    hsv = cv2.cvtColor(lower, cv2.COLOR_BGR2HSV)
                    mask_r = np.count_nonzero((hsv[:, :, 1] < 38) & (hsv[:, :, 2] > 140)) / max(1, lower.shape[0] * lower.shape[1])

                is_masked = (mask_r >= 0.22)
                if is_masked:
                    # In hospital CCTV, surgical masks occlude mouth/chin leading face models to default to male.
                    # Head/hair features (long hair over shoulders, ponytail, female silhouette) give definitive truth (>95%).
                    gender = 'female' if f_head >= 0.45 else 'male'
                    conf = max(f_head, 0.75) if gender == 'female' else max(m_head, 0.75)
                    age = a_head
                else:
                    # When unmasked:
                    hsv_fc = cv2.cvtColor(fc, cv2.COLOR_BGR2HSV)
                    mean_v = float(np.mean(hsv_fc[:, :, 2]))

                    # Severe shadow under cap (e.g. VIS-207CB4A9): mean_v < 65 and head shows strong male (f_head < 0.22)
                    if mean_v < 65 and f_head < 0.22 and f_face >= 0.50:
                        gender = 'male'
                        conf = max(m_head, 0.75)
                        age = a_head
                    elif f_face >= 0.55:
                        gender = 'female'
                        conf = f_face
                        age = a_face
                    elif m_face >= 0.55:
                        gender = 'male'
                        conf = m_face
                        age = a_face
                    else:
                        comb_f = 0.60 * f_face + 0.40 * f_head
                        gender = 'female' if comb_f >= 0.50 else 'male'
                        conf = comb_f if gender == 'female' else (1.0 - comb_f)
                        age = a_face

                return gender, conf, age
            except Exception:
                pass

        # Skin Tone / Luminance fallback
        try:
            hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
            h_mean = np.mean(hsv[:, :, 0])
            s_mean = np.mean(hsv[:, :, 1])
            is_female = (h_mean < 18 and s_mean < 80)
            return ('female' if is_female else 'male'), 0.65, 30
        except Exception:
            return 'male', 0.60, 30

    def _extract_crop_embedding(self, photo_b64: str) -> np.ndarray:
        try:
            raw_b64 = photo_b64.split(',', 1)[1] if ',' in photo_b64 else photo_b64
            img_bytes = base64.b64decode(raw_b64)
            img = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                padded = cv2.copyMakeBorder(img, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                faces = self._detect_faces(padded)
                if len(faces):
                    return self._extract_embedding(padded, faces[0])
                faces_raw = self._detect_faces(img)
                if len(faces_raw):
                    return self._extract_embedding(img, faces_raw[0])
        except Exception:
            pass
        return None

    def _load_caches_from_db(self):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        
        self.watchlist_cache = []
        self.blacklisted_visitor_ids = set()

        cur.execute('SELECT id, name, alias, reason, embedding_json, photo_b64, crops_json, category, enrolled_at FROM blacklist_watchlist WHERE active = 1')
        for r in cur.fetchall():
            emb = np.array(json.loads(r[4]), dtype=np.float32) if r[4] else None
            crops = json.loads(r[6]) if r[6] else ([r[5]] if r[5] else [])
            alias = r[2]
            if alias:
                self.blacklisted_visitor_ids.add(alias)
            embeddings_list = []
            if emb is not None:
                embeddings_list.append(emb)
            for c_img in crops[:8]:
                c_emb = self._extract_crop_embedding(c_img)
                if c_emb is not None:
                    embeddings_list.append(c_emb)
            self.watchlist_cache.append({
                'id': r[0],
                'name': r[1],
                'alias': alias,
                'category': r[7] if len(r) > 7 and r[7] else 'visitor',
                'reason': r[3],
                'embedding': emb,
                'embeddings': embeddings_list,
                'photo_b64': r[5],
                'crops': crops,
                'enrolled_at': r[8] if len(r) > 8 and r[8] else get_ist_iso()
            })

        self.unique_cache = []
        self.unique_cache_by_id = {}
        self.locked_genders = set()
        try:
            cur.execute('SELECT id, gender, embedding_json, last_seen, photo_b64, crops_json, gender_locked, is_blacklisted, blacklist_reason, last_camera, previous_camera FROM unique_visitors WHERE photo_b64 IS NOT NULL AND photo_b64 != ""')
        except Exception:
            cur.execute('SELECT id, gender, embedding_json, last_seen, photo_b64, crops_json, 0, 0, NULL, "main", NULL FROM unique_visitors WHERE photo_b64 IS NOT NULL AND photo_b64 != ""')
        for r in cur.fetchall():
            vis_id = r[0]
            emb = np.array(json.loads(r[2]), dtype=np.float32) if r[2] else None
            crops = json.loads(r[5]) if r[5] else ([r[4]] if r[4] else [])
            db_is_bl = bool(r[7]) if len(r) > 7 and r[7] else False
            is_blk = (vis_id in self.blacklisted_visitor_ids) or db_is_bl
            if is_blk:
                self.blacklisted_visitor_ids.add(vis_id)
            reason = (r[8] if len(r) > 8 else None) or None
            if is_blk and not reason:
                for bl in self.watchlist_cache:
                    if bl.get('alias') == vis_id or bl['name'] == vis_id:
                        reason = bl['reason']
                        break
            is_locked = bool(r[6]) if len(r) > 6 and r[6] else False
            if is_locked:
                self.locked_genders.add(vis_id)

            last_seen_epoch = 0.0
            if r[3]:
                try:
                    last_seen_epoch = datetime.fromisoformat(r[3]).timestamp()
                except Exception:
                    last_seen_epoch = 0.0

            if emb is not None:
                vis_embeddings = [emb]
                if is_blk:
                    for c_img in crops[:6]:
                        c_emb = self._extract_crop_embedding(c_img)
                        if c_emb is not None:
                            vis_embeddings.append(c_emb)
                vis_obj = {
                    'id': vis_id,
                    'gender': r[1],
                    'gender_locked': is_locked,
                    'embedding': emb,
                    'embeddings': vis_embeddings,
                    'last_seen': r[3],
                    'last_seen_epoch': last_seen_epoch,
                    'is_blacklisted': is_blk,
                    'blacklist_reason': reason,
                    'photo_b64': r[4],
                    'crops': crops,
                    'last_camera': r[9] if len(r) > 9 else 'main',
                    'previous_camera': r[10] if len(r) > 10 else None
                }
                self.unique_cache.append(vis_obj)
                self.unique_cache_by_id[vis_id] = vis_obj

        # Seed recent cross-camera transits from database history
        try:
            cur.execute('''
                SELECT s1.visitor_id, s1.camera_id, s1.timestamp, s2.camera_id, s2.timestamp,
                       u.gender, u.age, u.photo_b64
                FROM visitor_sightings s1
                JOIN visitor_sightings s2 ON s1.visitor_id = s2.visitor_id AND s1.camera_id != s2.camera_id AND s2.timestamp > s1.timestamp
                JOIN unique_visitors u ON s1.visitor_id = u.id
                ORDER BY s2.timestamp DESC LIMIT 15
            ''')
            seen_pairs = set()
            for r in cur.fetchall():
                vid, c1, t1, c2, t2, g, a, p = r
                pair_key = (vid, c1, c2)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                cam1_obj = CAMERA_SOURCES.get(c1, {'name': c1})
                cam2_obj = CAMERA_SOURCES.get(c2, {'name': c2})
                dt1 = datetime.fromisoformat(t1)
                dt2 = datetime.fromisoformat(t2)
                mins = max(1, int((dt2 - dt1).total_seconds() / 60))
                self.recent_transits.append({
                    'visitor_id': vid,
                    'gender': g,
                    'age': a,
                    'from_camera': c1,
                    'from_camera_name': cam1_obj.get('name', c1),
                    'to_camera': c2,
                    'to_camera_name': cam2_obj.get('name', c2),
                    'dwell_mins': mins,
                    'timestamp': t2,
                    'photo_b64': p
                })
        except Exception as e:
            print("Error loading initial transits:", e)

        conn.close()
        self.rebuild_gallery_index()
        self.rebuild_watchlist_index()
        print(f"[CACHE MATRIX READY] {len(self.gallery_index)} gallery vectors, {len(self.watchlist_index)} watchlist vectors indexed!")

    def _safe_db_write(self, statements: list):
        """Execute a list of (sql, params) statements safely with WAL retries."""
        for attempt in range(5):
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute("PRAGMA synchronous=NORMAL")
                cur = conn.cursor()
                for sql, params in statements:
                    cur.execute(sql, params)
                conn.commit()
                conn.close()
                return True
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < 4:
                    time.sleep(0.08 * (attempt + 1))
                    continue
                print("[SAFE DB WRITE ERROR]:", e)
                break
            except Exception as e:
                print("[SAFE DB WRITE UNEXPECTED ERROR]:", e)
                break
        # Fallback: queue to background db writer
        for sql, params in statements:
            self.async_db_execute(sql, params)
        return False

    def _db_writer_loop(self):
        conn = None
        current_connected_db = None
        while self.running:
            try:
                task = self.db_queue.get(timeout=0.5)
                if task is None:
                    continue
                batch = [task]
                while len(batch) < 64:
                    try:
                        next_task = self.db_queue.get_nowait()
                        if next_task is not None:
                            batch.append(next_task)
                    except queue.Empty:
                        break

                target_db = DB_PATH
                if conn is not None and current_connected_db != target_db:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                    current_connected_db = None

                if conn is None:
                    try:
                        conn = sqlite3.connect(target_db, timeout=30.0)
                        conn.execute("PRAGMA journal_mode=WAL")
                        conn.execute("PRAGMA busy_timeout=30000")
                        conn.execute("PRAGMA synchronous=NORMAL")
                        current_connected_db = target_db
                    except Exception as e:
                        print(f"[DB WRITER CONNECT ERROR] {target_db}:", e)
                        conn = None
                        current_connected_db = None

                if conn:
                    try:
                        cur = conn.cursor()
                        cur.execute("BEGIN TRANSACTION")
                        for sql, params in batch:
                            cur.execute(sql, params)
                        conn.commit()
                    except Exception as e:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                        current_connected_db = None
            except queue.Empty:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    def async_db_execute(self, sql: str, params: tuple):
        try:
            self.db_queue.put_nowait((sql, params))
        except Exception:
            pass

    def rebuild_gallery_index(self):
        with self.matrix_lock:
            rows = []
            idx = []
            expected_dim = 512 if getattr(self, 'arcface_sess', None) is not None else 128
            for vis in self.unique_cache:
                embs = vis.get('embeddings') or ([vis['embedding']] if vis.get('embedding') is not None else [])
                for e in embs:
                    if e is not None:
                        ef = np.asarray(e, dtype=np.float32).flatten()
                        if ef.shape[0] != expected_dim:
                            continue
                        norm = np.linalg.norm(ef)
                        if norm > 1e-6:
                            rows.append(ef / norm)
                            idx.append(vis)
            if rows:
                self.gallery_matrix = np.array(rows, dtype=np.float32)
                self.gallery_index = idx
            else:
                self.gallery_matrix = None
                self.gallery_index = []
            print(f"[Gallery] Rebuilt matrix index with {len(self.gallery_index)} embeddings across {len(self.unique_cache)} visitors (Dim: {expected_dim}d).")

    def rebuild_watchlist_index(self):
        with self.matrix_lock:
            rows = []
            idx = []
            expected_dim = 512 if getattr(self, 'arcface_sess', None) is not None else 128
            for bl in self.watchlist_cache:
                embs = bl.get('embeddings') or ([bl['embedding']] if bl.get('embedding') is not None else [])
                for e in embs:
                    if e is not None:
                        ef = np.asarray(e, dtype=np.float32).flatten()
                        if ef.shape[0] != expected_dim:
                            continue
                        norm = np.linalg.norm(ef)
                        if norm > 1e-6:
                            rows.append(ef / norm)
                            idx.append(bl)
            if rows:
                self.watchlist_matrix = np.array(rows, dtype=np.float32)
                self.watchlist_index = idx
            else:
                self.watchlist_matrix = None
                self.watchlist_index = []
            print(f"[Watchlist] Rebuilt matrix index with {len(self.watchlist_index)} suspect profiles (Dim: {expected_dim}d).")

    def search_gallery(self, emb: np.ndarray, threshold: float = None, recent_threshold: float = None, recent_seconds: float = 10800.0, query_gender: str = None, gender_conf: float = 0.0, is_exit: bool = False, max_active_seconds: float = 14400.0):
        with self.matrix_lock:
            if self.gallery_matrix is None or len(self.gallery_index) == 0:
                return None, 0.0
            ef = np.asarray(emb, dtype=np.float32).flatten()
            expected_dim = 512 if getattr(self, 'arcface_sess', None) is not None else 128
            if ef.shape[0] != expected_dim:
                return None, 0.0
            if threshold is None:
                threshold = 0.63 if expected_dim == 512 else 0.52
            if recent_threshold is None:
                recent_threshold = 0.60 if expected_dim == 512 else 0.48

            norm = np.linalg.norm(ef)
            if norm < 1e-6:
                return None, 0.0
            query = ef / norm
            sims = np.dot(self.gallery_matrix, query)
            if len(sims) == 0:
                return None, 0.0

            now_epoch = time.time()
            today_str = get_ist_str("%Y-%m-%d")
            top_k_indices = np.argsort(sims)[::-1][:15]

            # 1. Temporal Active Campus Corridor: If seen on campus within active window on today's date
            window_limit = max_active_seconds if is_exit else recent_seconds
            for idx in top_k_indices:
                sim = float(sims[idx])
                if sim < recent_threshold:
                    break
                vis = self.gallery_index[idx]

                # Gender Consistency Guard:
                cand_gender = vis.get('gender')
                if query_gender and cand_gender and gender_conf >= 0.70:
                    if cand_gender != query_gender and (vis.get('gender_locked') or vis.get('gender_confidence', 0) >= 0.75):
                        continue

                # Same-date check: Active campus stay must have started on today's calendar date
                vis_first_seen = vis.get('first_seen', '')
                if vis_first_seen and not vis_first_seen.startswith(today_str):
                    continue

                last_seen_epoch = vis.get('last_seen_epoch', 0)
                elapsed = now_epoch - last_seen_epoch
                # Physical transit buffer: requires at least 12 seconds between camera transitions
                if is_exit and elapsed < 12.0:
                    continue

                if elapsed <= window_limit:
                    return vis, sim

            # If this is an EXIT camera, DO NOT search historical visitors from past days!
            # Exit camera strictly matches active on-campus visitors from today.
            if is_exit:
                return None, 0.0

            # 2. General Historical Gallery Match: Requires strict threshold for returning visitors
            for idx in top_k_indices:
                sim = float(sims[idx])
                if sim < threshold:
                    break
                vis = self.gallery_index[idx]
                cand_gender = vis.get('gender')
                if query_gender and cand_gender and gender_conf >= 0.70:
                    if cand_gender != query_gender and (vis.get('gender_locked') or vis.get('gender_confidence', 0) >= 0.75):
                        continue
                return vis, sim

            return None, 0.0

    def search_watchlist(self, emb: np.ndarray, threshold: float = None):
        with self.matrix_lock:
            if self.watchlist_matrix is None or len(self.watchlist_index) == 0:
                return None, 0.0
            ef = np.asarray(emb, dtype=np.float32).flatten()
            expected_dim = 512 if getattr(self, 'arcface_sess', None) is not None else 128
            if ef.shape[0] != expected_dim:
                return None, 0.0
            if threshold is None:
                threshold = 0.60 if expected_dim == 512 else 0.50
            norm = np.linalg.norm(ef)
            if norm < 1e-6:
                return None, 0.0
            query = ef / norm
            sims = np.dot(self.watchlist_matrix, query)
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= threshold:
                return self.watchlist_index[best_idx], best_sim
            return None, best_sim

    def add_to_gallery(self, vis: dict, emb: np.ndarray):
        """Add one embedding row to the in-memory gallery matrix.
        Hard cap: max 5 matrix rows per visitor (prevents stationary-person flooding).
        """
        with self.matrix_lock:
            ef = np.asarray(emb, dtype=np.float32).flatten()
            expected_dim = 512 if getattr(self, 'arcface_sess', None) is not None else 128
            if ef.shape[0] != expected_dim:
                return
            norm = np.linalg.norm(ef)
            if norm > 1e-6:
                # Count existing rows for this visitor
                vis_id = vis.get('id', '')
                existing_count = sum(1 for v in self.gallery_index if v.get('id') == vis_id)
                if existing_count >= 5:
                    return  # Already at cap — do not add more rows for this person
                row = (ef / norm).reshape(1, expected_dim)
                if self.gallery_matrix is not None:
                    self.gallery_matrix = np.vstack([self.gallery_matrix, row])
                    self.gallery_index.append(vis)
                else:
                    self.gallery_matrix = row
                    self.gallery_index = [vis]

    def get_cameras(self):
        return list(CAMERA_SOURCES.values())

    def add_camera(self, name: str, location: str, rtsp: str, role: str = None):
        cam_id = f"cam_{uuid.uuid4().hex[:6]}"
        now_ts = get_ist_iso()
        if not role:
            role = 'entry'
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('INSERT INTO cameras (id, name, location, rtsp, created_at, role) VALUES (?, ?, ?, ?, ?, ?)',
                    (cam_id, name, location, rtsp, now_ts, role))
        conn.commit()
        conn.close()
        cam_obj = {
            'id': cam_id,
            'name': name,
            'location': location,
            'rtsp': rtsp,
            'role': role
        }
        CAMERA_SOURCES[cam_id] = cam_obj
        # Start new stream pipeline immediately
        try:
            self.pipelines[cam_id] = CameraStreamPipeline(cam_id, name, location, rtsp, self, role=role)
        except Exception as e:
            print(f"Error starting pipeline for {cam_id}:", e)
        return cam_obj

    def edit_camera(self, camera_id: str, name: str = None, location: str = None, rtsp: str = None, role: str = None):
        if camera_id not in CAMERA_SOURCES:
            return False, "Camera not found"
        cam = CAMERA_SOURCES[camera_id]
        new_name = name.strip() if name is not None and name.strip() else cam.get('name')
        new_loc = location.strip() if location is not None and location.strip() else cam.get('location')
        new_rtsp = rtsp.strip() if rtsp is not None and rtsp.strip() else cam.get('rtsp')
        new_role = role.strip() if role is not None and role.strip() else cam.get('role', 'entry')

        # Enforcement: At least one camera with 'entry' role must remain active
        if cam.get('role') == 'entry' and new_role != 'entry':
            other_entry_cams = [cid for cid, c in CAMERA_SOURCES.items() if cid != camera_id and c.get('role') == 'entry']
            if not other_entry_cams:
                return False, "Cannot change role: at least one camera with 'entry' role must remain active in the system"

        rtsp_changed = (new_rtsp != cam.get('rtsp'))

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('''
            UPDATE cameras 
            SET name = ?, location = ?, rtsp = ?, role = ?
            WHERE id = ?
        ''', (new_name, new_loc, new_rtsp, new_role, camera_id))
        conn.commit()
        conn.close()

        cam['name'] = new_name
        cam['location'] = new_loc
        cam['rtsp'] = new_rtsp
        cam['role'] = new_role

        if camera_id in self.pipelines:
            pipe = self.pipelines[camera_id]
            pipe.name = new_name
            pipe.location = new_loc
            pipe.role = new_role
            if rtsp_changed:
                pipe.switch_source(new_rtsp)
        else:
            try:
                self.pipelines[camera_id] = CameraStreamPipeline(camera_id, new_name, new_loc, new_rtsp, self, role=new_role)
            except Exception as e:
                print(f"Error starting pipeline for {camera_id}:", e)

        return True, cam

    def remove_camera(self, camera_id: str):
        if camera_id not in CAMERA_SOURCES:
            return False, "Camera not found"
        if len(CAMERA_SOURCES) <= 1:
            return False, "Cannot delete camera: at least one camera must remain active"

        cam_to_remove = CAMERA_SOURCES[camera_id]
        if cam_to_remove.get('role') == 'entry':
            other_entry_cams = [cid for cid, c in CAMERA_SOURCES.items() if cid != camera_id and c.get('role') == 'entry']
            if not other_entry_cams:
                return False, "Cannot delete camera: at least one camera with 'entry' role must remain active"

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('DELETE FROM cameras WHERE id = ?', (camera_id,))
        conn.commit()
        conn.close()
        if camera_id in self.pipelines:
            self.pipelines[camera_id].stop()
            del self.pipelines[camera_id]
        if camera_id in CAMERA_SOURCES:
            del CAMERA_SOURCES[camera_id]
        if self.active_camera == camera_id:
            next_cam = next(iter(CAMERA_SOURCES.keys()), None)
            if next_cam:
                self.switch_camera(next_cam)
        return True, "Camera removed successfully"

    def switch_camera(self, camera_id: str):
        if camera_id not in CAMERA_SOURCES:
            return False
        self.active_camera = camera_id
        return True

    def get_visitor_journey(self, visitor_id: str):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('''
            SELECT camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted 
            FROM visitor_sightings 
            WHERE visitor_id = ? 
            ORDER BY timestamp ASC
        ''', (visitor_id,))
        rows = cur.fetchall()

        cur.execute('SELECT id, gender, age, first_seen, last_seen, last_camera, previous_camera, is_blacklisted, photo_b64 FROM unique_visitors WHERE id = ?', (visitor_id,))
        vis_row = cur.fetchone()
        conn.close()

        if not vis_row:
            return None

        checkpoints = []
        prev_time = None
        for r in rows:
            cam_info = CAMERA_SOURCES.get(r[0], {})
            ts_str = r[1]
            dwell_mins = 0
            try:
                curr_dt = datetime.fromisoformat(ts_str)
                if prev_time:
                    dwell_mins = max(1, int((curr_dt - prev_time).total_seconds() / 60))
                prev_time = curr_dt
            except Exception:
                pass

            checkpoints.append({
                'camera_id': r[0],
                'camera_name': cam_info.get('name', r[0]),
                'location': cam_info.get('location', 'Hospital Zone'),
                'role': cam_info.get('role', 'entry'),
                'timestamp': ts_str,
                'time_display': ts_str.replace('T', ' ').split('.')[0],
                'dwell_mins_since_prev': dwell_mins,
                'confidence': round(float(r[3] or 0.95) * 100, 1),
                'photo_b64': r[4],
                'is_blacklisted': bool(r[5])
            })

        # If last_seen is more than 30s after the last sighting, include the latest passage checkpoint
        last_seen_str = vis_row[4]
        last_cam_id = vis_row[5] or (checkpoints[-1]['camera_id'] if checkpoints else 'main')
        last_cam_info = CAMERA_SOURCES.get(last_cam_id, {})
        if checkpoints and last_seen_str:
            try:
                last_dt = datetime.fromisoformat(last_seen_str)
                prev_cp_dt = datetime.fromisoformat(checkpoints[-1]['timestamp'])
                diff_sec = (last_dt - prev_cp_dt).total_seconds()
                if diff_sec > 30:
                    checkpoints.append({
                        'camera_id': last_cam_id,
                        'camera_name': last_cam_info.get('name', last_cam_id),
                        'location': last_cam_info.get('location', 'Hospital Zone'),
                        'role': last_cam_info.get('role', 'entry'),
                        'timestamp': last_seen_str,
                        'time_display': last_seen_str.replace('T', ' ').split('.')[0],
                        'dwell_mins_since_prev': max(1, int(diff_sec / 60)),
                        'confidence': 98.4,
                        'photo_b64': vis_row[8],
                        'is_blacklisted': bool(vis_row[7])
                    })
            except Exception:
                pass

        total_dwell_mins = 0
        try:
            f_dt = datetime.fromisoformat(vis_row[3])
            l_dt = datetime.fromisoformat(vis_row[4])
            total_dwell_mins = max(1, int((l_dt - f_dt).total_seconds() / 60))
        except Exception:
            total_dwell_mins = len(checkpoints) * 2

        f_raw = vis_row[3]
        l_raw = vis_row[4]
        f_time_ist = f_raw.split('T')[1].split('.')[0] if (f_raw and 'T' in f_raw) else f_raw
        l_time_ist = l_raw.split('T')[1].split('.')[0] if (l_raw and 'T' in l_raw) else l_raw

        return {
            'visitor_id': vis_row[0],
            'gender': vis_row[1],
            'age': vis_row[2] or 30,
            'first_seen': f_raw,
            'first_seen_time': f_time_ist,
            'last_seen': l_raw,
            'last_seen_time': l_time_ist,
            'last_camera': vis_row[5],
            'last_camera_name': last_cam_info.get('name', vis_row[5]),
            'is_blacklisted': bool(vis_row[7]),
            'photo_b64': vis_row[8],
            'total_dwell_mins': total_dwell_mins,
            'checkpoints': checkpoints
        }

    def add_to_blacklist(self, person_id_or_photo: str, name: str, reason: str, is_photo: bool = False):
        now_iso = get_ist_iso()
        bl_id = f"BLK-{uuid.uuid4().hex[:8].upper()}"

        if not is_photo:
            visitor_id = str(person_id_or_photo).strip()
            target_name = name or visitor_id
            target_reason = reason or "Flagged manually"

            # 1. Look up cached visitor profile in RAM (instant <0.01ms)
            vis_cached = self.unique_cache_by_id.get(visitor_id)
            emb = None
            embeddings_list = []
            photo_b64 = None
            crops = []

            if vis_cached:
                photo_b64 = vis_cached.get('photo_b64')
                crops = list(vis_cached.get('crops', []))
                if vis_cached.get('embeddings'):
                    embeddings_list = list(vis_cached['embeddings'])
                elif vis_cached.get('embedding') is not None:
                    embeddings_list = [vis_cached['embedding']]
                if embeddings_list:
                    emb = embeddings_list[0]

            # If not in RAM, read once from DB
            if emb is None:
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=10.0)
                    conn.execute("PRAGMA busy_timeout=10000")
                    cur = conn.cursor()
                    cur.execute('SELECT embedding_json, photo_b64, crops_json FROM unique_visitors WHERE id = ?', (visitor_id,))
                    row = cur.fetchone()
                    conn.close()
                    if row:
                        if row[0]:
                            emb = np.array(json.loads(row[0]), dtype=np.float32)
                            embeddings_list = [emb]
                        photo_b64 = photo_b64 or row[1]
                        if row[2]:
                            crops = crops or json.loads(row[2])
                except Exception as e:
                    print("[ADD_TO_BLACKLIST DB READ ERROR]:", e)

            # 2. UPDATE IN-MEMORY DATA STRUCTURES FIRST (0ms latency!)
            self.blacklisted_visitor_ids.add(visitor_id)
            self.dismissed_targets.discard(visitor_id.lower())
            self.dismissed_targets.discard(target_name.lower())

            new_item = {
                'id': bl_id,
                'name': target_name,
                'alias': visitor_id,
                'category': 'visitor',
                'reason': target_reason,
                'embedding': emb,
                'embeddings': embeddings_list if embeddings_list else ([emb] if emb is not None else []),
                'photo_b64': photo_b64 or (crops[0] if crops else ''),
                'crops': crops if crops else ([photo_b64] if photo_b64 else []),
                'enrolled_at': now_iso
            }

            existing_idx = next((i for i, b in enumerate(self.watchlist_cache) if b.get('alias') == visitor_id or b['id'] == bl_id), None)
            if existing_idx is not None:
                self.watchlist_cache[existing_idx] = new_item
            else:
                self.watchlist_cache.insert(0, new_item)

            if vis_cached:
                vis_cached['is_blacklisted'] = True
                vis_cached['blacklist_reason'] = target_reason
            for vis in self.unique_cache:
                if vis.get('id') == visitor_id:
                    vis['is_blacklisted'] = True
                    vis['blacklist_reason'] = target_reason

            # CRITICAL: Rebuild watchlist index vector matrix immediately!
            self.rebuild_watchlist_index()

            # UPDATE ACTIVE PIPELINE TRACKS IMMEDIATELY (0ms frame reaction!)
            for pipe in self.pipelines.values():
                with pipe.lock:
                    for tid, trk in list(pipe.active_tracks.items()):
                        if trk.get('visitor_id') == visitor_id:
                            trk['is_blacklisted'] = True
                            trk['threat_name'] = target_name
                            trk['reason'] = target_reason
                            trk['threat_id'] = bl_id

            # 3. PERSIST SAFELY TO SQLITE (non-blocking, retry safe)
            emb_json = json.dumps(emb.tolist()) if emb is not None else None
            crops_json = json.dumps(crops) if crops else (json.dumps([photo_b64]) if photo_b64 else '[]')
            stmts = [
                ('''INSERT INTO blacklist_watchlist (id, name, alias, category, reason, embedding_json, photo_b64, crops_json, enrolled_at, enrolled_by, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''',
                 (bl_id, target_name, visitor_id, 'visitor', target_reason, emb_json, photo_b64, crops_json, now_iso, 'admin')),
                ('UPDATE unique_visitors SET is_blacklisted = 1, blacklist_reason = ? WHERE id = ?',
                 (target_reason, visitor_id)),
                ('UPDATE visitor_sightings SET is_blacklisted = 1 WHERE visitor_id = ?',
                 (visitor_id,))
            ]
            self._safe_db_write(stmts)
            return True, bl_id
        else:
            photo_b64 = person_id_or_photo
            raw_b64 = photo_b64.split(',', 1)[1] if ',' in photo_b64 else photo_b64
            img_bytes = base64.b64decode(raw_b64)
            img = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return False, "Invalid image data"

            faces = self._detect_faces(img)
            if not len(faces):
                padded = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                faces_p = self._detect_faces(padded)
                if len(faces_p):
                    emb = self._extract_embedding(padded, faces_p[0])
                else:
                    return False, "No face detected in uploaded photo"
            else:
                emb = self._extract_embedding(img, faces[0])
            if emb is None:
                return False, "Could not extract face embedding from photo"
            emb_json = json.dumps(emb.tolist())
            crops_json = json.dumps([photo_b64])

            new_item = {
                'id': bl_id,
                'name': name or f"Target {bl_id}",
                'alias': bl_id,
                'category': 'manual_photo',
                'reason': reason or "Security Watchlist",
                'embedding': emb,
                'embeddings': [emb],
                'photo_b64': photo_b64,
                'crops': [photo_b64],
                'enrolled_at': now_iso
            }
            self.watchlist_cache.insert(0, new_item)
            self.rebuild_watchlist_index()

            stmts = [
                ('''INSERT INTO blacklist_watchlist (id, name, alias, category, reason, embedding_json, photo_b64, crops_json, enrolled_at, enrolled_by, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)''',
                 (bl_id, name, bl_id, 'manual_photo', reason, emb_json, photo_b64, crops_json, now_iso, 'admin'))
            ]
            self._safe_db_write(stmts)
            return True, bl_id

    def remove_from_blacklist(self, watchlist_id: str, alias: str = None, name: str = None):
        target_ids = {str(watchlist_id).strip()}
        if alias:
            target_ids.add(str(alias).strip())

        # Resolve bidirectional IDs from watchlist cache (e.g. BLK-xxx <-> VIS-xxx)
        for b in self.watchlist_cache:
            if b.get('id') in target_ids or b.get('alias') in target_ids or (name and b.get('name') == name):
                if b.get('id'):
                    target_ids.add(b['id'])
                if b.get('alias'):
                    target_ids.add(b['alias'])
                if b.get('name'):
                    name = name or b['name']

        # 1. Update in-memory tracking structures IMMEDIATELY (0ms delay)
        for tid in list(target_ids):
            self.blacklisted_visitor_ids.discard(tid)
            self.dismissed_targets.discard(tid.strip().lower())
            if tid in self.unique_cache_by_id:
                self.unique_cache_by_id[tid]['is_blacklisted'] = False
                self.unique_cache_by_id[tid]['blacklist_reason'] = None

        if name:
            self.dismissed_targets.discard(name.strip().lower())

        for vis in self.unique_cache:
            if vis.get('id') in target_ids:
                vis['is_blacklisted'] = False
                vis['blacklist_reason'] = None

        # Filter in-memory watchlist_cache
        self.watchlist_cache = [
            b for b in self.watchlist_cache
            if b['id'] not in target_ids and b.get('alias') not in target_ids and (not name or b.get('name') != name)
        ]

        # CRITICAL: Rebuild watchlist index vector matrix immediately!
        self.rebuild_watchlist_index()

        # Clear active pipeline tracks immediately (0ms reaction on live CCTV feed!)
        for pipe in self.pipelines.values():
            with pipe.lock:
                for tid, trk in list(pipe.active_tracks.items()):
                    vid = trk.get('visitor_id')
                    thid = trk.get('threat_id')
                    if vid in target_ids or thid in target_ids or vid == watchlist_id or (alias and vid == alias):
                        trk['is_blacklisted'] = False
                        trk['threat_name'] = None
                        trk['reason'] = None
                        trk['threat_id'] = None

        # 2. Persist safely to DB with retries and fallback
        stmts = [
            ('''UPDATE blacklist_watchlist 
                SET active = 0 
                WHERE id = ? OR (alias IS NOT NULL AND alias != "" AND (alias = ? OR alias = ?))''',
             (watchlist_id, watchlist_id, alias or watchlist_id))
        ]
        for tid in target_ids:
            stmts.append(('UPDATE unique_visitors SET is_blacklisted = 0, blacklist_reason = NULL WHERE id = ?', (tid,)))
            stmts.append(('UPDATE visitor_sightings SET is_blacklisted = 0 WHERE visitor_id = ?', (tid,)))
            stmts.append(('DELETE FROM security_alerts WHERE watchlist_id = ? OR watchlist_id = ? OR person_name = ? OR person_name LIKE ?',
                          (tid, watchlist_id, name or tid, f"%{tid}%")))
        self._safe_db_write(stmts)
        return True

    def remove_from_blacklist_by_alias(self, alias: str):
        """Remove a visitor from the blacklist using their visitor ID alias."""
        return self.remove_from_blacklist(watchlist_id=alias, alias=alias)

    def prune_unwanted_exit_records(self):
        """Clean up and purge any visitor profiles that were created solely by exit cameras."""
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        # Find all visitors whose ONLY sightings are on exit cameras
        cur.execute('''
            SELECT id FROM unique_visitors
            WHERE id NOT IN (
                SELECT DISTINCT visitor_id FROM visitor_sightings
                WHERE camera_id IN (SELECT id FROM cameras WHERE role = 'entry')
            )
        ''')
        exit_only_ids = [r[0] for r in cur.fetchall()]

        pruned_count = len(exit_only_ids)
        if exit_only_ids:
            placeholders = ','.join(['?'] * len(exit_only_ids))
            cur.execute(f'DELETE FROM unique_visitors WHERE id IN ({placeholders})', exit_only_ids)
            cur.execute(f'DELETE FROM visitor_sightings WHERE visitor_id IN ({placeholders})', exit_only_ids)
            conn.commit()
        conn.close()

        if exit_only_ids:
            exit_set = set(exit_only_ids)
            self.unique_cache = [v for v in self.unique_cache if v['id'] not in exit_set]
            for vid in exit_only_ids:
                self.unique_cache_by_id.pop(vid, None)
            self.rebuild_gallery_index()

        return pruned_count

    def is_valid_face_crop(self, face_crop: np.ndarray) -> bool:
        if face_crop is None or face_crop.size == 0:
            return False
        ih, iw = face_crop.shape[:2]
        if iw < 32 or ih < 36:
            return False
        try:
            with self.detector_lock:
                self.detector.setInputSize((iw, ih))
                _, faces = self.detector.detect(face_crop)
            if faces is None or len(faces) == 0:
                return False
            f = faces[0]
            det_score = float(f[-1])
            if det_score < 0.65:
                return False
            is_sharp, _ = self._is_sharp_face_crop(face_crop, f, det_score)
            return is_sharp
        except Exception:
            return False

    def is_valid_face_b64(self, photo_b64: str) -> bool:
        if not photo_b64:
            return False
        try:
            raw = photo_b64.split(',', 1)[1] if ',' in photo_b64 else photo_b64
            img_bytes = base64.b64decode(raw)
            img = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            return self.is_valid_face_crop(img)
        except Exception:
            return False

    def clean_unwanted_non_face_records(self, limit: int = 100):
        """Scans recent unique visitors, purges false-positive crops (arms, elbows, backs of head),
        and deletes profiles that have 0 valid frontal face crops."""
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        cur = conn.cursor()
        if limit and limit > 0:
            cur.execute('SELECT id, photo_b64, crops_json FROM unique_visitors ORDER BY last_seen DESC LIMIT ?', (limit,))
        else:
            cur.execute('SELECT id, photo_b64, crops_json FROM unique_visitors ORDER BY last_seen DESC')
        rows = cur.fetchall()

        deleted_ids = []
        updated_records = []

        for vid, photo_b64, crops_json in rows:
            crops = json.loads(crops_json) if crops_json else ([photo_b64] if photo_b64 else [])
            valid_crops = [c for c in crops if self.is_valid_face_b64(c)]
            
            if not valid_crops:
                deleted_ids.append(vid)
            elif len(valid_crops) != len(crops):
                new_avatar = photo_b64 if (photo_b64 and self.is_valid_face_b64(photo_b64)) else valid_crops[0]
                updated_records.append((new_avatar, json.dumps(valid_crops[:8]), vid))

        if deleted_ids:
            cur.execute("BEGIN TRANSACTION")
            placeholders = ','.join(['?'] * len(deleted_ids))
            cur.execute(f'DELETE FROM unique_visitors WHERE id IN ({placeholders})', deleted_ids)
            cur.execute(f'DELETE FROM visitor_sightings WHERE visitor_id IN ({placeholders})', deleted_ids)
            conn.commit()

        if updated_records:
            cur.execute("BEGIN TRANSACTION")
            cur.executemany('UPDATE unique_visitors SET photo_b64 = ?, crops_json = ? WHERE id = ?', updated_records)
            conn.commit()

        conn.close()

        # Update RAM caches
        if deleted_ids:
            del_set = set(deleted_ids)
            self.unique_cache = [v for v in self.unique_cache if v['id'] not in del_set]
            for vid in deleted_ids:
                self.unique_cache_by_id.pop(vid, None)
            self.rebuild_gallery_index()

        for new_avatar, crops_str, vid in updated_records:
            if vid in self.unique_cache_by_id:
                self.unique_cache_by_id[vid]['photo_b64'] = new_avatar
                self.unique_cache_by_id[vid]['crops'] = json.loads(crops_str)

        return len(deleted_ids), len(updated_records)

    def remove_visitor_crop(self, visitor_id: str, crop_index: int = None, crop_b64: str = None):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('SELECT crops_json, photo_b64 FROM unique_visitors WHERE id = ?', (visitor_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "Visitor not found"

        crops = json.loads(row[0]) if row[0] else ([row[1]] if row[1] else [])
        removed = False

        # 1. Match by image base64 if provided
        if crop_b64:
            clean_target = crop_b64.split(',', 1)[-1].strip()
            for i, c in enumerate(crops):
                if c and c.split(',', 1)[-1].strip() == clean_target:
                    crops.pop(i)
                    removed = True
                    break
            if not removed:
                # crop_b64 not found in DB → already pruned by cleaner or prior delete call
                conn.close()
                return True, "Crop already removed or pruned"

        # 2. Match by index if in valid range
        if not removed and crop_index is not None and 0 <= crop_index < len(crops):
            crops.pop(crop_index)
            removed = True

        # 3. If crop_index is beyond current crops, it means cleaner or another action already pruned it
        if not removed and crop_index is not None and crop_index >= len(crops):
            conn.close()
            return True, "Crop already removed or pruned"

        if removed:
            cur_photo = row[1]
            new_primary = cur_photo if (cur_photo and cur_photo != crop_b64) else (crops[0] if len(crops) > 0 else '')
            new_crops_json = json.dumps(crops)
            cur.execute('UPDATE unique_visitors SET crops_json = ?, photo_b64 = ? WHERE id = ?',
                        (new_crops_json, new_primary, visitor_id))
            conn.commit()
            conn.close()

            if visitor_id in self.unique_cache_by_id:
                self.unique_cache_by_id[visitor_id]['crops'] = crops
                self.unique_cache_by_id[visitor_id]['photo_b64'] = new_primary
            return True, "Crop removed successfully"

        conn.close()
        return True, "Crop removed"

    def delete_visitor(self, visitor_id: str):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('DELETE FROM unique_visitors WHERE id = ?', (visitor_id,))
        cur.execute('DELETE FROM visitor_sightings WHERE visitor_id = ?', (visitor_id,))
        cur.execute('DELETE FROM blacklist_watchlist WHERE alias = ?', (visitor_id,))
        conn.commit()
        conn.close()

        self.unique_cache = [v for v in self.unique_cache if v['id'] != visitor_id]
        if visitor_id in self.unique_cache_by_id:
            del self.unique_cache_by_id[visitor_id]
        self.blacklisted_visitor_ids.discard(visitor_id)
        self.locked_genders.discard(visitor_id)
        return True, "Visitor deleted"

    def toggle_visitor_gender(self, visitor_id: str, new_gender: str):
        new_g = str(new_gender).strip().lower()
        if new_g not in ('male', 'female'):
            return False, "Gender must be 'male' or 'female'"

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('UPDATE unique_visitors SET gender = ?, gender_locked = 1 WHERE id = ?', (new_g, visitor_id))
        conn.commit()
        conn.close()

        if visitor_id in self.unique_cache_by_id:
            self.unique_cache_by_id[visitor_id]['gender'] = new_g
            self.unique_cache_by_id[visitor_id]['gender_locked'] = True
        self.locked_genders.add(visitor_id)
        self.gender_votes[visitor_id] = collections.deque([(new_g, 0.99)], maxlen=30)

        # Propagate immediately to any active tracks currently in camera frame
        for pipe in self.pipelines.values():
            for trk in pipe.active_tracks.values():
                if trk.get('visitor_id') == visitor_id:
                    trk['gender'] = new_g

        return True, {'id': visitor_id, 'gender': new_g, 'gender_locked': True}

    def search_by_photo(self, photo_b64: str, min_threshold: float = 0.35, max_results: int = 8):
        try:
            raw_b64 = photo_b64.split(',', 1)[1] if ',' in photo_b64 else photo_b64
            img_bytes = base64.b64decode(raw_b64)
            img = cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return False, "Could not decode uploaded image."

            h, w = img.shape[:2]
            faces = []
            max_dim = max(h, w)
            if max_dim > 1280:
                scale = 1280.0 / max_dim
                dw, dh = int(w * scale), int(h * scale)
                small = cv2.resize(img, (dw, dh))
                with self.inference_lock:
                    self.detector.setInputSize((dw, dh))
                    _, d_faces = self.detector.detect(small)
                if d_faces is not None and len(d_faces):
                    inv_s = 1.0 / scale
                    faces = d_faces.copy()
                    for i in range(len(faces)):
                        faces[i][0] *= inv_s
                        faces[i][1] *= inv_s
                        faces[i][2] *= inv_s
                        faces[i][3] *= inv_s
                        for l in range(4, 14, 2):
                            faces[i][l] *= inv_s
                            faces[i][l+1] *= inv_s
            else:
                with self.inference_lock:
                    self.detector.setInputSize((w, h))
                    _, d_faces = self.detector.detect(img)
                if d_faces is not None and len(d_faces):
                    faces = d_faces.copy()

            if not len(faces):
                faces = self._detect_faces(img)

            if not len(faces):
                padded = cv2.copyMakeBorder(img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                faces_p = self._detect_faces(padded)
                if len(faces_p):
                    img = padded
                    faces = faces_p
                    h, w = img.shape[:2]

            if not len(faces):
                return False, "No face detected in the uploaded photo. Please upload a clear photo with a visible face."

            best_face = max(faces, key=lambda f: f[2] * f[3])
            query_emb = self._extract_embedding(img, best_face)
            if query_emb is None:
                return False, "Could not extract biometric face features."

            fx, fy, fw, fh = int(best_face[0]), int(best_face[1]), int(best_face[2]), int(best_face[3])
            pad_x = int(fw * 0.22)
            pad_y = int(fh * 0.25)
            x1 = max(0, fx - pad_x)
            y1 = max(0, fy - pad_y)
            x2 = min(w, fx + fw + pad_x)
            y2 = min(h, fy + fh + pad_y)
            probe_face_img = img[y1:y2, x1:x2]
            if probe_face_img.size > 0:
                _, p_buf = cv2.imencode('.jpg', probe_face_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                probe_crop_b64 = "data:image/jpeg;base64," + base64.b64encode(p_buf).decode('utf-8')
            else:
                probe_crop_b64 = photo_b64

            scored = []
            for vis in self.unique_cache:
                vis_embs = vis.get('embeddings') or ([vis['embedding']] if vis.get('embedding') is not None else [])
                vis_embs = [ve for ve in vis_embs if ve is not None]
                if not vis_embs:
                    continue
                sims = [cosine_sim(query_emb, ve) for ve in vis_embs]
                max_s = max(sims)
                if max_s >= min_threshold:
                    scored.append((max_s, vis, False))

            # Also search across Watchlist Cache (suspects enrolled via photo or modal)
            for bl in self.watchlist_cache:
                alias = bl.get('alias')
                if alias and alias in self.unique_cache_by_id:
                    continue
                bl_embs = bl.get('embeddings') or ([bl['embedding']] if bl.get('embedding') is not None else [])
                bl_embs = [be for be in bl_embs if be is not None]
                if not bl_embs:
                    continue
                sims = [cosine_sim(query_emb, be) for be in bl_embs]
                max_s = max(sims)
                if max_s >= min_threshold:
                    bl_adapted = {
                        'id': bl['id'],
                        'name': bl.get('name') or bl['id'],
                        'alias': alias or bl['id'],
                        'gender': 'threat',
                        'age': 30,
                        'first_seen': bl.get('enrolled_at', ''),
                        'last_seen': bl.get('enrolled_at', ''),
                        'last_camera': 'Watchlist Record',
                        'photo_b64': bl.get('photo_b64'),
                        'crops': bl.get('crops', []),
                        'is_blacklisted': True,
                        'blacklist_reason': bl.get('reason', 'Security Threat / Watchlist')
                    }
                    scored.append((max_s, bl_adapted, True))

            scored.sort(key=lambda x: x[0], reverse=True)

            if not scored:
                return True, {
                    'matched': False,
                    'probe_crop_b64': probe_crop_b64,
                    'message': "No matching visitor or blacklisted individual found in the captured database.",
                    'candidates': []
                }

            top_score, top_vis, is_wl_suspect = scored[0]
            top_id = top_vis['id']
            is_bl = bool(top_vis.get('is_blacklisted', False) or (top_id in self.blacklisted_visitor_ids) or is_wl_suspect)
            bl_reason = top_vis.get('blacklist_reason')
            if is_bl and not bl_reason:
                for bl in self.watchlist_cache:
                    if bl.get('alias') == top_id or bl.get('id') == top_id or bl.get('name') == top_id:
                        bl_reason = bl.get('reason')
                        break
            if is_bl and not bl_reason:
                bl_reason = 'Security Watchlist Alert'

            journey = self.get_visitor_journey(top_id)

            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cur = conn.cursor()
            cur.execute('''
                SELECT s.id, s.visitor_id, s.camera_id, s.timestamp, s.gender, s.confidence, s.photo_b64, s.is_blacklisted,
                       COALESCE(c.name, s.camera_id) as camera_name, COALESCE(c.location, 'Hospital Zone') as camera_location
                FROM visitor_sightings s
                LEFT JOIN cameras c ON s.camera_id = c.id
                WHERE s.visitor_id = ? OR s.visitor_id = ?
                ORDER BY s.timestamp DESC
            ''', (top_id, top_vis.get('alias', top_id)))
            cols = [col[0] for col in cur.description]
            sightings = [dict(zip(cols, row)) for row in cur.fetchall()]

            # Also check security alerts for this suspect
            if is_bl:
                cur.execute('''
                    SELECT id, watchlist_id, person_name, reason, camera_id, camera_name, confidence, photo_b64, timestamp, status
                    FROM security_alerts
                    WHERE watchlist_id = ? OR watchlist_id = ? OR person_name = ?
                    ORDER BY timestamp DESC
                ''', (top_id, top_vis.get('alias', top_id), top_vis.get('name', '')))
                a_cols = [col[0] for col in cur.description]
                alerts = [dict(zip(a_cols, row)) for row in cur.fetchall()]
                existing_ts = {s['timestamp'] for s in sightings}
                for a in alerts:
                    if a['timestamp'] not in existing_ts:
                        sightings.append({
                            'id': a['id'],
                            'visitor_id': top_id,
                            'camera_id': a['camera_id'],
                            'camera_name': a['camera_name'],
                            'camera_location': 'Alert Checkpoint',
                            'timestamp': a['timestamp'],
                            'gender': 'threat',
                            'confidence': a['confidence'],
                            'photo_b64': a['photo_b64'],
                            'is_blacklisted': 1
                        })
                sightings.sort(key=lambda x: x['timestamp'], reverse=True)
            conn.close()

            candidates_summary = []
            for item in scored[:max_results]:
                sim, c_vis, c_is_wl = item
                crops = c_vis.get('crops', [])
                c_is_bl = bool(c_vis.get('is_blacklisted', False) or (c_vis['id'] in self.blacklisted_visitor_ids) or c_is_wl)
                c_reason = c_vis.get('blacklist_reason')
                if c_is_bl and not c_reason:
                    for bl in self.watchlist_cache:
                        if bl.get('alias') == c_vis['id'] or bl.get('id') == c_vis['id'] or bl.get('name') == c_vis['id']:
                            c_reason = bl.get('reason')
                            break
                if c_is_bl and not c_reason:
                    c_reason = 'Security Watchlist Alert'
                candidates_summary.append({
                    'id': c_vis['id'],
                    'name': c_vis.get('name'),
                    'similarity': round(sim * 100, 1),
                    'raw_score': float(sim),
                    'gender': c_vis.get('gender', 'unknown'),
                    'age': c_vis.get('age', 30),
                    'last_seen': c_vis.get('last_seen', ''),
                    'last_camera': c_vis.get('last_camera', ''),
                    'photo_b64': c_vis.get('photo_b64') or (crops[0] if crops else ''),
                    'is_blacklisted': c_is_bl,
                    'blacklist_reason': c_reason if c_is_bl else None
                })

            crops_list = top_vis.get('crops', [])
            return True, {
                'matched': True,
                'probe_crop_b64': probe_crop_b64,
                'top_match': {
                    'visitor_id': top_id,
                    'name': top_vis.get('name'),
                    'similarity': round(top_score * 100, 1),
                    'raw_score': float(top_score),
                    'gender': top_vis.get('gender', 'unknown'),
                    'age': top_vis.get('age', 30),
                    'first_seen': top_vis.get('first_seen', ''),
                    'last_seen': top_vis.get('last_seen', ''),
                    'last_camera': top_vis.get('last_camera', ''),
                    'last_camera_name': CAMERA_SOURCES.get(top_vis.get('last_camera', ''), {}).get('name', top_vis.get('last_camera', '')),
                    'previous_camera': top_vis.get('previous_camera'),
                    'photo_b64': top_vis.get('photo_b64') or (crops_list[0] if crops_list else ''),
                    'crops': crops_list,
                    'is_blacklisted': is_bl,
                    'blacklist_reason': bl_reason,
                    'threat_name': top_vis.get('name'),
                    'journey': journey,
                    'sightings': sightings
                },
                'candidates': candidates_summary
            }
        except Exception as e:
            return False, f"Error performing biometric photo search: {str(e)}"

    def find_similar_visitors(self, visitor_id: str, threshold: float = 0.28):
        target = self.unique_cache_by_id.get(visitor_id)
        if not target or target.get('embedding') is None:
            return False, "Visitor embedding not available"

        target_embs = target.get('embeddings') or [target['embedding']]
        matches = []
        for vis in self.unique_cache:
            if vis['id'] == visitor_id:
                continue
            v_embs = vis.get('embeddings') or ([vis['embedding']] if vis.get('embedding') is not None else [])
            best_sim = 0.0
            for te in target_embs:
                for ve in v_embs:
                    sim = cosine_sim(te, ve)
                    if sim > best_sim:
                        best_sim = sim
            if best_sim >= threshold:
                crops = vis.get('crops', [])
                if not crops and vis.get('photo_b64'):
                    crops = [vis['photo_b64']]
                matches.append({
                    'id': vis['id'],
                    'gender': vis.get('gender', 'unknown'),
                    'age': vis.get('age', 30),
                    'last_seen': vis.get('last_seen', ''),
                    'photo_b64': vis.get('photo_b64', ''),
                    'crops': crops,
                    'similarity': round(best_sim * 100, 1),
                    'raw_score': float(best_sim)
                })

        matches.sort(key=lambda x: x['raw_score'], reverse=True)
        return True, {'primary_id': visitor_id, 'candidates': matches[:12]}

    def merge_visitor_profiles(self, primary_id: str, merge_ids: list, excluded_crops: list = None):
        if not primary_id or not merge_ids:
            return False, "Primary ID and merge IDs required"

        excluded_set = set(excluded_crops or [])
        primary = self.unique_cache_by_id.get(primary_id)
        if not primary:
            return False, "Primary profile not found"

        all_crops = list(primary.get('crops', []))
        all_embs = list(primary.get('embeddings', []))

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()

        for mid in merge_ids:
            m_vis = self.unique_cache_by_id.get(mid)
            if m_vis:
                for c in m_vis.get('crops', []):
                    if c and c not in all_crops and c not in excluded_set:
                        all_crops.append(c)
                for e in m_vis.get('embeddings', []):
                    if len(all_embs) < 8:
                        all_embs.append(e)

            cur.execute('UPDATE visitor_sightings SET visitor_id = ? WHERE visitor_id = ?', (primary_id, mid))
            cur.execute('DELETE FROM unique_visitors WHERE id = ?', (mid,))
            self.unique_cache = [v for v in self.unique_cache if v['id'] != mid]
            if mid in self.unique_cache_by_id:
                del self.unique_cache_by_id[mid]

        cur.execute('SELECT count(*) FROM visitor_sightings WHERE visitor_id = ?', (primary_id,))
        tot_sightings = cur.fetchone()[0]

        filtered_crops = [c for c in all_crops if c not in excluded_set][:8]
        new_primary_photo = primary.get('photo_b64') or (filtered_crops[0] if filtered_crops else '')

        cur.execute('UPDATE unique_visitors SET crops_json = ?, photo_b64 = ?, total_sightings = ? WHERE id = ?',
                    (json.dumps(filtered_crops), new_primary_photo, tot_sightings, primary_id))
        conn.commit()
        conn.close()

        primary['crops'] = filtered_crops
        primary['photo_b64'] = new_primary_photo
        primary['embeddings'] = all_embs[:8]

        # 1. Update any in-flight active tracks across all camera pipelines that were pointing to merged IDs
        merged_set = set(merge_ids)
        for pipe in self.pipelines.values():
            for trk in pipe.active_tracks.values():
                if trk.get('visitor_id') in merged_set:
                    trk['visitor_id'] = primary_id
                    trk['gender'] = primary.get('gender', trk.get('gender'))
                elif trk.get('visitor_id') == primary_id:
                    trk['gender'] = primary.get('gender', trk.get('gender'))

        # 2. Rebuild the vector gallery index so deleted embeddings are purged and primary is refreshed
        self.rebuild_gallery_index()

        return True, {'primary_id': primary_id, 'merged_count': len(merge_ids), 'total_crops': len(filtered_crops)}

    def get_kpis(self, period='today'):
        p = str(period or 'today').lower().strip()
        if p in ('7d', '7 days', '7'):
            p_norm = '7d'
        elif p in ('30d', '30 days', '30'):
            p_norm = '30d'
        elif p == 'yesterday':
            p_norm = 'yesterday'
        else:
            p_norm = 'today'

        today_dt = get_ist_now()
        today_str = today_dt.strftime('%Y-%m-%d')
        now_ts = time.time()

        cached_db = None
        with self._cache_lock:
            cached = self._kpi_cache.get((today_str, p_norm))
            if cached:
                db_data, cached_at = cached
                if p_norm == 'yesterday':
                    cached_db = db_data
                elif p_norm in ('7d', '30d') and (now_ts - cached_at < 120.0):
                    cached_db = db_data
                elif p_norm == 'today' and (now_ts - cached_at < 5.0):
                    cached_db = db_data

        if cached_db is not None:
            pipe = self.get_pipeline()
            res = dict(cached_db)
            res.update({
                'fps': pipe.fps if pipe else 0.0,
                'active_camera': self.active_camera,
                'camera_name': CAMERA_SOURCES.get(self.active_camera, {}).get('name', 'Main Porch Entry'),
                'is_rtsp_connected': pipe.is_rtsp_connected if pipe else False,
                'error_msg': pipe.error_msg if pipe else None,
                'auto_enroll_enabled': getattr(self, 'auto_enroll_enabled', True),
                'period': p_norm
            })
            return res

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()

        if p_norm == 'today':
            s_start = today_str
            s_end = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        elif p_norm == 'yesterday':
            s_start = (today_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            s_end = today_str
        elif p_norm == '7d':
            s_start = (today_dt - timedelta(days=6)).strftime('%Y-%m-%d')
            s_end = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        elif p_norm == '30d':
            s_start = (today_dt - timedelta(days=29)).strftime('%Y-%m-%d')
            s_end = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')

        date_filter_s = "s.timestamp >= ? AND s.timestamp < ?"
        date_params = (s_start, s_end)
        entry_cam_filter = "s.camera_id IN (SELECT id FROM cameras WHERE role = 'entry')"

        # Strictly count distinct individuals (Males, Females, and Total) who entered through the Entry Camera
        cur.execute(f"""
            SELECT 
                COUNT(DISTINCT s.visitor_id),
                COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'male' THEN s.visitor_id END),
                COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'female' THEN s.visitor_id END)
            FROM visitor_sightings s
            LEFT JOIN unique_visitors u ON s.visitor_id = u.id
            WHERE {date_filter_s}
              AND {entry_cam_filter}
        """, date_params)
        uv_total, male_cnt, female_cnt = cur.fetchone()

        # Total hospital footfall: de-duplicated visitor entries (hourly passage sessions) through Entry Camera
        cur.execute(f"""
            SELECT COUNT(DISTINCT s.visitor_id || '_' || strftime('%Y-%m-%d %H', s.timestamp))
            FROM visitor_sightings s
            WHERE {date_filter_s} AND {entry_cam_filter}
        """, date_params)
        footfall_cnt = cur.fetchone()[0] or 0
        total_footfall = max(footfall_cnt, uv_total or 0)

        cur.execute('SELECT count(*) FROM blacklist_watchlist WHERE active = 1')
        wl_cnt = cur.fetchone()[0]

        cur.execute("SELECT count(*) FROM security_alerts WHERE status = 'open'")
        open_alerts = cur.fetchone()[0]

        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT visitor_id FROM visitor_sightings s
                WHERE {date_filter_s}
                GROUP BY visitor_id HAVING COUNT(DISTINCT camera_id) > 1
            )
        """, date_params)
        multi_cam_count = cur.fetchone()[0] or 0

        conn.close()

        db_res = {
            'total_visitors_detected': total_footfall or 0,
            'unique_visitors_verified': uv_total or 0,
            'male_visitors': male_cnt or 0,
            'female_visitors': female_cnt or 0,
            'watchlist_count': wl_cnt or 0,
            'active_threats': open_alerts or 0,
            'multi_camera_visitors': multi_cam_count or 0
        }

        with self._cache_lock:
            for k in list(self._kpi_cache.keys()):
                if k[0] != today_str:
                    self._kpi_cache.pop(k, None)
            self._kpi_cache[(today_str, p_norm)] = (db_res, now_ts)

        pipe = self.get_pipeline()
        res = dict(db_res)
        res.update({
            'fps': pipe.fps if pipe else 0.0,
            'active_camera': self.active_camera,
            'camera_name': CAMERA_SOURCES.get(self.active_camera, {}).get('name', 'Main Porch Entry'),
            'is_rtsp_connected': pipe.is_rtsp_connected if pipe else False,
            'error_msg': pipe.error_msg if pipe else None,
            'auto_enroll_enabled': getattr(self, 'auto_enroll_enabled', True),
            'period': p_norm
        })
        return res

    def get_traffic_trend(self, period='today'):
        p = str(period or 'today').lower().strip()
        if p in ('7d', '7 days', '7'):
            p_norm = '7d'
        elif p in ('30d', '30 days', '30'):
            p_norm = '30d'
        elif p == 'yesterday':
            p_norm = 'yesterday'
        else:
            p_norm = 'today'

        today_dt = get_ist_now()
        today_str = today_dt.strftime('%Y-%m-%d')
        now_ts = time.time()

        with self._cache_lock:
            cached = self._trend_cache.get((today_str, p_norm))
            if cached:
                data, cached_at = cached
                if p_norm == 'yesterday':
                    return copy.deepcopy(data)
                elif p_norm in ('7d', '30d') and (now_ts - cached_at < 120.0):
                    return copy.deepcopy(data)
                elif p_norm == 'today' and (now_ts - cached_at < 10.0):
                    return copy.deepcopy(data)

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        chart_data = []

        entry_cam_filter = "s.camera_id IN (SELECT id FROM cameras WHERE role = 'entry')"

        if p_norm == 'today':
            t_start = today_str
            t_end = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            cur.execute(f"""
                SELECT 
                    strftime('%H:00', s.timestamp) as hr,
                    COUNT(DISTINCT s.visitor_id) as total_unique,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'female' THEN s.visitor_id END) as females,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) != 'female' THEN s.visitor_id END) as males
                FROM visitor_sightings s
                LEFT JOIN unique_visitors u ON s.visitor_id = u.id
                WHERE {entry_cam_filter}
                  AND s.timestamp >= ? AND s.timestamp < ?
                GROUP BY hr
            """, (t_start, t_end))
            hour_data = {r[0]: {'total': r[1], 'females': r[2], 'males': r[3]} for r in cur.fetchall()}
            for h in range(8, 20):
                lbl = f"{h:02d}:00"
                hd = hour_data.get(lbl, {'total': 0, 'males': 0, 'females': 0})
                chart_data.append({
                    'label': lbl,
                    'count': hd['total'],
                    'males': hd['males'],
                    'females': hd['females']
                })

        elif p_norm == 'yesterday':
            y_date = (today_dt - timedelta(days=1)).strftime('%Y-%m-%d')
            y_start = y_date
            y_end = today_str
            cur.execute(f"""
                SELECT 
                    strftime('%H:00', s.timestamp) as hr,
                    COUNT(DISTINCT s.visitor_id) as total_unique,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'female' THEN s.visitor_id END) as females,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) != 'female' THEN s.visitor_id END) as males
                FROM visitor_sightings s
                LEFT JOIN unique_visitors u ON s.visitor_id = u.id
                WHERE {entry_cam_filter}
                  AND s.timestamp >= ? AND s.timestamp < ?
                GROUP BY hr
            """, (y_start, y_end))
            hour_data = {r[0]: {'total': r[1], 'females': r[2], 'males': r[3]} for r in cur.fetchall()}
            for h in range(8, 20):
                lbl = f"{h:02d}:00"
                hd = hour_data.get(lbl, {'total': 0, 'males': 0, 'females': 0})
                chart_data.append({
                    'label': lbl,
                    'count': hd['total'],
                    'males': hd['males'],
                    'females': hd['females']
                })

        elif p_norm == '7d':
            start_date = (today_dt - timedelta(days=6)).strftime('%Y-%m-%d')
            start_iso = start_date
            end_iso = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            cur.execute(f"""
                SELECT 
                    strftime('%m-%d', s.timestamp) as dy,
                    COUNT(DISTINCT s.visitor_id) as total_unique,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'female' THEN s.visitor_id END) as females,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) != 'female' THEN s.visitor_id END) as males
                FROM visitor_sightings s
                LEFT JOIN unique_visitors u ON s.visitor_id = u.id
                WHERE {entry_cam_filter}
                  AND s.timestamp >= ? AND s.timestamp < ?
                GROUP BY dy
            """, (start_iso, end_iso))
            day_data = {r[0]: {'total': r[1], 'females': r[2], 'males': r[3]} for r in cur.fetchall()}
            for i in range(6, -1, -1):
                d = today_dt - timedelta(days=i)
                dy_key = d.strftime('%m-%d')
                lbl = d.strftime('%a %d')
                dd = day_data.get(dy_key, {'total': 0, 'males': 0, 'females': 0})
                chart_data.append({
                    'label': lbl,
                    'count': dd['total'],
                    'males': dd['males'],
                    'females': dd['females']
                })

        elif p_norm == '30d':
            start_date = (today_dt - timedelta(days=29)).strftime('%Y-%m-%d')
            start_iso = start_date
            end_iso = (today_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            cur.execute(f"""
                SELECT 
                    strftime('%Y-%m-%d', s.timestamp) as dy,
                    COUNT(DISTINCT s.visitor_id) as total_unique,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) = 'female' THEN s.visitor_id END) as females,
                    COUNT(DISTINCT CASE WHEN LOWER(COALESCE(u.gender, s.gender, '')) != 'female' THEN s.visitor_id END) as males
                FROM visitor_sightings s
                LEFT JOIN unique_visitors u ON s.visitor_id = u.id
                WHERE {entry_cam_filter}
                  AND s.timestamp >= ? AND s.timestamp < ?
                GROUP BY dy
            """, (start_iso, end_iso))
            day_data = {r[0]: {'total': r[1], 'females': r[2], 'males': r[3]} for r in cur.fetchall()}
            for b in range(6):
                b_start = today_dt - timedelta(days=(5 - b) * 5 + 4)
                b_end = today_dt - timedelta(days=(5 - b) * 5)
                lbl = f"{b_start.strftime('%d %b')}-{b_end.strftime('%d %b')}"
                bucket_total = 0
                bucket_males = 0
                bucket_females = 0
                for offset in range((5 - b) * 5, (5 - b) * 5 + 5):
                    d_str = (today_dt - timedelta(days=offset)).strftime('%Y-%m-%d')
                    dd = day_data.get(d_str, {'total': 0, 'males': 0, 'females': 0})
                    bucket_total += dd['total']
                    bucket_males += dd['males']
                    bucket_females += dd['females']
                chart_data.append({
                    'label': lbl,
                    'count': bucket_total,
                    'males': bucket_males,
                    'females': bucket_females
                })

        conn.close()

        with self._cache_lock:
            for k in list(self._trend_cache.keys()):
                if k[0] != today_str:
                    self._trend_cache.pop(k, None)
            self._trend_cache[(today_str, p_norm)] = (chart_data, now_ts)

        return chart_data

    def get_recent_visitors(self, limit=100, filter_mode=None, start_time=None, end_time=None):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        fmode = str(filter_mode or '').lower().strip()
        
        # Parse time boundaries (supports relative presets or ISO timestamps)
        s_iso = None
        e_iso = None
        now_ist = get_ist_now()

        if start_time:
            st = str(start_time).strip().lower()
            if st in ('15m', '15min', '15mins'):
                s_iso = (now_ist - timedelta(minutes=15)).strftime('%Y-%m-%dT%H:%M:%S')
            elif st in ('30m', '30min', '30mins'):
                s_iso = (now_ist - timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%S')
            elif st in ('1h', '60m', '1hour'):
                s_iso = (now_ist - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S')
            elif st in ('4h', '4hours'):
                s_iso = (now_ist - timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S')
            elif st == 'today':
                s_iso = now_ist.strftime('%Y-%m-%dT00:00:00')
            elif st == 'yesterday':
                s_iso = (now_ist - timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
                if not end_time:
                    e_iso = now_ist.strftime('%Y-%m-%dT00:00:00')
            elif st in ('live', 'latest'):
                # Live stream sync: only return recent detections (within the last 30 minutes)
                s_iso = (now_ist - timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%S')
            elif st in ('all', 'any', 'unlimited', 'history'):
                s_iso = None
            else:
                s_iso = str(start_time).strip().replace(' ', 'T')

        if end_time and str(end_time).strip().lower() != 'live':
            e_iso = str(end_time).strip().replace(' ', 'T')

        time_clauses = []
        time_params = []
        if s_iso and e_iso:
            time_clauses.append("((uv.first_seen >= ? AND uv.first_seen <= ?) OR (uv.last_seen >= ? AND uv.last_seen <= ?))")
            time_params.extend([s_iso, e_iso, s_iso, e_iso])
        elif s_iso:
            time_clauses.append("(uv.last_seen >= ? OR uv.first_seen >= ?)")
            time_params.extend([s_iso, s_iso])
        elif e_iso:
            time_clauses.append("(uv.last_seen <= ? OR uv.first_seen <= ?)")
            time_params.extend([e_iso, e_iso])

        time_where = (" AND " + " AND ".join(time_clauses)) if time_clauses else ""

        try:
            if time_where:
                # Time-bounded query: scans indexed timestamp slice directly with zero overhead
                base_sql = f'''
                    SELECT 
                        uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                        uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                        uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                        CASE WHEN uv.previous_camera IS NOT NULL THEN 2 ELSE 1 END AS camera_count,
                        COALESCE(uv.previous_camera || ',' || uv.last_camera, uv.last_camera) AS cameras_seen_csv,
                        COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.88) AS max_confidence,
                        COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.85) AS avg_confidence
                    FROM unique_visitors uv
                    WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' {time_where}
                '''
                if fmode in ('multi', 'multi_camera', 'multi_cam'):
                    base_sql += " AND uv.previous_camera IS NOT NULL"
                elif fmode in ('blacklisted', 'blacklist'):
                    base_sql += " AND uv.is_blacklisted = 1"
                base_sql += " ORDER BY uv.last_seen DESC LIMIT ?"
                cur.execute(base_sql, tuple(time_params + [limit]))
            elif fmode in ('multi', 'multi_camera', 'multi_cam'):
                # Fetch only visitors observed across more than 1 distinct camera (0ms using indexed previous_camera)
                cur.execute('''
                    SELECT 
                        uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                        uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                        uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                        2 AS camera_count,
                        COALESCE(uv.previous_camera || ',' || uv.last_camera, uv.last_camera) AS cameras_seen_csv,
                        COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.88) AS max_confidence,
                        COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.85) AS avg_confidence
                    FROM unique_visitors uv
                    WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' AND uv.previous_camera IS NOT NULL
                    ORDER BY uv.last_seen DESC
                    LIMIT ?
                ''', (limit,))
            elif fmode in ('blacklisted', 'blacklist'):
                # Fetch only blacklisted visitors
                cur.execute('''
                    SELECT 
                        uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                        uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                        uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                        CASE WHEN uv.previous_camera IS NOT NULL THEN 2 ELSE 1 END AS camera_count,
                        COALESCE(uv.previous_camera || ',' || uv.last_camera, uv.last_camera) AS cameras_seen_csv,
                        COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.95) AS max_confidence,
                        COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.90) AS avg_confidence
                    FROM unique_visitors uv
                    WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' AND uv.is_blacklisted = 1
                    ORDER BY uv.last_seen DESC
                    LIMIT ?
                ''', (limit,))
            else:
                # Default query: prioritize blacklisted and multi-camera visitors combined with latest sightings
                cur.execute('''
                    WITH blacklisted_all AS (
                        SELECT 
                            uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                            uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                            uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                            CASE WHEN uv.previous_camera IS NOT NULL THEN 2 ELSE 1 END AS camera_count,
                            COALESCE(uv.previous_camera || ',' || uv.last_camera, uv.last_camera) AS cameras_seen_csv,
                            COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.95) AS max_confidence,
                            COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.90) AS avg_confidence
                        FROM unique_visitors uv
                        WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' AND uv.is_blacklisted = 1
                        ORDER BY uv.last_seen DESC
                        LIMIT 20
                    ),
                    multi_cams AS (
                        SELECT 
                            uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                            uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                            uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                            2 AS camera_count,
                            uv.previous_camera || ',' || uv.last_camera AS cameras_seen_csv,
                            COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.88) AS max_confidence,
                            COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.85) AS avg_confidence
                        FROM unique_visitors uv
                        WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' AND uv.previous_camera IS NOT NULL
                        ORDER BY uv.last_seen DESC
                        LIMIT ?
                    ),
                    top_recent_uv AS (
                        SELECT * FROM unique_visitors
                        WHERE photo_b64 IS NOT NULL AND photo_b64 != ''
                        ORDER BY last_seen DESC
                        LIMIT ?
                    ),
                    recent_all AS (
                        SELECT 
                            uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                            uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                            uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                            CASE WHEN uv.previous_camera IS NOT NULL THEN 2 ELSE 1 END AS camera_count,
                            COALESCE(uv.previous_camera || ',' || uv.last_camera, uv.last_camera) AS cameras_seen_csv,
                            COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.88) AS max_confidence,
                            COALESCE((SELECT AVG(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = uv.id), 0.85) AS avg_confidence
                        FROM top_recent_uv uv
                        ORDER BY uv.last_seen DESC
                    ),
                    combined_recent AS (
                        SELECT * FROM multi_cams
                        UNION
                        SELECT * FROM recent_all
                        ORDER BY last_seen DESC
                        LIMIT ?
                    )
                    SELECT * FROM blacklisted_all
                    UNION
                    SELECT * FROM combined_recent
                    ORDER BY last_seen DESC
                    LIMIT ?
                ''', (limit, limit, limit, limit))
        except Exception as e:
            print("[GET_RECENT_VISITORS ERROR]", e)
            cur.execute('''
                SELECT id, gender, last_seen, last_camera, is_blacklisted, blacklist_reason, photo_b64, crops_json, total_sightings, age, 0, NULL, NULL, last_seen, 1, last_camera, COALESCE((SELECT MAX(vs.confidence) FROM visitor_sightings vs WHERE vs.visitor_id = unique_visitors.id), 0.85), 0.85
                FROM unique_visitors 
                WHERE photo_b64 IS NOT NULL AND photo_b64 != ''
                ORDER BY last_seen DESC LIMIT ?
            ''', (limit,))

        CAMERA_FALLBACKS = {
            'main': 'Main Porch Entry — Inbound',
            'cam_cd9e9a': 'Main Porch Exit',
            'main_exit': 'Main Porch Exit',
            'recep1': 'Main Reception & OPD Lobby',
            'outside': 'Main Porch Outer',
            'exit_gate': 'Main Hospital Exit Gate',
            'base_entry': '1st Basement Entry',
            'base_exit': '1st Basement Exit',
        }

        rows = []
        seen_ids = set()
        for r in cur.fetchall():
            if r[0] in seen_ids:
                continue
            seen_ids.add(r[0])
            crops = json.loads(r[7]) if r[7] else ([r[6]] if r[6] else [])
            if not crops and r[6]:
                crops = [r[6]]
            is_locked = bool(r[10]) if len(r) > 10 and r[10] else False
            cam_id = r[3] or 'main'
            cam_obj = CAMERA_SOURCES.get(cam_id, {})
            cam_name = cam_obj.get('name') or CAMERA_FALLBACKS.get(cam_id, cam_id)
            location = cam_obj.get('location') or 'Gate 01 Main Entry'

            first_seen = r[13] if len(r) > 13 and r[13] else r[2]
            last_seen = r[2]
            cam_cnt = r[14] if len(r) > 14 and r[14] else 1
            cams_csv = r[15] if len(r) > 15 and r[15] else cam_id
            cams_list = [c.strip() for c in cams_csv.split(',') if c.strip()]
            
            cam_names = []
            for c in cams_list:
                cn = CAMERA_SOURCES.get(c, {}).get('name') or CAMERA_FALLBACKS.get(c, c)
                if cn not in cam_names:
                    cam_names.append(cn)

            dwell_mins = 0
            try:
                dt1 = datetime.fromisoformat(first_seen)
                dt2 = datetime.fromisoformat(last_seen)
                dwell_mins = max(1, int((dt2 - dt1).total_seconds() / 60))
            except Exception:
                dwell_mins = 1

            if dwell_mins >= 60:
                dwell_str = f"{dwell_mins // 60}h {dwell_mins % 60}m"
            else:
                dwell_str = f"{dwell_mins}m"

            route_str = " ➔ ".join(cam_names) if len(cam_names) > 1 else cam_name
            is_multi = cam_cnt > 1

            if fmode in ('multi', 'multi_camera', 'multi_cam'):
                dwell_limit_mins = int(getattr(self, 'dwell_window_hours', 4.0) * 60)
                if dwell_mins > dwell_limit_mins:
                    continue

            # Extract actual biometric verification / detection confidence from sightings
            raw_conf = r[16] if len(r) > 16 and r[16] is not None else None
            if raw_conf is not None:
                verification_rate = round(float(raw_conf) * 100, 1)
            else:
                verification_rate = 85.0

            rows.append({
                'id': r[0],
                'name': r[0],
                'gender': r[1],
                'gender_locked': is_locked,
                'age': r[9] or 32,
                'started_at': first_seen or r[2],
                'first_seen': first_seen,
                'last_seen': last_seen,
                'camera_id': cam_id,
                'camera_name': cam_name,
                'camera_role': cam_obj.get('role', 'entry'),
                'location': location,
                'previous_camera': r[11] if len(r) > 11 else None,
                'previous_camera_name': r[12] if len(r) > 12 else None,
                'previous_camera_role': CAMERA_SOURCES.get(r[11], {}).get('role') if len(r) > 11 and r[11] else None,
                'is_blacklisted': bool(r[4]),
                'blacklist_reason': r[5],
                'photo_b64': r[6],
                'crops': crops,
                'sightings': len(crops) if len(crops) > 0 else (r[8] or 1),
                'total_sightings': r[8] or len(crops) or 1,
                'camera_count': cam_cnt,
                'is_multi_camera': is_multi,
                'cameras_seen': cams_list,
                'camera_names': cam_names,
                'dwell_mins': dwell_mins,
                'dwell_str': dwell_str,
                'route_str': route_str,
                'verification_rate': verification_rate,
                'confidence': verification_rate,
                'status': 'BLACKLISTED' if r[4] else ('MULTI-CAM VERIFIED' if is_multi else 'VERIFIED')
            })
        conn.close()
        return rows

    def get_watchlist(self):
        # Serve directly from memory cache for sub-millisecond instant response!
        if self.watchlist_cache is not None:
            rows = []
            for b in self.watchlist_cache:
                rows.append({
                    'id': b.get('id'),
                    'name': b.get('name'),
                    'alias': b.get('alias'),
                    'category': b.get('category', 'visitor'),
                    'reason': b.get('reason'),
                    'photo_b64': b.get('photo_b64'),
                    'crops': b.get('crops', []),
                    'enrolled_at': b.get('enrolled_at', get_ist_iso())
                })
            return rows

        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('SELECT id, name, alias, category, reason, photo_b64, crops_json, enrolled_at FROM blacklist_watchlist WHERE active = 1 ORDER BY enrolled_at DESC')
        rows = []
        for r in cur.fetchall():
            crops = json.loads(r[6]) if r[6] else ([r[5]] if r[5] else [])
            rows.append({
                'id': r[0],
                'name': r[1],
                'alias': r[2],
                'category': r[3],
                'reason': r[4],
                'photo_b64': r[5],
                'crops': crops,
                'enrolled_at': r[7]
            })
        conn.close()
        return rows

    def get_alerts(self, limit=100):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        try:
            cur.execute('SELECT id, watchlist_id, person_name, reason, camera_id, camera_name, confidence, photo_b64, timestamp, status FROM security_alerts ORDER BY timestamp DESC LIMIT ?', (limit,))
        except Exception:
            conn.close()
            return []
        rows = []
        for r in cur.fetchall():
            rows.append({
                'id': r[0],
                'watchlist_id': r[1],
                'person_name': r[2],
                'reason': r[3],
                'camera_id': r[4],
                'camera_name': r[5],
                'confidence': r[6],
                'photo_b64': r[7],
                'timestamp': r[8],
                'status': r[9]
            })
        conn.close()
        return rows


# ── HTTP Server Request Handler ─────────────────────────────────────────────

class FaceTrackerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status: int, data: dict or list):
        try:
            payload = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/feed-source':
            return self.send_json(200, {
                'mode': tracker.get_feed_mode(),
                'active_db': os.path.basename(DB_PATH)
            })

        if path == '/api/settings/auto-enroll':
            return self.send_json(200, {
                'auto_enroll_enabled': getattr(tracker, 'auto_enroll_enabled', True)
            })

        if path == '/api/settings/dwell-window':
            return self.send_json(200, {
                'dwell_window_hours': getattr(tracker, 'dwell_window_hours', 4.0),
                'max_active_seconds': getattr(tracker, 'max_active_seconds', 14400.0)
            })

        if path == '/api/kpis':
            params = urllib.parse.parse_qs(parsed.query)
            period = params.get('range', ['today'])[0]
            return self.send_json(200, tracker.get_kpis(period=period))

        if path == '/api/traffic-trend':
            params = urllib.parse.parse_qs(parsed.query)
            period = params.get('range', ['today'])[0]
            return self.send_json(200, tracker.get_traffic_trend(period=period))

        if path == '/api/visitors':
            params = urllib.parse.parse_qs(parsed.query)
            limit = int(params.get('limit', [36])[0]) if params.get('limit') else 36
            limit = min(limit, 150)
            filter_mode = params.get('filter', [None])[0]
            start_time = params.get('start_time', [None])[0]
            end_time = params.get('end_time', [None])[0]
            time_filter = params.get('time_filter', params.get('time_range', params.get('range', [None])))[0]
            if time_filter and not start_time:
                start_time = time_filter
            return self.send_json(200, tracker.get_recent_visitors(
                limit=limit, filter_mode=filter_mode, start_time=start_time, end_time=end_time
            ))

        if path == '/api/visitors/multi-camera':
            params = urllib.parse.parse_qs(parsed.query)
            limit = int(params.get('limit', [36])[0]) if params.get('limit') else 36
            limit = min(limit, 150)
            start_time = params.get('start_time', [None])[0]
            end_time = params.get('end_time', [None])[0]
            return self.send_json(200, tracker.get_recent_visitors(
                limit=limit, filter_mode='multi', start_time=start_time, end_time=end_time
            ))

        if path == '/api/visitors/similar':
            params = urllib.parse.parse_qs(parsed.query)
            visitor_id = params.get('visitor_id', [''])[0]
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, res = tracker.find_similar_visitors(visitor_id)
            if ok:
                return self.send_json(200, res)
            return self.send_json(404, {'error': res})

        if path == '/api/visitors/journey':
            params = urllib.parse.parse_qs(parsed.query)
            visitor_id = params.get('visitor_id', [''])[0]
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            journey = tracker.get_visitor_journey(visitor_id)
            if journey:
                return self.send_json(200, journey)
            return self.send_json(404, {'error': 'Journey not found'})

        if path == '/api/transits':
            return self.send_json(200, list(tracker.recent_transits))

        if path == '/api/watchlist':
            return self.send_json(200, tracker.get_watchlist())

        if path == '/api/alerts':
            params = urllib.parse.parse_qs(parsed.query)
            limit = int(params.get('limit', [100])[0]) if params.get('limit') else 100
            return self.send_json(200, tracker.get_alerts(limit=limit))

        if path == '/api/cameras':
            cams = []
            for c in tracker.get_cameras():
                pipe = tracker.get_pipeline(c['id'])
                c_copy = dict(c)
                c_copy['is_connected'] = pipe.is_rtsp_connected if pipe else False
                c_copy['fps'] = pipe.fps if pipe else 0.0
                c_copy['error_msg'] = pipe.error_msg if pipe else None
                cams.append(c_copy)
            return self.send_json(200, {'cameras': cams, 'active': tracker.active_camera})

        # SSE Stream for Instant Tactical Threat Alerts & Transit Events
        if path == '/api/alerts/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            import queue
            q = queue.Queue(maxsize=30)
            tracker.alert_queues.append(q)
            try:
                self.wfile.write(b"event: ping\ndata: {}\n\n")
                self.wfile.flush()
                while tracker.running:
                    try:
                        item = q.get(timeout=15.0)
                        evt_type = item.get('_event_type', 'alert')
                        msg = f"event: {evt_type}\ndata: {json.dumps(item)}\n\n".encode('utf-8')
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b"event: ping\ndata: {}\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError, OSError):
                pass
            finally:
                if q in tracker.alert_queues:
                    tracker.alert_queues.remove(q)
            return

        # Single Frame Snapshot (supports ?camera=<cam_id>)
        if path == '/api/frame':
            params = urllib.parse.parse_qs(parsed.query)
            cam_id = params.get('camera', [tracker.active_camera])[0]
            pipe = tracker.get_pipeline(cam_id)
            frame_bytes = None
            if pipe:
                with pipe.lock:
                    frame_bytes = pipe.latest_jpeg
            if frame_bytes:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(frame_bytes)))
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(frame_bytes)
            else:
                self.send_json(503, {'error': f'No frame available for camera {cam_id}'})
            return

        # MJPEG Video Stream (Supports multi-camera ?camera=<cam_id>)
        if path in ('/stream.mjpg', '/api/stream/feed', '/api/stream'):
            params = urllib.parse.parse_qs(parsed.query)
            cam_id = params.get('camera', [tracker.active_camera])[0]
            pipe = tracker.get_pipeline(cam_id)
            if not pipe:
                return self.send_json(404, {'error': f'Camera {cam_id} not found'})

            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            # Zero-Buffer Stream Pacing & Anti-Catchup
            try:
                import socket
                self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.request.settimeout(3.0)
            except Exception:
                pass

            seq = -1
            min_interval = 0.045  # ~21-22 FPS maximum pacing
            last_sent = 0.0
            try:
                while tracker.running and pipe.running:
                    with pipe.lock:
                        pipe.lock.wait_for(lambda: pipe.sequence != seq and pipe.latest_jpeg is not None, timeout=0.1)
                        if pipe.latest_jpeg is None or pipe.sequence == seq:
                            continue
                        now = time.monotonic()
                        if (now - last_sent) < min_interval:
                            continue
                        seq = pipe.sequence
                        frame_bytes = pipe.latest_jpeg

                    header = (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n'
                        b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
                    )
                    self.wfile.write(header + frame_bytes + b'\r\n')
                    self.wfile.flush()
                    last_sent = time.monotonic()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError, OSError, TimeoutError):
                return
            except Exception:
                return
            return

        # Static React UI files fallback
        self._serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length) or b'{}') if length > 0 else {}

        if path in ('/api/feed-source', '/api/feed-source/toggle'):
            mode = body.get('mode')
            res = tracker.set_feed_mode(mode)
            return self.send_json(200, res)

        if path == '/api/settings/auto-enroll':
            enabled = body.get('enabled')
            if enabled is None:
                enabled = body.get('auto_enroll_enabled', True)
            tracker.set_setting('auto_enroll_enabled', '1' if enabled else '0')
            return self.send_json(200, {
                'success': True,
                'auto_enroll_enabled': tracker.auto_enroll_enabled
            })

        if path == '/api/settings/dwell-window':
            hours = body.get('dwell_window_hours', body.get('hours', 4.0))
            try:
                hours_val = max(0.5, min(72.0, float(hours)))
                tracker.set_setting('dwell_window_hours', str(hours_val))
                return self.send_json(200, {
                    'success': True,
                    'dwell_window_hours': tracker.dwell_window_hours,
                    'max_active_seconds': tracker.max_active_seconds
                })
            except Exception as e:
                return self.send_json(400, {'error': str(e)})

        if path == '/api/visitors/search-by-photo':
            photo_b64 = body.get('photo_b64')
            if not photo_b64:
                return self.send_json(400, {'error': 'Missing photo_b64 in request body'})
            threshold = float(body.get('threshold', 0.35))
            ok, res = tracker.search_by_photo(photo_b64, min_threshold=threshold)
            if ok:
                return self.send_json(200, res)
            return self.send_json(400, {'error': res})

        if path == '/api/control':
            camera_id = body.get('camera') or body.get('stream')
            if tracker.switch_camera(camera_id):
                return self.send_json(200, {'success': True, 'camera': tracker.active_camera})
            return self.send_json(400, {'error': 'Invalid camera'})

        if path == '/api/cameras/add':
            name = (body.get('name') or '').strip()
            location = (body.get('location') or '').strip()
            rtsp = (body.get('rtsp') or body.get('url') or '').strip()
            role = (body.get('role') or '').strip()
            if not name or not rtsp:
                return self.send_json(400, {'error': 'Camera name and RTSP stream URL are required'})
            cam = tracker.add_camera(name, location or 'Checkpoint', rtsp, role=role if role else None)
            return self.send_json(200, {'success': True, 'camera': cam, 'camera_id': cam['id'], 'cameras': tracker.get_cameras()})

        if path in ('/api/cameras/edit', '/api/cameras/update'):
            camera_id = body.get('id') or body.get('camera_id') or body.get('stream')
            if not camera_id:
                return self.send_json(400, {'error': 'Missing camera_id'})
            name = body.get('name')
            location = body.get('location')
            rtsp = body.get('rtsp') or body.get('url')
            role = body.get('role')
            ok, res = tracker.edit_camera(camera_id, name=name, location=location, rtsp=rtsp, role=role)
            if ok:
                return self.send_json(200, {'success': True, 'camera': res, 'cameras': tracker.get_cameras()})
            return self.send_json(400, {'error': res})

        if path in ('/api/cameras/remove', '/api/cameras/delete'):
            camera_id = body.get('id') or body.get('camera_id') or body.get('stream')
            if not camera_id:
                return self.send_json(400, {'error': 'Missing camera_id'})
            ok, msg = tracker.remove_camera(camera_id)
            if ok:
                return self.send_json(200, {'success': True, 'cameras': tracker.get_cameras(), 'active': tracker.active_camera})
            return self.send_json(400, {'error': msg})

        if path == '/api/blacklist/add':
            is_photo = body.get('is_photo', False) or ('photo_b64' in body and not body.get('person_id'))
            target = body.get('photo_b64') if is_photo else body.get('person_id')
            name = body.get('name', 'Unknown Threat')
            reason = body.get('reason', 'Security Watchlist')

            if not target:
                return self.send_json(400, {'error': 'Missing person_id or photo_b64'})

            ok, res = tracker.add_to_blacklist(target, name, reason, is_photo=is_photo)
            if ok:
                vis_photo = None
                if not is_photo and target in tracker.unique_cache_by_id:
                    vis_photo = tracker.unique_cache_by_id[target].get('photo_b64')
                elif is_photo:
                    vis_photo = target

                alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
                now_iso = get_ist_iso()
                tracker._safe_db_write([
                    ('''INSERT INTO security_alerts (id, watchlist_id, person_name, reason, camera_id, camera_name, confidence, photo_b64, timestamp, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')''',
                     (alert_id, res, name, reason, 'MANUAL', 'Watchlist Enrolled', 1.0, vis_photo, now_iso))
                ])

                alert_payload = {
                    'id': alert_id,
                    'watchlist_id': res,
                    'person_name': name,
                    'reason': reason,
                    'camera_id': 'MANUAL',
                    'camera_name': 'Watchlist Enrolled',
                    'confidence': 1.0,
                    'timestamp': get_ist_str("%I:%M:%S %p IST"),
                    'photo_b64': vis_photo
                }
                tracker._broadcast_alert(alert_payload)
                return self.send_json(200, {
                    'success': True,
                    'watchlist_id': res,
                    'watchlist': tracker.get_watchlist(),
                    'alert': alert_payload
                })
            return self.send_json(400, {'error': res})

        if path == '/api/blacklist/remove':
            wid = body.get('watchlist_id') or body.get('id')
            alias = body.get('alias')
            name = body.get('name')
            if not wid and not alias:
                return self.send_json(400, {'error': 'Missing watchlist_id or alias'})
            tracker.remove_from_blacklist(wid or alias, alias=alias, name=name)
            return self.send_json(200, {'success': True, 'watchlist': tracker.get_watchlist()})

        if path == '/api/alerts/dismiss':
            for k in ['watchlist_id', 'person_name', 'id', 'alias', 'visitor_id']:
                val = body.get(k)
                if val:
                    tracker.dismiss_alert(val)
            return self.send_json(200, {'success': True})

        if path == '/api/visitors/remove-crop':
            visitor_id = body.get('visitor_id')
            crop_index = body.get('crop_index')
            crop_index_int = int(crop_index) if crop_index is not None else None
            crop_b64 = body.get('crop_b64')
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, msg = tracker.remove_visitor_crop(visitor_id, crop_index=crop_index_int, crop_b64=crop_b64)
            if ok:
                return self.send_json(200, {'success': True, 'message': msg})
            return self.send_json(400, {'error': msg})

        if path == '/api/visitors/delete':
            visitor_id = body.get('visitor_id')
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, msg = tracker.delete_visitor(visitor_id)
            if ok:
                return self.send_json(200, {'success': True})
            return self.send_json(400, {'error': msg})

        if path == '/api/visitors/merge':
            primary_id = body.get('primary_id')
            merge_ids = body.get('merge_ids', [])
            excluded_crops = body.get('excluded_crops', [])
            if not primary_id or not merge_ids:
                return self.send_json(400, {'error': 'Missing primary_id or merge_ids'})
            ok, res = tracker.merge_visitor_profiles(primary_id, merge_ids, excluded_crops)
            if ok:
                return self.send_json(200, {'success': True, 'data': res})
            return self.send_json(400, {'error': res})

        if path == '/api/visitors/find-similar':
            visitor_id = body.get('visitor_id')
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, res = tracker.find_similar_visitors(visitor_id)
            if ok:
                return self.send_json(200, res)
            return self.send_json(404, {'error': res})

        if path == '/api/visitors/toggle-gender':
            visitor_id = body.get('visitor_id')
            new_gender = body.get('gender')
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, res = tracker.toggle_visitor_gender(visitor_id, new_gender)
            if ok:
                return self.send_json(200, {'success': True, 'data': res})
            return self.send_json(400, {'error': res})

        if path == '/api/feed/click':
            cam_id = body.get('camera') or tracker.active_camera
            try:
                x = float(body.get('x', 0.5))
                y = float(body.get('y', 0.5))
            except (ValueError, TypeError):
                x, y = 0.5, 0.5
            action = body.get('action', 'toggle_blacklist')
            pipe = tracker.get_pipeline(cam_id)
            if not pipe:
                return self.send_json(404, {'success': False, 'error': f'Camera {cam_id} not found'})
            res = pipe.handle_feed_click(x, y, action)
            status_code = 200 if res.get('success') else 400
            return self.send_json(status_code, res)

        if path == '/api/maintenance/prune-exit-data':
            count = tracker.prune_unwanted_exit_records()
            return self.send_json(200, {'success': True, 'pruned_visitors': count})

        if path == '/api/maintenance/clean-invalid-faces':
            limit = int(body.get('limit', 50))
            deleted_count, updated_count = tracker.clean_unwanted_non_face_records(limit=limit)
            return self.send_json(200, {
                'success': True,
                'deleted_non_face_profiles': deleted_count,
                'cleaned_profile_crops': updated_count
            })

        if path == '/api/alerts/test':
            cam_info = CAMERA_SOURCES.get(tracker.active_camera, {})
            test_alert = {
                'id': f"TEST-{uuid.uuid4().hex[:6].upper()}",
                'watchlist_id': 'BLK-TEST',
                'person_name': body.get('name', 'Vikramaditya Rao'),
                'reason': body.get('reason', 'Barred from OPD Premises (Past Incident)'),
                'camera_id': tracker.active_camera,
                'camera_name': cam_info.get('name', 'Main Porch Entry'),
                'confidence': 96.4,
                'photo_b64': body.get('photo_b64', ''),
                'timestamp': get_ist_str("%I:%M:%S %p IST")
            }
            tracker._broadcast_alert(test_alert)
            return self.send_json(200, {'success': True, 'alert': test_alert})

        return self.send_json(404, {'error': 'Endpoint not found'})

    def _serve_static(self, path: str):
        if path == '/' or not path:
            file_path = DIST_DIR / 'index.html'
        else:
            rel = path.lstrip('/')
            file_path = DIST_DIR / rel

        if not file_path.exists() or file_path.is_dir():
            file_path = DIST_DIR / 'index.html'

        if not file_path.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Static build not found. Run 'npm run build' in ui directory.")
            return

        ext = file_path.suffix.lower()
        mime = MIME_TYPES.get(ext, 'application/octet-stream')

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            if ext in ('.js', '.css', '.svg', '.png', '.jpg'):
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            else:
                self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(500)
            self.end_headers()


# ── Server Bootstrapper ─────────────────────────────────────────────────────

tracker = FaceTrackerEngine()

def run_server():
    server_address = (HOST, PORT)
    httpd = ThreadingHTTPServer(server_address, FaceTrackerHandler)
    print(f"============================================================")
    print(f"  MEDANTA HOSPITALS — MULTI-CAMERA VISITOR RECOGNITION AI")
    print(f"  Live Server listening on http://127.0.0.1:{PORT}")
    print(f"  Registered Pipelines: {list(CAMERA_SOURCES.keys())}")
    print(f"============================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        tracker.running = False
        for p in tracker.pipelines.values():
            p.stop()
        httpd.server_close()

if __name__ == '__main__':
    run_server()
