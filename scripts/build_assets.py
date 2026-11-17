from __future__ import annotations

import json
import math
import os
import random
import re
import urllib.request
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
ASSETS = ROOT / "assets"


def fit_width(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def shimmer_frame(base: Image.Image, progress: float, contribution: bool = False) -> Image.Image:
    frame = base.convert("RGBA")
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    center = int((-0.25 + progress * 1.5) * frame.width)
    band = max(70, frame.width // 10)
    polygon = [
        (center - band, 0),
        (center, 0),
        (center - band // 2, frame.height),
        (center - band * 3 // 2, frame.height),
    ]
    draw.polygon(polygon, fill=(255, 218, 112, 24 if contribution else 18))

    rng = random.Random(9137)
    for index in range(24 if contribution else 34):
        x = rng.randrange(frame.width)
        y = rng.randrange(frame.height)
        phase = (progress + index * 0.137) % 1.0
        alpha = int(90 * max(0.0, math.sin(phase * math.pi)))
        radius = 1 + (index % 2)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 225, 130, alpha))

    overlay = overlay.filter(ImageFilter.GaussianBlur(0.7))
    return Image.alpha_composite(frame, overlay).convert("RGB")


def save_gif(frames: list[Image.Image], path: Path, duration: int) -> None:
    palette_frames = [frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for frame in frames]
    palette_frames[0].save(
        path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


def contribution_weeks() -> list[list[int]]:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    login = os.getenv("GITHUB_USER", "DrZeem")
    if token:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar {
                weeks { contributionDays { contributionCount weekday } }
              }
            }
          }
        }
        """
        body = json.dumps({"query": query, "variables": {"login": login}}).encode()
        request = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "DrZeem-profile-builder",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
            raw_weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
            weeks: list[list[int]] = []
            for week in raw_weeks[-53:]:
                days = [0] * 7
                for day in week["contributionDays"]:
                    days[int(day["weekday"])] = int(day["contributionCount"])
                weeks.append(days)
            return weeks
        except Exception as exc:
            print(f"Contribution API unavailable; trying public calendar: {exc}")

    try:
        request = urllib.request.Request(
            f"https://github.com/users/{login}/contributions",
            headers={"User-Agent": "DrZeem-profile-builder"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8", errors="replace")
        matches = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d)"', html)
        if matches:
            by_date = {date.fromisoformat(day): int(level) for day, level in matches}
            ordered = sorted(by_date)
            first_sunday = ordered[0]
            weeks: list[list[int]] = []
            for offset in range(0, len(ordered), 7):
                week = [0] * 7
                for day_index in range(7):
                    current = date.fromordinal(first_sunday.toordinal() + offset + day_index)
                    week[day_index] = by_date.get(current, 0)
                weeks.append(week)
            print(f"Loaded {len(matches)} public contribution days for {login}.")
            return weeks[-53:]
    except Exception as exc:
        print(f"Public contribution calendar unavailable; using preview data: {exc}")

    rng = random.Random(365)
    return [[max(0, rng.randrange(0, 8) - rng.randrange(0, 5)) for _ in range(7)] for _ in range(53)]


def contribution_frame(base: Image.Image, weeks: list[list[int]], progress: float) -> Image.Image:
    frame = shimmer_frame(base, progress, contribution=True).convert("RGBA")
    draw = ImageDraw.Draw(frame)
    width, _ = frame.size
    x0, y0 = int(width * 0.344), int(width * 0.050)
    cell, gap = max(5, int(width * 0.0063)), max(1, int(width * 0.0013))
    grid_w = 53 * (cell + gap) - gap
    grid_h = 7 * (cell + gap) - gap
    draw.rounded_rectangle((x0 - 5, y0 - 5, x0 + grid_w + 5, y0 + grid_h + 5), radius=7, fill=(8, 30, 55, 232))

    palette = [(22, 50, 63), (14, 94, 72), (24, 145, 87), (63, 200, 111), (116, 238, 137)]
    reveal = int(progress * (53 + 8))
    for x, week in enumerate(weeks[-53:]):
        for y, count in enumerate(week):
            level = 0 if count == 0 else min(4, 1 + int(math.log2(count + 1)))
            if x > reveal:
                level = 0
            color = palette[level]
            left = x0 + x * (cell + gap)
            top = y0 + y * (cell + gap)
            draw.rounded_rectangle((left, top, left + cell, top + cell), radius=1, fill=color + (255,))
            if x == reveal and level:
                draw.rectangle((left - 1, top - 1, left + cell + 1, top + cell + 1), outline=(255, 221, 112, 210), width=1)
    return frame.convert("RGB")


def build() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    mockup = Image.open(SOURCE / "profile-master.png").convert("RGB")

    hero = fit_width(mockup.crop((268, 76, 1646, 315)), 1200)
    hero.save(ASSETS / "zephyr-arcade-hero.webp", "WEBP", quality=90, method=6)
    hero_frames = [shimmer_frame(hero, index / 19) for index in range(20)]
    save_gif(hero_frames, ASSETS / "zephyr-arcade-hero.gif", 110)

    contribution = fit_width(mockup.crop((268, 697, 1646, 878)), 1200)
    contribution.save(ASSETS / "contribution-city.webp", "WEBP", quality=90, method=6)
    weeks = contribution_weeks()
    contribution_frames = [contribution_frame(contribution, weeks, index / 23) for index in range(24)]
    save_gif(contribution_frames, ASSETS / "contribution-city.gif", 105)

    brand_365 = Image.open(SOURCE / "365games-brand-reference.png").convert("RGBA")
    brand_365.crop((72, 724, 328, 858)).save(ASSETS / "365games.png", optimize=True)

    xpgg = Image.open(SOURCE / "xpgg-original-logo.png").convert("RGBA")
    xpgg.thumbnail((360, 360), Image.Resampling.LANCZOS)
    xpgg.save(ASSETS / "xpgg.png", optimize=True)

    print("Built profile assets:")
    for path in sorted(ASSETS.iterdir()):
        print(f"- {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
