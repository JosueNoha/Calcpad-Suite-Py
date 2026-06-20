# -*- coding: utf-8 -*-
"""Motor de render de Calcpad-Suite-Py: un .py -> HTML formateado como Calcpad.

Usa SOLO stdlib (ast + tokenize). Reglas (ver memoria reference-suite-py-render-design):
  - Asignación  a = b*h         -> auto-render  "a = b·h = 0.15"
  - Inline      a = ...  #noc    -> solo simbólico ;  #val -> solo valor ;  #hide -> oculto (ejecuta)
  - String suelto 'texto' / '''multi''' -> texto / párrafo
  - Comentario  ## titulo / ### subtitulo -> headings ;  '#' a secas -> interno (no se ve)
  - for / if / def / import -> se ejecutan SIN renderizarse (solo lógica)

Uso:  python render_py.py <script.py> [salida.html] [--no-open]
"""
import sys, ast, tokenize, io, html, os


def fmt_val(v):
    """Formatea un valor de Python para mostrar (escalar, lista, ndarray)."""
    try:
        import numpy as np
    except Exception:
        np = None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else f"{round(v, 4):g}"
    if isinstance(v, int):
        return str(v)
    if np is not None and isinstance(v, np.ndarray):
        a = np.round(v, 4)
        if a.ndim == 1:
            return "[ " + "  ".join(fmt_val(float(x)) for x in a) + " ]"
        if a.ndim == 2:
            rows = "".join(
                "<tr>" + "".join(f"<td>{fmt_val(float(x))}</td>" for x in row) + "</tr>" for row in a)
            return f"<table class='mat'>{rows}</table>"
    if isinstance(v, (list, tuple)):
        return "[ " + "  ".join(fmt_val(x) for x in v) + " ]"
    return html.escape(str(v))


def sub_name(name):
    """a_1 -> a<sub>1</sub> ; sigma_xx -> sigma<sub>xx</sub>."""
    if "_" in name:
        base, sub = name.split("_", 1)
        return f"{html.escape(base)}<sub>{html.escape(sub)}</sub>"
    return html.escape(name)


def expr_html(node):
    """AST de expresión -> HTML con formato (·, potencias como superíndice, subíndices)."""
    if isinstance(node, ast.BinOp):
        l, r = expr_html(node.left), expr_html(node.right)
        op = node.op
        if isinstance(op, ast.Mult):
            return f"{l}·{r}"
        if isinstance(op, ast.Div):
            return f"{l}/{r}"
        if isinstance(op, ast.Add):
            return f"{l} + {r}"
        if isinstance(op, ast.Sub):
            return f"{l} − {r}"
        if isinstance(op, ast.Pow):
            return f"{l}<sup>{r}</sup>"
        return f"{l} {r}"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return f"−{expr_html(node.operand)}"
    if isinstance(node, ast.Name):
        return sub_name(node.id)
    if isinstance(node, ast.Constant):
        return fmt_val(node.value)
    if isinstance(node, ast.Call):
        fn = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "f")
        args = "; ".join(expr_html(a) for a in node.args)
        return f"{html.escape(fn)}({args})"
    if isinstance(node, ast.Attribute):
        return html.escape(node.attr)
    try:
        return html.escape(ast.unparse(node).replace("**", "^").replace("*", "·"))
    except Exception:
        return "…"


def render_blocks(path):
    """Devuelve una lista de bloques HTML EN ORDEN DE LÍNEA."""
    code = open(path, encoding="utf-8").read()
    comments = {}
    for t in tokenize.generate_tokens(io.StringIO(code).readline):
        if t.type == tokenize.COMMENT:
            comments[t.start[0]] = t.string.strip()
    tree = ast.parse(code)
    ns = {"__name__": "__main__"}
    events = []   # (linea, html)

    # headings desde comentarios  ## / ###  (1 '#' = interno, no se emite)
    for ln, c in comments.items():
        n_hash = len(c) - len(c.lstrip("#"))
        if n_hash >= 2:
            level = min(n_hash - 1, 4)   # ## -> h1, ### -> h2, #### -> h3
            txt = c.lstrip("#").strip()
            if txt:
                events.append((ln, f'<h{level}>{html.escape(txt)}</h{level}>'))

    # nodos top-level
    for node in tree.body:
        ln0 = node.lineno
        ln1 = getattr(node, "end_lineno", node.lineno)
        # la directiva es el PRIMER token del comentario inline; lo demás es texto que se ignora
        # (ej.  c = a + b  #noc esto es solo un comentario  ->  directiva = "#noc")
        drv_full = comments.get(ln1, "")
        drv = drv_full.split()[0] if drv_full else ""
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                exec(compile(ast.Module([node], type_ignores=[]), "<s>", "exec"), ns)
            except Exception as e:
                events.append((ln0, f'<p class="err">Error línea {ln0}: {html.escape(str(e))}</p>'))
                continue
            if drv == "#hide":
                continue
            name = sub_name(node.targets[0].id)
            formula = expr_html(node.value)
            val = fmt_val(ns.get(node.targets[0].id))
            is_literal = isinstance(node.value, ast.Constant)   # b = 0.30 -> "b = 0.3" (no "0.3 = 0.3")
            if drv == "#noc":
                events.append((ln0, f'<p class="eq">{name} = {formula}</p>'))
            elif drv == "#val" or is_literal:
                events.append((ln0, f'<p class="eq">{name} = {val}</p>'))
            else:
                events.append((ln0, f'<p class="eq">{name} = {formula} = {val}</p>'))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            txt = node.value.value.strip()
            if txt:
                events.append((ln0, f'<p class="txt">{html.escape(txt)}</p>'))
        else:
            # imports, def, for, if, while, expr con efecto: ejecutar SIN renderizar
            try:
                exec(compile(ast.Module([node], type_ignores=[]), "<s>", "exec"), ns)
            except Exception as e:
                events.append((ln0, f'<p class="err">Error línea {ln0}: {html.escape(str(e))}</p>'))

    events.sort(key=lambda x: x[0])
    return [h for _, h in events]


def build_html(path):
    body = "\n".join(render_blocks(path))
    name = os.path.basename(path)
    css = """
    body{font-family:'Times New Roman',serif;max-width:820px;margin:24px auto;padding:0 24px;color:#1a1a1a}
    h1,h2,h3,h4{font-family:Arial,sans-serif;color:#10314f;margin:.9em 0 .3em}
    h1{font-size:1.5em;border-bottom:2px solid #10314f;padding-bottom:4px}
    h2{font-size:1.25em} h3{font-size:1.1em}
    p.txt{margin:.4em 0;line-height:1.5}
    p.eq{font-style:italic;font-size:1.12em;margin:.25em 0}
    p.eq sub,p.eq sup{font-style:normal}
    p.err{color:#b00020;background:#fff0f0;padding:4px 8px;font-family:monospace;font-style:normal}
    table.mat{display:inline-table;border-left:2px solid #333;border-right:2px solid #333;margin:0 4px;vertical-align:middle}
    table.mat td{padding:1px 8px;text-align:right}
    """
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
            f'<title>{html.escape(name)} — Calcpad-Suite-Py</title><style>{css}</style></head>'
            f'<body>{body}</body></html>')


def main():
    args = [a for a in sys.argv[1:] if a != "--no-open"]
    no_open = "--no-open" in sys.argv
    if not args:
        print("uso: python render_py.py <script.py> [salida.html] [--no-open]")
        return 2
    path = args[0]
    out = args[1] if len(args) > 1 else os.path.splitext(path)[0] + ".html"
    open(out, "w", encoding="utf-8").write(build_html(path))
    print("[render_py] HTML:", out)
    if not no_open:
        try:
            os.startfile(out)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
