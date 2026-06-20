# -*- coding: utf-8 -*-
# =============================================================================
#  py_console.py — Consola HTML para ver el script Python de un worksheet
# =============================================================================
#  Genera un HTML legible (números de línea + resaltado de sintaxis básico) a
#  partir de un archivo .py, para revisar EXACTAMENTE qué script se ejecuta en
#  Calcpad Suite Py. Sin dependencias (solo stdlib).
#
#  Uso:
#     python py_console.py "ruta/al/script.py" [salida.html]
#  Si no se da salida, crea <script>.console.html al lado y lo abre.
# =============================================================================
import sys, os, html, re, webbrowser, subprocess

IMG_MARKER = "__CPSPY_IMG__:"


def render_with_cli(path):
    """Genera el HTML REAL de Calcpad Suite Py (con template.html) vía el CLI.
    Devuelve la ruta del .html generado, o None si no se encuentra el CLI."""
    here = os.path.dirname(os.path.abspath(__file__))
    cli = os.path.abspath(os.path.join(
        here, "..", "Symbolic.Cli", "bin", "Debug", "net10.0", "CalcpadSuitePyCli.exe"))
    if not os.path.isfile(cli):
        return None
    apath = os.path.abspath(path)
    out_html = os.path.splitext(apath)[0] + ".html"
    try:
        subprocess.run([cli, apath, "html", "-s"], capture_output=True, timeout=300)
    except Exception:
        return None
    return out_html if os.path.isfile(out_html) else None


def render_output(path):
    """Ejecuta el script con python real y renderiza su salida igual que Calcpad
    Suite Py: texto como bloque pre, y __CPSPY_IMG__:<base64> como <img>."""
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", path],
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
    except Exception as e:
        return f'<pre class="err">No se pudo ejecutar: {html.escape(str(e))}</pre>'
    parts, buf = [], []

    def flush():
        if buf:
            t = "".join(buf).rstrip("\n")
            if t.strip():
                parts.append(f'<pre class="out">{html.escape(t)}</pre>')
            buf.clear()

    for ln in (r.stdout or "").replace("\r\n", "\n").split("\n"):
        if ln.startswith(IMG_MARKER):
            flush()
            b64 = ln[len(IMG_MARKER):].strip()
            if b64:
                parts.append(f'<img class="fig" src="data:image/png;base64,{b64}"/>')
        else:
            buf.append(ln + "\n")
    flush()
    if r.returncode != 0 and (r.stderr or "").strip():
        parts.append(f'<pre class="err">{html.escape(r.stderr)}</pre>')
    return "\n".join(parts) or '<pre class="out">(sin salida)</pre>'

KEYWORDS = {
    "False","None","True","and","as","assert","async","await","break","class",
    "continue","def","del","elif","else","except","finally","for","from","global",
    "if","import","in","is","lambda","nonlocal","not","or","pass","raise","return",
    "try","while","with","yield","match","case",
}
BUILTINS = {
    "print","range","len","abs","min","max","sum","round","int","float","str","bool",
    "list","tuple","dict","set","sorted","reversed","enumerate","zip","map","filter",
    "any","all","type","isinstance","repr","open","np","plt","matplotlib","io","base64",
}

def highlight_line(line):
    """Resalta una línea de Python a HTML (comentarios, strings, keywords, números)."""
    out = []
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        # comentario
        if c == "#":
            out.append(f'<span class="c">{html.escape(line[i:])}</span>')
            break
        # string (simple/triple)
        if c in "\"'":
            quote = c
            triple = line[i:i+3] in ('"""', "'''")
            q = line[i:i+3] if triple else c
            j = i + len(q)
            while j < n:
                if line[j] == "\\":
                    j += 2; continue
                if line[j:j+len(q)] == q:
                    j += len(q); break
                j += 1
            out.append(f'<span class="s">{html.escape(line[i:j])}</span>')
            i = j
            continue
        # identificador / keyword
        if c.isalpha() or c == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            cls = "k" if word in KEYWORDS else ("b" if word in BUILTINS else None)
            out.append(f'<span class="{cls}">{html.escape(word)}</span>' if cls else html.escape(word))
            i = j
            continue
        # número
        if c.isdigit():
            j = i
            while j < n and (line[j].isalnum() or line[j] in "._"):
                j += 1
            out.append(f'<span class="n">{html.escape(line[i:j])}</span>')
            i = j
            continue
        out.append(html.escape(c))
        i += 1
    return "".join(out)


def build_html(path, run=False):
    src = open(path, encoding="utf-8").read().replace("\r\n", "\n").split("\n")
    name = os.path.basename(path)
    rows = []
    for k, line in enumerate(src, 1):
        rows.append(
            f'<tr><td class="ln">{k}</td><td class="code">{highlight_line(line) or "&nbsp;"}</td></tr>'
        )
    body = "\n".join(rows)
    cli_html = render_with_cli(path) if run else None
    output_html = "" if (not run or cli_html) else render_output(path)
    css = """
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:#1e1e1e;color:#d4d4d4;font-family:Consolas,'Cascadia Code',monospace}
    header{position:sticky;top:0;background:#252526;border-bottom:1px solid #333;padding:10px 16px;
           display:flex;align-items:center;gap:12px;z-index:3}
    header h1{font-size:14px;margin:0;color:#9cdcfe;font-weight:600}
    header .tag{font-size:11px;color:#888}
    header button{margin-left:auto;background:#0e639c;border:0;color:#fff;padding:6px 12px;
                  border-radius:4px;cursor:pointer;font-size:12px}
    .split{display:flex;align-items:stretch;gap:0;height:calc(100vh - 43px)}
    .pane{overflow:auto;flex:1 1 50%;min-width:0}
    .pane.code-pane{border-right:2px solid #333}
    .pane h2{position:sticky;top:0;background:#2d2d30;color:#9cdcfe;font-size:12px;margin:0;
             padding:6px 16px;border-bottom:1px solid #333;font-weight:600}
    table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.55}
    td.ln{user-select:none;text-align:right;color:#5a5a5a;padding:0 12px 0 16px;width:1%;
          white-space:nowrap;border-right:1px solid #2d2d2d}
    td.code{padding:0 16px;white-space:pre}
    tr:hover td.code{background:#2a2d2e}
    .k{color:#569cd6}.b{color:#dcdcaa}.s{color:#ce9178}.c{color:#6a9955;font-style:italic}.n{color:#b5cea8}
    .render{background:#fff;color:#222;min-height:100%}
    .render pre.out{font-family:Consolas,monospace;font-size:13px;white-space:pre-wrap;
                    margin:0;padding:10px 16px;color:#1a1a1a}
    .render pre.err{color:#b00020;background:#fff0f0;padding:10px 16px;white-space:pre-wrap;margin:0}
    .render img.fig{display:block;max-width:100%;height:auto;margin:8px auto;border:1px solid #eee}
    iframe.renderframe{width:100%;height:calc(100vh - 76px);border:0;background:#fff;display:block}
    """
    if run:
        if cli_html:
            src_uri = "file:///" + cli_html.replace("\\", "/")
            out_pane = f'<iframe class="renderframe" src="{src_uri}"></iframe>'
            sub = "render real con template.html (CLI)"
        else:
            out_pane = f'<div class="render">{output_html}</div>'
            sub = "render simple (CLI no encontrado — compilá el CLI para el template real)"
        layout = f"""<div class="split">
  <div class="pane code-pane"><h2>📄 Código Python</h2><table id="src">{body}</table></div>
  <div class="pane"><h2>▶ Salida — {sub}</h2>{out_pane}</div>
</div>"""
        tag = f"{len(src)} líneas · código + salida renderizada"
    else:
        layout = f'<table id="src">{body}</table>'
        tag = f"{len(src)} líneas · script ejecutado por Calcpad Suite Py"
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>Consola Python — {html.escape(name)}</title><style>{css}</style></head>
<body>
<header>
  <h1>🐍 {html.escape(name)}</h1>
  <span class="tag">{tag}</span>
  <button onclick="navigator.clipboard.writeText(document.getElementById('src').innerText)">Copiar código</button>
</header>
{layout}
</body></html>"""


def main():
    args = [a for a in sys.argv[1:]]
    run = "--run" in args
    args = [a for a in args if a != "--run"]
    if not args:
        print("Uso: python py_console.py <script.py> [salida.html] [--run]")
        print("  --run : ejecuta el script y muestra código + salida renderizada")
        return 1
    path = args[0]
    if not os.path.isfile(path):
        print("No existe:", path); return 1
    out = args[1] if len(args) > 1 else os.path.splitext(path)[0] + (".run.html" if run else ".console.html")
    open(out, "w", encoding="utf-8").write(build_html(path, run=run))
    print("Consola generada:", out)
    try:
        webbrowser.open("file:///" + os.path.abspath(out).replace("\\", "/"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
