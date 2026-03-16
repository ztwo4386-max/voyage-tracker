"""
==============================================
  VOYAGE TRACKER — Backend Flask + SQLite
  PKL Indocement | ESP32 GPS System
==============================================
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime
import sqlite3
import os
import math

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), "voyage_data.db")
INTERVAL_UPDATE = 60


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/update_gps", methods=["GET", "POST"])
def update_gps():
    global INTERVAL_UPDATE
    params = request.args if request.method == "GET" else request.form

    try:
        lat      = float(params.get("lat", 0))
        lon      = float(params.get("lon", 0))
        speed    = float(params.get("speed", 0))
        altitude = float(params.get("altitude", 0))
        accuracy = float(params.get("accuracy", 0))
        provider = params.get("provider", "gps")

        kecepatan_kmh = round(speed * 3.6, 2)
        waktu_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn, c = get_db()

        c.execute("""
            INSERT INTO titik_gps (lat, lon, kecepatan, altitude, akurasi, provider, sumber, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, 'gpslogger', ?)
        """, (lat, lon, kecepatan_kmh, altitude, accuracy, provider, waktu_now))

        c.execute("""
            INSERT INTO log_jadwal (timestamp, lat, lon, kecepatan, interval_s)
            VALUES (?, ?, ?, ?, ?)
        """, (waktu_now, lat, lon, kecepatan_kmh, INTERVAL_UPDATE))

        c.execute("SELECT id FROM sesi_voyage WHERE aktif = 1 ORDER BY id DESC LIMIT 1")
        sesi = c.fetchone()

        if sesi:
            sesi_id = sesi["id"]
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
            c.execute("""
                INSERT INTO sesi_voyage (nama, mulai, aktif)
                VALUES (?, ?, 1)
            """, (f"Voyage {waktu_now[:10]}", waktu_now))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "waktu": waktu_now, "kecepatan_kmh": kecepatan_kmh}), 200

    except Exception as e:
        return jsonify({"status": "error", "pesan": str(e)}), 400


@app.route("/update_esp32", methods=["POST"])
def update_esp32():
    try:
        data = request.get_json()
        lat       = float(data.get("lat", 0))
        lon       = float(data.get("lon", 0))
        kecepatan = float(data.get("kecepatan", 0))
        altitude  = float(data.get("altitude", 0))
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


@app.route("/api/live")
def api_live():
    try:
        conn, c = get_db()

        c.execute("SELECT * FROM titik_gps ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        terakhir = dict(row) if row else {}

        c.execute("SELECT lat, lon, kecepatan, timestamp FROM titik_gps ORDER BY id DESC LIMIT 100")
        rute_raw = [dict(r) for r in c.fetchall()]
        rute = list(reversed(rute_raw))

        c.execute("SELECT * FROM sesi_voyage WHERE aktif = 1 ORDER BY id DESC LIMIT 1")
        sesi_row = c.fetchone()
        sesi = dict(sesi_row) if sesi_row else {}

        conn.close()
        return jsonify({"terakhir": terakhir, "rute": rute, "sesi": sesi})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/voyage_log")
def api_voyage_log():
    try:
        conn, c = get_db()
        c.execute("SELECT * FROM sesi_voyage ORDER BY id DESC LIMIT 50")
        sesi_list = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(sesi_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route("/api/set_interval", methods=["POST"])
def set_interval():
    global INTERVAL_UPDATE
    data = request.get_json()
    INTERVAL_UPDATE = int(data.get("interval", 60))
    return jsonify({"status": "ok", "interval": INTERVAL_UPDATE})


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def reset_semua():
    try:
        conn, c = get_db()
        c.execute("DELETE FROM titik_gps")
        c.execute("DELETE FROM log_jadwal")
        c.execute("DELETE FROM sesi_voyage")
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    print("Database siap")
    print("Server jalan di http://localhost:5000")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
