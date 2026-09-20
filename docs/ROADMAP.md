# ROADMAP — dari MVP people counter ke platform AI CCTV subscription

Sumber: `Riset_Perangkat_dan_Stack_AI_CCTV_Subscription.pdf` (garis besar tujuan) + keadaan repo per 2026-06 (`docs/STATUS.md`).
Prinsip: **usability dulu, paket subscription belakangan** (pilihan pemilik produk, 2026-06). Setiap fase harus bisa dipakai pemilik toko tanpa bantuan operator lewat CLI.

## Yang sudah ada (baseline)
Edge agent (deteksi + tracking + hitung garis, buffer SQLite, sender idempoten, heartbeat) · Backend FastAPI (multi-tenant, device key, JWT login, ringkasan harian/jam, daftar perangkat) · Dashboard (ringkasan pengunjung, halaman Perangkat, login). Provisioning tenant/toko/perangkat/pengguna **hanya lewat CLI** → hambatan usability terbesar.

## Fase 1 — Manajemen mandiri lewat UI + peran pengguna  ← **SELESAI (2026-06, ADR-024)**
Tujuan: operator/pemilik toko bisa mendaftarkan toko, perangkat (dapat API key), kamera, dan pengguna tanpa CLI.
- Peran: **platform admin** (kita), **owner** tenant (kelola), **staff** (lihat saja). Admin di-seed dari env (`ADMIN_EMAIL`/`ADMIN_PASSWORD`).
- API tulis: tenant (admin), toko, perangkat (+ API key tampil sekali, rotasi kunci, nonaktifkan), kamera, anggota tenant (buat pengguna, ubah peran, reset sandi, cabut akses), ganti sandi sendiri.
- UI: halaman **Pengaturan** (`/pengaturan`): Toko & perangkat, Pengguna, Tenant (admin), Akun. Dashboard kosong mengarah ke Pengaturan, bukan ke perintah CLI.
- Uji: isolasi tenant untuk semua endpoint tulis (owner A tidak bisa menyentuh B), staff ditolak 403, kunci perangkat lama mati setelah rotasi.

## Fase 2 — Laporan & perbandingan (usability data)  ← **SELESAI (2026-06)**
- Rentang tanggal (7/30 hari, kustom ≤ 92 hari), grafik harian per toko, perbandingan vs periode sebelumnya (%), hari & jam tersibuk, ekspor CSV — halaman `/laporan`.
- Multi-toko: tabel semua toko sekali lihat (masuk/keluar hari ini, vs kemarin, rata-rata 7 hari, event terakhir, perangkat bermasalah).
- Ditunda: ringkasan email harian/mingguan (butuh penyedia email — belum dipilih).

## Fase 3 — Notifikasi & kesehatan operasional  ← **SELESAI sebagian (2026-06, ADR-026/027/028)**
- ✅ Jam operasional toko (ADR-026) — laporan & flag perangkat mengabaikan jam tutup.
- ✅ Riwayat heartbeat 24 jam per perangkat (ADR-027) — timeline di halaman Perangkat.
- ✅ Aturan alert per toko (tanpa heartbeat > N mnt, kamera terputus > N mnt, buffer penuh ≥ N, tidak ada event pada jam buka) + pusat notifikasi in-app `/notifikasi` dengan badge di nav, tandai dilihat, riwayat (ADR-028).
- ✅ Kanal Telegram per toko (ADR-029) — token bot di server, chat_id per toko, pesan uji; email/WhatsApp masih ditunda.
- ✅ Konfigurasi garis dari server + snapshot kamera + hot-reload edge (ADR-030). ⏳ Pembaruan agent terkontrol (versi, rollout).

## Fase 4 — Analitik zona: okupansi, dwell, antrean (fitur A/B dokumen)  ← **irisan pertama SELESAI (2026-06, ADR-031)**
- ✅ Zona poligon per kamera (editor di Pengaturan), kontrak `zone_sample_v1`, okupansi per jam, panel okupansi zona di dashboard.
- ⏳ Dwell time per track, antrean (zona khusus + estimasi waktu tunggu), retensi/pre-agregasi sampel.
- Edge: zona poligon per kamera, hitung orang di zona per interval, dwell time per track; antrean = zona khusus + estimasi waktu tunggu.
- Kontrak event baru (`zone_sample_v1`), agregasi per 5 menit, dashboard heatmap zona sederhana + KPI antrean.
- Uji penerimaan lapangan sesuai dokumen (hitung pintu vs manual, panjang antrean, waktu tunggu).

## Fase 5 — Subscription & billing (ditunda sesuai keputusan)
- Paket per toko (fitur & retensi), status langganan (aktif/tenggang/nonaktif) manual oleh admin dulu; gateway (Midtrans/Xendit) setelah paket final.
- Konversi penjualan (POS) dan fitur C (OSA/rak, OCR label, LLM ringkasan) = R&D, setelah Fase 4 stabil.

## Lintas fase
- PostgreSQL via Compose belum pernah dijalankan (tidak ada Docker di workspace) → tes pertama di mesin Anda.
- Angka akurasi lapangan belum ada (butuh kamera pintu + tally manual, `docs/PILOT_RUNBOOK.md`).
