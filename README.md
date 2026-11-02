# Template Video "Dilema Malam" (9:16, tanpa narator)

Gaya video: ilustrasi malam yang hangat, jam di pojok kiri-atas, teks per kata
dengan kata kunci berwarna hijau, label pembicara untuk dialog, dan kartu
**"APA PILIHANMU?"** dengan dua pilihan di akhir. **Tidak ada suara narator**:
audio hanya suasana ruangan yang sunyi, atau musik latar kalau kamu menaruhnya
di `assets/music/`.

## Cara kerja (alurnya)

1. Kamu kirim **judul** ke Claude.
2. Claude menulis file cerita `story/<nama>.json` (scene, teks, pilihan) dan
   prompt gambar per scene.
3. Gambar scene dibuat dengan generator gambar favoritmu memakai prompt itu,
   lalu simpan di `assets/scenes/` (scene01.png, scene02.png, ...).
4. Render video:

```bash
pip install -r requirements.txt     # sekali saja (butuh ffmpeg terpasang)
python render.py story/bajaj-episode-1.json          # 720x1280
python render.py story/bajaj-episode-1.json --hd     # 1080x1920
python render.py story/bajaj-episode-1.json --preview  # cek tata letak saja
python render.py story/bajaj-episode-1.json --prompts  # prompt gambar per scene
```

Hasil ada di `output/`. Kalau gambar scene belum ada, render tetap jalan
dengan latar sementara (gradasi gelap), jadi tata letak bisa dicek dulu.

## Menghubungkan ke GitHub

1. Buat repo baru di GitHub, lalu unggah seluruh isi folder ini.
2. Buka tab **Actions** > **Render video** > **Run workflow**, isi file cerita.
3. Setelah selesai, unduh MP4 dari bagian **Artifacts**.
Setiap kali kamu mengunggah/ubah file di `story/*.json`, video dirender otomatis.

## Format file cerita

```json
{
  "title": "Judul",
  "art_style": "gaya gambar yang konsisten untuk semua scene",
  "hud": { "label": "Malam Pertama", "time": "21:47", "subtitle": "Seri · Episode 1" },
  "scenes": [
    {
      "mood": "warm",                 // warm | night | dark (latar sementara)
      "image": "scene01.png",         // file di assets/scenes/
      "visual": "deskripsi gambar untuk prompt",
      "captions": [
        "BAYANGKAN",
        "KOTA INI *KEHABISAN* AIR",   // *...* = kata hijau
        { "t": "“SEDIKIT *SAJA*”", "speaker": "Tetangga", "d": 2.2 }
      ]
    }
  ],
  "choice": { "question": "Apa pilihanmu?", "option_a": "...", "option_b": "...", "cta": "Komentar di bawah" }
}
```

Tips: 2-3 kata per baris teks, durasi otomatis (atur di `config.json`:
`seconds_per_word`, `min_chunk_seconds`). Warna, ukuran teks, dan posisi
juga ada di `config.json`.
