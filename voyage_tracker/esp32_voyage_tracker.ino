/*
 * ============================================================
 *   VOYAGE TRACKER — ESP32 Firmware
 *   PKL Indocement | GPS via HP Hotspot + TFT ILI9341
 * ============================================================
 *
 * CARA KERJA:
 *   1. HP nyalain hotspot + jalankan GPSLogger
 *   2. ESP32 konek ke hotspot HP via WiFi
 *   3. ESP32 ambil data GPS dari endpoint GPSLogger (HTTP)
 *   4. Tampilkan di layar TFT
 *   5. Kirim ke server Flask via internet (lewat hotspot HP)
 *
 * WIRING ILI9341:
 *   TFT VCC   → 3.3V
 *   TFT GND   → GND
 *   TFT CS    → GPIO 5
 *   TFT RESET → GPIO 4
 *   TFT DC    → GPIO 2
 *   TFT MOSI  → GPIO 23
 *   TFT SCK   → GPIO 18
 *   TFT LED   → 3.3V
 *
 * LIBRARY (install via Library Manager):
 *   - Adafruit ILI9341
 *   - Adafruit GFX Library
 *   - ArduinoJson (by Benoit Blanchon)
 *
 * ============================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <SPI.h>
#include <time.h>

// ── KONFIGURASI — SESUAIKAN INI ──────────────────────────────

// WiFi hotspot HP
const char* WIFI_SSID     = "NAMA_HOTSPOT_HP";
const char* WIFI_PASSWORD = "PASSWORD_HOTSPOT";

// URL server Flask (Railway/Render setelah deploy)
const char* SERVER_URL = "https://DOMAIN-LO.railway.app/update_esp32";

// IP HP di jaringan hotspot (cek di pengaturan hotspot HP)
// GPSLogger harus sudah running dan kirim ke port ini
// Atau bisa ambil dari endpoint GPSLogger share
// Kalau GPSLogger kirim langsung ke server, kosongkan GPS_HP_URL
const char* GPS_HP_URL = "http://192.168.43.1:8080/gps_data"; // opsional

// Interval kirim ke server (ms)
const unsigned long INTERVAL_KIRIM = 10000; // 10 detik

// Timezone WIB = UTC+7
const long  GMT_OFFSET_SEC  = 7 * 3600;
const int   DAYLIGHT_OFFSET = 0;
const char* NTP_SERVER      = "pool.ntp.org";

// ── PIN TFT ──────────────────────────────────────────────────
#define TFT_CS    5
#define TFT_RST   4
#define TFT_DC    2

// ── WARNA ────────────────────────────────────────────────────
#define C_BG      0x0841   // Hitam kebiruan gelap
#define C_ACCENT  0x07E0   // Hijau
#define C_CYAN    0x07FF   // Cyan
#define C_KUNING  0xFFE0   // Kuning
#define C_MERAH   0xF800   // Merah
#define C_PUTIH   0xFFFF
#define C_ABU     0x8410   // Abu gelap
#define C_PANEL   0x1082   // Panel gelap

// ─────────────────────────────────────────────────────────────

Adafruit_ILI9341 tft = Adafruit_ILI9341(TFT_CS, TFT_DC, TFT_RST);

// Data GPS global (diisi dari server atau HP)
double  gps_lat       = 0.0;
double  gps_lon       = 0.0;
float   gps_kecepatan = 0.0;  // km/h
float   gps_altitude  = 0.0;
bool    gps_valid     = false;
bool    server_ok     = false;
bool    wifi_ok       = false;

unsigned long waktu_kirim_terakhir = 0;
unsigned long waktu_update_layar   = 0;

// ─────────────────────────────────────────────────────────────
//   FUNGSI LAYAR
// ─────────────────────────────────────────────────────────────

void gambarLayout() {
  tft.fillScreen(C_BG);

  // Header bar
  tft.fillRect(0, 0, 240, 32, C_PANEL);
  tft.drawFastHLine(0, 32, 240, C_ACCENT);

  // Judul
  tft.setTextColor(C_ACCENT);
  tft.setTextSize(2);
  tft.setCursor(8, 8);
  tft.print("VOYAGE TRACKER");

  // Garis pemisah horizontal
  tft.drawFastHLine(0, 150, 240, C_ABU);
  tft.drawFastHLine(0, 200, 240, C_ABU);

  // Label statis
  tft.setTextSize(1);
  tft.setTextColor(C_KUNING);
  tft.setCursor(8, 40);  tft.print("LAT");
  tft.setCursor(8, 60);  tft.print("LON");
  tft.setCursor(8, 85);  tft.print("KECEPATAN");
  tft.setCursor(8, 110); tft.print("ALTITUDE");
  tft.setCursor(8, 130); tft.print("JAM WIB");

  tft.setTextColor(C_ABU);
  tft.setCursor(8, 155);  tft.print("WiFi");
  tft.setCursor(80, 155); tft.print("GPS");
  tft.setCursor(152, 155);tft.print("Server");

  // Footer
  tft.setTextColor(C_ABU);
  tft.setTextSize(1);
  tft.setCursor(8, 210);
  tft.print("PKL Indocement | ESP32");
}

// Hapus area nilai sebelum tulis ulang
void clearNilai(int x, int y, int w, int h) {
  tft.fillRect(x, y, w, h, C_BG);
}

void tampilkanNilai() {
  tft.setTextSize(1);

  // LAT
  clearNilai(50, 38, 185, 14);
  tft.setTextColor(gps_valid ? C_PUTIH : C_ABU);
  tft.setCursor(50, 40);
  if (gps_valid) {
    tft.print(gps_lat, 6);
  } else {
    tft.print("Mencari...");
  }

  // LON
  clearNilai(50, 58, 185, 14);
  tft.setCursor(50, 60);
  if (gps_valid) {
    tft.print(gps_lon, 6);
  } else {
    tft.print("Mencari...");
  }

  // KECEPATAN (lebih besar)
  clearNilai(50, 80, 185, 20);
  tft.setTextColor(C_CYAN);
  tft.setTextSize(2);
  tft.setCursor(50, 82);
  tft.print(gps_kecepatan, 1);
  tft.print(" km/h");
  tft.setTextSize(1);

  // ALTITUDE
  clearNilai(50, 108, 185, 14);
  tft.setTextColor(C_PUTIH);
  tft.setCursor(50, 110);
  tft.print(gps_altitude, 1);
  tft.print(" m");

  // JAM WIB (dari NTP)
  clearNilai(50, 128, 185, 14);
  tft.setTextColor(C_ACCENT);
  tft.setCursor(50, 130);
  struct tm timeinfo;
  if (getLocalTime(&timeinfo)) {
    char buf[12];
    strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
    tft.print(buf);
    tft.print(" WIB");
  } else {
    tft.setTextColor(C_ABU);
    tft.print("Sync NTP...");
  }
}

void tampilkanStatus() {
  // Hapus area status
  tft.fillRect(0, 163, 240, 34, C_BG);
  tft.setTextSize(1);

  // Indikator WiFi
  uint16_t warna_wifi = wifi_ok ? C_ACCENT : C_MERAH;
  tft.fillCircle(12, 173, 5, warna_wifi);
  tft.setTextColor(warna_wifi);
  tft.setCursor(20, 169);
  tft.print(wifi_ok ? "OK" : "X");

  // Indikator GPS
  uint16_t warna_gps = gps_valid ? C_ACCENT : C_MERAH;
  tft.fillCircle(84, 173, 5, warna_gps);
  tft.setTextColor(warna_gps);
  tft.setCursor(92, 169);
  tft.print(gps_valid ? "FIX" : "NO");

  // Indikator Server
  uint16_t warna_srv = server_ok ? C_ACCENT : C_MERAH;
  tft.fillCircle(156, 173, 5, warna_srv);
  tft.setTextColor(warna_srv);
  tft.setCursor(164, 169);
  tft.print(server_ok ? "SENT" : "FAIL");
}

// ─────────────────────────────────────────────────────────────
//   FUNGSI KONEKSI
// ─────────────────────────────────────────────────────────────

void sambungWiFi() {
  tft.setTextColor(C_KUNING);
  tft.setTextSize(1);
  tft.setCursor(8, 50);
  tft.print("Menyambungkan WiFi...");
  tft.setCursor(8, 65);
  tft.setTextColor(C_PUTIH);
  tft.print(WIFI_SSID);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int coba = 0;
  while (WiFi.status() != WL_CONNECTED && coba < 30) {
    delay(500);
    tft.setCursor(8 + coba * 6, 80);
    tft.setTextColor(C_ACCENT);
    tft.print(".");
    coba++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifi_ok = true;
    tft.fillRect(0, 90, 240, 16, C_BG);
    tft.setTextColor(C_ACCENT);
    tft.setCursor(8, 92);
    tft.print("WiFi OK: ");
    tft.print(WiFi.localIP());

    // Sync NTP
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET, NTP_SERVER);
    delay(1000);
  } else {
    wifi_ok = false;
    tft.setTextColor(C_MERAH);
    tft.setCursor(8, 90);
    tft.print("WiFi GAGAL!");
  }
  delay(1500);
}

// ─────────────────────────────────────────────────────────────
//   AMBIL DATA GPS DARI HP (opsional, kalau pakai GPS2NET)
//   Kalau GPSLogger langsung kirim ke server, fungsi ini
//   tidak diperlukan — ESP32 bisa ambil data dari /api/live
// ─────────────────────────────────────────────────────────────

bool ambilGPSdariServer() {
  /*
   * Alternatif: ESP32 ambil data GPS dari endpoint /api/live
   * server Flask. Ini berguna kalau GPSLogger sudah kirim ke server
   * dan ESP32 tinggal ambil data yang sudah tersimpan.
   */
  if (WiFi.status() != WL_CONNECTED) return false;

  // Buat URL /api/live (ganti SERVER_URL dengan base URL)
  String base = String(SERVER_URL);
  // Hapus bagian /update_esp32 untuk dapat base URL
  int idx = base.lastIndexOf("/update_esp32");
  if (idx < 0) return false;
  String apiUrl = base.substring(0, idx) + "/api/live";

  HTTPClient http;
  http.begin(apiUrl);
  http.setTimeout(5000);
  int code = http.GET();

  if (code == 200) {
    String payload = http.getString();
    StaticJsonDocument<1024> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      JsonObject t = doc["terakhir"];
      if (!t.isNull() && t["lat"] != 0) {
        gps_lat       = t["lat"].as<double>();
        gps_lon       = t["lon"].as<double>();
        gps_kecepatan = t["kecepatan"].as<float>();
        gps_altitude  = t["altitude"].as<float>();
        gps_valid     = true;
        http.end();
        return true;
      }
    }
  }

  http.end();
  return false;
}

// ─────────────────────────────────────────────────────────────
//   KIRIM DATA KE SERVER FLASK
// ─────────────────────────────────────────────────────────────

bool kirimKeServer() {
  if (WiFi.status() != WL_CONNECTED || !gps_valid) return false;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(8000);

  // Buat JSON payload
  StaticJsonDocument<256> doc;
  doc["lat"]       = gps_lat;
  doc["lon"]       = gps_lon;
  doc["kecepatan"] = gps_kecepatan;
  doc["altitude"]  = gps_altitude;
  doc["sumber"]    = "esp32";

  String payload;
  serializeJson(doc, payload);

  int code = http.POST(payload);
  http.end();

  return (code == 200);
}

// ─────────────────────────────────────────────────────────────
//   SETUP & LOOP
// ─────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);

  // Inisialisasi TFT
  tft.begin();
  tft.setRotation(2); // Portrait, konektor di bawah
  tft.fillScreen(C_BG);

  // Tampilkan splash screen
  tft.setTextColor(C_ACCENT);
  tft.setTextSize(2);
  tft.setCursor(20, 80);
  tft.print("VOYAGE TRACKER");
  tft.setTextSize(1);
  tft.setTextColor(C_ABU);
  tft.setCursor(40, 110);
  tft.print("PKL Indocement");
  tft.setCursor(30, 125);
  tft.print("Inisialisasi...");
  delay(1500);

  // Sambung WiFi
  sambungWiFi();

  // Gambar layout utama
  gambarLayout();
}

void loop() {
  unsigned long now = millis();

  // Cek WiFi, reconnect kalau putus
  if (WiFi.status() != WL_CONNECTED) {
    wifi_ok = false;
    WiFi.reconnect();
    delay(2000);
  } else {
    wifi_ok = true;
  }

  // Update layar setiap 1 detik
  if (now - waktu_update_layar >= 1000) {
    waktu_update_layar = now;
    tampilkanNilai();
    tampilkanStatus();
  }

  // Ambil GPS + kirim ke server sesuai interval
  if (now - waktu_kirim_terakhir >= INTERVAL_KIRIM) {
    waktu_kirim_terakhir = now;

    // Ambil data GPS dari server (sudah dikirim GPSLogger)
    bool dapat = ambilGPSdariServer();

    if (dapat) {
      // Kirim konfirmasi dari ESP32 ke server
      server_ok = kirimKeServer();
    } else {
      server_ok = false;
    }
  }
}
