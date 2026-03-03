#!/usr/bin/env python3
"""
スマホ表示の縦方向オーバーフロー検査スクリプト
JS による transform: scale(vw/393) 方式に対応。
375px (iPhone SE/13 mini) と 393px (iPhone 14 Pro) の両方で検証する。

使い方:
  python3 check-mobile.py
  python3 check-mobile.py --screenshot   # 全スライドのスクショも保存

前提:
  pip install playwright pillow && playwright install chromium
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
VIEWPORTS = [
    {"width": 375, "height": 812},   # iPhone SE 3rd gen / iPhone 13 mini
    {"width": 393, "height": 852},   # iPhone 14 Pro（デザイン基準幅）
]
TOTAL_SLIDES = 20
DESIGN_WIDTH = 393   # JS の --ms = innerWidth / DESIGN_WIDTH
SLIDE_PAD_TOP = 8    # .slide の padding-top (compact media query)
TOLERANCE = 9        # 許容誤差 (px)
# --------------------------


def check_overflow(page, vw: int) -> list[dict]:
    """各スライドの visual bottom を計算してオーバーフローを検出する。
    visual bottom = SLIDE_PAD_TOP + scrollH * scale
    scale = min(1.0, vw / DESIGN_WIDTH)  ← JS の updateMobileScale() と同じ計算
    """
    scale = min(1.0, vw / DESIGN_WIDTH)
    return page.evaluate("""(args) => {
        const {total, vw, scale, slidePadTop} = args;
        const results = [];
        for (let i = 1; i <= total; i++) {
            const slide = document.getElementById('slide-' + i);
            if (!slide) { results.push({i, error: 'not found'}); continue; }
            document.querySelectorAll('.slide').forEach(el => el.classList.remove('active'));
            slide.classList.add('active');
            const inner = slide.querySelector('.slide-inner');
            const h = inner ? inner.scrollHeight : slide.scrollHeight;
            // slide は overflow:hidden で高さ = vw (portrait 時)
            // slide-inner は transform:scale(scale) / transform-origin: top center
            // → visual bottom = slidePadTop + h * scale
            const visualBottom = slidePadTop + h * scale;
            results.push({
                i, scrollH: h, scale,
                visualBottom: Math.round(visualBottom * 10) / 10,
                vw, overflow: visualBottom - vw
            });
        }
        return results;
    }""", {"total": TOTAL_SLIDES, "vw": vw, "scale": scale, "slidePadTop": SLIDE_PAD_TOP})


def take_screenshots(page, vw: int, out_dir: Path):
    """各スライドのスクリーンショットを保存（-90°回転して正立させる）"""
    out_dir.mkdir(exist_ok=True)
    # swipe-hint を非表示にする
    page.evaluate("""() => {
        const h = document.getElementById('swipe-hint');
        if (h) h.style.display = 'none';
    }""")
    for i in range(1, TOTAL_SLIDES + 1):
        page.evaluate(f"""() => {{
            document.querySelectorAll('.slide').forEach(el => el.classList.remove('active'));
            const s = document.getElementById('slide-{i}');
            if (s) s.classList.add('active');
        }}""")
        time.sleep(0.15)
        png = page.screenshot()
        if Image:
            import io
            img = Image.open(io.BytesIO(png))
            img.rotate(90, expand=True).save(out_dir / f"slide_{i:02d}_vw{vw}.png")
        else:
            (out_dir / f"slide_{i:02d}_vw{vw}.png").write_bytes(png)
    print(f"  → スクリーンショット保存: {out_dir}/ (vw={vw})")


def main():
    parser = argparse.ArgumentParser(description="モバイルオーバーフロー検査")
    parser.add_argument("--screenshot", action="store_true", help="全スライドのスクリーンショットも保存")
    args = parser.parse_args()

    all_ng: list[tuple[int, int]] = []

    with sync_playwright() as p:
        for vp in VIEWPORTS:
            vw = vp["width"]
            scale = min(1.0, vw / DESIGN_WIDTH)
            print(f"\n── vw={vw}px  scale={scale:.4f} ──────────────────────────")

            browser = p.chromium.launch()
            page = browser.new_page(viewport=vp)
            page.goto(HTML_PATH, wait_until="networkidle")
            time.sleep(0.8)

            results = check_overflow(page, vw)

            if args.screenshot:
                take_screenshots(page, vw, Path("mobile-screenshots"))

            browser.close()

            # ---------- 結果表示 ----------
            ng_slides = []
            print(f"{'S':>3} | {'scrollH':>8} | {'visBottom':>10} | {'vw':>5} | {'overflow':>9} | 判定")
            print("─" * 60)
            for r in results:
                if "error" in r:
                    print(f"S{r['i']:>2} | {'ERROR':>8} | {'─':>10} | {'─':>5} | {'─':>9} | ❌")
                    ng_slides.append(r["i"])
                    continue
                ov = r["overflow"]
                ok = ov <= TOLERANCE
                mark = "✅" if ok else f"❌ +{ov - TOLERANCE:.1f}px"
                print(f"S{r['i']:>2} | {r['scrollH']:>8} | {r['visualBottom']:>10.1f} | {r['vw']:>5} | {ov:>9.1f} | {mark}")
                if not ok:
                    ng_slides.append(r["i"])

            if ng_slides:
                print(f"\n⚠️  vw={vw}: {len(ng_slides)} 枚がはみ出しています: S{ng_slides}")
                all_ng.extend([(vw, s) for s in ng_slides])
            else:
                print(f"\n✅ vw={vw}: 全 {len(results)} 枚 OK（DESIGN_WIDTH={DESIGN_WIDTH}, tolerance={TOLERANCE}px）")

    print()
    if all_ng:
        print(f"⚠️  合計 {len(all_ng)} 件の問題があります:")
        for vw, s in all_ng:
            print(f"   S{s} at vw={vw}px")
        print("\ncompact media query で font-size / padding / margin を調整してください。")
        sys.exit(1)
    else:
        print("✅ 全ビューポート・全スライド正常です。")
        sys.exit(0)


if __name__ == "__main__":
    main()
