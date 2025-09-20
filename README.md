# semeru-kapasitas

Polling kapasitas Semeru/Bromo langsung dari endpoint resmi `bromotenggersemeru.id` untuk tanggal target tertentu.  
Mendukung loop/polling, backoff otomatis saat error, dan highlight status **TERSEDIA / PENUH** di terminal.

## Fitur
- Ambil tabel kapasitas via `POST /website/home/get_view`
- Parsing tanggal Indonesia → ISO (contoh: `18 Oktober 2025` → `2025-10-18`)
- Deteksi **Kuota Penuh** walau nilai `sisa` disembunyikan di `.hide`
- Loop terus dengan `--interval`, auto refresh session, dan exponential backoff
- Opsi memaksa IPv4 (stabil untuk DC/VPS tertentu)

## Persyaratan
- Python 3.9+ (butuh modul stdlib `zoneinfo`)
- `pip install requests beautifulsoup4 colorama`

## Instalasi (Lokal / VPS)
```bash
# 1) clone
git clone https://github.com/welldanyogia/semeru-kapasitas.git
cd semeru-kapasitas

# 2) (opsional) gunakan virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3) install dependency
python -m pip install --upgrade pip wheel
pip install requests beautifulsoup4 colorama
