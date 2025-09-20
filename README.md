# semeru-kapasitas

Polling kapasitas Semeru/Bromo langsung dari endpoint resmi `bromotenggersemeru.id` untuk tanggal target tertentu.  
Mendukung loop/polling, backoff otomatis saat error, dan highlight status **TERSEDIA / PENUH** di terminal.  
Sudah handle kasus ketika status menunjukkan **Kuota Penuh** walau nilai `sisa` disembunyikan.

## Fitur
- Ambil tabel kapasitas via `POST /website/home/get_view`
- Parsing tanggal Indonesia → ISO (contoh: `18 Oktober 2025` → `2025-10-18`)
- Deteksi **Kuota Penuh** walau `.hide` tidak menampilkan angka
- Loop dengan `--interval`, auto refresh session tiap 100 request, exponential backoff saat error
- Opsi paksa IPv4 (lebih stabil di banyak VPS/DC)

---

## Persyaratan
- **Ubuntu/Debian** dengan Python **3.9+** (perlu modul stdlib `zoneinfo`)
- Paket berikut (kalau belum ada, install pada bagian di bawah):
  - `python3`, `python3-venv`, `python3-pip`, `ca-certificates`
  - (opsional) `python-is-python3` agar perintah `python` = `python3`

---

## Instalasi Cepat (disarankan, pakai virtualenv)

```bash
# 0) paket dasar Python (wajib)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ca-certificates

# (opsional) biar 'python' menunjuk ke python3
sudo apt install -y python-is-python3

# 1) clone repo
git clone https://github.com/welldanyogia/semeru-kapasitas.git
cd semeru-kapasitas

# 2) virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3) dependencies
python -m pip install --upgrade pip wheel
pip install requests beautifulsoup4 colorama
