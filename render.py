#!/usr/bin/env python3
"""
Template video "Dilema Malam" (vertikal 9:16, tanpa narator).

Pakai:
    python render.py story/bajaj-episode-1.json            # render mp4 ke output/
    python render.py story/bajaj-episode-1.json --hd       # 1080x1920
    python render.py story/bajaj-episode-1.json --preview  # contact sheet PNG saja (cepat)
    python render.py story/bajaj-episode-1.json --prompts  # prompt gambar per scene

Hanya butuh: Python 3, Pillow, numpy, dan ffmpeg.
"""
import argparse
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
ZOOM_PAD = 1.15          # gambar latar dibuat 15% lebih besar untuk gerakan kamera
DIP = 0.25               # detik fade-hitam di pergantian scene
DEFAULT_ART_STYLE = (
    "2D flat vector cartoon illustration, simple stick-like characters with round heads, "
    "warm lamplight interior at night, deep brown and orange palette, soft vignette, "
    "cinematic, moody, no text, no watermark"
)


# --------------------------------------------------------------------------- util
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_font(cfg, size):
    candidates = [
        ROOT / cfg.get("font", ""),
        ROOT / "assets/fonts/Poppins-Bold.ttf",
        Path("/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for p in candidates:
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def parse_marked(text):
    """'KAMU *SEGERA* PERGI' -> [(kata, highlight)]; tanda baca murni menempel ke kata sebelumnya."""
    words = []
    for seg in re.split(r"(\*[^*]+\*)", text):
        if not seg:
            continue
        hl = len(seg) > 2 and seg.startswith("*") and seg.endswith("*")
        if hl:
            seg = seg[1:-1]
        starts_space = seg[:1].isspace()
        for i, w in enumerate(seg.split()):
            if i == 0 and not starts_space and words and re.fullmatch(r"[\W_]+", w):
                words[-1] = (words[-1][0] + w, words[-1][1])
            else:
                words.append((w, hl))
    return words


def alpha_scale(layer, k):
    if k >= 0.999:
        return layer
    r, g, b, a = layer.split()
    a = a.point(lambda v: int(v * max(0.0, k)))
    return Image.merge("RGBA", (r, g, b, a))


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


# --------------------------------------------------------------- latar prosedural
def procedural_bg(mood, idx, size):
    """Latar cadangan bila tidak ada gambar scene. Ganti dengan ilustrasi sendiri di assets/scenes/."""
    w, h = size
    rng = random.Random(idx * 7 + 3)
    palettes = {
        "warm": ((36, 20, 13), (96, 54, 26)),
        "night": ((7, 12, 28), (28, 36, 62)),
        "dark": ((5, 5, 7), (20, 17, 21)),
    }
    top, bot = (np.array(c, dtype=np.float32) for c in palettes.get(mood, palettes["warm"]))
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    base = top[None, None, :] * (1 - yy[..., None]) + bot[None, None, :] * yy[..., None]
    base = np.broadcast_to(base, (h, w, 3)).copy()

    def glow(cx, cy, sx, sy, color, k):
        g = np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
        return g[..., None] * np.array(color, dtype=np.float32) * k

    if mood == "warm":
        base += glow(0.82, 0.34, 0.10, 0.12, (255, 150, 60), 0.9)
        base += glow(rng.uniform(0.2, 0.45), 0.52, 0.14, 0.10, (255, 190, 90), 0.8)
        base += glow(0.5, 0.78, 0.6, 0.18, (200, 110, 40), 0.35)
    elif mood == "night":
        base += glow(rng.uniform(0.55, 0.8), 0.18, 0.07, 0.05, (190, 210, 255), 0.9)
        base += glow(0.5, 0.45, 0.7, 0.25, (60, 70, 120), 0.35)
    else:
        base += glow(0.5, 0.5, 0.35, 0.25, (60, 45, 40), 0.5)

    base += np.random.default_rng(idx + 11).normal(0, 2.5, base.shape).astype(np.float32)
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)

    if mood == "warm":
        d.rectangle([w * 0.08, h * 0.14, w * 0.30, h * 0.60], fill=(52, 28, 18))          # pintu
        d.rectangle([w * 0.70, h * 0.22, w * 0.94, h * 0.44], fill=(255, 170, 80))        # jendela
        d.rectangle([0, h * 0.70, w, h], fill=(120, 64, 28))                              # meja
        d.rectangle([0, h * 0.70, w, h * 0.715], fill=(170, 96, 40))
    elif mood == "night":
        x = 0
        while x < w:
            bw = rng.randint(int(w * 0.08), int(w * 0.18))
            bh = rng.randint(int(h * 0.12), int(h * 0.30))
            d.rectangle([x, h * 0.72 - bh, x + bw, h], fill=(10, 13, 24))
            for _ in range(rng.randint(1, 4)):
                wx, wy = x + rng.randint(4, max(5, bw - 14)), h * 0.72 - bh + rng.randint(8, max(9, bh - 20))
                if rng.random() < 0.6:
                    d.rectangle([wx, wy, wx + 9, wy + 13], fill=(255, 176, 88))
            x += bw + rng.randint(0, 8)
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    return img


def cover_fit(img, size):
    tw, th = size
    s = max(tw / img.width, th / img.height)
    img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    l, t = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((l, t, l + tw, t + th))


# ------------------------------------------------------------------------ renderer
class Renderer:
    def __init__(self, story, cfg, size):
        self.story, self.cfg = story, cfg
        self.W, self.H = size
        self.fps = cfg["fps"]
        self.col = {k: hex_rgb(v) for k, v in cfg["colors"].items()}
        self.black = Image.new("RGB", size, (0, 0, 0))
        self.vig = self._vignette()
        self._build_timeline()
        self._build_hud()
        self._build_end_card()

    # ---- layout dasar
    def _vignette(self):
        yy = np.linspace(-1, 1, self.H, dtype=np.float32)[:, None]
        xx = np.linspace(-1, 1, self.W, dtype=np.float32)[None, :]
        r = np.sqrt(xx ** 2 * 0.9 + yy ** 2 * 0.7)
        a = np.clip((r - 0.45) * 1.15, 0, 0.85) * 255
        return Image.fromarray(a.astype(np.uint8), "L")

    def _load_bg(self, sc, idx):
        pad = (int(self.W * ZOOM_PAD), int(self.H * ZOOM_PAD))
        name = sc.get("image")
        if name:
            p = ROOT / "assets/scenes" / name
            if p.is_file():
                return cover_fit(Image.open(p).convert("RGB"), pad)
            print(f"  ! gambar '{name}' tidak ada, pakai latar cadangan (scene {idx + 1})")
        return procedural_bg(sc.get("mood", "warm"), idx, pad)

    def _build_timeline(self):
        c = self.cfg
        self.scenes, t = [], 0.0
        for i, sc in enumerate(self.story["scenes"]):
            chunks, ct = [], 0.0
            for ch in sc["captions"]:
                if isinstance(ch, str):
                    ch = {"t": ch}
                words = parse_marked(ch["t"].upper())
                d = ch.get("d", max(c["min_chunk_seconds"], len(words) * c["seconds_per_word"]))
                chunks.append({"start": ct, "dur": d, "layer": self._caption_layer(words, ch.get("speaker"))})
                ct += d
            self.scenes.append({"start": t, "dur": ct, "chunks": chunks, "bg": self._load_bg(sc, i),
                                "dir": 1 if i % 2 == 0 else -1})
            t += ct
        self.end_start = t
        self.total = t + c["end_card_seconds"]

    # ---- caption
    def _caption_layer(self, words, speaker=None):
        W = self.W
        fsize = int(W * self.cfg["caption_size"])
        font = load_font(self.cfg, fsize)
        stroke = max(3, int(fsize * 0.10))
        maxw = W * 0.86
        lines, cur = [], []
        for w, hl in words:
            trial = cur + [(w, hl)]
            if font.getlength(" ".join(x for x, _ in trial)) > maxw and cur:
                lines.append(cur)
                cur = [(w, hl)]
            else:
                cur = trial
        if cur:
            lines.append(cur)

        lh = int(fsize * 1.28)
        tag_h = int(fsize * 0.95) if speaker else 0
        pad = stroke + 6
        layer = Image.new("RGBA", (W, lh * len(lines) + tag_h + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)

        if speaker:
            tf = load_font(self.cfg, int(fsize * 0.40))
            label = speaker.upper()
            tw = tf.getlength(label)
            bw, bh = int(tw + fsize * 0.5), int(fsize * 0.62)
            x0, y0 = (W - bw) // 2, pad
            d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=bh // 4, fill=self.col["amber"])
            d.text((W / 2, y0 + bh / 2), label, font=tf, fill=(30, 18, 8), anchor="mm")

        y = pad + tag_h
        for line in lines:
            total = font.getlength(" ".join(x for x, _ in line))
            x = (W - total) / 2
            for w, hl in line:
                fill = self.col["highlight"] if hl else self.col["text"]
                d.text((x, y), w, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
                x += font.getlength(w + " ")
            y += lh
        return layer

    # ---- HUD kiri-atas
    def _build_hud(self):
        self.hud = None
        h = self.story.get("hud")
        if not h:
            return
        W = self.W
        L = Image.new("RGBA", (int(W * 0.6), int(W * 0.24)), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        small, big = load_font(self.cfg, int(W * 0.027)), load_font(self.cfg, int(W * 0.078))
        r = int(W * 0.007)
        d.ellipse([2, 8 - r + 4, 2 + 2 * r, 8 + r + 4], fill=self.col["red"])
        x = 2 + 2 * r + 8
        for ch in h.get("label", "").upper():
            d.text((x, 4), ch, font=small, fill=self.col["red"])
            x += small.getlength(ch) + 2
        d.text((0, int(W * 0.04)), h.get("time", ""), font=big, fill=self.col["text"])
        x = 0
        for ch in h.get("subtitle", "").upper():
            d.text((x, int(W * 0.145)), ch, font=small, fill=self.col["muted"])
            x += small.getlength(ch) + 1.5
        self.hud = L

    # ---- kartu pilihan
    def _pill(self, text, color):
        W = self.W
        font = load_font(self.cfg, int(W * 0.036))
        pw, ph = int(W * 0.64), int(self.H * 0.052)
        m = 4
        L = Image.new("RGBA", (pw + m * 2, ph + m * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        d.rounded_rectangle([m, m, m + pw, m + ph], radius=ph // 2, fill=(*color, 46), outline=color, width=3)
        d.text((m + pw / 2, m + ph / 2), text.upper(), font=font, fill=color, anchor="mm")
        return L

    def _build_end_card(self):
        ch = self.story.get("choice", {})
        W, H = self.W, self.H
        last = self.scenes[-1]
        bg = self._kb(last, last["dur"])
        bg = bg.filter(ImageFilter.GaussianBlur(max(2, W // 140)))
        bg = Image.blend(self.black, bg, 0.42)
        bg.paste((0, 0, 0), mask=self.vig)
        self.end_bg = bg

        qf = load_font(self.cfg, int(W * 0.092))
        q = Image.new("RGBA", (W, int(W * 0.14)), (0, 0, 0, 0))
        ImageDraw.Draw(q).text((W / 2, q.height / 2), ch.get("question", "APA PILIHANMU?").upper(), font=qf,
                               fill=self.col["text"], stroke_width=3, stroke_fill=(0, 0, 0), anchor="mm")
        self.end_q = q
        self.end_a = self._pill(ch.get("option_a", "OPSI A"), self.col["red"])
        self.end_b = self._pill(ch.get("option_b", "OPSI B"), self.col["cyan"])
        cf = load_font(self.cfg, int(W * 0.024))
        c = Image.new("RGBA", (W, int(W * 0.06)), (0, 0, 0, 0))
        ImageDraw.Draw(c).text((W / 2, c.height / 2), ch.get("cta", "KOMENTAR DI BAWAH").upper(), font=cf,
                               fill=self.col["muted"], anchor="mm")
        self.end_cta = c

    # ---- gerakan kamera
    def _kb(self, sc, lt):
        bg = sc["bg"]
        p = min(1.0, max(0.0, lt / max(sc["dur"], 0.01)))
        zoom = 1.0 + 0.10 * p
        cw, ch = bg.width / zoom, bg.height / zoom
        fx = 0.5 + sc["dir"] * 0.25 * (p - 0.5) * 2
        x0, y0 = (bg.width - cw) * fx, (bg.height - ch) * 0.5
        return bg.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

    # ---- satu frame
    def frame_at(self, t):
        if t >= self.end_start:
            return self._end_frame(t - self.end_start)
        sc = next((s for s in reversed(self.scenes) if t >= s["start"]), self.scenes[0])
        lt = t - sc["start"]
        img = self._kb(sc, lt)
        img.paste((0, 0, 0), mask=self.vig)

        for ch in sc["chunks"]:
            if ch["start"] <= lt < ch["start"] + ch["dur"]:
                layer, age = ch["layer"], lt - ch["start"]
                cy = int(self.H * self.cfg["caption_y"])
                if age < 0.14:                       # efek "pop" kecil saat kata muncul
                    s = 0.82 + 0.18 * ease_out(age / 0.14)
                    layer = layer.resize((int(layer.width * s), int(layer.height * s)), Image.BILINEAR)
                img.paste(layer, ((self.W - layer.width) // 2, cy - layer.height // 2), layer)
                break

        hs = self.cfg["hud_seconds"]
        if self.hud is not None and t < hs:
            k = min(1.0, (hs - t) / 0.5, t / 0.4 + 0.0)
            img.paste(self.hud, (int(self.W * 0.06), int(self.H * 0.045)), alpha_scale(self.hud, k))

        fade = min(1.0, lt / DIP, (sc["dur"] - lt) / DIP)
        if fade < 1.0:
            img = Image.blend(self.black, img, max(0.0, fade))
        return img

    def _end_frame(self, lt):
        W, H = self.W, self.H
        img = self.end_bg.copy()
        q = alpha_scale(self.end_q, lt / 0.4)
        img.paste(q, ((W - q.width) // 2, int(H * 0.27)), q)
        for layer, y, t0 in ((self.end_a, 0.355, 0.5), (self.end_b, 0.425, 0.8)):
            lay = alpha_scale(layer, (lt - t0) / 0.35)
            if lt >= t0:
                img.paste(lay, ((W - lay.width) // 2, int(H * y)), lay)
        if lt >= 1.2:
            c = alpha_scale(self.end_cta, (lt - 1.2) / 0.4)
            img.paste(c, ((W - c.width) // 2, int(H * 0.495)), c)
        if lt < 0.4:
            img = Image.blend(self.black, img, lt / 0.4)
        return img


# ------------------------------------------------------------------------- output
def audio_args(cfg, total, music):
    fade = f"afade=t=in:d=1.5,afade=t=out:st={max(0.0, total - 2.0):.2f}:d=2"
    if music:
        inputs = ["-stream_loop", "-1", "-i", str(music)]
        graph = f"[1:a]volume={cfg['music_volume']},{fade}[a]"
    else:  # suasana ruangan sunyi (tanpa narator, tanpa musik)
        inputs = ["-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.5:sample_rate=44100",
                  "-f", "lavfi", "-i", "sine=f=110:sample_rate=44100"]
        graph = ("[1:a]lowpass=f=250,volume=0.35[n];[2:a]volume=0.03,tremolo=f=0.15:d=0.6[s];"
                 f"[n][s]amix=inputs=2:normalize=0,{fade}[a]")
    return inputs, graph


def find_music():
    for ext in ("mp3", "wav", "m4a", "ogg"):
        for p in sorted((ROOT / "assets/music").glob(f"*.{ext}")):
            return p
    return None


def prompts(story, out):
    style = story.get("art_style", DEFAULT_ART_STYLE)
    lines = [f"# Gaya konsisten (tempel di setiap prompt):\n{style}\n"]
    for i, sc in enumerate(story["scenes"], 1):
        file = sc.get("image", f"scene{i:02d}.png")
        lines.append(f"[{file}]\n{sc.get('visual', '(isi field \"visual\" di story)')}. {style}. Vertical 9:16.\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Prompt gambar -> {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--hd", action="store_true", help="1080x1920")
    ap.add_argument("--preview", action="store_true", help="hanya contact sheet PNG")
    ap.add_argument("--prompts", action="store_true", help="tulis prompt gambar per scene")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    story_path = Path(a.story)
    story = json.loads(story_path.read_text(encoding="utf-8"))
    name = story_path.stem
    (ROOT / "output").mkdir(exist_ok=True)

    if a.prompts:
        prompts(story, ROOT / "output" / f"{name}_prompts.txt")
        return

    size = (1080, 1920) if a.hd else (cfg["width"], cfg["height"])
    print(f"Menyiapkan '{story.get('title', name)}' ({size[0]}x{size[1]})...")
    r = Renderer(story, cfg, size)
    print(f"Durasi total: {r.total:.1f} detik")

    if a.preview:
        times = [s["start"] + c["start"] + 0.5 for s in r.scenes for c in s["chunks"]] + [r.end_start + 2.5]
        thumbs = [r.frame_at(t).resize((size[0] // 3, size[1] // 3)) for t in times]
        cols = 8
        rows = math.ceil(len(thumbs) / cols)
        sheet = Image.new("RGB", (thumbs[0].width * cols, thumbs[0].height * rows))
        for i, im in enumerate(thumbs):
            sheet.paste(im, ((i % cols) * im.width, (i // cols) * im.height))
        p = ROOT / "output" / f"{name}_preview.png"
        sheet.save(p)
        print(f"Preview -> {p}")
        return

    out = Path(a.out) if a.out else ROOT / "output" / f"{name}.mp4"
    music = find_music()
    ain, graph = audio_args(cfg, r.total, music)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{size[0]}x{size[1]}", "-r", str(r.fps), "-i", "-", *ain,
           "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-t", f"{r.total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(r.total * r.fps)
    try:
        for i in range(n):
            proc.stdin.write(r.frame_at(i / r.fps).tobytes())
            if i % (r.fps * 5) == 0:
                print(f"  {i / r.fps:5.1f}s / {r.total:.1f}s", flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        sys.exit("ffmpeg gagal")
    print(f"Selesai -> {out}")


if __name__ == "__main__":
    main()
