#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calculus-professor — 学习报告生成脚本。

读取学习档案（学生档案.md / 进度追踪.md / 错题本.md），生成一份可打印的 HTML 学习报告。

设计取舍:
  * 默认**完全离线**——公式统一用 Unicode 书写，图表用内联 SVG，页面不加载任何外部资源。
  * 需要 LaTeX 公式渲染时加 --mathjax，会从 CDN 引入 MathJax（此时需要联网）。

用法:
  python build_report.py
  python build_report.py --root "微积分学习"
  python build_report.py --out "微积分学习/报告/2026-09-17_学习报告.html"
  python build_report.py --mathjax
  python build_report.py --note "本次报告未做机器验算（未找到 sympy 环境）"
"""

import argparse
import datetime
import html
import os
import re
import sys

RET_OK = 0
RET_ERROR = 1

DEFAULT_ROOT = "微积分学习"

TIER_LABEL = {
    "基础补强": "基础补强",
    "期末达标": "期末达标",
    "考研提高": "考研提高",
}

MASTERY_ORDER = ["未接触", "听过", "能看懂", "能独立做", "能讲给别人"]


# --------------------------------------------------------------------------
# Markdown 解析（容错，不追求通用）
# --------------------------------------------------------------------------
def read_text(path):
    if not os.path.isfile(path):
        return None
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def parse_frontmatter(text):
    if not text:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and not k.startswith("-"):
            data[k] = v
    return data


def parse_tables(text):
    """返回 [{'header': [...], 'rows': [[...], ...]}]"""
    tables = []
    if not text:
        return tables
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            if len(block) >= 3:
                def cells(row):
                    parts = [c.strip() for c in row.strip("|").split("|")]
                    return parts

                header = cells(block[0])
                sep = cells(block[1])
                if all(re.fullmatch(r":?-{2,}:?", s.replace(" ", "")) for s in sep if s != ""):
                    # 跳过分隔行有效但内容为空的情况
                    rows = [cells(r) for r in block[2:]]
                    rows = [r for r in rows if any(c.strip() for c in r)]
                    tables.append({"header": header, "rows": rows})
                    continue
            # 不是合法表格，继续前进
            continue
        i += 1
    return tables


def find_table(tables, *keywords):
    """先按精确单元格匹配（避免"掌握度"同时出现在多张表头里造成误认），再退化为子串匹配。"""
    for t in tables:
        cells = [c.strip() for c in t["header"]]
        if all(k in cells for k in keywords):
            return t
    for t in tables:
        head = " ".join(t["header"])
        if all(k in head for k in keywords):
            return t
    return None


def parse_wrong_entries(text):
    """解析错题本条目：以 '## ' 开头，属性行形如 '- **键**：值'"""
    entries = []
    if not text:
        return entries
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            if cur:
                entries.append(cur)
            cur = {"title": s[3:].strip(), "fields": {}}
            continue
        if cur is None:
            continue
        m = re.match(r"^[-*]\s*\*\*(.+?)\*\*[：:]\s*(.*)$", s)
        if m:
            cur["fields"][m.group(1).strip()] = m.group(2).strip()
            continue
        m2 = re.match(r"^[-*]\s*([^:：]+)[：:]\s*(.*)$", s)
        if m2 and m2.group(1).strip() not in cur["fields"]:
            cur["fields"][m2.group(1).strip()] = m2.group(2).strip()
    if cur:
        entries.append(cur)
    return entries


def chapter_of(text):
    if not text:
        return None
    m = re.search(r"第\s*(\d+)\s*章", text)
    return m.group(1) if m else None


def to_float(s):
    try:
        return float(str(s).replace("%", "").strip())
    except Exception:
        return None


# --------------------------------------------------------------------------
# 内联 SVG 横向条形图（离线）
# --------------------------------------------------------------------------
BAR_H = 30
GAP = 10
LEFT = 130
RIGHT = 600


def hbar_chart(items, color="#378ADD", unit=""):
    items = [(k, v) for k, v in items if v is not None]
    if not items:
        return '<p class="empty">暂无数据</p>'
    height = len(items) * (BAR_H + GAP) + 24
    maxv = max([v for _, v in items] + [1])
    parts = [
        '<svg viewBox="0 0 680 %d" width="100%%" role="img" aria-label="横向条形图">' % height
    ]
    y = 12
    for label, value in items:
        w = (RIGHT - LEFT) * (value / maxv) if maxv else 0
        parts.append(
            '<text x="%d" y="%d" text-anchor="end" font-size="12" fill="#6b6b6b" '
            'dominant-baseline="central">%s</text>' % (LEFT - 10, y + BAR_H // 2, html.escape(str(label)))
        )
        parts.append(
            '<rect x="%d" y="%d" width="%d" height="%d" rx="4" fill="%s" fill-opacity="0.85"/>'
            % (LEFT, y, max(2, int(w)), BAR_H - 10, color)
        )
        parts.append(
            '<text x="%d" y="%d" font-size="12" fill="#4a4a4a" dominant-baseline="central">%s%s</text>'
            % (LEFT + max(2, int(w)) + 8, y + BAR_H // 2, value, html.escape(unit))
        )
        y += BAR_H + GAP
    parts.append("</svg>")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# 报告生成
# --------------------------------------------------------------------------
def build_context(root):
    profile_text = read_text(os.path.join(root, "学生档案.md"))
    progress_text = read_text(os.path.join(root, "进度追踪.md"))
    wrong_text = read_text(os.path.join(root, "错题本.md"))

    profile = parse_frontmatter(profile_text) if profile_text else {}
    prog_tables = parse_tables(progress_text)
    wrong_entries = parse_wrong_entries(wrong_text)

    chapter_table = find_table(prog_tables, "章", "掌握度")
    kp_table = find_table(prog_tables, "知识点", "掌握度")
    practice_table = find_table(prog_tables, "题数", "正确")

    ctx = {
        "tier": profile.get("difficulty_tier", "未设定"),
        "target": profile.get("target", "未设定"),
        "textbook": profile.get("textbook", "苏德矿《微积分》第三版（高教社2021）"),
        "chapters": [],
        "kps": [],
        "practices": [],
        "wrong": wrong_entries,
        "has_profile": bool(profile_text),
        "has_progress": bool(progress_text),
        "has_wrong": bool(wrong_text),
    }

    if chapter_table:
        for row in chapter_table["rows"]:
            r = row + [""] * (len(chapter_table["header"]) - len(row))
            ctx["chapters"].append(
                {
                    "no": r[0],
                    "name": r[1] if len(r) > 1 else "",
                    "status": r[2] if len(r) > 2 else "",
                    "kps": r[3] if len(r) > 3 else "",
                    "mastery": r[4] if len(r) > 4 else "",
                    "recent": r[5] if len(r) > 5 else "",
                }
            )
    if kp_table:
        for row in kp_table["rows"]:
            r = row + [""] * (len(kp_table["header"]) - len(row))
            ctx["kps"].append(
                {
                    "kp": r[0],
                    "chapter": r[1] if len(r) > 1 else "",
                    "mastery": r[2] if len(r) > 2 else "",
                    "rate": r[3] if len(r) > 3 else "",
                    "updated": r[4] if len(r) > 4 else "",
                }
            )
    if practice_table:
        for row in practice_table["rows"]:
            r = row + [""] * (len(practice_table["header"]) - len(row))
            ctx["practices"].append(
                {
                    "date": r[0],
                    "source": r[1] if len(r) > 1 else "",
                    "total": r[2] if len(r) > 2 else "",
                    "right": r[3] if len(r) > 3 else "",
                    "cause": r[4] if len(r) > 4 else "",
                }
            )

    total_q, total_r = 0, 0
    for p in ctx["practices"]:
        t, rr = to_float(p["total"]), to_float(p["right"])
        if t and rr is not None:
            total_q += t
            total_r += rr
    ctx["total_questions"] = int(total_q)
    ctx["total_right"] = int(total_r)
    ctx["accuracy"] = (total_r / total_q * 100.0) if total_q else None

    cause_count, chapter_count = {}, {}
    for e in wrong_entries:
        cause = e["fields"].get("错因类别", "未归类")
        cause = re.split(r"[（(]", cause)[0].strip() or "未归类"
        cause_count[cause] = cause_count.get(cause, 0) + 1
        ch = chapter_of(e["title"]) or chapter_of(e["fields"].get("题目", "")) or "未标章"
        chapter_count[ch] = chapter_count.get(ch, 0) + 1

    ctx["cause_count"] = sorted(cause_count.items(), key=lambda kv: -kv[1])
    ctx["chapter_count"] = sorted(
        [("第%s章" % k if k.isdigit() else k, v) for k, v in chapter_count.items()],
        key=lambda kv: -kv[1],
    )

    weak = []
    for kp in ctx["kps"]:
        m = kp["mastery"]
        rate = to_float(kp["rate"])
        if m in ("未接触", "听过", "能看懂") or (rate is not None and rate < 0.6):
            weak.append(kp)
    ctx["weak"] = weak

    studied = 0
    done = 0
    for c in ctx["chapters"]:
        if c["status"] and c["status"] not in ("未开始", "-", "—"):
            studied += 1
        if c["mastery"] in ("能独立做", "能讲给别人"):
            done += 1
    ctx["studied"] = studied
    ctx["done"] = done
    ctx["total_chapters"] = len(ctx["chapters"])

    ctx["advice"] = build_advice(ctx)
    return ctx


def build_advice(ctx):
    tips = []
    acc = ctx["accuracy"]
    if not ctx["has_profile"]:
        tips.append("还没有建立学生档案——先做一次摸底，才能按你的水平调整讲解方式。")
    if ctx["total_questions"] == 0:
        tips.append("还没有练习记录。建议每学完一节就做 3~5 道题，光看讲解记不住。")
    elif acc is not None and acc < 60:
        tips.append(
            "练习正确率 %.0f%%，偏低。建议**降低题量、提高讲解颗粒度**，先把一类题型做透再换下一类。"
            % acc
        )
    elif acc is not None and acc < 80:
        tips.append("练习正确率 %.0f%%，中等。建议把错题本里「计算失误」类的题重做一遍，稳定准确率。" % acc)
    elif acc is not None:
        tips.append("练习正确率 %.0f%%，不错。可以适当加难度，试试综合题和证明题。" % acc)

    if ctx["chapter_count"]:
        ch, n = ctx["chapter_count"][0]
        tips.append("错题最集中在 **%s**，建议优先回头补这一章。" % ch)
    if ctx["cause_count"]:
        cause, n = ctx["cause_count"][0]
        cause_tip = {
            "概念不清": "错因以「概念不清」为主——先回去把定义和成立条件捋一遍，再刷题。",
            "计算失误": "错因以「计算失误」为主——不是不会，是不稳。建议限时做题 + 逐步书写，别跳步。",
            "思路断点": "错因以「思路断点」为主——会算但不知道何时用哪个方法。建议专题总结题型识别特征。",
            "条件误读": "错因以「条件误读」为主——读题时先圈出条件与所求，再动笔。",
            "前置漏洞": "错因以「前置漏洞」为主——需要先补中学数学（三角、对数、因式分解）。",
        }.get(cause)
        if cause_tip:
            tips.append(cause_tip)
    if ctx["weak"]:
        names = "、".join(k["kp"] for k in ctx["weak"][:5] if k["kp"])
        if names:
            tips.append("薄弱知识点：%s。建议逐个做成知识卡片，隔天自测。" % names)
    if ctx["tier"] == "基础补强":
        tips.append("当前档位是「基础补强」，节奏可以放慢，别跟别人比进度。")
    elif ctx["tier"] == "考研提高":
        tips.append("当前档位是「考研提高」，建议在常规题之外补充证明题与综合题。")
    return tips


def esc(s):
    return html.escape(str(s if s is not None else ""))


def md_inline(s):
    """转义 HTML 后，把 **粗体** 转成 <strong>。"""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc(s))


def render(ctx, note=None, use_mathjax=False):
    today = datetime.date.today().isoformat()
    acc_txt = "—" if ctx["accuracy"] is None else "%.0f%%" % ctx["accuracy"]

    mathjax = ""
    if use_mathjax:
        mathjax = (
            '<script>window.MathJax={tex:{inlineMath:[["$","$"]],displayMath:[["$$","$$"]]}};</script>\n'
            '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>'
        )

    def cards():
        items = [
            ("难度档位", esc(ctx["tier"])),
            ("已学章节", "%d / %d" % (ctx["studied"], ctx["total_chapters"] or 0)),
            ("累计错题", str(len(ctx["wrong"]))),
            ("练习正确率", acc_txt),
        ]
        out = ['<div class="cards">']
        for label, value in items:
            out.append(
                '<div class="card"><div class="card-label">%s</div><div class="card-value">%s</div></div>'
                % (label, value)
            )
        out.append("</div>")
        return "\n".join(out)

    def chapter_table_html():
        if not ctx["chapters"]:
            return '<p class="empty">暂无章节进度记录。</p>'
        rows = []
        for c in ctx["chapters"]:
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (esc(c["no"]), esc(c["name"]), esc(c["status"]), esc(c["mastery"]), esc(c["recent"]))
            )
        return (
            "<table><thead><tr><th>章</th><th>章节名</th><th>状态</th>"
            "<th>掌握度</th><th>最近活动</th></tr></thead><tbody>%s</tbody></table>"
            % "".join(rows)
        )

    def kp_table_html():
        if not ctx["kps"]:
            return '<p class="empty">暂无知识点级记录。</p>'
        rows = []
        for k in ctx["kps"]:
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (esc(k["kp"]), esc(k["chapter"]), esc(k["mastery"]), esc(k["rate"]))
            )
        return (
            "<table><thead><tr><th>知识点</th><th>章</th><th>掌握度</th>"
            "<th>练习正确率</th></tr></thead><tbody>%s</tbody></table>" % "".join(rows)
        )

    def wrong_table_html():
        if not ctx["wrong"]:
            return '<p class="empty">错题本还是空的。做错的题记得让我记下来。</p>'
        rows = []
        for e in ctx["wrong"]:
            f = e["fields"]
            rows.append(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (
                    esc(e["title"]),
                    esc(f.get("日期", "")),
                    esc(re.split(r"[（(]", f.get("错因类别", "") or "")[0]),
                    esc(f.get("同类提醒", "")),
                )
            )
        return (
            "<table><thead><tr><th>题目</th><th>日期</th><th>错因</th>"
            "<th>同类提醒</th></tr></thead><tbody>%s</tbody></table>" % "".join(rows)
        )

    advice_html = "".join("<li>%s</li>" % md_inline(t) for t in ctx["advice"]) or "<li>暂无建议。</li>"
    note_html = ""
    if note:
        note_html = '<div class="note"><strong>技术备注：</strong>%s</div>' % esc(note)

    progress_missing = ""
    if not ctx["has_progress"]:
        progress_missing = '<div class="note">未找到「进度追踪.md」，章节与知识点数据为空。</div>'

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>微积分学习报告 · {today}</title>
<style>
  :root {{
    --bg:#ffffff; --fg:#1c1c1c; --muted:#6b6b6b; --line:#e2e2e2;
    --accent:#378ADD; --warn:#D85A30; --ok:#639922;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#161616; --fg:#f0f0f0; --muted:#a0a0a0; --line:#333; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin:0; padding:32px 24px 64px; background:var(--bg); color:var(--fg);
    font:14px/1.7 system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size:22px; font-weight:500; margin:0 0 4px; }}
  h2 {{ font-size:16px; font-weight:500; margin:32px 0 12px; padding-bottom:6px;
        border-bottom:1px solid var(--line); }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:24px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
  .card {{ background:rgba(127,127,127,.08); border-radius:10px; padding:14px 16px; }}
  .card-label {{ font-size:12px; color:var(--muted); margin-bottom:6px; }}
  .card-value {{ font-size:24px; font-weight:500; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; table-layout:fixed; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
            overflow-wrap:break-word; }}
  th {{ font-weight:500; color:var(--muted); font-size:12px; }}
  .empty {{ color:var(--muted); font-size:13px; }}
  .note {{ background:rgba(216,90,48,.10); border-radius:8px; padding:10px 14px;
           font-size:13px; margin:16px 0; }}
  ul.advice {{ padding-left:20px; }}
  ul.advice li {{ margin-bottom:8px; }}
  .chart-box {{ margin: 8px 0 20px; }}
  @media print {{
    body {{ padding:0; background:#fff; color:#000; }}
    h2 {{ page-break-after:avoid; }}
    table, .card {{ page-break-inside:avoid; }}
  }}
</style>
{mathjax}
</head>
<body>
<div class="wrap">
  <h1>微积分学习报告</h1>
  <div class="sub">生成日期：{today} · 目标：{target} · 教材：{textbook}</div>

  {cards}

  <h2>一、学习进度</h2>
  {progress_missing}
  {chapter_table}

  <h2>二、知识点掌握情况</h2>
  {kp_table}

  <h2>三、错题分析</h2>
  <div class="chart-box">
    <h3 style="font-size:13px;font-weight:500;margin:0 0 8px">按章节分布</h3>
    {chart_chapter}
  </div>
  <div class="chart-box">
    <h3 style="font-size:13px;font-weight:500;margin:0 0 8px">按错因分布</h3>
    {chart_cause}
  </div>
  {wrong_table}

  <h2>四、薄弱环节</h2>
  {weak_html}

  <h2>五、下一步建议</h2>
  <ul class="advice">{advice}</ul>

  {note}
</div>
</body>
</html>
""".format(
        today=today,
        target=esc(ctx["target"]),
        textbook=esc(ctx["textbook"]),
        cards=cards(),
        progress_missing=progress_missing,
        chapter_table=chapter_table_html(),
        kp_table=kp_table_html(),
        chart_chapter=hbar_chart(ctx["chapter_count"], color="#378ADD", unit=" 道"),
        chart_cause=hbar_chart(ctx["cause_count"], color="#D85A30", unit=" 道"),
        wrong_table=wrong_table_html(),
        weak_html=(
            "".join(
                "<p>· <strong>%s</strong>（%s，掌握度：%s）</p>"
                % (esc(k["kp"]), esc(k["chapter"]), esc(k["mastery"]))
                for k in ctx["weak"][:12]
            )
            or '<p class="empty">暂无明显薄弱环节。</p>'
        ),
        advice=advice_html,
        note=note_html,
        mathjax=mathjax,
    )


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="build_report.py",
        description="根据学习档案生成可打印的 HTML 学习报告（默认离线）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--root", default=DEFAULT_ROOT, help="档案根目录，默认 微积分学习")
    p.add_argument("--out", help="输出文件路径，默认 <root>/报告/YYYY-MM-DD_学习报告.html")
    p.add_argument("--note", help="附加到报告末尾的技术备注")
    p.add_argument("--mathjax", action="store_true", help="引入 CDN MathJax 渲染 LaTeX（需联网）")
    args = p.parse_args(argv)

    root = os.path.normpath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        print("[ERROR] 档案目录不存在：%s" % root, file=sys.stderr)
        print("        请先运行 create_archive.py 初始化档案。", file=sys.stderr)
        return RET_ERROR

    ctx = build_context(root)
    content = render(ctx, note=args.note, use_mathjax=args.mathjax)

    out = args.out
    if not out:
        out = os.path.join(root, "报告", "%s_学习报告.html" % datetime.date.today().isoformat())
    out = os.path.normpath(os.path.expanduser(out))
    try:
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        print("[ERROR] 写入报告失败：%s（%s）" % (out, exc), file=sys.stderr)
        return RET_ERROR

    print("[OK] 学习报告已生成：%s" % out)
    print("     已学章节 %d/%d · 错题 %d 道 · 练习正确率 %s"
          % (ctx["studied"], ctx["total_chapters"], len(ctx["wrong"]),
             "—" if ctx["accuracy"] is None else "%.0f%%" % ctx["accuracy"]))
    if not ctx["has_profile"]:
        print("     提示：未找到 学生档案.md，报告信息较少。")
    return RET_OK


if __name__ == "__main__":
    sys.exit(main())
