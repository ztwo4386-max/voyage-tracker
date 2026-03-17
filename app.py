"""
==============================================
  VOYAGE TRACKER — Backend Flask + SQLite
  PKL Indocement | ESP32 GPS System
==============================================

Install:
    pip install flask flask-cors

Jalankan lokal:
    python app.py

Deploy Railway:
    - Push ke GitHub
    - Connect di railway.app
    - Start command otomatis terbaca dari Procfile
==============================================
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os
import math

app = Flask(__name__)
CORS(app)

# ── Path database SQLite ──
DB_PATH = os.path.join(os.path.dirname(__file__), "voyage_data.db")

# ── Interval jadwal update (detik), bisa diubah dari dashboard ──
INTERVAL_UPDATE = 60  # default 1 menit


# ==============================================
#   INISIALISASI DATABASE
# ==============================================

def init_db():
    """Buat tabel kalau belum ada."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Tabel utama: setiap titik GPS yang masuk
    c.execute("""
        CREATE TABLE IF NOT EXISTS titik_gps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lat         REAL NOT NULL,
            lon         REAL NOT NULL,
            kecepatan   REAL DEFAULT 0,
            altitude    REAL DEFAULT 0,
            akurasi     REAL DEFAULT 0,
            provider    TEXT DEFAULT 'gps',
            sumber      TEXT DEFAULT 'gpslogger',
            timestamp   TEXT NOT NULL
        )
    """)

    # Tabel sesi voyage: satu sesi = satu perjalanan
    c.execute("""
        CREATE TABLE IF NOT EXISTS sesi_voyage (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nama            TEXT DEFAULT 'Voyage',
            mulai           TEXT,
            selesai         TEXT,
            jarak_km        REAL DEFAULT 0,
            kecepatan_avg   REAL DEFAULT 0,
            kecepatan_max   REAL DEFAULT 0,
            jumlah_titik    INTEGER DEFAULT 0,
            aktif           INTEGER DEFAULT 1
        )
    """)

    # Tabel jadwal: log kapan update diterima
    c.execute("""
        CREATE TABLE IF NOT EXISTS log_jadwal (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL,
            lat         REAL,
            lon         REAL,
            kecepatan   REAL,
            interval_s  INTEGER,
            status      TEXT DEFAULT 'diterima'
        )
    """)

    conn.commit()
    conn.close()


def get_db():
    """Buka koneksi DB dan return (conn, cursor)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Hasil bisa diakses seperti dict
    return conn, conn.cursor()


# ==============================================
#   HELPER: HITUNG JARAK (Haversine)
# ==============================================

def haversine(lat1, lon1, lat2, lon2):
    """Hitung jarak dua koordinat dalam km."""
    R = 6371  # radius bumi km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


# ==============================================
#   ROUTES
# ==============================================

@app.route("/")
def index():
    return render_template("index.html")


# ── Terima data dari GPSLogger ──
@app.route("/update_gps", methods=["GET", "POST"])
def update_gps():
    """
    Endpoint untuk GPSLogger.
    Setting URL di GPSLogger:
    http://DOMAIN/update_gps?lat=%LAT&lon=%LON&speed=%SPD&altitude=%ALT&accuracy=%ACC&provider=%PROV
    """
    global INTERVAL_UPDATE

    params = request.args if request.method == "GET" else request.form

    try:
        lat      = float(params.get("lat", 0))
        lon      = float(params.get("lon", 0))
        speed    = float(params.get("speed", 0))    # m/s dari GPSLogger
        altitude = float(params.get("altitude", 0))
        accuracy = float(params.get("accuracy", 0))
        provider = params.get("provider", "gps")

        kecepatan_kmh = round(speed * 3.6, 2)
        waktu_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn, c = get_db()

        # Simpan titik GPS
        c.execute("""
            INSERT INTO titik_gps (lat, lon, kecepatan, altitude, akurasi, provider, sumber, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, 'gpslogger', ?)
        """, (lat, lon, kecepatan_kmh, altitude, accuracy, provider, waktu_now))

        # Simpan ke log jadwal
        c.execute("""
            INSERT INTO log_jadwal (timestamp, lat, lon, kecepatan, interval_s)
            VALUES (?, ?, ?, ?, ?)
        """, (waktu_now, lat, lon, kecepatan_kmh, INTERVAL_UPDATE))

        # Update sesi aktif
        c.execute("SELECT id FROM sesi_voyage WHERE aktif = 1 ORDER BY id DESC LIMIT 1")
        sesi = c.fetchone()

        if sesi:
            sesi_id = sesi["id"]
            # Ambil semua titik untuk hitung statistik
            c.execute("""
                SELECT lat, lon, kecepatan FROM titik_gps
                WHERE timestamp >= (SELECT mulai FROM sesi_voyage WHERE id = ?)
                ORDER BY id ASC
            """, (sesi_id,))
            titik_sesi = c.fetchall()

            jarak_total = 0.0
            kec_vals = []
            for i in range(1, len(titik_sesi)):
                jarak_total += haversine(
                    titik_sesi[i-1]["lat"], titik_sesi[i-1]["lon"],
                    titik_sesi[i]["lat"],   titik_sesi[i]["lon"]
                )
                kec_vals.append(titik_sesi[i]["kecepatan"])

            kec_avg = round(sum(kec_vals) / len(kec_vals), 2) if kec_vals else 0
            kec_max = round(max(kec_vals), 2) if kec_vals else 0

            c.execute("""
                UPDATE sesi_voyage
                SET jarak_km=?, kecepatan_avg=?, kecepatan_max=?, jumlah_titik=?
                WHERE id=?
            """, (round(jarak_total, 3), kec_avg, kec_max, len(titik_sesi), sesi_id))
        else:
            # Auto buat sesi baru kalau belum ada
            c.execute("""
                INSERT INTO sesi_voyage (nama, mulai, aktif)
                VALUES (?, ?, 1)
            """, (f"Voyage {waktu_now[:10]}", waktu_now))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "waktu": waktu_now, "kecepatan_kmh": kecepatan_kmh}), 200

    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


# ── Terima data dari ESP32 ──
@app.route("/update_esp32", methods=["POST"])
def update_esp32():
    """Endpoint khusus ESP32 (JSON body)."""
    try:
        data = request.get_json()
        lat      = float(data.get("lat", 0))
        lon      = float(data.get("lon", 0))
        kecepatan = float(data.get("kecepatan", 0))
        altitude = float(data.get("altitude", 0))
        waktu_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn, c = get_db()
        c.execute("""
            INSERT INTO titik_gps (lat, lon, kecepatan, altitude, sumber, timestamp)
            VALUES (?, ?, ?, ?, 'esp32', ?)
        """, (lat, lon, kecepatan, altitude, waktu_now))
        conn.commit()
        conn.close()

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


# ── API: Data live untuk dashboard ──
@app.route("/api/live")
def api_live():
    """Data terbaru untuk polling dashboard."""
    try:
        init_db()  # Pastikan tabel ada
        conn, c = get_db()

        # Titik terakhir
        c.execute("SELECT * FROM titik_gps ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        terakhir = dict(row) if row else {}

        # Sesi aktif
        c.execute("SELECT * FROM sesi_voyage WHERE aktif = 1 ORDER BY id DESC LIMIT 1")
        sesi_row = c.fetchone()
        sesi = dict(sesi_row) if sesi_row else {}

        # Rute HANYA dari sesi aktif
        rute = []
        if sesi_row and sesi_row["mulai"]:
            c.execute("""
                SELECT lat, lon, kecepatan, timestamp FROM titik_gps
                WHERE timestamp >= ?
                ORDER BY id ASC LIMIT 200
            """, (sesi_row["mulai"],))
            rute = [dict(r) for r in c.fetchall()]

        conn.close()
        return jsonify({"terakhir": terakhir, "rute": rute, "sesi": sesi})
    except Exception as e:
        return jsonify({"error": str(e), "terakhir": {}, "rute": [], "sesi": {}}), 200


# ── API: Log voyage semua sesi ──
@app.route("/api/voyage_log")
def api_voyage_log():
    try:
        conn, c = get_db()
        c.execute("SELECT * FROM sesi_voyage ORDER BY id DESC LIMIT 50")
        sesi_list = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(sesi_list)
    except Exception as e:
        return jsonify([])


# ── API: Log jadwal update ──
@app.route("/api/jadwal_log")
def api_jadwal_log():
    try:
        conn, c = get_db()
        c.execute("""
            SELECT timestamp, lat, lon, kecepatan, interval_s, status
            FROM log_jadwal ORDER BY id DESC LIMIT 100
        """)
        logs = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(logs)
    except Exception as e:
        return jsonify([])


# ── API: Set interval update ──
@app.route("/api/set_interval", methods=["POST"])
def set_interval():
    global INTERVAL_UPDATE
    try:
        data = request.get_json()
        INTERVAL_UPDATE = int(data.get("interval", 60))
        return jsonify({"status": "ok", "interval": INTERVAL_UPDATE})
    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


# ── API: Mulai sesi voyage baru ──
@app.route("/api/sesi_baru", methods=["POST"])
def sesi_baru():
    try:
        data = request.get_json()
        nama = data.get("nama", f"Voyage {datetime.now().strftime('%d/%m %H:%M')}")
        waktu_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn, c = get_db()
        c.execute("UPDATE sesi_voyage SET aktif=0, selesai=? WHERE aktif=1", (waktu_now,))
        c.execute("INSERT INTO sesi_voyage (nama, mulai, aktif) VALUES (?, ?, 1)", (nama, waktu_now))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "nama": nama})
    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


# ── API: Tutup sesi aktif ──
@app.route("/api/tutup_sesi", methods=["POST"])
def tutup_sesi():
    try:
        waktu_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn, c = get_db()
        c.execute("UPDATE sesi_voyage SET aktif=0, selesai=? WHERE aktif=1", (waktu_now,))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


# ── API: Reset semua data ──
@app.route("/api/reset", methods=["POST"])
def reset_semua():
    try:
        conn, c = get_db()
        c.execute("DELETE FROM titik_gps")
        c.execute("DELETE FROM log_jadwal")
        c.execute("DELETE FROM sesi_voyage")
        conn.commit()
        conn.close()
        return jsonify({"status": "ok", "pesan": "Semua data direset"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Inisialisasi DB saat startup (Railway maupun lokal)
init_db()

if __name__ == "__main__":
    print("✅ Database siap")
    print("🚀 Server jalan di http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
