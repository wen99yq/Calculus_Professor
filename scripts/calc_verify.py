#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calculus-professor 验算脚本。

用 sympy 对导数 / 积分 / 极限 / 泰勒展开 / 方程求解等结果做符号验算，
保证助教出题与批改不出错。

特点:
  * 自动探测可用的 Python + sympy 环境（含常见 WorkBuddy 托管路径与 venv），
    探测到时自动重新执行，无需任何预先配置。
  * 探测失败时以退出码 2 结束，并打印明确的降级提示，方便调用方如实告知用户。

用法示例:
  python calc_verify.py --op diff      --expr "x^3*sin(x)" --var x
  python calc_verify.py --op integral  --expr "x*exp(x)"  --var x
  python calc_verify.py --op defint    --expr "sin(x)" --var x --from 0 --to "pi/2"
  python calc_verify.py --op limit     --expr "sin(x)/x" --var x --to 0
  python calc_verify.py --op taylor    --expr "exp(x)"   --var x --at 0 --order 4
  python calc_verify.py --op solve     --expr "x^2-3*x+2" --var x
  python calc_verify.py --op check-integral --expr "x*exp(x)" --antiderivative "(x-1)*exp(x)"
  python calc_verify.py --op check-derivative --expr "x^3" --derivative "3*x^2"
  python calc_verify.py --op simplify  --expr "(x^2-1)/(x-1)" --var x
  python calc_verify.py --op evaluate  --expr "sin(x)/x" --var x --at 0.001
"""

import argparse
import json
import os
import subprocess
import sys

RET_OK = 0
RET_ERROR = 1
RET_NO_SYMPY = 2
_RETRY_FLAG = "CALC_VERIFY_REEXEC"


# --------------------------------------------------------------------------
# 环境探测：找到带 sympy 的解释器
# --------------------------------------------------------------------------
def _looks_like_interpreter(path):
    if not path or not os.path.isfile(path):
        return False
    base = os.path.basename(path).lower()
    return base in ("python", "python.exe", "python3", "python3.exe", "pythonw.exe")


def _candidate_interpreters():
    seen = []
    home = os.path.expanduser("~")

    def add(p):
        if p:
            p = os.path.normpath(p)
            if p not in seen:
                seen.append(p)

    add(sys.executable)

    roots = [
        os.path.join(home, ".workbuddy", "binaries", "python"),
        os.path.join(home, "AppData", "Local", "Programs", "Python"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
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

    for names in (("python3", "python"),) if os.name != "nt" else (("python", "python3"),):
        for name in names:
            for d in os.environ.get("PATH", "").split(os.pathsep):
                add(os.path.join(d, name))

    for fixed in ("/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"):
        add(fixed)

    return [p for p in seen if _looks_like_interpreter(p)]


def _has_sympy(interpreter):
    try:
        proc = subprocess.run(
            [interpreter, "-c", "import sympy"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _try_reexec_with_sympy():
    """当前解释器没有 sympy 时，尝试找一个有 sympy 的解释器重新执行本脚本。"""
    if os.environ.get(_RETRY_FLAG) == "1":
        return False
    for cand in _candidate_interpreters():
        if os.path.normpath(cand) == os.path.normpath(sys.executable):
            continue
        if not _has_sympy(cand):
            continue
        env = dict(os.environ)
        env[_RETRY_FLAG] = "1"
        try:
            proc = subprocess.run([cand, os.path.abspath(__file__)] + sys.argv[1:], env=env)
            sys.exit(proc.returncode)
        except Exception:
            continue
    return False


def _load_sympy():
    try:
        import sympy  # noqa: F401
    except ImportError:
        if _try_reexec_with_sympy():
            sys.exit(RET_NO_SYMPY)
        print("[FALLBACK] 未找到可用的 sympy 环境，无法进行符号验算。", file=sys.stderr)
        print("           请改用另一种方式自查（例如对积分结果求导看是否还原），", file=sys.stderr)
        print("           并在回复中如实说明本次未做机器验算。", file=sys.stderr)
        sys.exit(RET_NO_SYMPY)


# --------------------------------------------------------------------------
# 表达式解析
# --------------------------------------------------------------------------
def _build_parser(sympy):
    from sympy.parsing.sympy_parser import (
        parse_expr,
        standard_transformations,
        implicit_multiplication_application,
        convert_xor,
    )

    transformations = standard_transformations + (convert_xor, implicit_multiplication_application)
    local_dict = {
        "e": sympy.E,
        "E": sympy.E,
        "pi": sympy.pi,
        "Pi": sympy.pi,
        "PI": sympy.pi,
        "oo": sympy.oo,
        "inf": sympy.oo,
        "infty": sympy.oo,
        "infinity": sympy.oo,
        "ln": sympy.log,
        "lg": lambda a: sympy.log(a, 10),
        "log10": lambda a: sympy.log(a, 10),
        "arcsin": sympy.asin,
        "arccos": sympy.acos,
        "arctan": sympy.atan,
        "arcsinh": sympy.asinh,
        "arccosh": sympy.acosh,
        "arctanh": sympy.atanh,
    }

    def parse(text, extra_symbols=()):
        return parse_expr(
            text.replace("\u222b", "").replace("\uff5c", "|"),
            local_dict=dict(local_dict),
            transformations=transformations,
            evaluate=True,
        )

    return parse, local_dict


def _to_sympy_expr(sympy, text, var_name, parse):
    """把用户输入转成 sympy 表达式，并保证主变量存在。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("表达式为空")
    text = text.replace("^", "**")
    expr = parse(text)
    var = sympy.Symbol(var_name)
    return expr, var


# --------------------------------------------------------------------------
# 各运算实现
# --------------------------------------------------------------------------
def op_diff(sympy, args, ctx):
    expr, var = ctx
    order = int(args.order or 1)
    res = sympy.diff(expr, var, order)
    return {"结果": res, "化简": sympy.simplify(res)}


def op_integral(sympy, args, ctx):
    expr, var = ctx
    res = sympy.integrate(expr, var)
    info = {}
    if res.has(sympy.Integral):
        info["提示"] = "sympy 未能求出初等原函数，该积分可能不可积为初等函数"
    else:
        info["检验"] = "对结果求导是否还原：" + (
            "是" if sympy.simplify(sympy.diff(res, var) - expr) == 0 else "待人工确认"
        )
    return {"结果": res, **info}


def op_defint(sympy, args, ctx):
    expr, var = ctx
    if args.__dict__.get("frm") is None or args.to is None:
        raise ValueError("定积分需要同时给出 --from 与 --to")
    a = sympy.sympify(args.__dict__["frm"], locals={"pi": sympy.pi, "e": sympy.E, "oo": sympy.oo})
    b = sympy.sympify(args.to, locals={"pi": sympy.pi, "e": sympy.E, "oo": sympy.oo})
    res = sympy.integrate(expr, (var, a, b))
    data = {"积分值": res, "数值": res.evalf(10) if res.is_number else None}
    if res.has(sympy.Integral) or res.has(sympy.oo) or res.has(sympy.zoo) or res.has(sympy.nan):
        data["提示"] = "结果含无穷或未求出，可能是广义积分发散，请人工确认收敛性"
    return data


def op_limit(sympy, args, ctx):
    expr, var = ctx
    if args.to is None:
        raise ValueError("求极限需要给出 --to（可为 0, oo, -oo 等）")
    to = sympy.sympify(args.to, locals={"pi": sympy.pi, "e": sympy.E, "oo": sympy.oo, "-oo": -sympy.oo})
    direction = args.direction or "+-"
    if direction in ("+-", "both"):
        res = sympy.limit(expr, var, to)
        extra = {}
        left = sympy.limit(expr, var, to, "-")
        right = sympy.limit(expr, var, to, "+")
        extra["左极限"] = left
        extra["右极限"] = right
        extra["结论"] = "左右极限相等，极限存在" if sympy.simplify(left - right) == 0 else "左右极限不等，极限不存在"
        return {"极限": res, **extra}
    res = sympy.limit(expr, var, to, direction)
    return {"极限": res}


def op_taylor(sympy, args, ctx):
    expr, var = ctx
    at = sympy.sympify(args.at or "0", locals={"pi": sympy.pi, "e": sympy.E})
    order = int(args.order or 5)
    return {
        "展开式": sympy.series(expr, var, at, order + 1).removeO(),
        "带余项形式": sympy.series(expr, var, at, order + 1),
    }


def op_solve(sympy, args, ctx):
    expr, var = ctx
    sols = sympy.solve(sympy.Eq(expr, 0), var)
    return {"解": sols, "解的个数": len(sols)}


def op_simplify(sympy, args, ctx):
    expr, var = ctx
    return {"化简": sympy.simplify(expr), "展开": sympy.expand(expr)}


def op_factor(sympy, args, ctx):
    expr, var = ctx
    return {"因式分解": sympy.factor(expr)}


def op_evaluate(sympy, args, ctx):
    expr, var = ctx
    if args.at is None:
        raise ValueError("数值计算需要给出 --at")
    at = sympy.sympify(args.at, locals={"pi": sympy.pi, "e": sympy.E})
    return {"值": sympy.simplify(expr.subs(var, at)), "数值": expr.subs(var, at).evalf(12)}


def op_check_integral(sympy, args, ctx):
    expr, var = ctx
    if not args.antiderivative:
        raise ValueError("需要给出 --antiderivative")
    f = parse_expr_safe(sympy, args.antiderivative)
    diff = sympy.simplify(sympy.diff(f, var) - expr)
    ok = diff == 0
    return {
        "被积函数": expr,
        "所给原函数": f,
        "导数": sympy.diff(f, var),
        "差值（导数 - 被积函数）": diff,
        "结论": "✅ 正确（相差常数意义下相等）" if ok else "❌ 不正确",
    }


def op_check_derivative(sympy, args, ctx):
    expr, var = ctx
    if not args.derivative:
        raise ValueError("需要给出 --derivative")
    g = parse_expr_safe(sympy, args.derivative)
    diff = sympy.simplify(sympy.diff(expr, var) - g)
    return {
        "原函数": expr,
        "所给导数": g,
        "实际导数": sympy.diff(expr, var),
        "差值": diff,
        "结论": "✅ 正确" if diff == 0 else "❌ 不正确",
    }


OPS = {
    "diff": op_diff,
    "integral": op_integral,
    "defint": op_defint,
    "limit": op_limit,
    "taylor": op_taylor,
    "solve": op_solve,
    "simplify": op_simplify,
    "factor": op_factor,
    "evaluate": op_evaluate,
    "check-integral": op_check_integral,
    "check-derivative": op_check_derivative,
}

_GLOBAL_PARSE = None


def parse_expr_safe(sympy, text):
    global _GLOBAL_PARSE
    if _GLOBAL_PARSE is None:
        _GLOBAL_PARSE, _ = _build_parser(sympy)
    return _GLOBAL_PARSE(text.replace("^", "**"))


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def build_arg_parser():
    p = argparse.ArgumentParser(
        prog="calc_verify.py",
        description="calculus-professor 微积分验算工具（sympy）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--op", required=True, choices=sorted(OPS.keys()), help="运算类型")
    p.add_argument("--expr", required=True, help="表达式，如 x^3*sin(x)")
    p.add_argument("--var", default="x", help="主变量，默认 x")
    p.add_argument("--from", dest="frm", help="定积分下限（defint）")
    p.add_argument("--to", help="定积分上限 / 极限趋近值")
    p.add_argument("--at", help="泰勒展开点或求值点")
    p.add_argument("--order", help="阶数（diff 的阶 / taylor 的项数）")
    p.add_argument("--direction", help="极限方向：+、-、+-（默认 +-）")
    p.add_argument("--antiderivative", help="check-integral：待检验的原函数")
    p.add_argument("--derivative", help="check-derivative：待检验的导数")
    p.add_argument("--latex", action="store_true", help="额外输出 LaTeX 形式")
    p.add_argument("--json", action="store_true", help="以 JSON 输出（便于程序读取）")
    return p


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    _load_sympy()

    import sympy

    parse, _ = _build_parser(sympy)
    expr, var = _to_sympy_expr(sympy, args.expr, args.var, parse)

    try:
        data = OPS[args.op](sympy, args, (expr, var))
    except ValueError as exc:
        print("参数错误：%s" % exc, file=sys.stderr)
        return RET_ERROR
    except Exception as exc:  # noqa: BLE001
        print("计算失败：%s" % exc, file=sys.stderr)
        return RET_ERROR

    if args.json:
        payload = {}
        for k, v in data.items():
            if v is None:
                continue
            payload[k] = str(v)
        if args.latex:
            payload["latex"] = {
                k: sympy.latex(v) for k, v in data.items() if isinstance(v, sympy.Basic)
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return RET_OK

    print("[op] %s   expr = %s   var = %s" % (args.op, args.expr, args.var))
    print("-" * 56)
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, sympy.Basic):
            print("%s:" % k)
            print("    %s" % sympy.sstr(v))
            if args.latex:
                print("    LaTeX: %s" % sympy.latex(v))
        else:
            print("%s: %s" % (k, v))
    return RET_OK


if __name__ == "__main__":
    sys.exit(main())
