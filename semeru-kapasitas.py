# -*- coding: utf-8 -*-
# Semeru/Bromo kapasitas poller
# Dependencies:
#   pip install requests beautifulsoup4 colorama
#
# Contoh pakai:
#   python semeru-kapasitas.py --site-id 8 --year-month 2025-10 --target 2025-10-18 --ipv4
#   python semeru-kapasitas.py --site-id 8 --year-month 2025-10 --target 2025-10-18 --loop --stop-when-available --interval 1 --ipv4

import os
import socket
import time
from typing import Optional, List, Dict, Any, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from datetime import datetime
from zoneinfo import ZoneInfo  # Python 3.9+

# ======================= KONFIG & KONST =======================
BASE_URL = "https://bromotenggersemeru.id"
GET_VIEW_URL = f"{BASE_URL}/website/home/get_view"

MONTHS_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12
}

# ======================= UTIL WAKTU =======================
def now_wib() -> str:
    """Timestamp WIB presisi detik, mis: 2025-09-17 21:43:05 WIB"""
    return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S WIB")


# ======================= WARNA TERMINAL =======================
try:
    # pip install colorama
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    # Fallback tanpa warna jika colorama tidak tersedia
    class _Dummy:
        RESET_ALL = ""
        BRIGHT = ""
        DIM = ""
        NORMAL = ""
        RED = ""
        GREEN = ""
        YELLOW = ""
        BLUE = ""
        MAGENTA = ""
        CYAN = ""
        WHITE = ""
    Fore = Style = _Dummy()  # type: ignore[misc,assignment]

def C(txt: str, fg: str = "", bright: bool = False, dim: bool = False) -> str:
    """Pembungkus warna sederhana."""
    pre = ""
    if bright:
        pre += Style.BRIGHT
    elif dim:
        pre += Style.DIM
    if fg:
        pre += fg
    return f"{pre}{txt}{Style.RESET_ALL}"

ACCENT = (Fore.CYAN, True)  # (warna, bright?)

def ts(tag: str) -> str:
    fg, bright = ACCENT
    return f"[{C(now_wib(), fg, bright=bright)}] {C(tag, Fore.WHITE, dim=True)}"


# ======================= SESSION TAHAN BANTING =======================
class IPv4HTTPAdapter(HTTPAdapter):
    """Opsional: paksa IPv4 dan aktifkan TCP keepalive."""
    def init_poolmanager(self, *args, **kwargs):
        from urllib3.poolmanager import PoolManager
        # Tambah opsi TCP keepalive agar koneksi idle tidak cepat 'basi'
        kwargs["socket_options"] = kwargs.get("socket_options", []) + [
            (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30),
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10),
            (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3),
        ]
        self.poolmanager = PoolManager(*args, **kwargs)

def build_session(force_ipv4: bool = True) -> requests.Session:
    """Session tanpa proxy env + retry/backoff + header mirip browser."""
    # Pastikan tidak pakai proxy env yang bisa bikin hang
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        os.environ.pop(k, None)

    s = requests.Session()
    s.trust_env = False  # jangan baca proxy/dll dari environment

    retry = Retry(
        total=5,
        connect=3,
        read=3,
        backoff_factor=0.8,  # 0.8s, 1.6s, 3.2s, ...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )

    adapter = IPv4HTTPAdapter(max_retries=retry) if force_ipv4 else HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)

    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": BASE_URL,
        "Referer": BASE_URL + "/",
    })
    return s


# ======================= PARSER & FORMATTER =======================
def to_iso_from_tanggal_id(text: str) -> Optional[str]:
    """
    "Rabu, 1 Oktober 2025" -> "2025-10-01"
    Mengabaikan warna/span apapun; pakai angka hari, nama bulan (ID), dan tahun.
    """
    if not text:
        return None
    t = " ".join(text.split()).strip()
    import re
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", t)
    if not m:
        return None
    dd, mm_name, yy = m.group(1), m.group(2).lower(), m.group(3)
    mm = MONTHS_ID.get(mm_name)
    if not mm:
        return None
    return f"{yy}-{mm:02d}-{int(dd):02d}"

def parse_kapasitas_rows(html: str) -> List[Dict[str, Any]]:
    """
    Parse tabel kapasitas menjadi list dict:
    {tanggalText, tanggalISO, statusText, sisa, isFull, available}
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        tanggal_text = tds[0].get_text(strip=True, separator=" ")

        status_el = tds[1].select_one(".text-red, .text-green, .text-blue")
        status_text = (status_el.get_text(" ", strip=True) if status_el
                       else tds[1].get_text(" ", strip=True))

        hide_el = tds[1].select_one(".hide")
        hide_val_raw = hide_el.get_text(strip=True) if hide_el else None

        # parse sisa jika .hide berisi angka, jika tidak biarkan None
        sisa: Optional[int]
        if hide_val_raw and hide_val_raw.isdigit():
            sisa = int(hide_val_raw)
        else:
            sisa = None

        tanggal_iso = to_iso_from_tanggal_id(tanggal_text)
        st_low = status_text.lower()

        # indikasi penuh dari teks
        is_full_text = ("penuh" in st_low) or ("kuota penuh" in st_low)

        # jika .hide tidak menampilkan angka (disembunyikan) dan teks "Kuota Penuh",
        # paksa dianggap penuh meskipun sisa=None
        hide_is_hidden = hide_el is not None and (not hide_val_raw or not hide_val_raw.isdigit())
        full_by_hidden = ("kuota penuh" in st_low) and hide_is_hidden

        # juga anggap penuh bila sisa==0 (kalau kebetulan ada angkanya)
        is_full_zero = (isinstance(sisa, int) and sisa == 0)

        is_full = bool(is_full_text or full_by_hidden or is_full_zero)

        # available hanya jika tidak penuh DAN ada indikasi tersedia ATAU sisa>0
        available = (not is_full) and (
            any(k in st_low for k in ["tersedia", "available", "tersisa"]) or
            (isinstance(sisa, int) and sisa > 0)
        )

        rows.append({
            "tanggalText": tanggal_text,
            "tanggalISO": tanggal_iso,
            "statusText": status_text,
            "sisa": sisa,
            "isFull": is_full,
            "available": available
        })
    return rows

def _match_target(row: Dict[str, Any], target: Union[int, str]) -> bool:
    """Cocokkan baris dengan target tanggal."""
    if isinstance(target, int):
        dd = f"-{int(target):02d}"
        return bool(row.get("tanggalISO") and row["tanggalISO"].endswith(dd))
    if isinstance(target, str):
        t = target.strip()
        # ISO
        if len(t) == 10 and t[4] == "-" and t[7] == "-":
            return row.get("tanggalISO") == t
        # Coba format Indonesia
        iso = to_iso_from_tanggal_id(t)
        if iso:
            return row.get("tanggalISO") == iso
        # fallback: substring pada tanggalText
        return t.lower() in (row.get("tanggalText", "").lower())
    return False

def _human_summary(row: Dict[str, Any]) -> str:
    """Ringkasan ramah-awam, multi-baris (berwarna)."""
    sisa = row.get("sisa")
    sisa_txt = f"{sisa} kuota" if isinstance(sisa, int) else "tidak diketahui"

    # Warna ketersediaan
    available = bool(row.get("available"))
    is_full = bool(row.get("isFull"))

    if available:
        avail_txt = C("TERSEDIA ✅", Fore.GREEN, bright=True)
    elif is_full:
        avail_txt = C("PENUH ❌", Fore.RED, bright=True)
    else:
        avail_txt = C("BELUM TERSEDIA ❌", Fore.YELLOW, bright=True)

    # Warna 'sisa'
    if isinstance(sisa, int) and sisa > 0:
        sisa_colored = C(sisa_txt, Fore.GREEN, bright=True)
    elif isinstance(sisa, int) and sisa == 0:
        sisa_colored = C(sisa_txt, Fore.RED, bright=True)
    else:
        sisa_colored = C(sisa_txt, Fore.YELLOW)

    tanggal_line = f"Tanggal : {C(row.get('tanggalText') or '-', Fore.CYAN, bright=True)} " \
                   f"(ISO: {C(row.get('tanggalISO') or '-', Fore.MAGENTA)})"
    status_line  = f"Status  : {C(row.get('statusText') or '-', Fore.WHITE)}"
    sisa_line    = f"Sisa    : {sisa_colored}"
    info_line    = f"Info    : {avail_txt}"

    return "\n".join([tanggal_line, status_line, sisa_line, info_line])


# ======================= HTTP REQUEST =======================
def get_kapasitas(session: Optional[requests.Session] = None,
                  id_site: int = 8,
                  year_month: str = "2025-10",
                  timeout_connect: int = 5,
                  timeout_read: int = 45) -> str:
    """
    Hit endpoint get_view (POST) dan kembalikan HTML string.
    Akan menjaga cookie (ci_session) jika menggunakan Session yang sama.
    """
    s = session or build_session(force_ipv4=True)
    data = {"action": "kapasitas", "id_site": str(id_site), "year_month": year_month}
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
        "Referer": BASE_URL + "/"
    }

    t0 = time.monotonic()
    resp = s.post(GET_VIEW_URL, data=data, headers=headers, timeout=(timeout_connect, timeout_read))
    t1 = time.monotonic()
    resp.raise_for_status()
    html = resp.text
    t2 = time.monotonic()

    print(
        f"{ts(C('[get_view]', Fore.CYAN))} "
        f"{C(str(resp.status_code), Fore.GREEN if resp.ok else Fore.RED, bright=True)} "
        f"{C(resp.reason or '', Fore.WHITE)} | {C(str(len(html))+' bytes', Fore.YELLOW)} | "
        f"{C(f'total={t2-t0:.3f}s recv={t2-t1:.3f}s', Fore.CYAN)}"
    )
    return html


# ======================= API UTAMA =======================
def get_kapasitas_by_date(session: Optional[requests.Session] = None,
                          id_site: int = 8,
                          year_month: str = "2025-10",
                          target: Union[int, str] = None,
                          timeout_connect: int = 5,
                          timeout_read: int = 45,
                          loop_forever: bool = False,
                          interval_sec: int = 20,
                          stop_when_available: bool = False) -> Optional[Dict[str, Any]]:
    """
    Ambil satu baris untuk tanggal target.
    - Jika loop_forever=False (default): cek sekali, return row/None.
    - Jika loop_forever=True: polling terus sampai dihentikan (Ctrl+C).
        * Jika stop_when_available=True, loop akan berhenti ketika available==True.
        * Jika stop_when_available=False, loop tidak pernah berhenti (kecuali Ctrl+C).
    """
    s = session or build_session(force_ipv4=True)

    def _once() -> Optional[Dict[str, Any]]:
        html = get_kapasitas(session=s, id_site=id_site, year_month=year_month,
                             timeout_connect=timeout_connect, timeout_read=timeout_read)
        rows = parse_kapasitas_rows(html)
        found = next((r for r in rows if _match_target(r, target)), None)
        if not found:
            print(f"{ts(C('[Info]', Fore.YELLOW))} Tanggal {C(str(target), Fore.CYAN)} "
                  f"tidak ditemukan di {C(year_month, Fore.MAGENTA)}.")
            return None
        print(f"{ts(C('[Ditemukan]', Fore.GREEN))} Target: {C(str(target), Fore.CYAN, bright=True)}")
        print(_human_summary(found))
        return found

    if not loop_forever:
        return _once()

    # Loop tanpa henti (kecuali Ctrl+C). Opsional berhenti jika sudah tersedia.
    err_count = 0
    requests_made = 0
    try:
        attempt = 0
        while True:
            attempt += 1
            try:
                row = _once()
                requests_made += 1
                err_count = 0

                # Refresh session tiap 100 permintaan
                if requests_made % 100 == 0:
                    try:
                        s.close()
                    finally:
                        s = build_session(force_ipv4=True)  # rebuild
                        print(f"{ts(C('[Session]', Fore.MAGENTA))} Refresh session (100 requests).")

                if row and stop_when_available and row.get("available"):
                    print(f"{ts(C('[Selesai]', Fore.GREEN))} {C('TERSEDIA', Fore.GREEN, bright=True)} — menghentikan loop.")
                    return row

                # jeda normal
                time.sleep(interval_sec)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                err_count += 1
                extra = min(60, 2 ** err_count)  # backoff maksimal +60s
                wait = interval_sec + extra
                print(f"{ts(C('[Peringatan]', Fore.RED))} Percobaan #{C(str(attempt), Fore.YELLOW)} "
                      f"error: {C(repr(e), Fore.RED)}")
                print(f"{ts(C('[Backoff]', Fore.YELLOW))} tidur {C(str(wait)+'s', Fore.YELLOW)} "
                      f"(error#{C(str(err_count), Fore.YELLOW)}).")
                time.sleep(wait)
                # opsional: refresh session setelah error berturut-turut
                if err_count >= 3:
                    try:
                        s.close()
                    finally:
                        s = build_session(force_ipv4=True)
                        print(f"{ts(C('[Session]', Fore.MAGENTA))} Refresh session (error streak).")

    except KeyboardInterrupt:
        print(f"\n{ts(C('[Stop]', Fore.MAGENTA))} Dihentikan oleh pengguna (Ctrl+C).")
        return None


def wait_until_tanggal_ada(session: Optional[requests.Session] = None,
                           id_site: int = 8,
                           year_month: str = "2025-10",
                           target: Union[int, str] = None,
                           interval_sec: int = 20,
                           max_attempts: int = 9999,
                           timeout_connect: int = 5,
                           timeout_read: int = 45) -> Optional[Dict[str, Any]]:
    """Loop sampai tanggal target MUNCUL di kalender (apa pun statusnya), atau habis attempt."""
    s = session or build_session(force_ipv4=True)
    for attempt in range(1, max_attempts + 1):
        try:
            row = get_kapasitas_by_date(s, id_site=id_site, year_month=year_month, target=target,
                                        timeout_connect=timeout_connect, timeout_read=timeout_read)
            if row:
                print(f"{ts(C('[Ditemukan]', Fore.GREEN))} {C('✅ DITEMUKAN', Fore.GREEN, bright=True)} "
                      f"(percobaan #{C(str(attempt), Fore.YELLOW)} )")
                print(_human_summary(row))
                return row
        except Exception as e:
            print(f"{ts(C('[Peringatan]', Fore.RED))} Percobaan #{C(str(attempt), Fore.YELLOW)} error: {C(repr(e), Fore.RED)}")

        print(f"{ts(C('[Menunggu]', Fore.WHITE, dim=True))} Belum ada di kalender. "
              f"Coba lagi dalam {C(str(interval_sec)+' detik', Fore.YELLOW)} "
              f"(percobaan #{C(str(attempt), Fore.YELLOW)}).")
        time.sleep(interval_sec)

    print(f"{ts(C('[Gagal]', Fore.RED))} Batas percobaan habis, tanggal {C(str(target), Fore.CYAN)} "
          f"belum muncul di {C(year_month, Fore.MAGENTA)}.")
    return None


def wait_until_tanggal_tersedia(session: Optional[requests.Session] = None,
                                id_site: int = 8,
                                year_month: str = "2025-10",
                                target: Union[int, str] = None,
                                interval_sec: int = 20,
                                max_attempts: int = 9999,
                                timeout_connect: int = 5,
                                timeout_read: int = 45) -> Optional[Dict[str, Any]]:
    """Loop sampai tanggal target MUNCUL dan BERSTATUS TERSEDIA (available==True), atau habis attempt."""
    s = session or build_session(force_ipv4=True)
    for attempt in range(1, max_attempts + 1):
        try:
            row = get_kapasitas_by_date(s, id_site=id_site, year_month=year_month, target=target,
                                        timeout_connect=timeout_connect, timeout_read=timeout_read)
            if row and row.get("available"):
                print(f"{ts(C('[Sukses]', Fore.GREEN))} {C('🎉 TERSEDIA!', Fore.GREEN, bright=True)} "
                      f"(percobaan #{C(str(attempt), Fore.YELLOW)})")
                print(_human_summary(row))
                return row
        except Exception as e:
            print(f"{ts(C('[Peringatan]', Fore.RED))} Percobaan #{C(str(attempt), Fore.YELLOW)} error: {C(repr(e), Fore.RED)}")

        print(f"{ts(C('[Menunggu]', Fore.WHITE, dim=True))} Belum tersedia. "
              f"Akan cek lagi dalam {C(str(interval_sec)+' detik', Fore.YELLOW)} "
              f"(percobaan #{C(str(attempt), Fore.YELLOW)}).")
        time.sleep(interval_sec)

    print(f"{ts(C('[Gagal]', Fore.RED))} Batas percobaan habis, "
          f"{C(str(target), Fore.CYAN)} belum tersedia di {C(year_month, Fore.MAGENTA)}.")
    return None


# ======================= ENTRY POINT (CLI) =======================
def _derive_year_month_from_target(target: Union[int, str]) -> Optional[str]:
    """
    Turunkan year_month ('YYYY-MM') dari:
      - ISO 'YYYY-MM-DD' -> 'YYYY-MM'
      - 'D NamaBulan YYYY' -> parse ke ISO -> 'YYYY-MM'
      - angka hari -> None (butuh --year-month)
    """
    if isinstance(target, int):
        return None
    t = str(target).strip()
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return t[:7]
    iso = to_iso_from_tanggal_id(t)
    if iso:
        return iso[:7]
    return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Polling kapasitas Semeru/Bromo by tanggal target.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--site-id", type=int, default=8, help="ID site (default 8 = Semeru)")
    parser.add_argument("--year-month", type=str, default=None, help="Bulan target format YYYY-MM")
    parser.add_argument("--target", required=False, help="Tanggal target: 2025-10-18 / '18 Oktober 2025' / 18")
    parser.add_argument("--loop", action="store_true", help="Loop terus sampai dihentikan")
    parser.add_argument("--stop-when-available", action="store_true", help="Berhenti otomatis jika TERSEDIA")
    parser.add_argument("--interval", type=int, default=20, help="Interval polling (detik)")
    parser.add_argument("--timeout-connect", type=int, default=5, help="Timeout CONNECT (detik)")
    parser.add_argument("--timeout-read", type=int, default=45, help="Timeout READ (detik)")
    parser.add_argument("--ipv4", action="store_true", help="Paksa IPv4 (disarankan di VPS/DC)")

    args = parser.parse_args()

    # Target interaktif jika tidak diberikan
    if args.target is None:
        args.target = input("Masukkan target tanggal (contoh: 2025-10-18 / '18 Oktober 2025' / 18): ").strip()

    # Normalisasi target (int jika digit semua)
    target_val: Union[int, str]
    if str(args.target).isdigit():
        target_val = int(args.target)
    else:
        target_val = args.target

    ym = args.year_month or _derive_year_month_from_target(target_val)
    if ym is None:
        raise SystemExit("ERROR: --year-month wajib diisi jika --target hanya angka hari (contoh: --year-month 2025-10)")

    sess = build_session(force_ipv4=args.ipv4 or True)  # default paksa IPv4 di VPS

    # Jalankan
    get_kapasitas_by_date(
        session=sess,
        id_site=args.site_id,
        year_month=ym,
        target=target_val,
        timeout_connect=args.timeout_connect,
        timeout_read=args.timeout_read,
        loop_forever=args.loop,
        interval_sec=args.interval,
        stop_when_available=args.stop_when_available,
    )
