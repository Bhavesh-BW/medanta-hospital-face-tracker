# Medanta Hospital - Face Recognition & Threat Security Watchlist Hub

> Multi-camera facial recognition and hospital security intelligence platform. Provides real-time visitor passage audits, demographic categorization, patient/visitor journey tracking across hospital gates, and instant one-click blacklist threat alerting.

---

## 🚀 Key Features
- YuNet lightweight ONNX face detector + SFace ONNX 128-d deep embedding extractor
- Demographic inference (estimated gender and age bracket)
- Multi-camera visitor journey tracking (identifies same person across Inbound, Reception, and OPD)
- **Security Watchlist & Instant Blacklist**: enroll threats directly from video feeds with 1-click
- Real-time audio alert chime and visual banner on blacklist match (>92% similarity)
- Searchable passage verification log with pagination and filter controls
- Zero-setup bundled web dashboard (runs directly via Python backend)

---

## 🧠 Pre-Installed Models
The repository includes all required pre-trained weights and ONNX model files:
- `backend/models/face_detection_yunet_2023mar.onnx`: OpenCV YuNet face detector
- `backend/models/face_recognition_sface_2021dec.onnx`: SFace feature extractor
- `backend/models/genderage.onnx`: Gender and age classification model

---

## 🛠️ Quick Start Guide

### 1. Prerequisites
- **Python**: Version `3.9`, `3.10`, or `3.11` recommended.
- **Hardware**: Compatible with standard CPU. A CUDA-capable NVIDIA GPU is recommended for high-FPS multi-stream processing.
- **Node.js**: *(Optional)* The production UI is **pre-compiled** inside `backend/dist` and served automatically by the Python backend. Node.js is only required if you want to modify the React frontend.

---

### 2. Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Bhavesh-BW/medanta-hospital-face-tracker.git
   cd medanta-hospital-face-tracker
   ```

2. **Create and activate a virtual environment**:
   - **Windows**:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - **Linux / macOS**:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

### 3. Running the Service

#### Option A: One-Click Launch Script
- **Windows**: Double-click `start.bat` (or run `start.bat` in CMD)
- **Linux / macOS**: Run `./start.sh`

#### Option B: Direct Python Execution
```bash
cd backend
python face_tracker.py
```

---

### 4. Accessing the Dashboard

Once started, open your web browser and navigate to:
```
http://localhost:8198
```

---

## ⚙️ Configuration & Customization

The service can be customized using environment variables or directly in the UI:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `TRACKER_BIND` | `0.0.0.0` | Host IP interface to bind the web server |
| `TRACKER_PORT` / `PORT` | `8198` | Port for HTTP API and Web Dashboard |
| `DEVICE` | Auto (`cuda:0` / `cpu`) | Inference device execution provider |

---

## 📁 Repository Structure
```
├── backend/
│   ├── face_tracker.py      # Main engine and HTTP server
│   ├── dist/                 # Pre-built production web dashboard
│   ├── models/               # Neural network weights & ONNX models
│   └── requirements.txt      # Python dependencies
├── ui/                       # Frontend source code (React / Vite / Tailwind)
│   ├── src/                  # Components, hooks, and views
│   └── package.json          # Node.js dependencies (for UI development)
├── start.bat                 # Windows one-click launcher
├── start.sh                  # Linux / macOS one-click launcher
├── .gitignore                # Excludes node_modules, temp files & databases
└── README.md                 # Project documentation
```

---

## 🔒 Database & Privacy Notice
Local runtime databases (`*.db`), temporary snapshot photos, and security tokens are excluded from this repository via `.gitignore`. 
When running for the first time, SQLite database tables are automatically initialized with fresh schema structures.
