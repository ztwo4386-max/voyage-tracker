# 🛳️ Voyage Tracker — PKL Indocement
**GPS Monitor System | ESP32 + HP + Dashboard Web**

---

## 📁 Struktur Project
```
voyage_tracker/
├── app.py                    ← Backend Flask + SQLite
├── requirements.txt
├── Procfile                  ← Untuk Railway deploy
├── esp32_voyage_tracker.ino  ← Kode ESP32 (Arduino IDE)
└── templates/
    └── index.html            ← Dashboard Web
```

---

## 🔗 Alur Sistem
```
[HP Android]
  GPS aktif + Hotspot ON
  GPSLogger → kirim HTTP ke server
       │
       │ (internet via hotspot)
       ▼
[Server Flask] ← deploy di Railway
  SQLite simpan semua titik GPS
  Hitung jarak, kecepatan avg/max
       │
       ├──► [Dashboard Web] — peta, log, jadwal
       │
       └──► [ESP32] ambil data /api/live
              └──► TFT tampil: koordinat, kecepatan, jam
```

---

## 🚀 Langkah Setup

### 1. Deploy ke Railway
```bash
# Di folder voyage_tracker:
git init
git add .
git commit -m "voyage tracker init"
# Push ke GitHub, lalu connect di railway.app
```
Dapat URL: `https://voyage-tracker-xxx.railway.app`

### 2. Setting GPSLogger di HP
- Install **GPSLogger** (Play Store, gratis)
- Buka → **⋮ → Preferences → Logging Details** → Enable
- **Auto send → Custom URL** → centang ✅
- Isi URL:
```
https://DOMAIN.railway.app/update_gps?lat=%LAT&lon=%LON&speed=%SPD&altitude=%ALT&accuracy=%ACC&provider=%PROV
```
- Interval: **30 detik** atau **1 menit**
- Nyalakan hotspot HP
- Tekan ▶ **Start Logging**

### 3. Upload ke ESP32
- Buka `esp32_voyage_tracker.ino` di Arduino IDE
- Install library:
  - `Adafruit ILI9341`
  - `Adafruit GFX Library`
  - `ArduinoJson` (by Benoit Blanchon)
- Edit bagian konfigurasi:
  ```cpp
  const char* WIFI_SSID     = "NAMA_HOTSPOT_HP";
  const char* WIFI_PASSWORD = "PASSWORD_HOTSPOT";
  const char* SERVER_URL    = "https://DOMAIN.railway.app/update_esp32";
  ```
- Upload ke ESP32

---

## 🖥️ Fitur Dashboard
| Fitur | Keterangan |
|---|---|
| Peta Live | Posisi real-time + rute perjalanan |
| Kecepatan | Bar meter + nilai km/h |
| Voyage Log | Tabel sesi perjalanan: jarak, avg speed, max speed |
| Jadwal Update | Log kapan setiap update GPS masuk |
| Interval | Bisa atur 30 detik – 10 menit |
| Multi Sesi | Bisa buka/tutup sesi, data tersimpan di DB |

---

## 🔧 Test Lokal
```bash
pip install flask flask-cors
python app.py
# Buka http://localhost:5000

# Test kirim data GPS manual:
curl "http://localhost:5000/update_gps?lat=-6.2&lon=106.8&speed=8.3&altitude=15&accuracy=3&provider=gps"
```

---

## ⚡ API Endpoints
| URL | Method | Fungsi |
|---|---|---|
| `/` | GET | Dashboard |
| `/update_gps` | GET/POST | Terima dari GPSLogger |
| `/update_esp32` | POST | Terima dari ESP32 (JSON) |
| `/api/live` | GET | Data terbaru + rute |
| `/api/voyage_log` | GET | Semua sesi voyage |
| `/api/jadwal_log` | GET | Log jadwal update |
| `/api/set_interval` | POST | Set interval update |
| `/api/sesi_baru` | POST | Mulai sesi baru |
| `/api/tutup_sesi` | POST | Tutup sesi aktif |
| `/api/reset` | POST | Reset semua data |
