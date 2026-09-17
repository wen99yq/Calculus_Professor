#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Calculus_Professor 绘图辅助脚本。

把函数曲线转成可直接粘贴进内联 SVG 的坐标点列，或直接输出完整 SVG 片段。
避免手算坐标导致图形失真。

用法示例:
  # 只要点列（自己拼进已有 SVG）
  python plot_svg.py --expr "x^2" --xmin -2 --xmax 2 --samples 60 --mode points

  # 直接要一段完整可用的 SVG
  python plot_svg.py --expr "sin(x)" --xmin -6.5 --xmax 6.5 --ymin -1.6 --ymax 1.6 --mode svg

  # 标出若干关键点（切线切点、极值点、拐点）
  python plot_svg.py --expr "x^2" --xmin -2 --xmax 2 --mode svg --mark "1" --mark "-1"

  # 输出曲线在指定 x 处的斜率（便于标注切线）
  python plot_svg.py --expr "x^2" --slope-at 1
"""

import argparse
import math
import os
import sys

RET_OK = 0
RET_ERROR = 1
RET_NO_SYMPY = 2

RETRY_FLAG = "CALC_VERIFY_REEXEC"

SVG_WIDTH = 680.0
PAD_X = 40.0
PAD_Y = 40.0


# --------------------------------------------------------------------------
# 环境：优先用 sympy（表达式解析宽容），退化到 math 求值
# --------------------------------------------------------------------------
def _candidate_interpreters():
    seen = []
    home = os.path.expanduser("~")

    def add(p):
        if p:
            p = os.path.normpath(p)
            if p not in seen:
                seen.append(p)

    add(sys.executable)
    root = os.path.join(home, ".workbuddy", "binaries", "python")
    for sub in ("envs", "versions"):
        base = os.path.join(root, sub)
        if not os.path.isdir(base):
            continue
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            d = os.path.join(base, name)
            if not os.path.isdir(d):
                continue
            for rel in (
                os.path.join("Scripts", "python.exe"),
                os.path.join("bin", "python"),
                os.path.join("bin", "python3"),
                "python.exe",
            ):
                add(os.path.join(d, rel))
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("python3", "python"):
            add(os.path.join(d, name))
    for fixed in ("/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"):
        add(fixed)
    out = []
    for p in seen:
        if os.path.isfile(p) and os.path.basename(p).lower() in (
            "python",
            "python.exe",
            "python3",
            "python3.exe",
        ):
            out.append(p)
    return out


def _has_sympy(interpreter):
    try:
        import subprocess

        return (
            subprocess.run(
                [interpreter, "-c", "import sympy"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            ).returncode
            == 0
        )
    except Exception:
        return False


def _load_sympy():
    try:
        import sympy

        return sympy
    except ImportError:
        pass
    if os.environ.get(RETRY_FLAG) != "1":
        import subprocess

        for cand in _candidate_interpreters():
            if os.path.normpath(cand) == os.path.normpath(sys.executable):
                continue
            if not _has_sympy(cand):
                continue
            env = dict(os.environ)
            env[RETRY_FLAG] = "1"
            try:
                sys.exit(
                    subprocess.run(
                        [cand, os.path.abspath(__file__)] + sys.argv[1:], env=env
                    ).returncode
                )
            except Exception:
                continue
    print("[FALLBACK] 未找到 sympy 环境，无法解析表达式绘图。", file=sys.stderr)
    print("           可改用 --mode points 手算少量点，或让学生用交互 HTML 自行观察。", file=sys.stderr)
    sys.exit(RET_NO_SYMPY)


# --------------------------------------------------------------------------
# 采样
# --------------------------------------------------------------------------
def sample_curve(sympy, expr_text, var_name, xmin, xmax, samples):
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication_application,
        convert_xor,
    )

    transformations = standard_transformations + (convert_xor, implicit_multiplication_application)
    local = {"e": sympy.E, "pi": sympy.pi, "ln": sympy.log, "oo": sympy.oo}
    expr = parse_expr(expr_text.replace("^", "**"), local_dict=local, transformations=transformations)
    var = sympy.Symbol(var_name)
    f = sympy.lambdify(var, expr, modules=["math"])

    xs, ys = [], []
    if samples < 2:
        samples = 2
    step = (xmax - xmin) / float(samples - 1)
    for i in range(samples):
        x = xmin + i * step
        try:
            y = f(x)
        except Exception:
            y = None
        if y is None:
            xs.append(x)
            ys.append(None)
            continue
        try:
            y = float(y)
        except Exception:
            xs.append(x)
            ys.append(None)
            continue
        if not math.isfinite(y):
            xs.append(x)
            ys.append(None)
            continue
        xs.append(x)
        ys.append(y)
    return xs, ys


def auto_yrange(ys, pad_ratio=0.10):
    vals = [y for y in ys if y is not None]
    if not vals:
        return -1.0, 1.0
    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo, hi = lo - 1.0, hi + 1.0
    pad = (hi - lo) * pad_ratio
    lo, hi = lo - pad, hi + pad
    if lo > 0 and lo < (hi - lo) * 0.6:
        lo = 0.0
    if hi < 0 and -hi < (hi - lo) * 0.6:
        hi = 0.0
    return lo, hi


class Mapper(object):
    def __init__(self, xmin, xmax, ymin, ymax, plot_h):
        self.xmin, self.xmax = xmin, xmax
        self.ymin, self.ymax = ymin, ymax
        self.plot_w = SVG_WIDTH - 2 * PAD_X
        self.plot_h = plot_h
        self.x0 = PAD_X
        self.y0 = PAD_Y + plot_h

    def px(self, x):
        return self.x0 + (x - self.xmin) / (self.xmax - self.xmin) * self.plot_w

    def py(self, y):
        return self.y0 - (y - self.ymin) / (self.ymax - self.ymin) * self.plot_h

    def inside(self, y):
        return y is not None and self.ymin <= y <= self.ymax


def segments(xs, ys, mapper):
    """把点列切成连续段（遇到越界/无效点断开）。"""
    segs, cur = [], []
    for x, y in zip(xs, ys):
        if mapper.inside(y):
            cur.append((mapper.px(x), mapper.py(y)))
        else:
            if len(cur) >= 2:
                segs.append(cur)
            cur = []
    if len(cur) >= 2:
        segs.append(cur)
    return segs


def fmt_points(seg):
    return " ".join("%.1f,%.1f" % (x, y) for x, y in seg)


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------
TICK_MIN_PX = 70.0


def _nice_ticks(lo, hi, length_px, min_px=TICK_MIN_PX):
    span = hi - lo
    if span <= 0:
        return []
    max_ticks = max(2, int(length_px / min_px))
    raw = span / max_ticks
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        step = mag * mult
        if span / step <= max_ticks:
            break
    ticks, k = [], math.ceil(lo / step)
    while k * step <= hi + 1e-9:
        v = k * step
        if abs(v) > 1e-9 or lo < 0 < hi:
            ticks.append(0.0 if abs(v) < 1e-9 else v)
        k += 1
    return ticks


def _num(v):
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return ("%.2f" % v).rstrip("0").rstrip(".")


def render_svg(mapper, segs, marks, labels, title, height, grid):
    h = height
    parts = []
    parts.append(
        '<svg viewBox="0 0 680 %d" width="100%%" role="img" xmlns="http://www.w3.org/2000/svg">' % h
    )
    parts.append("<title>%s</title>" % (title or "函数图像"))
    parts.append("<desc>函数曲线示意图</desc>")
    parts.append(
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" '
        'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>'
    )

    x_axis_y = mapper.py(0.0) if mapper.ymin <= 0 <= mapper.ymax else mapper.y0
    y_axis_x = mapper.px(0.0) if mapper.xmin <= 0 <= mapper.xmax else mapper.x0

    if grid:
        for t in _nice_ticks(mapper.xmin, mapper.xmax, mapper.plot_w):
            gx = mapper.px(t)
            parts.append(
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--color-border-tertiary)" stroke-width="0.5"/>'
                % (gx, PAD_Y, gx, PAD_Y + mapper.plot_h)
            )
        for t in _nice_ticks(mapper.ymin, mapper.ymax, mapper.plot_h):
            gy = mapper.py(t)
            parts.append(
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--color-border-tertiary)" stroke-width="0.5"/>'
                % (PAD_X, gy, PAD_X + mapper.plot_w, gy)
            )

    parts.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--color-border-secondary)" '
        'stroke-width="0.5" marker-end="url(#arrow)"/>' % (PAD_X, x_axis_y, PAD_X + mapper.plot_w, x_axis_y)
    )
    parts.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--color-border-secondary)" '
        'stroke-width="0.5" marker-end="url(#arrow)"/>' % (y_axis_x, mapper.y0, y_axis_x, PAD_Y)
    )

    x_name_y = x_axis_y - 8 if x_axis_y - 8 > PAD_Y + 10 else x_axis_y + 20
    parts.append(
        '<text class="ts" x="%.1f" y="%.1f" text-anchor="end">x</text>' % (PAD_X + mapper.plot_w, x_name_y)
    )
    parts.append('<text class="ts" x="%.1f" y="%.1f">y</text>' % (y_axis_x + 10, PAD_Y + 4))
    parts.append('<text class="ts" x="%.1f" y="%.1f">O</text>' % (y_axis_x + 8, x_axis_y + 16))

    for t in _nice_ticks(mapper.xmin, mapper.xmax, mapper.plot_w):
        if abs(t) < 1e-9:
            continue
        parts.append(
            '<text class="ts" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
            % (mapper.px(t), x_axis_y + 16, _num(t))
        )
    for t in _nice_ticks(mapper.ymin, mapper.ymax, mapper.plot_h):
        if abs(t) < 1e-9:
            continue
        parts.append(
            '<text class="ts" x="%.1f" y="%.1f" text-anchor="end">%s</text>'
            % (y_axis_x - 6, mapper.py(t) + 4, _num(t))
        )

    color = "#378ADD"
    for i, seg in enumerate(segs):
        parts.append(
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="1.8" '
            'stroke-linecap="round" stroke-linejoin="round"/>' % (fmt_points(seg), color)
        )

    for mx in marks:
        try:
            xv = float(mx)
        except ValueError:
            continue
        my = labels.get(mx)
        if my is None:
            continue
        if not mapper.inside(my):
            continue
        cx, cy = mapper.px(xv), mapper.py(my)
        parts.append('<circle cx="%.1f" cy="%.1f" r="4" fill="#D4537E"/>' % (cx, cy))
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--color-text-tertiary)" '
            'stroke-width="0.5" stroke-dasharray="3 3"/>' % (cx, cy, cx, x_axis_y)
        )

    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="plot_svg.py",
        description="把函数曲线转成内联 SVG 的坐标点列或完整 SVG 片段",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--expr", help="函数表达式，如 x^2 或 sin(x)/x")
    p.add_argument("--var", default="x")
    p.add_argument("--xmin", type=float, default=-5.0)
    p.add_argument("--xmax", type=float, default=5.0)
    p.add_argument("--ymin", type=float)
    p.add_argument("--ymax", type=float)
    p.add_argument("--samples", type=int, default=121, help="采样点数，默认 121")
    p.add_argument("--plot-height", type=float, default=240.0, help="绘图区高度（不含轴标签留白）")
    p.add_argument("--mode", choices=["points", "svg"], default="points")
    p.add_argument("--mark", action="append", default=[], help="要标出的 x 值，可重复")
    p.add_argument("--title", help="SVG 标题")
    p.add_argument("--grid", action="store_true", help="画网格线")
    p.add_argument("--slope-at", type=float, help="输出该点处的函数值与切线斜率，然后退出")
    args = p.parse_args(argv)

    if not args.expr:
        print("请提供 --expr", file=sys.stderr)
        return RET_ERROR

    sympy = _load_sympy()

    if args.slope_at is not None:
        from sympy.parsing.sympy_parser import (
            parse_expr,
            standard_transformations,
            implicit_multiplication_application,
            convert_xor,
        )

        transformations = standard_transformations + (convert_xor, implicit_multiplication_application)
        local = {"e": sympy.E, "pi": sympy.pi, "ln": sympy.log}
        expr = parse_expr(args.expr.replace("^", "**"), local_dict=local, transformations=transformations)
        var = sympy.Symbol(args.var)
        x0 = sympy.sympify(args.slope_at)
        y0 = sympy.simplify(expr.subs(var, x0))
        k = sympy.simplify(sympy.diff(expr, var).subs(var, x0))
        print("x0 = %s" % x0)
        print("y0 = %s   (%.6f)" % (y0, float(y0)))
        print("k  = %s   (%.6f)" % (k, float(k)))
        print("切线方程: y = %s + %s * (x - %s)" % (y0, k, x0))
        return RET_OK

    xs, ys = sample_curve(sympy, args.expr, args.var, args.xmin, args.xmax, args.samples)
    ymin = args.ymin
    ymax = args.ymax
    if ymin is None or ymax is None:
        auto_lo, auto_hi = auto_yrange(ys)
        ymin = auto_lo if ymin is None else ymin
        ymax = auto_hi if ymax is None else ymax
    if ymax <= ymin:
        print("--ymax 必须大于 --ymin", file=sys.stderr)
        return RET_ERROR

    mapper = Mapper(args.xmin, args.xmax, ymin, ymax, args.plot_height)
    segs = segments(xs, ys, mapper)

    if args.mode == "points":
        print("# expr = %s   x in [%g, %g]   y in [%g, %g]" % (args.expr, args.xmin, args.xmax, ymin, ymax))
        print("# 共 %d 段（遇到未定义或越界处自动断开）" % len(segs))
        for i, seg in enumerate(segs, 1):
            if len(segs) > 1:
                print("# --- 第 %d 段 ---" % i)
            print('points="%s"' % fmt_points(seg))
        return RET_OK

    labels = {}
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication_application,
        convert_xor,
    )

    transformations = standard_transformations + (convert_xor, implicit_multiplication_application)
    local = {"e": sympy.E, "pi": sympy.pi, "ln": sympy.log}
    expr = parse_expr(args.expr.replace("^", "**"), local_dict=local, transformations=transformations)
    var = sympy.Symbol(args.var)
    for m in args.mark:
        try:
            xv = float(m)
        except ValueError:
            continue
        try:
            labels[m] = float(sympy.simplify(expr.subs(var, sympy.sympify(m))))
        except Exception:
            continue

    height = int(args.plot_height + 2 * PAD_Y)
    print(render_svg(mapper, segs, args.mark, labels, args.title, height, args.grid))
    return RET_OK


if __name__ == "__main__":
    sys.exit(main())
