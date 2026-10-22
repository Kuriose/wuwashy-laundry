# WuWashy Laundry

Aplikasi web layanan laundry berbasis **Django**. Pelanggan bisa memesan penjemputan laundry, memantau pesanan, dan mengumpulkan poin. Admin outlet mengelola pesanan lewat panel khusus.

> Repositori ini dibuat agar rekan tim dapat melihat dan memeriksa hasil pengerjaan. Panduan di bawah menjelaskan cara menjalankan aplikasi secara lokal.

## Fitur

- **Landing page**: beranda, tentang kami, layanan, dan outlet.
- **Booking**: bisa dilakukan tanpa login. Setelah dikirim, pengguna diarahkan ke WhatsApp admin dengan pesan yang sudah terisi.
- **Akun pelanggan (USER)**: daftar di `/signup/`, masuk dengan email dan password. Dashboard menampilkan ringkasan, daftar pesanan, serta poin dan hadiah.
- **Panel admin (ADMIN)**: dashboard statistik pesanan, daftar pesanan terbaru, dan halaman detail untuk mengubah status pesanan.
- **Sistem poin**: setiap Rp1.000 total pesanan = 1 poin. Poin masuk otomatis saat status pesanan menjadi `selesai` dan hanya dicatat satu kali per pesanan.
- **Akun saya** (`/akun/`): pelanggan mengubah nama, nama panggilan, WhatsApp, dan tanggal lahir. Email hanya bisa dibaca karena dipakai untuk login.
- **Alamat saya** (`/alamat/`): pelanggan menyimpan beberapa alamat (label, penerima, WhatsApp, kecamatan, kota, kode pos, catatan kurir). Satu alamat menjadi alamat utama, yang otomatis mengisi form booking dan tampil di kartu alamat Beranda, Pesanan saya, dan Akun saya. Daftar kota dan kecamatan ada di `WILAYAH` (`laundry/services.py`).
- **Riwayat pesanan** (`/riwayat/`): ringkasan (pesanan selesai, total transaksi, poin didapat), filter (nomor/layanan, periode, layanan), pembagian halaman, tombol Pesan lagi. Logikanya ada di `laundry/riwayat.py`.
- **Pencarian pesanan**: kolom cari di header dashboard pelanggan (`/cari/`) menemukan pesanan milik akun itu, semua status.
- **Tagihan di panel admin**: admin mengisi berat hasil timbang dan koreksi harga di halaman detail pesanan. Tagihan dikunci setelah poin diberikan.
- **Notifikasi** (`/notifikasi/`): setiap pesanan baru, perubahan status, poin masuk, dan hadiah yang sudah bisa ditukar otomatis membuat `Notifikasi` untuk pemilik akun. Halamannya punya filter (Semua, Belum dibaca, Pesanan, Poin & hadiah), pembagian halaman, tombol Tandai semua dibaca, dan titik biru di ikon lonceng header selama ada yang belum dibaca. Pembuatnya ada di `laundry/notifikasi.py` (tiap kelas menentukan ikon dan tautannya sendiri), logika halamannya di `laundry/kotak_notifikasi.py`.
- **Penautan pesanan ke akun**: akun yang sedang login diprioritaskan, lalu nomor WhatsApp yang cocok tepat satu akun, dan terakhir dicatat sebagai tamu.

## Teknologi

| Komponen | Keterangan |
|----------|------------|
| Bahasa | Python |
| Framework | Django 6.x |
| Database | SQLite (otomatis dibuat, tidak perlu instalasi tambahan) |
| Tampilan | Template Django, CSS, dan JavaScript bawaan (tanpa Node.js) |

## Prasyarat

Pastikan perangkat sudah memiliki:

- **Python 3.12 atau lebih baru**. Cek dengan `python --version` (di macOS/Linux bisa jadi `python3 --version`).
- **Git**.
- Koneksi internet saat instalasi dan saat membuka aplikasi. Font tampilan dimuat dari Google Fonts, sehingga tanpa internet font akan memakai font bawaan browser.

## Cara menjalankan secara lokal

### 1. Clone repositori

```bash
git clone https://github.com/<username>/<nama-repo>.git
cd <nama-repo>
```

> Ganti `<username>` dan `<nama-repo>` sesuai alamat repositori. Setelah `cd`, pastikan berada di folder yang berisi file `manage.py`. Jika `manage.py` ada di dalam subfolder (misalnya `wabby/`), masuk dulu ke folder tersebut.

### 2. Buat dan aktifkan virtual environment

Virtual environment menjaga paket proyek ini tidak bercampur dengan proyek lain.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Jika muncul galat soal *execution policy*, jalankan sekali: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, lalu ulangi perintah aktivasi. Pengguna Command Prompt (CMD) cukup memakai `.venv\Scripts\activate.bat`.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Jika berhasil, terminal menampilkan awalan `(.venv)`.

### 3. Pasang dependensi

```bash
pip install -r requirements.txt
```

### 4. Siapkan database

```bash
python manage.py migrate
```

Perintah ini membuat file `db.sqlite3` di folder proyek.

### 5. Isi data contoh

```bash
python manage.py seed_users      # membuat 1 akun pelanggan dan 1 akun admin untuk uji coba
python manage.py seed_pesanan    # opsional: 60 pesanan contoh agar dashboard admin terisi
python manage.py seed_demo_pesanan   # opsional: 5 pesanan contoh (satu per tahap) untuk akun uji; lihat bar progres di Beranda
```

Perintah seed ini hanya untuk pengembangan. `seed_demo_pesanan` aman dijalankan berulang kali (contoh lama diganti), mendukung `--status dijemput` untuk satu pesanan saja, dan `--hapus` untuk membersihkannya. `seed_users` aman dijalankan berulang kali, sedangkan `seed_pesanan` menolak berjalan jika sudah ada pesanan, kecuali ditambah opsi `--force`.

### 6. Jalankan server

```bash
python manage.py runserver
```

Buka **http://127.0.0.1:8000/** di browser. Untuk menghentikan server, tekan `Ctrl + C` di terminal.

## Akun uji

Dibuat oleh `python manage.py seed_users`. Login memakai **email** dan password:

| Role  | Email               | Password            | Setelah login masuk ke |
|-------|---------------------|---------------------|------------------------|
| USER  | `nadia@example.com` | `wuwashy-user-123`  | `/dashboard/`          |
| ADMIN | `admin@example.com` | `wuwashy-admin-123` | `/panel/`              |

> Akun ini hanya untuk pengembangan lokal. Jangan dipakai di server produksi.

Untuk mengembalikan password akun uji ke nilai bawaan: `python manage.py seed_users --reset-password`.

## Daftar halaman

| URL | Keterangan | Akses |
|-----|------------|-------|
| `/` | Beranda | Publik |
| `/about/`, `/services/` | Mengarah ke bagian terkait di beranda | Publik |
| `/booking/` | Form pemesanan (lanjut ke WhatsApp admin) | Publik |
| `/signup/` | Daftar akun pelanggan | Publik |
| `/login/` | Masuk (pelanggan dan admin) | Publik |
| `/dashboard/` | Beranda pelanggan | USER |
| `/akun/` | Akun saya (nama, WhatsApp, tanggal lahir) | USER |
| `/alamat/` | Alamat saya (banyak alamat: tambah, ubah, jadikan utama, hapus) | USER |
| `/pesanan/` | Pesanan saya | USER |
| `/cari/?q=` | Hasil pencarian nomor pesanan | USER |
| `/riwayat/` | Riwayat pesanan (selesai/dibatalkan, filter, halaman) | USER |
| `/notifikasi/` | Notifikasi pesanan, poin, dan hadiah (filter, tandai dibaca) | USER |
| `/poin/` | Poin dan hadiah | USER |
| `/panel/` | Dashboard admin | ADMIN |
| `/panel/pesanan/<id>/` | Detail pesanan dan ubah status | ADMIN |
| `/admin/` | Django Admin bawaan (kelola data mentah) | Superuser |

Pengunjung yang belum login lalu membuka halaman USER atau ADMIN akan diarahkan ke `/login/`. Akun USER yang membuka `/panel/` mendapat galat 403.

## Struktur proyek

```
.
├── manage.py
├── requirements.txt
├── config/                  # pengaturan proyek (settings, urls, wsgi/asgi)
└── laundry/                 # aplikasi utama
    ├── models.py            # Booking, Profile, Alamat, PoinLog, Notifikasi
    ├── notifikasi.py        # pembuat notifikasi (kelas abstrak + subkelas per status, poin, hadiah)
    ├── kotak_notifikasi.py  # data halaman Notifikasi (filter, hitungan, pembagian halaman)
    ├── views.py, urls.py    # halaman dan routing
    ├── forms.py             # form booking, login, signup, akun saya, dan tagihan
    ├── poin.py, services.py # logika poin, katalog layanan, dan hadiah
    ├── panel.py             # data ringkasan untuk panel admin
    ├── signals.py           # pemberian poin otomatis saat pesanan selesai
    ├── templates/laundry/   # template HTML
    ├── static/laundry/      # CSS dan gambar
    ├── management/commands/ # seed_users, seed_pesanan
    ├── migrations/
    └── tests.py
```

## Konfigurasi yang bisa disesuaikan

Dibaca dari environment variable atau file `.env` (contoh: `.env.example`), dengan nilai bawaan untuk pengembangan lokal. Daftar yang paling penting ada di `config/settings.py`:

| Pengaturan | Fungsi |
|------------|--------|
| `WHATSAPP_ADMIN` | Nomor WhatsApp tujuan booking, format `62812xxxx` tanpa tanda `+` |
| `OUTLET_NAMA`, `OUTLET_KOTA` | Identitas outlet di sidebar panel admin |

Daftar layanan dan harga ada di `SERVICES`, sedangkan katalog hadiah di `HADIAH`, keduanya dalam `laundry/services.py`. Penukaran voucher hadiah belum dibuat.

## Menjalankan tes

```bash
python manage.py test
```

> Semua tes lulus (208 tes). Tes fitur akun, pencarian, tagihan, notifikasi (data), dan konfigurasi produksi ada di `laundry/tests_akun.py`; tes halaman Notifikasi di `laundry/tests_notifikasi.py`.

## Kolaborasi tim dan mencegah merge conflict

*Merge conflict* terjadi ketika dua orang mengubah baris yang sama (atau berdekatan) di file yang sama, lalu Git tidak tahu versi mana yang dipakai. Mencegahnya jauh lebih mudah daripada memperbaikinya. Mohon seluruh anggota tim mengikuti aturan berikut.

### Aturan dasar

1. **Jangan bekerja langsung di `main`.** Satu tugas = satu branch. Gabungkan ke `main` lewat Pull Request (PR).
2. **Selalu mulai dari `main` yang terbaru.** Sebelum membuat branch baru, ambil dulu pembaruan terakhir.
3. **Sinkronkan sering-sering.** Tarik pembaruan `main` ke branch Anda minimal sekali sehari, jangan menunggu berminggu-minggu.
4. **Buat perubahan kecil dan fokus.** Satu PR sebaiknya hanya mengerjakan satu hal. Perubahan besar yang menyentuh banyak file hampir pasti bentrok.
5. **Bagi pekerjaan per file/fitur.** Sebelum mulai, beri tahu tim file apa yang akan Anda ubah, terutama file rawan bentrok (lihat tabel di bawah).
6. **Jangan memformat ulang file yang bukan bagian tugas Anda.** Mengubah indentasi atau merapikan seluruh file membuat Git menganggap semua barisnya berubah.
7. **Pastikan `.gitignore` dipatuhi.** Jangan pernah meng-commit `db.sqlite3`, `.venv/`, `__pycache__/`, atau file `.env`. Database lokal setiap orang berbeda, dan file biner seperti itu tidak bisa digabung.

### Alur kerja harian

```bash
# 1. Ambil kondisi terbaru
git checkout main
git pull origin main

# 2. Buat branch untuk tugas Anda
git checkout -b fitur/nama-singkat-tugas

# 3. Kerjakan, lalu commit secara berkala
git add <file-yang-diubah>
git commit -m "Pesan commit yang jelas"

# 4. Sebelum push, tarik pembaruan main ke branch Anda
git fetch origin
git merge origin/main        # atau: git rebase origin/main (sepakati satu cara dalam tim)

# 5. Jalankan aplikasi dan tes, pastikan masih berjalan
python manage.py migrate
python manage.py test

# 6. Kirim branch, lalu buat Pull Request di GitHub
git push origin fitur/nama-singkat-tugas
```

Gunakan awalan nama branch yang seragam, misalnya `fitur/...`, `perbaikan/...`, atau `dokumen/...`. Hindari `git add .` secara membabi buta; periksa dulu dengan `git status` agar tidak ikut meng-commit file yang tidak dimaksud.

### File yang rawan bentrok di proyek ini

| File / folder | Alasan rawan | Saran |
|---------------|--------------|-------|
| `laundry/migrations/` | Dua orang yang sama-sama mengubah model akan membuat migrasi bernomor sama (misalnya dua file `0005_...`) | Lihat bagian "Konflik migrasi Django" di bawah |
| `laundry/models.py` | Semua perubahan struktur data berkumpul di sini | Beri tahu tim sebelum mengubah model; selesaikan dan gabungkan secepatnya |
| `laundry/views.py`, `laundry/urls.py` | Setiap halaman baru menambah baris di file yang sama | Tambahkan di bagian yang berbeda; merge lebih sering |
| `laundry/tests.py` | File sangat panjang (sekitar 36 KB) dan semua orang menambah tes di sana | Tambahkan tes baru di akhir kelas/bagian milik fitur Anda, jangan menyisipkan di tengah |
| `config/settings.py` | Pengaturan global yang dipakai bersama | Ubah hanya bila perlu, dan jangan commit pengaturan khusus mesin Anda |
| `laundry/static/laundry/*.css` | File CSS besar (`dashboard.css`, `panel.css`, `style.css`) | Kerjakan bagian halaman yang berbeda, dan jangan merapikan ulang seluruh file |
| `laundry/templates/laundry/*_base.html` | Template induk dipakai banyak halaman | Koordinasikan sebelum mengubah |

### Konflik migrasi Django

Ini sumber konflik paling khas di proyek Django. Jika branch A dan branch B sama-sama menjalankan `makemigrations` dari kondisi yang sama, keduanya menghasilkan migrasi dengan nomor berurutan yang sama. Setelah digabung, Django akan menolak berjalan dengan pesan *"Conflicting migrations detected"*.

Cara mencegah dan menanganinya:

- **Jangan mengedit migrasi yang sudah di-merge ke `main`.** Jika perlu perubahan lagi, buat migrasi baru.
- **Selalu tarik `main` terbaru sebelum menjalankan `makemigrations`**, agar nomor migrasi Anda melanjutkan yang terakhir.
- **Commit file migrasi bersama perubahan `models.py`-nya** dalam PR yang sama.
- **Jangan hapus lalu buat ulang migrasi** hanya untuk menghindari konflik.
- Jika konflik sudah terjadi setelah menarik `main`, jalankan:

  ```bash
  python manage.py makemigrations --merge
  python manage.py migrate
  ```

  Perintah ini membuat satu migrasi penggabung. Commit file tersebut dalam branch Anda.
- Jika database lokal Anda menjadi aneh karena migrasi, cara paling aman adalah mengulang dari awal: hapus `db.sqlite3`, lalu jalankan `migrate` dan `seed_users` lagi (lihat bagian "Masalah umum").

### Jika terjadi konflik

Git akan menandai file bermasalah dengan penanda seperti ini:

```
<<<<<<< HEAD
versi di branch Anda
=======
versi dari main
>>>>>>> origin/main
```

Langkah penanganannya:

1. Jalankan `git status` untuk melihat file yang konflik (ditandai *both modified*).
2. Buka file tersebut, putuskan isi akhir yang benar (bisa gabungan keduanya), lalu **hapus ketiga baris penanda** (`<<<<<<<`, `=======`, `>>>>>>>`).
3. Jika ragu, tanyakan kepada rekan yang mengubah bagian itu. Jangan asal memilih salah satu versi.
4. Jalankan `python manage.py test` dan buka aplikasi untuk memastikan semuanya masih berfungsi.
5. Selesaikan:

   ```bash
   git add <file-yang-sudah-diperbaiki>
   git commit        # untuk merge; jika memakai rebase: git rebase --continue
   ```

6. Ingin membatalkan proses merge dan kembali ke kondisi awal? Jalankan `git merge --abort` (atau `git rebase --abort`).

### Saran pengaturan repositori (untuk pemilik repo)

- Aktifkan **branch protection** untuk `main` di GitHub (*Settings > Branches*): wajib lewat Pull Request dan minimal satu orang me-review.
- Sepakati satu cara menyinkronkan branch (*merge* atau *rebase*) agar riwayat tidak campur aduk.
- Jika tim memakai Windows dan macOS/Linux bersamaan, perbedaan akhir baris (CRLF/LF) bisa membuat seluruh file terlihat berubah. Atur sekali per perangkat: Windows `git config --global core.autocrlf true`, macOS/Linux `git config --global core.autocrlf input`.

## Masalah umum

| Gejala | Solusi |
|--------|--------|
| `python` atau `pip` tidak dikenali | Di macOS/Linux coba `python3` dan `pip3`. Di Windows, pasang ulang Python dan centang *Add Python to PATH*. |
| `No module named django` | Virtual environment belum aktif atau dependensi belum terpasang. Aktifkan `.venv`, lalu jalankan `pip install -r requirements.txt`. |
| `Port is already in use` | Jalankan di port lain: `python manage.py runserver 8001`. |
| Muncul peringatan migrasi belum diterapkan | Jalankan `python manage.py migrate`. |
| Ingin mengulang database dari awal | Hentikan server, hapus file `db.sqlite3`, lalu ulangi langkah 4 dan 5. |
| Tampilan tanpa gambar/CSS | Pastikan server dijalankan dengan `runserver` dari folder yang berisi `manage.py`. |

## Deploy ke server

Tanpa file `.env`, aplikasi berjalan dalam mode pengembangan (`DEBUG` aktif). Untuk server:

1. Pasang dependensi dan salin pengaturan:

   ```bash
   pip install -r requirements.txt
   cp .env.example .env        # lalu isi DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, dan DJANGO_CSRF_TRUSTED_ORIGINS
   ```

2. Siapkan database dan file static:

   ```bash
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```

3. Jalankan dengan gunicorn (file `Procfile` sudah tersedia untuk Railway, Render, atau Heroku):

   ```bash
   gunicorn config.wsgi
   ```

Catatan:

- Dengan `DJANGO_DEBUG=False`, aplikasi menolak berjalan bila `DJANGO_SECRET_KEY` kosong, dan cookie otomatis dibuat aman (HTTPS).
- File static dilayani oleh WhiteNoise, tanpa perlu Nginx.
- SQLite cukup untuk uji coba. Untuk produksi isi `DATABASE_URL` (mis. PostgreSQL) dan pasang `psycopg2-binary`.
- Jangan pakai akun dari `seed_users` di server produksi.
