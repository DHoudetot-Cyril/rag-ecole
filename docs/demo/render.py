# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Rend docs/demo.gif à partir des échanges réels enregistrés par docs/demo/record.py.

Questions, réponses, sources, scores et latences viennent tels quels de docs/demo/turns.json :
seul l'affichage est mis en scène (frappe de la commande, apparition progressive).

    uv run docs/demo/render.py        # ou : pip install pillow && python docs/demo/render.py
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 640
PAD_X, TOP, LINE_H, COLS = 22, 50, 21, 98

BG, BAR, FG, DIM = (24, 24, 27), (39, 39, 42), (228, 228, 231), (130, 130, 140)
ACCENT, SRC, OK, WARN = (217, 119, 87), (125, 180, 255), (134, 239, 172), (250, 204, 21)
ROLE_COLOR = {"élève": (125, 211, 252), "direction": (196, 181, 253)}
ROLE_ICON = {"élève": "élève     (niveau 1)", "direction": "direction (niveaux 1 + 2)"}
NO_ANSWER_PREFIX = "Je ne trouve pas cette information"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for path in ("/usr/share/fonts/truetype/dejavu/" + name, name):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit("Police DejaVu Sans Mono introuvable (apt install fonts-dejavu-core).")


FONT, BOLD = _font("DejaVuSansMono.ttf", 15), _font("DejaVuSansMono-Bold.ttf", 15)
SMALL = _font("DejaVuSansMono.ttf", 12)


class Screen:
    def __init__(self, footer: str) -> None:
        self.footer = footer
        self.lines: list[list[tuple]] = []
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def add(self, *segments) -> None:
        self.lines.append([(s[0], s[1], s[2] if len(s) > 2 else FONT) for s in segments])

    def snap(self, ms: int) -> None:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 32], fill=BAR)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([14 + i * 21, 10, 26 + i * 21, 22], fill=c)
        d.text((W // 2, 16), "rag-ecole — POST /chat", font=SMALL, fill=DIM, anchor="mm")
        y = TOP
        for segments in self.lines[-((H - TOP - 30) // LINE_H) :]:
            x = PAD_X
            for text, color, font in segments:
                d.text((x, y), text, font=font, fill=color)
                x += d.textlength(text, font=font)
            y += LINE_H
        d.text((PAD_X, H - 20), self.footer, font=SMALL, fill=DIM)
        self.frames.append(img)
        self.durations.append(ms)


def num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def render(record: dict, output: Path) -> None:
    s = Screen(
        f"Échanges réels avec l'API (LLM : {record.get('llm_label') or record['llm_model']}, embeddings : "
        f"{record['embedding_model'].split('/')[-1]}), rejoués depuis docs/demo/turns.json"
    )
    for turn in record["turns"]:
        s.lines = []
        role = turn["role"]
        key = "$STUDENT_API_KEY" if role == "élève" else "$DIRECTION_API_KEY"
        cmd = f'curl /chat -H "X-API-Key: {key}" -d \'{{"question": "{turn["question"]}"}}\''
        s.add(("rôle  ", DIM), (ROLE_ICON[role], ROLE_COLOR[role], BOLD))
        s.add(("", FG))
        wrapped = textwrap.wrap(cmd, COLS - 2)
        for j in range(len(wrapped)):
            s.add(("$ " if j == 0 else "  ", ACCENT, BOLD), ("", FG))
        base = len(s.lines) - len(wrapped)
        for j, full in enumerate(wrapped):
            for i in [*range(0, len(full), 5), len(full)]:
                s.lines[base + j] = [("$ " if j == 0 else "  ", ACCENT, BOLD), (full[:i], FG, FONT)]
                s.snap(28)
        s.snap(500)
        s.add(("", FG))

        refused = turn["answer"].startswith(NO_ANSWER_PREFIX)
        color = WARN if refused else OK
        for j, line in enumerate(textwrap.wrap(turn["answer"], COLS - 4)):
            s.add(("● " if j == 0 else "  ", color, BOLD), (line, FG))
            s.snap(260)
        s.add(("", FG))
        if turn["sources"] and not refused:
            used = turn["sources"][0]
            s.add(
                ("  [1] ", SRC, BOLD),
                (used["document"], SRC),
                (f"   niveau {used['level'][-1]} · score {num(used['score'])}", DIM),
            )
        levels = " + ".join(lv.replace("level", "niveau ") for lv in turn["levels_searched"])
        s.add(("  ", FG), (f"niveaux consultés : {levels}", DIM))
        if not turn["sources"]:
            s.add(("  ", FG), ("aucun passage au-dessus du seuil → réponse refusée sans appeler le LLM", WARN))
        elif refused:
            s.add(("  ", FG), ("passages trouvés hors sujet → le LLM répond qu'il ne sait pas", WARN))
        s.add(("  ", FG), (f"latence : {turn['latency_ms']} ms", DIM))
        s.snap(4200 if refused or role == "direction" else 3400)

    # Palette commune, tirée des écrans de fin de chaque échange (toutes les couleurs y sont).
    sample = Image.new("RGB", (W, H * len(record["turns"])))
    holds = [i for i, d in enumerate(s.durations) if d >= 3400]
    for k, i in enumerate(holds):
        sample.paste(s.frames[i], (0, H * k))
    palette = sample.quantize(colors=96, method=Image.Quantize.MEDIANCUT)
    frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in s.frames]
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=s.durations, loop=0, optimize=True)
    print(f"{output} : {len(frames)} images, {sum(s.durations) / 1000:.0f} s, {output.stat().st_size / 1e6:.1f} Mo")


def main() -> None:
    here = Path(__file__).resolve().parent
    render(json.loads((here / "turns.json").read_text(encoding="utf-8")), here.parent / "demo.gif")


if __name__ == "__main__":
    main()
