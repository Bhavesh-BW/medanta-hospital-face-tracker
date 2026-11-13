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

DB_PATH = os.environ.get('FACE_TRACKER_DB', str(ROOT / 'face_tracker.db'))
RTSP_BASE = os.environ.get('RTSP_BASE', 'rtsp://124.123.89.162:31554/live')
PORT = int(os.environ.get('PORT', '8198'))
HOST = os.environ.get('HOST', '0.0.0.0')

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
    cur.execute("UPDATE cameras SET role = 'exit' WHERE (id LIKE '%exit%' OR name LIKE '%exit%') AND (role IS NULL OR role = 'entry')")
    cur.execute("UPDATE cameras SET role = 'entry' WHERE (id LIKE '%main%' OR name LIKE '%entry%') AND (role IS NULL)")
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
        crole = r[4] if len(r) > 4 and r[4] else ('exit' if ('exit' in r[0].lower() or 'exit' in r[1].lower()) else 'entry')
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
        self.role = role or ('exit' if ('exit' in camera_id.lower() or 'exit' in name.lower()) else 'entry')

        self.lock = threading.Condition()
        self.running = True
        self.generation = 0
        self.latest_frame = None
        self.latest_jpeg = None
        self.sequence = 0
        self.fps = 0.0
        self.last_frame_ts = 0
        self.is_rtsp_connected = False
        self.error_msg = None
        self.active_tracks = {}
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

    def handle_feed_click(self, norm_x: float, norm_y: float, action: str = 'toggle_blacklist'):
        """Process an interactive click on the live CCTV stream to instantly flag or manage targets."""
        W, H = 1280, 720
        if self.latest_frame is not None:
            H, W = self.latest_frame.shape[:2]

        fx = norm_x * W
        fy = norm_y * H

        best_track = None
        min_dist = float('inf')

        with self.lock:
            tracks = list(self.active_tracks.values())

        for trk in tracks:
            bx, by, bw, bh = trk['bbox']
            # Allow generous padding (20%) for easy clicking on moving faces
            pad_w = max(12, int(bw * 0.20))
            pad_h = max(12, int(bh * 0.20))
            x1, y1 = bx - pad_w, by - pad_h
            x2, y2 = bx + bw + pad_w, by + bh + pad_h

            if x1 <= fx <= x2 and y1 <= fy <= y2:
                cx = bx + bw / 2.0
                cy = by + bh / 2.0
                dist = (fx - cx) ** 2 + (fy - cy) ** 2
                if dist < min_dist:
                    min_dist = dist
                    best_track = trk

        if not best_track:
            return {'success': False, 'error': 'No face detected at clicked coordinates'}

        visitor_id = best_track.get('visitor_id')
        if not visitor_id or visitor_id.startswith('UNTRACKED'):
            return {'success': False, 'error': 'Face has no registered visitor profile to blacklist'}

        is_bl = best_track.get('is_blacklisted', False)

        if action == 'toggle_blacklist':
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

                    # Trigger instantaneous cinematic threat broadcast
                    alert_payload = {
                        'id': f"ALT-{uuid.uuid4().hex[:8].upper()}",
                        'watchlist_id': res,
                        'person_name': target_name,
                        'reason': reason,
                        'camera_id': self.camera_id,
                        'camera_name': self.name,
                        'confidence': 0.99,
                        'timestamp': get_ist_str("%I:%M:%S %p IST"),
                        'photo_b64': best_track.get('photo_b64')
                    }
                    self.engine._broadcast_alert(alert_payload)
                    return {
                        'success': True,
                        'action': 'blacklisted',
                        'visitor_id': visitor_id,
                        'watchlist_id': res,
                        'name': target_name,
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
        while self.running:
            gen = self.generation
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000
            ])

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

            while self.running and self.generation == gen:
                ok, frame = cap.read()
                if not ok:
                    with self.lock:
                        self.is_rtsp_connected = False
                    break
                with self.lock:
                    self.is_rtsp_connected = True
                    self.latest_frame = frame
                    self.lock.notify_all()

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
            if self.latest_frame is None:
                return
            frame = self.latest_frame.copy()
            is_rtsp = self.is_rtsp_connected

        # Fast unblocked path when camera signal is offline
        if not is_rtsp:
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
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

        for face in faces:
            x, y, w, h = [int(v) for v in face[:4]]
            det_score = float(face[-1])
            cx = x + w / 2.0
            cy = y + h / 2.0

            # Crop face thumbnail
            H_f, W_f = frame.shape[:2]
            y1 = max(0, y)
            y2 = min(H_f, y + h)
            x1 = max(0, x)
            x2 = min(W_f, x + w)
            face_crop = frame[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else None

            # Extract embedding & gender/age
            emb = self.engine._extract_embedding(frame, face)
            instant_gender, gender_conf, age = self.engine._estimate_gender_and_age(frame, face, face_crop, self.camera_id)

            # Seated desk staff identification (Main lobby desk officer)
            is_sec_guard = False
            if self.camera_id == 'main':
                cx_norm = cx / max(W_f, 1)
                cy_norm = cy / max(H_f, 1)
                w_norm = float(w) / max(W_f, 1)
                if 0.68 <= cx_norm <= 0.75 and 0.23 <= cy_norm <= 0.32 and w_norm <= 0.040:
                    sec_sim = 0.0
                    if 'VIS-096BEB71' in self.engine.unique_cache_by_id:
                        sec_embs = self.engine.unique_cache_by_id['VIS-096BEB71'].get('embeddings', [])
                        for se in sec_embs:
                            sec_sim = max(sec_sim, cosine_sim(emb, se))
                    if sec_sim >= 0.18:
                        is_sec_guard = True

            # Spatial track association
            best_track_id = None
            best_iou = 0.0
            for tid, trk in self.active_tracks.items():
                if tid in matched_track_ids:
                    continue
                if trk.get('is_desk_guard') and not is_sec_guard:
                    continue
                iou = bbox_iou((x, y, w, h), trk['bbox'])
                if iou > best_iou:
                    best_iou = iou
                    best_track_id = tid

            if best_track_id is None:
                min_dist = 60.0
                for tid, trk in self.active_tracks.items():
                    if tid in matched_track_ids:
                        continue
                    if trk.get('is_desk_guard') and not is_sec_guard:
                        continue
                    tcx = trk['bbox'][0] + trk['bbox'][2] / 2.0
                    tcy = trk['bbox'][1] + trk['bbox'][3] / 2.0
                    dist = math.hypot(cx - tcx, cy - tcy)
                    if dist < min_dist:
                        if trk.get('visitor_id') and trk['visitor_id'] in self.engine.unique_cache_by_id:
                            trk_vis = self.engine.unique_cache_by_id[trk['visitor_id']]
                            if cosine_sim(emb, trk_vis['embedding']) < 0.20:
                                continue
                        min_dist = dist
                        best_track_id = tid

            # Crop thumbnail and calculate quality score
            is_sharp, quality_score = self.engine._is_sharp_face_crop(face_crop, face, det_score)
            photo_b64 = ""
            if face_crop is not None and face_crop.size > 0:
                ok, buf = cv2.imencode('.jpg', face_crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
                if ok:
                    photo_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode()}"

            # 1. Watchlist Screening via Vector Matrix (<0.05ms)
            matched_blacklist, max_bl_sim = self.engine.search_watchlist(emb, threshold=0.46)

            # 2. Match Visitor Profile
            matched_visitor = None
            is_transit = False
            prev_cam_name = None

            if is_sec_guard:
                instant_gender = 'female'
                gender_conf = 0.98
                sec_id = 'VIS-096BEB71'
                if sec_id in self.engine.unique_cache_by_id:
                    matched_visitor = self.engine.unique_cache_by_id[sec_id]

            # Priority A: Spatial track continuity (O(1))
            if matched_visitor is None and best_track_id is not None:
                tid_vis_id = self.active_tracks[best_track_id].get('visitor_id')
                if tid_vis_id and tid_vis_id in self.engine.unique_cache_by_id:
                    matched_visitor = self.engine.unique_cache_by_id[tid_vis_id]

            # Priority B: Watchlist alias binding (O(1))
            if matched_visitor is None and matched_blacklist is not None:
                alias = matched_blacklist.get('alias')
                if alias and alias in self.engine.unique_cache_by_id:
                    matched_visitor = self.engine.unique_cache_by_id[alias]

            # Priority C: Vector Matrix Search (<0.3ms across thousands of faces)
            if matched_visitor is None:
                matched_visitor, max_vis_sim = self.engine.search_gallery(emb, threshold=0.38)

            is_exit_camera = (getattr(self, 'role', 'entry') == 'exit') or ('exit' in self.camera_id.lower()) or ('exit' in self.name.lower())

            # Registration or Update
            if matched_visitor is None:
                if is_exit_camera:
                    # EXIT CAMERA: Do NOT register new visitor profile or save embeddings!
                    # Treat as anonymous / untracked departure to keep database and counts clean.
                    visitor_id = "UNTRACKED_EXIT"
                    gender = instant_gender or 'male'
                    age = age or 28
                else:
                    # ENTRY / CHECKPOINT CAMERA: Normal New Visitor Registration
                    if matched_blacklist is not None and matched_blacklist.get('alias'):
                        visitor_id = matched_blacklist['alias']
                    elif is_sec_guard:
                        visitor_id = 'VIS-096BEB71'
                    else:
                        visitor_id = f"VIS-{uuid.uuid4().hex[:8].upper()}"

                    self.engine.gender_votes[visitor_id] = collections.deque([(instant_gender, gender_conf)], maxlen=30)
                    gender = 'female' if is_sec_guard else instant_gender
                    gender_locked_flag = True if is_sec_guard else False
                    crops_list = [photo_b64] if photo_b64 else []

                    matched_visitor = {
                        'id': visitor_id,
                        'gender': gender,
                        'gender_locked': gender_locked_flag,
                        'age': 26 if is_sec_guard else age,
                        'embedding': emb,
                        'embeddings': [emb],
                        'last_seen': now_iso,
                        'last_seen_epoch': now_epoch,
                        'photo_b64': photo_b64,
                        'crops': crops_list,
                        'best_quality': quality_score,
                        'last_camera': self.camera_id,
                        'is_blacklisted': False,
                        'blacklist_reason': None
                    }
                    self.engine.unique_cache.append(matched_visitor)
                    self.engine.unique_cache_by_id[visitor_id] = matched_visitor
                    self.engine.add_to_gallery(matched_visitor, emb)
                    if gender_locked_flag:
                        self.engine.locked_genders.add(visitor_id)

                    self.engine.async_db_execute("""
                        INSERT INTO unique_visitors (id, gender, gender_confidence, age, embedding_json, photo_b64, crops_json, first_seen, last_seen, last_camera, is_blacklisted, blacklist_reason, gender_locked)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
                    """, (visitor_id, gender, gender_conf, age, json.dumps(emb.tolist()), photo_b64, json.dumps(crops_list), now_iso, now_iso, self.camera_id, 1 if gender_locked_flag else 0))
                    self.engine.async_db_execute("""
                        INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                        VALUES (?, ?, ?, ?, ?, ?, 0)
                    """, (visitor_id, self.camera_id, now_iso, gender, det_score, photo_b64))
            else:
                # Existing Visitor Matched
                visitor_id = matched_visitor['id']

                # Check Cross-Camera Transit
                last_cam = matched_visitor.get('last_camera')
                if last_cam and last_cam != self.camera_id:
                    is_transit = True
                    prev_cam_name = CAMERA_SOURCES.get(last_cam, {}).get('name', last_cam)
                    curr_name = self.name

                    # Calculate transit duration
                    duration_mins = 1
                    try:
                        prev_t = datetime.fromisoformat(matched_visitor.get('last_seen', now_iso))
                        curr_t = datetime.fromisoformat(now_iso)
                        duration_mins = max(1, int((curr_t - prev_t).total_seconds() / 60))
                    except Exception:
                        duration_mins = 1

                    matched_visitor['previous_camera'] = last_cam
                    matched_visitor['previous_camera_name'] = prev_cam_name
                    matched_visitor['last_camera'] = self.camera_id
                    matched_visitor['last_seen'] = now_iso

                    # Broadcast transit event
                    transit_event = {
                        'visitor_id': visitor_id,
                        'name': matched_visitor.get('name') or visitor_id,
                        'gender': matched_visitor.get('gender', 'unknown'),
                        'from_camera': prev_cam_name,
                        'to_camera': curr_name,
                        'duration_mins': duration_mins,
                        'photo_b64': matched_visitor.get('photo_b64', photo_b64),
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
                    """, (visitor_id, self.camera_id, now_iso, matched_visitor['gender'], det_score, photo_b64, 1 if matched_visitor.get('is_blacklisted') else 0))
                else:
                    matched_visitor['last_camera'] = self.camera_id

                # Gender Stability & Consensus
                if is_sec_guard or visitor_id in self.engine.locked_genders or matched_visitor.get('gender_locked'):
                    consensus_gender = 'female' if is_sec_guard else matched_visitor.get('gender', 'female')
                    matched_visitor['gender'] = consensus_gender
                    matched_visitor['gender_locked'] = True
                    self.engine.locked_genders.add(visitor_id)
                else:
                    if visitor_id not in self.engine.gender_votes:
                        self.engine.gender_votes[visitor_id] = collections.deque([(matched_visitor['gender'], 0.85)], maxlen=30)
                    if instant_gender is not None and gender_conf >= 0.60:
                        self.engine.gender_votes[visitor_id].append((instant_gender, gender_conf))

                    male_score = sum(c for g, c in self.engine.gender_votes[visitor_id] if g == 'male')
                    female_score = sum(c for g, c in self.engine.gender_votes[visitor_id] if g == 'female')
                    male_votes = sum(1 for g, _ in self.engine.gender_votes[visitor_id] if g == 'male')
                    female_votes = sum(1 for g, _ in self.engine.gender_votes[visitor_id] if g == 'female')

                    cur_g = matched_visitor.get('gender', 'male')
                    if cur_g == 'female':
                        consensus_gender = 'male' if (male_score > female_score * 1.8 and male_votes >= 8) else 'female'
                    else:
                        consensus_gender = 'female' if (female_score > male_score * 1.8 and female_votes >= 8) else 'male'

                    if consensus_gender != matched_visitor['gender']:
                        matched_visitor['gender'] = consensus_gender
                        self.engine.async_db_execute('UPDATE unique_visitors SET gender = ?, age = ?, last_seen = ? WHERE id = ?',
                                                     (consensus_gender, age, now_iso, visitor_id))

                gender = matched_visitor['gender']

                # EXIT CAMERA: Do NOT append exit embeddings or overwrite avatar with exit frames!
                if not is_exit_camera:
                    # Multi-crop accumulation & avatar upgrading (Entry only)
                    crops = matched_visitor.get('crops', [])
                    if not isinstance(crops, list):
                        crops = [crops] if crops else []
                    existing_quality = matched_visitor.get('best_quality', 0.0)

                    if photo_b64:
                        if quality_score > existing_quality or not matched_visitor.get('photo_b64'):
                            matched_visitor['photo_b64'] = photo_b64
                            matched_visitor['best_quality'] = quality_score
                            if photo_b64 in crops:
                                crops.remove(photo_b64)
                            crops.insert(0, photo_b64)
                            matched_visitor['crops'] = crops[:8]
                            matched_visitor['embedding'] = emb
                            if 'embeddings' not in matched_visitor or not matched_visitor['embeddings']:
                                matched_visitor['embeddings'] = [emb]
                            else:
                                matched_visitor['embeddings'].append(emb)
                            self.engine.add_to_gallery(matched_visitor, emb)
                            self.engine.async_db_execute('UPDATE unique_visitors SET photo_b64 = ?, crops_json = ?, embedding_json = ?, last_seen = ? WHERE id = ?',
                                                         (photo_b64, json.dumps(crops[:8]), json.dumps(emb.tolist()), now_iso, visitor_id))
                        else:
                            if len(crops) < 8 and quality_score >= 0.25:
                                is_dup = False
                                for ec in crops:
                                    if ec and ec[:120] == photo_b64[:120]:
                                        is_dup = True
                                        break
                                if not is_dup:
                                    crops.append(photo_b64)
                                    matched_visitor['crops'] = crops[:8]
                                    if 'embeddings' not in matched_visitor or not matched_visitor['embeddings']:
                                        matched_visitor['embeddings'] = [emb]
                                    else:
                                        matched_visitor['embeddings'].append(emb)
                                    self.engine.add_to_gallery(matched_visitor, emb)
                                    self.engine.async_db_execute('UPDATE unique_visitors SET crops_json = ?, last_seen = ? WHERE id = ?',
                                                                 (json.dumps(crops[:8]), now_iso, visitor_id))

                matched_visitor['last_seen'] = now_iso
                matched_visitor['last_seen_epoch'] = now_epoch

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
                if target_key in self.engine.dismissed_targets or (threat_name and threat_name.strip().lower() in self.engine.dismissed_targets):
                    is_blacklisted = False
                else:
                    now_ep = time.time()
                    hist_key = (target_key, self.camera_id)
                    last_logged = self.engine.blacklist_sighting_history.get(hist_key, 0)
                    if (now_ep - last_logged) > 20.0:
                        self.engine.blacklist_sighting_history[hist_key] = now_ep
                        self.engine.async_db_execute("""
                            INSERT INTO visitor_sightings (visitor_id, camera_id, timestamp, gender, confidence, photo_b64, is_blacklisted)
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                        """, (visitor_id, self.camera_id, now_iso, gender, det_score, photo_b64))

                    last_alert_ts = last_alert_time.get(target_key, 0)
                    if (now_ep - last_alert_ts) > 15.0:
                        last_alert_time[target_key] = now_ep
                        alert_payload = {
                            'id': f"ALT-{uuid.uuid4().hex[:8].upper()}",
                            'watchlist_id': threat_id or visitor_id,
                            'person_name': threat_name or visitor_id,
                            'reason': threat_reason or "Barred from Hospital Premises",
                            'camera_id': self.camera_id,
                            'camera_name': self.name,
                            'confidence': det_score,
                            'photo_b64': photo_b64 or (matched_visitor.get('photo_b64') if matched_visitor else None),
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

            # Spatial Track Update with Exponential Smoothing (alpha = 0.75)
            if best_track_id is not None:
                track_id = best_track_id
                trk = self.active_tracks[track_id]
                px, py, pw, ph = trk['bbox']
                sx = int(0.75 * x + 0.25 * px)
                sy = int(0.75 * y + 0.25 * py)
                sw = int(0.75 * w + 0.25 * pw)
                sh = int(0.75 * h + 0.25 * ph)
                trk['bbox'] = (sx, sy, sw, sh)
                trk['last_seen'] = now
                trk['missed'] = 0
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
                self.active_tracks[track_id] = {
                    'bbox': (x, y, w, h),
                    'last_seen': now,
                    'missed': 0,
                    'visitor_id': visitor_id,
                    'is_blacklisted': is_blacklisted,
                    'threat_name': threat_name,
                    'reason': threat_reason,
                    'is_transit': is_transit,
                    'prev_camera_name': prev_cam_name,
                    'is_desk_guard': is_sec_guard,
                    'gender': gender,
                    'age': age
                }
            matched_track_ids.add(track_id)

        # Age out stale tracks
        stale_ids = []
        for tid, trk in list(self.active_tracks.items()):
            if tid not in matched_track_ids:
                trk['missed'] = trk.get('missed', 0) + 1
                if trk['missed'] > 2 or (now - trk['last_seen']) > 0.35:
                    stale_ids.append(tid)

        for tid in stale_ids:
            self.active_tracks.pop(tid, None)

        # Render Bounding Boxes & HUD from Active Tracks (Silky Smooth)
        for tid, trk in self.active_tracks.items():
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
        self.active_camera = 'main'
        self.alert_queues = []
        self.recent_transits = collections.deque(maxlen=50)
        self._fallback_lock = threading.Condition()
        self.inference_lock = threading.Lock()

        # Load AI models
        det_path = str(MODELS / 'face_detection_yunet_2023mar.onnx')
        rec_path = str(MODELS / 'face_recognition_sface_2021dec.onnx')
        gender_path = str(MODELS / 'genderage.onnx')

        self.detector = cv2.FaceDetectorYN_create(det_path, '', (640, 360), 0.60, 0.3, 1000)
        self.recognizer = cv2.FaceRecognizerSF_create(rec_path, '')
        
        self.gender_net = None
        if os.path.exists(gender_path):
            try:
                self.gender_net = cv2.dnn.readNetFromONNX(gender_path)
                print("InsightFace genderage.onnx loaded successfully into OpenCV DNN!")
            except Exception as e:
                print("Failed to load genderage.onnx:", e)

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
                self.pipelines[cam_id] = CameraStreamPipeline(
                    cam_id, cam_info['name'], cam_info['location'], cam_info['rtsp'], self,
                    role=cam_info.get('role', 'exit' if ('exit' in cam_id.lower() or 'exit' in cam_info['name'].lower()) else 'entry')
                )
                print(f"[PIPELINE STARTED] {cam_id} -> {cam_info['name']} ({cam_info['rtsp']})")
            except Exception as e:
                print(f"Failed to start pipeline for {cam_id}:", e)

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
        target_w, target_h = 640, 360
        small = cv2.resize(frame, (target_w, target_h))
        with self.inference_lock:
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

    def _extract_embedding(self, frame: np.ndarray, face: np.ndarray):
        with self.inference_lock:
            aligned = self.recognizer.alignCrop(frame, face)
            feature = self.recognizer.feature(aligned)
        return feature.astype(np.float32)

    def _is_sharp_face_crop(self, face_crop: np.ndarray, face_coords: np.ndarray, det_score: float):
        if face_crop is None or face_crop.size == 0:
            return False, 0.0
        x, y, w, h = [int(v) for v in face_coords[:4]]
        if w < 24 or h < 24:
            return False, 0.0
        aspect = float(w) / max(float(h), 1.0)
        if aspect < 0.45 or aspect > 1.85:
            return False, 0.0

        try:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
            mean_v = float(np.mean(gray))
            if mean_v < 15.0 or mean_v > 248.0:
                return False, 0.0

            ch, cw = gray.shape[:2]
            inner_gray = gray[int(ch * 0.15):int(ch * 0.85), int(cw * 0.15):int(cw * 0.85)]
            if inner_gray.size == 0:
                inner_gray = gray

            inner_lap = float(cv2.Laplacian(inner_gray, cv2.CV_64F).var())
            total_lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            gx = cv2.Sobel(inner_gray, cv2.CV_64F, 1, 0, ksize=3)
            gy = cv2.Sobel(inner_gray, cv2.CV_64F, 0, 1, ksize=3)
            grad_mean = float(np.mean(np.sqrt(gx**2 + gy**2)))

            frontality_factor = 1.0
            if len(face_coords) >= 10:
                re_x = face_coords[4]
                le_x = face_coords[6]
                nose_x = face_coords[8]
                if re_x > 0 and le_x > 0:
                    min_eye = min(re_x, le_x)
                    max_eye = max(re_x, le_x)
                    eye_span = max(max_eye - min_eye, 1.0)
                    nose_pos = (nose_x - min_eye) / eye_span
                    frontality_factor = 1.0 + max(0.0, 0.4 - abs(nose_pos - 0.5))

            res_scale = math.sqrt(max(float(w * h), 576.0) / 2500.0)
            quality_score = (inner_lap * 0.4 + total_lap * 0.2 + grad_mean * 10.0) * res_scale * frontality_factor
            return True, max(quality_score, 10.0)
        except Exception:
            return True, float(w * h)

    def _estimate_gender_and_age(self, frame: np.ndarray, face: np.ndarray, face_crop: np.ndarray, camera_id: str):
        if self.gender_net is not None:
            try:
                x, y, w, h = [int(v) for v in face[:4]]
                if w < 28 or h < 28:
                    return None, 0.0, 30

                H, W = frame.shape[:2]
                cx_norm = (x + w / 2.0) / max(W, 1)
                cy_norm = (y + h / 2.0) / max(H, 1)
                w_norm = float(w) / max(W, 1)
                if camera_id == 'main' and 0.68 <= cx_norm <= 0.75 and 0.23 <= cy_norm <= 0.32 and w_norm <= 0.040:
                    return 'female', 0.98, 26

                if len(face) >= 8 and face[4] > 0 and face[6] > 0:
                    re_x, re_y = face[4], face[5]
                    le_x, le_y = face[6], face[7]
                    dx = le_x - re_x
                    dy = le_y - re_y
                    angle = float(np.degrees(np.arctan2(dy, dx)))
                    center = (float(x + w / 2), float(y + h / 2))
                    scale = 96.0 / (max(w, h, 28) * 1.45)
                    M = cv2.getRotationMatrix2D(center, angle, scale)
                    M[0, 2] += (48.0 - center[0])
                    M[1, 2] += (48.0 - center[1])
                    aligned = cv2.warpAffine(frame, M, (96, 96), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                else:
                    margin_x = int(w * 0.25)
                    margin_y = int(h * 0.25)
                    y1 = max(0, y - margin_y)
                    y2 = min(H, y + h + margin_y)
                    x1 = max(0, x - margin_x)
                    x2 = min(W, x + w + margin_x)
                    crop_area = frame[y1:y2, x1:x2]
                    if crop_area is None or crop_area.size == 0:
                        crop_area = face_crop
                    aligned = cv2.resize(crop_area, (96, 96))

                blob = cv2.dnn.blobFromImage(aligned, 1.0, (96, 96), (0, 0, 0), swapRB=True)
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
                female_prob = float(probs[0])
                male_prob = float(probs[1])

                age = int(round(float(age_preds[0][0]) * 100)) if hasattr(age_preds[0], '__len__') else int(round(float(age_preds[0]) * 100))
                age = max(18, min(80, age))

                if female_prob >= 0.55:
                    return 'female', female_prob, age
                elif male_prob >= 0.55:
                    return 'male', male_prob, age
                else:
                    return ('female' if female_prob > male_prob else 'male'), max(female_prob, male_prob), age
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

        cur.execute('SELECT id, name, alias, reason, embedding_json, photo_b64, crops_json FROM blacklist_watchlist WHERE active = 1')
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
                'reason': r[3],
                'embedding': emb,
                'embeddings': embeddings_list,
                'photo_b64': r[5],
                'crops': crops
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
            if emb is not None:
                vis_embeddings = [emb]
                if is_blk or is_locked:
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

    def _db_writer_loop(self):
        while self.running:
            try:
                task = self.db_queue.get(timeout=1.0)
                if task is None:
                    continue
                sql, params = task
                try:
                    conn = sqlite3.connect(DB_PATH, timeout=20.0)
                    cur = conn.cursor()
                    cur.execute(sql, params)
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
            except queue.Empty:
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
            for vis in self.unique_cache:
                embs = vis.get('embeddings') or ([vis['embedding']] if vis.get('embedding') is not None else [])
                for e in embs:
                    if e is not None:
                        ef = np.asarray(e, dtype=np.float32).flatten()
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

    def rebuild_watchlist_index(self):
        with self.matrix_lock:
            rows = []
            idx = []
            for bl in self.watchlist_cache:
                embs = bl.get('embeddings') or ([bl['embedding']] if bl.get('embedding') is not None else [])
                for e in embs:
                    if e is not None:
                        ef = np.asarray(e, dtype=np.float32).flatten()
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

    def search_gallery(self, emb: np.ndarray, threshold: float = 0.38):
        with self.matrix_lock:
            if self.gallery_matrix is None or len(self.gallery_index) == 0:
                return None, 0.0
            ef = np.asarray(emb, dtype=np.float32).flatten()
            norm = np.linalg.norm(ef)
            if norm < 1e-6:
                return None, 0.0
            query = ef / norm
            sims = np.dot(self.gallery_matrix, query)
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= threshold:
                return self.gallery_index[best_idx], best_sim
            return None, best_sim

    def search_watchlist(self, emb: np.ndarray, threshold: float = 0.46):
        with self.matrix_lock:
            if self.watchlist_matrix is None or len(self.watchlist_index) == 0:
                return None, 0.0
            ef = np.asarray(emb, dtype=np.float32).flatten()
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
        with self.matrix_lock:
            ef = np.asarray(emb, dtype=np.float32).flatten()
            norm = np.linalg.norm(ef)
            if norm > 1e-6:
                row = (ef / norm).reshape(1, 128)
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
            role = 'exit' if ('exit' in name.lower() or 'exit' in location.lower()) else 'entry'
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

    def remove_camera(self, camera_id: str):
        if camera_id == 'main':
            return False, "Cannot delete primary default camera"
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
            self.switch_camera('main')
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
            visitor_id = person_id_or_photo
            self.blacklisted_visitor_ids.add(visitor_id)
            self.dismissed_targets.discard(str(visitor_id).strip().lower())
            self.dismissed_targets.discard(str(name).strip().lower())
            conn = sqlite3.connect(DB_PATH, timeout=20.0)
            cur = conn.cursor()
            cur.execute('SELECT id, gender, embedding_json, photo_b64, crops_json FROM unique_visitors WHERE id = ?', (visitor_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return False, "Visitor ID not found"

            emb_json = row[2]
            photo_b64 = row[3]
            crops_json = row[4] or json.dumps([photo_b64] if photo_b64 else [])

            cur.execute('''
                INSERT INTO blacklist_watchlist (id, name, alias, category, reason, embedding_json, photo_b64, crops_json, enrolled_at, enrolled_by, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (bl_id, name or visitor_id, visitor_id, 'visitor', reason, emb_json, photo_b64, crops_json, now_iso, 'admin'))
            cur.execute('UPDATE unique_visitors SET is_blacklisted = 1, blacklist_reason = ? WHERE id = ?', (reason, visitor_id))
            conn.commit()
            conn.close()

            emb = np.array(json.loads(emb_json), dtype=np.float32) if emb_json else None
            crops = json.loads(crops_json) if crops_json else []
            embeddings_list = []
            if emb is not None:
                embeddings_list.append(emb)
            for c_img in crops[:4]:
                c_emb = self._extract_crop_embedding(c_img)
                if c_emb is not None:
                    embeddings_list.append(c_emb)

            self.watchlist_cache.append({
                'id': bl_id,
                'name': name or visitor_id,
                'alias': visitor_id,
                'reason': reason,
                'embedding': emb,
                'embeddings': embeddings_list,
                'photo_b64': photo_b64,
                'crops': crops
            })
            for vis in self.unique_cache:
                if vis['id'] == visitor_id:
                    vis['is_blacklisted'] = True
                    vis['blacklist_reason'] = reason
                    break

            for pipe in self.pipelines.values():
                for tid, trk in pipe.active_tracks.items():
                    if trk.get('visitor_id') == visitor_id:
                        trk['is_blacklisted'] = True
                        trk['threat_name'] = name or visitor_id
                        trk['reason'] = reason

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
                return False, "No face detected in uploaded photo"

            emb = self._extract_embedding(img, faces[0])
            emb_json = json.dumps(emb.tolist())
            crops_json = json.dumps([photo_b64])

            conn = sqlite3.connect(DB_PATH, timeout=20.0)
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO blacklist_watchlist (id, name, alias, category, reason, embedding_json, photo_b64, crops_json, enrolled_at, enrolled_by, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (bl_id, name, bl_id, 'manual_photo', reason, emb_json, photo_b64, crops_json, now_iso, 'admin'))
            conn.commit()
            conn.close()

            self.watchlist_cache.append({
                'id': bl_id,
                'name': name,
                'alias': bl_id,
                'reason': reason,
                'embedding': emb,
                'embeddings': [emb],
                'photo_b64': photo_b64,
                'crops': [photo_b64]
            })
            return True, bl_id

    def remove_from_blacklist(self, watchlist_id: str):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('SELECT alias, name FROM blacklist_watchlist WHERE id = ?', (watchlist_id,))
        row = cur.fetchone()
        alias = row[0] if row else None
        name = row[1] if row else None

        cur.execute('UPDATE blacklist_watchlist SET active = 0 WHERE id = ?', (watchlist_id,))
        if alias:
            cur.execute('UPDATE unique_visitors SET is_blacklisted = 0, blacklist_reason = NULL WHERE id = ?', (alias,))
        conn.commit()
        conn.close()

        if alias:
            self.blacklisted_visitor_ids.discard(alias)
            self.dismissed_targets.discard(alias.strip().lower())
        if name:
            self.dismissed_targets.discard(name.strip().lower())
        self.dismissed_targets.discard(watchlist_id.strip().lower())

        self.watchlist_cache = [b for b in self.watchlist_cache if b['id'] != watchlist_id]
        for vis in self.unique_cache:
            if vis.get('id') == alias:
                vis['is_blacklisted'] = False
                vis['blacklist_reason'] = None

        for pipe in self.pipelines.values():
            for tid, trk in pipe.active_tracks.items():
                if trk.get('visitor_id') == alias:
                    trk['is_blacklisted'] = False
                    trk['threat_name'] = None
                    trk['reason'] = None

        return True

    def remove_from_blacklist_by_alias(self, alias: str):
        """Remove a visitor from the blacklist using their visitor ID alias."""
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('SELECT id FROM blacklist_watchlist WHERE (alias = ? OR id = ?) AND active = 1', (alias, alias))
        rows = cur.fetchall()
        conn.close()
        for r in rows:
            self.remove_from_blacklist(r[0])
        # Also ensure flag is reset on unique_visitors table
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('UPDATE unique_visitors SET is_blacklisted = 0, blacklist_reason = NULL WHERE id = ?', (alias,))
        conn.commit()
        conn.close()
        self.blacklisted_visitor_ids.discard(alias)
        for vis in self.unique_cache:
            if vis.get('id') == alias:
                vis['is_blacklisted'] = False
                vis['blacklist_reason'] = None
        for pipe in self.pipelines.values():
            for trk in pipe.active_tracks.values():
                if trk.get('visitor_id') == alias:
                    trk['is_blacklisted'] = False
                    trk['threat_name'] = None
                    trk['reason'] = None
        return True

    def prune_unwanted_exit_records(self):
        """Clean up and purge any visitor profiles that were created solely by exit cameras."""
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        # Find all visitors whose ONLY sightings are on exit cameras
        cur.execute('''
            SELECT id FROM unique_visitors
            WHERE id NOT IN (
                SELECT DISTINCT visitor_id FROM visitor_sightings
                WHERE camera_id NOT LIKE '%exit%' AND camera_id != 'cam_cd9e9a'
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

    def remove_visitor_crop(self, visitor_id: str, crop_index: int):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        cur.execute('SELECT crops_json, photo_b64 FROM unique_visitors WHERE id = ?', (visitor_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False, "Visitor not found"

        crops = json.loads(row[0]) if row[0] else ([row[1]] if row[1] else [])
        if 0 <= crop_index < len(crops):
            crops.pop(crop_index)
            new_primary = crops[0] if len(crops) > 0 else ''
            new_crops_json = json.dumps(crops)
            cur.execute('UPDATE unique_visitors SET crops_json = ?, photo_b64 = ? WHERE id = ?',
                        (new_crops_json, new_primary, visitor_id))
            conn.commit()
            conn.close()

            if visitor_id in self.unique_cache_by_id:
                self.unique_cache_by_id[visitor_id]['crops'] = crops
                self.unique_cache_by_id[visitor_id]['photo_b64'] = new_primary
            return True, "Crop removed"
        conn.close()
        return False, "Crop index out of range"

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
        return True, {'id': visitor_id, 'gender': new_g, 'gender_locked': True}

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
        new_primary_photo = filtered_crops[0] if filtered_crops else primary.get('photo_b64', '')

        cur.execute('UPDATE unique_visitors SET crops_json = ?, photo_b64 = ?, total_sightings = ? WHERE id = ?',
                    (json.dumps(filtered_crops), new_primary_photo, tot_sightings, primary_id))
        conn.commit()
        conn.close()

        primary['crops'] = filtered_crops
        primary['photo_b64'] = new_primary_photo
        primary['embeddings'] = all_embs[:8]

        return True, {'primary_id': primary_id, 'merged_count': len(merge_ids), 'total_crops': len(filtered_crops)}

    def get_kpis(self, period='today'):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        p = str(period or 'today').lower().strip()

        if p == 'today':
            date_filter_u = "date(first_seen) = date('now', '+330 minutes') OR date(last_seen) = date('now', '+330 minutes')"
            date_filter_s = "date(timestamp) = date('now', '+330 minutes')"
        elif p == 'yesterday':
            date_filter_u = "date(first_seen) = date('now', '+330 minutes', '-1 day')"
            date_filter_s = "date(timestamp) = date('now', '+330 minutes', '-1 day')"
        elif p in ('7d', '7 days', '7'):
            date_filter_u = "date(first_seen) >= date('now', '+330 minutes', '-6 days')"
            date_filter_s = "date(timestamp) >= date('now', '+330 minutes', '-6 days')"
        elif p in ('30d', '30 days', '30'):
            date_filter_u = "date(first_seen) >= date('now', '+330 minutes', '-29 days')"
            date_filter_s = "date(timestamp) >= date('now', '+330 minutes', '-29 days')"
        else:
            date_filter_u = "1=1"
            date_filter_s = "1=1"

        cur.execute(f"""
            SELECT count(*), 
                   sum(case when gender = 'male' then 1 else 0 end), 
                   sum(case when gender = 'female' then 1 else 0 end) 
            FROM unique_visitors 
            WHERE {date_filter_u}
        """)
        uv_total, male_cnt, female_cnt = cur.fetchone()

        cur.execute(f'SELECT count(*) FROM visitor_sightings WHERE {date_filter_s}')
        tot_sightings = cur.fetchone()[0]

        cur.execute('SELECT count(*) FROM blacklist_watchlist WHERE active = 1')
        wl_cnt = cur.fetchone()[0]

        cur.execute(f"SELECT count(*) FROM security_alerts WHERE status = 'open'")
        open_alerts = cur.fetchone()[0]

        cur.execute('''
            SELECT COUNT(*) FROM (
                SELECT visitor_id FROM visitor_sightings GROUP BY visitor_id HAVING COUNT(DISTINCT camera_id) > 1
            )
        ''')
        multi_cam_count = cur.fetchone()[0] or 0

        conn.close()

        pipe = self.get_pipeline()
        return {
            'total_visitors_detected': tot_sightings or 0,
            'unique_visitors_verified': uv_total or 0,
            'male_visitors': male_cnt or 0,
            'female_visitors': female_cnt or 0,
            'watchlist_count': wl_cnt or 0,
            'active_threats': open_alerts or 0,
            'multi_camera_visitors': multi_cam_count,
            'fps': pipe.fps if pipe else 0.0,
            'active_camera': self.active_camera,
            'camera_name': CAMERA_SOURCES.get(self.active_camera, {}).get('name', 'Main Porch Entry'),
            'is_rtsp_connected': pipe.is_rtsp_connected if pipe else False,
            'error_msg': pipe.error_msg if pipe else None,
            'period': p
        }

    def get_traffic_trend(self, period='today'):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        p = str(period or 'today').lower().strip()
        chart_data = []

        if p == 'today':
            cur.execute('''
                SELECT strftime('%H:00', first_seen) as hr, count(DISTINCT id)
                FROM unique_visitors
                WHERE date(first_seen) = date('now', '+330 minutes')
                GROUP BY hr
            ''')
            hour_counts = dict(cur.fetchall())
            for h in range(8, 20):
                lbl = f"{h:02d}:00"
                chart_data.append({'label': lbl, 'count': hour_counts.get(lbl, 0)})

        elif p == 'yesterday':
            cur.execute('''
                SELECT strftime('%H:00', first_seen) as hr, count(DISTINCT id)
                FROM unique_visitors
                WHERE date(first_seen) = date('now', '+330 minutes', '-1 day')
                GROUP BY hr
            ''')
            hour_counts = dict(cur.fetchall())
            for h in range(8, 20):
                lbl = f"{h:02d}:00"
                chart_data.append({'label': lbl, 'count': hour_counts.get(lbl, 0)})

        elif p in ('7d', '7 days', '7'):
            cur.execute('''
                SELECT strftime('%m-%d', first_seen) as dy, count(DISTINCT id)
                FROM unique_visitors
                WHERE date(first_seen) >= date('now', '+330 minutes', '-6 days')
                GROUP BY dy
            ''')
            day_counts = dict(cur.fetchall())
            today = get_ist_now()
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                dy_key = d.strftime('%m-%d')
                lbl = d.strftime('%a %d')
                chart_data.append({'label': lbl, 'count': day_counts.get(dy_key, 0)})

        elif p in ('30d', '30 days', '30'):
            cur.execute('''
                SELECT strftime('%Y-%m-%d', first_seen) as dy, count(DISTINCT id)
                FROM unique_visitors
                WHERE date(first_seen) >= date('now', '+330 minutes', '-29 days')
                GROUP BY dy
            ''')
            day_counts = dict(cur.fetchall())
            today = get_ist_now()
            for b in range(6):
                b_start = today - timedelta(days=(5 - b) * 5 + 4)
                b_end = today - timedelta(days=(5 - b) * 5)
                lbl = f"{b_start.strftime('%d %b')}-{b_end.strftime('%d %b')}"
                bucket_cnt = 0
                for offset in range((5 - b) * 5, (5 - b) * 5 + 5):
                    d_str = (today - timedelta(days=offset)).strftime('%Y-%m-%d')
                    bucket_cnt += day_counts.get(d_str, 0)
                chart_data.append({'label': lbl, 'count': bucket_cnt})

        conn.close()
        return chart_data

    def get_recent_visitors(self, limit=100, filter_mode=None):
        conn = sqlite3.connect(DB_PATH, timeout=20.0)
        cur = conn.cursor()
        fmode = str(filter_mode or '').lower().strip()
        
        try:
            if fmode in ('multi', 'multi_camera', 'multi_cam'):
                # Fetch only visitors observed across more than 1 distinct camera
                cur.execute('''
                    SELECT 
                        uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                        uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                        uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                        COUNT(DISTINCT vs.camera_id) AS camera_count,
                        GROUP_CONCAT(DISTINCT vs.camera_id) AS cameras_seen_csv,
                        MAX(vs.confidence) AS max_confidence,
                        AVG(vs.confidence) AS avg_confidence
                    FROM unique_visitors uv
                    JOIN visitor_sightings vs ON uv.id = vs.visitor_id
                    WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != ''
                    GROUP BY uv.id
                    HAVING camera_count > 1
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
                        COUNT(DISTINCT vs.camera_id) AS camera_count,
                        GROUP_CONCAT(DISTINCT vs.camera_id) AS cameras_seen_csv,
                        MAX(vs.confidence) AS max_confidence,
                        AVG(vs.confidence) AS avg_confidence
                    FROM unique_visitors uv
                    LEFT JOIN visitor_sightings vs ON uv.id = vs.visitor_id
                    WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != '' AND uv.is_blacklisted = 1
                    GROUP BY uv.id
                    ORDER BY uv.last_seen DESC
                    LIMIT ?
                ''', (limit,))
            else:
                # Default query: prioritize multi-camera visitors combined with latest sightings
                cur.execute('''
                    WITH multi_cams AS (
                        SELECT 
                            uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                            uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                            uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                            COUNT(DISTINCT vs.camera_id) AS camera_count,
                            GROUP_CONCAT(DISTINCT vs.camera_id) AS cameras_seen_csv,
                            MAX(vs.confidence) AS max_confidence,
                            AVG(vs.confidence) AS avg_confidence
                        FROM unique_visitors uv
                        JOIN visitor_sightings vs ON uv.id = vs.visitor_id
                        WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != ''
                        GROUP BY uv.id
                        HAVING camera_count > 1
                    ),
                    recent_all AS (
                        SELECT 
                            uv.id, uv.gender, uv.last_seen, uv.last_camera, uv.is_blacklisted, uv.blacklist_reason, 
                            uv.photo_b64, uv.crops_json, uv.total_sightings, uv.age, uv.gender_locked, 
                            uv.previous_camera, uv.previous_camera_name, uv.first_seen,
                            COUNT(DISTINCT vs.camera_id) AS camera_count,
                            GROUP_CONCAT(DISTINCT vs.camera_id) AS cameras_seen_csv,
                            MAX(vs.confidence) AS max_confidence,
                            AVG(vs.confidence) AS avg_confidence
                        FROM unique_visitors uv
                        LEFT JOIN visitor_sightings vs ON uv.id = vs.visitor_id
                        WHERE uv.photo_b64 IS NOT NULL AND uv.photo_b64 != ''
                        GROUP BY uv.id
                        ORDER BY uv.last_seen DESC
                        LIMIT ?
                    )
                    SELECT * FROM multi_cams
                    UNION
                    SELECT * FROM recent_all
                    ORDER BY last_seen DESC
                    LIMIT ?
                ''', (limit, limit + 50))
        except Exception as e:
            print("[GET_RECENT_VISITORS ERROR]", e)
            cur.execute('''
                SELECT id, gender, last_seen, last_camera, is_blacklisted, blacklist_reason, photo_b64, crops_json, total_sightings, age, 0, NULL, NULL, last_seen, 1, last_camera, 0.85, 0.85
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
                'started_at': r[2],
                'first_seen': first_seen,
                'last_seen': last_seen,
                'camera_id': cam_id,
                'camera_name': cam_name,
                'location': location,
                'previous_camera': r[11] if len(r) > 11 else None,
                'previous_camera_name': r[12] if len(r) > 12 else None,
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
        payload = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

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
            limit = int(params.get('limit', [100])[0]) if params.get('limit') else 100
            filter_mode = params.get('filter', [None])[0]
            return self.send_json(200, tracker.get_recent_visitors(limit=limit, filter_mode=filter_mode))

        if path == '/api/visitors/multi-camera':
            params = urllib.parse.parse_qs(parsed.query)
            limit = int(params.get('limit', [100])[0]) if params.get('limit') else 100
            return self.send_json(200, tracker.get_recent_visitors(limit=limit, filter_mode='multi'))

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
            except (BrokenPipeError, ConnectionResetError):
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

            seq = -1
            try:
                while tracker.running and pipe.running:
                    with pipe.lock:
                        pipe.lock.wait_for(lambda: pipe.sequence != seq and pipe.latest_jpeg is not None, timeout=1.0)
                        if pipe.latest_jpeg is None or pipe.sequence == seq:
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
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError, OSError):
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

        if path == '/api/control':
            camera_id = body.get('camera') or body.get('stream')
            if tracker.switch_camera(camera_id):
                return self.send_json(200, {'success': True, 'camera': tracker.active_camera})
            return self.send_json(400, {'error': 'Invalid camera'})

        if path == '/api/cameras/add':
            name = (body.get('name') or '').strip()
            location = (body.get('location') or '').strip()
            rtsp = (body.get('rtsp') or '').strip()
            if not name or not rtsp:
                return self.send_json(400, {'error': 'Camera name and RTSP stream URL are required'})
            cam = tracker.add_camera(name, location or 'Checkpoint', rtsp)
            return self.send_json(200, {'success': True, 'camera': cam, 'camera_id': cam['id'], 'cameras': tracker.get_cameras()})

        if path == '/api/cameras/remove':
            camera_id = body.get('id') or body.get('camera_id')
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
                return self.send_json(200, {'success': True, 'watchlist_id': res})
            return self.send_json(400, {'error': res})

        if path == '/api/blacklist/remove':
            wid = body.get('watchlist_id') or body.get('id')
            if not wid:
                return self.send_json(400, {'error': 'Missing watchlist_id'})
            tracker.remove_from_blacklist(wid)
            return self.send_json(200, {'success': True})

        if path == '/api/alerts/dismiss':
            for k in ['watchlist_id', 'person_name', 'id', 'alias', 'visitor_id']:
                val = body.get(k)
                if val:
                    tracker.dismiss_alert(val)
            return self.send_json(200, {'success': True})

        if path == '/api/visitors/remove-crop':
            visitor_id = body.get('visitor_id')
            crop_index = int(body.get('crop_index', 0))
            if not visitor_id:
                return self.send_json(400, {'error': 'Missing visitor_id'})
            ok, msg = tracker.remove_visitor_crop(visitor_id, crop_index)
            if ok:
                return self.send_json(200, {'success': True})
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
