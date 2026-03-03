#!/usr/bin/env python3
"""
スマホ表示の縦方向オーバーフロー検査スクリプト
presentation.html を編集したら実行してください。

使い方:
  python3 check-mobile.py
  python3 check-mobile.py --screenshot   # 全スライドのスクショも保存
"""

import sys
import time
import argparse
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright が未インストールです: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    Image = None  # screenshot モード使用時のみ必要

# ---------- 設定 ----------
HTML_PATH = f"file://{Path(__file__).parent / 'presentation.html'}"
VIEWPORT = {"width": 393, "height": 852}  # iPhone 14 Pro 相当
TOTAL_SLIDES = 20
# slide padding: top=8, bottom=24 / slide-inner padding-top=6
AVAILABLE_HEIGHT = VIEWPORT["width"] - 8 - 24 - 6  # = 355px
TOLERANCE = 9  # slide-inner の padding-top 6px + 多少の誤差
# --------------------------

def check_overflow(page) -> list[dict]:
    return page.evaluate("""(args) => {
        const {total, available} = args;
        const results = [];
        for (let i = 1; i <= total; i++) {
            const slide = document.getElementById('slide-' + i);
            if (!slide) { results.push({i, error: 'not found'}); continue; }
            document.querySelectorAll('.slide').forEach(el => el.classList.remove('active'));
            slide.classList.add('active');
            const inner = slide.querySelector('.slide-inner');
            const h = inner ? inner.scrollHeight : slide.scrollHeight;
            results.push({i, scrollH: h, available, overflow: h - available});
        }
        return results;
    }""", {"total": TOTAL_SLIDES, "available": AVAILABLE_HEIGHT})


def take_screenshots(page, out_dir: Path):
    """各スライドのスクリーンショットを保存（-90°回転して正立させる）"""
    out_dir.mkdir(exist_ok=True)
    for i in range(1, TOTAL_SLIDES + 1):
        page.evaluate(f"""() => {{
            document.querySelectorAll('.slide').forEach(el => el.classList.remove('active'));
            const s = document.getElementById('slide-{i}');
            if (s) s.classList.add('active');
        }}""")
        time.sleep(0.15)
        png = page.screenshot()
        if Image:
            img = Image.open(__import__("io").BytesIO(png))
            img.rotate(90, expand=True).save(out_dir / f"slide_{i:02d}.png")
        else:
            (out_dir / f"slide_{i:02d}.png").write_bytes(png)
    print(f"スクリーンショット保存: {out_dir}/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", action="store_true", help="全スライドのスクリーンショットも保存")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(HTML_PATH, wait_until="networkidle")
        time.sleep(0.8)

        results = check_overflow(page)

        if args.screenshot:
            take_screenshots(page, Path("mobile-screenshots"))

        browser.close()

    # ---------- 結果表示 ----------
    ok_count = 0
    ng_slides = []

    print(f"\n{'S':>3} | {'scrollH':>8} | {'avail':>7} | {'overflow':>9} | 判定")
    print("─" * 48)
    for r in results:
        if "error" in r:
            print(f"S{r['i']:>2} | {'ERROR':>8} | {'─':>7} | {'─':>9} | ❌")
            ng_slides.append(r["i"])
            continue
        overflow = r["overflow"]
        ok = overflow <= TOLERANCE
        mark = "✅" if ok else f"❌ +{overflow - TOLERANCE}px はみ出し"
        print(f"S{r['i']:>2} | {r['scrollH']:>8} | {r['available']:>7} | {r['overflow']:>9} | {mark}")
        if ok:
            ok_count += 1
        else:
            ng_slides.append(r["i"])

    print()
    if ng_slides:
        print(f"⚠️  {len(ng_slides)} 枚のスライドがはみ出しています: {ng_slides}")
        print("   コンパクトCSSで font-size / padding / margin を調整してください。")
        sys.exit(1)
    else:
        print(f"✅ 全 {ok_count} 枚が正常です（available={AVAILABLE_HEIGHT}px, tolerance={TOLERANCE}px）")
        sys.exit(0)


if __name__ == "__main__":
    main()
