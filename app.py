# app.py
import os
from pathlib import Path
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    send_from_directory, flash, abort, get_flashed_messages, jsonify
)
from werkzeug.utils import secure_filename, safe_join
from datetime import datetime
from prometheus_flask_exporter import PrometheusMetrics

# --- Config ----------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "storage"
UPLOAD_DIR.mkdir(exist_ok=True)

API_KEY = os.getenv("API_KEY", "")

EDITABLE_EXTS = {".txt", ".md", ".json", ".csv", ".py", ".html", ".css", ".js"}
PREVIEW_IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
PREVIEW_PDF_EXTS = {".pdf"}

MAX_EDIT_BYTES = 1_000_000  # 1 MB para edição inline
MAX_UPLOAD_MB = 100
ALLOWED_EXTS = None  # None = aceitar tudo

app = Flask(__name__)
app.secret_key = "dev"
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
metrics = PrometheusMetrics(app)

# --- Helpers ---------------------------------------------------
def is_allowed(filename: str) -> bool:
    return True if ALLOWED_EXTS is None else Path(filename).suffix.lower() in ALLOWED_EXTS

def is_editable(path: Path) -> bool:
    return path.suffix.lower() in EDITABLE_EXTS and path.is_file() and path.stat().st_size <= MAX_EDIT_BYTES

def list_files():
    return sorted([p.name for p in UPLOAD_DIR.iterdir() if p.is_file()], key=str.casefold)

def total_space_bytes() -> int:
    return sum((p.stat().st_size for p in UPLOAD_DIR.iterdir() if p.is_file()), start=0)

def existing_file_path(name: str) -> Path:
    joined = safe_join(str(UPLOAD_DIR), name)
    if not joined:
        abort(400)
    p = Path(joined)
    if not p.exists() or not p.is_file():
        abort(404)
    if p.resolve().parent != UPLOAD_DIR.resolve():
        abort(400)
    return p

# --- Templates -------------------------------------------------
BASE_HTML = """
<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <title>UM Drive</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { --bg:#0b0d12; --card:#121620; --muted:#a3adbf; --line:#1e2431; --btn:#1f6feb; --btnh:#2b7cff; }
    *{box-sizing:border-box}
    body { margin:0; background:var(--bg); color:#e6edf3; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    header { padding:20px 24px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:center; }
    .brand { font-weight:800; letter-spacing:.2px; font-size:28px; }
    main { max-width:980px; margin:24px auto; padding:0 16px; display:grid; gap:16px; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:16px; }
    .upload { padding:16px; display:grid; gap:12px; }
    .drop {
      border:1.5px dashed #2b3242; border-radius:12px;
      padding:24px; min-height:180px; text-align:center; color:var(--muted); transition:.2s;
      display:grid; place-items:center; gap:12px;
    }
    .drop.dragover { border-color:var(--btn); color:#e6edf3; background:#0f1420; }
    .actions { display:flex; gap:8px; justify-content:center; }
    .btn { appearance:none; border:1px solid #284a9b; background:var(--btn); color:white; padding:10px 14px; border-radius:10px; cursor:pointer; font-weight:600; }
    .btn:hover { background:var(--btnh); }
    .muted { color:var(--muted); font-size:12px; }
    .list { overflow: hidden; }
    table { width:100%; border-collapse: collapse; }
    th, td { padding:12px 14px; border-top:1px solid var(--line); }
    thead th { text-transform: uppercase; letter-spacing:.08em; font-size:12px; color:var(--muted); border-top:none; }
    tbody tr:hover { background:#0f1420; }
    a.link { color:#e6edf3; text-decoration:none; }
    a.link:hover { text-decoration:underline; }
    .row-actions { display:flex; gap:8px; justify-content:flex-end; align-items:center;}
    .btn-secondary { border:1px solid #3a4458; background:#1a2333; }
    .btn-secondary:hover { background:#23314a; }
    .btn-danger { border:1px solid #6b2737; background:#8b1e2d; }
    .btn-danger:hover { background:#a62234; }
    .btn-icon { background:#1a2333; border:1px solid #3a4458; border-radius:8px; width:36px; height:36px; display:inline-grid; place-items:center; cursor:pointer; }
    .btn-icon:hover { background:#23314a; }
    .icon { font-style: normal; }
    .name-cell { display:flex; align-items:center; gap:10px; }
    .name-cell form { display:none; gap:8px; }
    .name-cell input[type="text"] { background:#0f1420; color:#e6edf3; border:1px solid var(--line); border-radius:8px; padding:6px 8px; min-width:220px; }
    .flash { margin:0 16px; padding:10px 12px; border-radius:10px; border:1px solid #2a364b; background:#0f1624; }
    .hidden { display:none; }
    dialog { border:none; border-radius:16px; padding:0; background:#0f1420; color:#e6edf3; width:min(920px, 96vw); }
    .modal-head { padding:12px 16px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:center; }
    .modal-body { padding:0; }
    .modal-body iframe, .modal-body img { width:100%; height:75vh; display:block; border:0; background:#0b0d12; }
    .close { background:#1a2333; border:1px solid #3a4458; border-radius:8px; padding:8px 10px; cursor:pointer; }
    .topbar { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; }
    .count { font-size:13px; color:var(--muted); }
    .preview-list { width:100%; display:grid; gap:10px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    .preview-item { border:1px solid #2b3242; border-radius:12px; padding:10px; background:#0f1420; }
    .preview-item .meta { font-size:12px; color:#a3adbf; margin-bottom:8px; }
    .preview-item img { width:100%; height:140px; object-fit:cover; border-radius:8px; display:block; }
    .badge { display:inline-block; font-size:12px; padding:2px 6px; border:1px solid #3a4458; border-radius:6px; }
    @media (max-width:640px){ .row-actions{justify-content:flex-start; flex-wrap:wrap} td:nth-child(2){display:none} .name-cell input[type="text"]{min-width:140px} }
  </style>
</head>
<body>
  <header>
    <div class="brand">UM Drive</div>
  </header>

  {% if messages %}
    <div class="flash">
      {% for cat,msg in messages %}
        <div>{{ msg }}</div>
      {% endfor %}
    </div>
  {% endif %}

  <main>
    {% block content %}{% endblock %}
  </main>

  <dialog id="previewModal">
    <div class="modal-head">
      <div id="previewTitle"></div>
      <button class="close" onclick="closePreview()">Fechar</button>
    </div>
    <div class="modal-body" id="previewBody"></div>
  </dialog>

  <script>
    function formatBytes(bytes){
      if(bytes === 0) return "0 B";
      const k=1024, sizes=["B","KB","MB","GB","TB"];
      const i=Math.floor(Math.log(bytes)/Math.log(k));
      return (bytes/Math.pow(k,i)).toFixed(1)+" "+sizes[i];
    }

    // drag & drop + preview múltiplo
    const drop = document.querySelector('.drop');
    if (drop) {
      const fileInput = document.getElementById('filesInput');
      const previewList = document.getElementById('previewList');

      function renderPreview(fileList){
        previewList.innerHTML = '';
        if (!fileList || fileList.length === 0){
          previewList.innerHTML = '<div class="muted">Nenhum ficheiro selecionado</div>';
          return;
        }
        [...fileList].forEach(f => {
          const card = document.createElement('div');
          card.className = 'preview-item';
          const meta = document.createElement('div');
          meta.className = 'meta';
          meta.textContent = f.name + ' • ' + formatBytes(f.size);
          card.appendChild(meta);
          if (f.type && f.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(f);
            img.onload = () => URL.revokeObjectURL(img.src);
            card.appendChild(img);
          } else {
            const badge = document.createElement('span');
            badge.className = 'badge';
            badge.textContent = f.type || 'Ficheiro';
            card.appendChild(badge);
          }
          previewList.appendChild(card);
        });
      }

      ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); drop.classList.add('dragover'); }));
      ['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); drop.classList.remove('dragover'); }));
      drop.addEventListener('drop', e => {
        if (e.dataTransfer.files && e.dataTransfer.files.length) {
          // usar DataTransfer para conseguir atribuir ao input em todos os browsers
          const dt = new DataTransfer();
          [...e.dataTransfer.files].forEach(f => dt.items.add(f));
          fileInput.files = dt.files;
          renderPreview(fileInput.files);
        }
      });
      drop.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', () => renderPreview(fileInput.files));
    }

    // botão "Adicionar": abre o seletor ou submete se já houver ficheiros
    const addBtn = document.getElementById('addBtn');
    if (addBtn) {
      addBtn.addEventListener('click', () => {
        const fileInput = document.getElementById('filesInput');
        if (!fileInput.files || fileInput.files.length === 0) {
          fileInput.click();
        } else {
          document.getElementById('uploadForm').submit();
        }
      });
    }

    // preview modal
    function openPreview(name, isImg, isPdf, url) {
      const dlg = document.getElementById('previewModal');
      const body = document.getElementById('previewBody');
      const title = document.getElementById('previewTitle');
      title.textContent = name;
      body.innerHTML = '';
      if (isImg) {
        const img = document.createElement('img');
        img.src = url;
        img.alt = name;
        body.appendChild(img);
      } else if (isPdf) {
        const iframe = document.createElement('iframe');
        iframe.src = url + '#view=FitH';
        body.appendChild(iframe);
      } else {
        const div = document.createElement('div');
        div.style.padding = '16px';
        div.innerHTML = 'Sem preview. Usa download.';
        body.appendChild(div);
      }
      dlg.showModal();
    }
    function closePreview() {
      document.getElementById('previewModal').close();
    }

    // inline rename toggle
    function startRename(rowId) {
      const row = document.getElementById(rowId);
      row.querySelector('.name-view').classList.add('hidden');
      row.querySelector('.name-edit').style.display = 'flex';
      row.querySelector('.name-edit input[type="text"]').focus();
    }
    function cancelRename(rowId) {
      const row = document.getElementById(rowId);
      row.querySelector('.name-edit').style.display = 'none';
      row.querySelector('.name-view').classList.remove('hidden');
    }
  </script>
</body>
</html>
"""

HOME_HTML = """
{% extends "base.html" %}
{% block content %}
  <section class="panel upload">
    <div class="topbar">
      <div class="muted">Adicionar ficheiros</div>
      <div class="count">{{ files|length }} ficheiro(s) • {{ total_bytes }} bytes</div>
    </div>
    <form id="uploadForm" method="post" enctype="multipart/form-data" action="{{ url_for('upload_inline') }}">
      <div class="drop">
        <div>Arrasta e larga aqui ou clica para escolher</div>
        <input id="filesInput" class="hidden" type="file" name="files" multiple required />
        <div id="previewList" class="preview-list">
          <div class="muted">Nenhum ficheiro selecionado</div>
        </div>
      </div>
      <div class="actions">
        <button class="btn" type="button" id="addBtn">Adicionar</button>
      </div>
      <div class="muted">Limite {{ max_mb }} MB por ficheiro.</div>
    </form>
  </section>

  <section class="panel list">
    <div class="topbar">
      <div class="muted">Ficheiros</div>
    </div>
    {% if files %}
    <table>
      <thead>
        <tr>
          <th>Nome</th>
          <th>Tamanho</th>
          <th style="width:260px; text-align:right;">Ações</th>
        </tr>
      </thead>
      <tbody>
        {% for f in files %}
        {% set fpath = (upload_dir / f) %}
        {% set ext = fpath.suffix.lower() %}
        {% set is_img = ext in preview_img_exts %}
        {% set is_pdf = ext in preview_pdf_exts %}
        {% set row_id = "row_" ~ loop.index %}
        <tr id="{{ row_id }}">
          <td class="name-cell">
            <div class="name-view">
              <a class="link" href="#" onclick="openPreview('{{ f }}', {{ 'true' if is_img else 'false' }}, {{ 'true' if is_pdf else 'false' }}, '{{ url_for('view_inline', name=f) }}'); return false;">{{ f }}</a>
            </div>
            <form class="name-edit" method="post" action="{{ url_for('rename', name=f) }}">
              <input type="text" name="new_name" value="{{ f }}" required />
              <button class="btn" type="submit">Guardar</button>
              <button class="btn btn-secondary" type="button" onclick="cancelRename('{{ row_id }}')">Cancelar</button>
            </form>
          </td>
          <td>{{ fpath.stat().st_size }} bytes</td>
          <td>
            <div class="row-actions">
              <a class="btn btn-secondary" href="{{ url_for('download', name=f) }}" title="Download">Download</a>
              {% if ext in editable_exts and fpath.stat().st_size <= max_edit %}
                <a class="btn btn-secondary" href="{{ url_for('edit', name=f) }}" title="Editar">Editar</a>
              {% else %}
                <a class="btn btn-secondary" href="{{ url_for('replace', name=f) }}" title="Substituir">Substituir</a>
              {% endif %}
              <button class="btn-icon" title="Renomear" onclick="startRename('{{ row_id }}')"><span class="icon">✏️</span></button>
              <form class="inline" method="post" action="{{ url_for('delete', name=f) }}" onsubmit="return confirm('Remover {{ f }}?');">
                <button class="btn btn-danger" type="submit">Remover</button>
              </form>
            </div>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
      <div style="padding:16px; color:#a3adbf;">Sem ficheiros ainda.</div>
    {% endif %}
  </section>
{% endblock %}
"""

EDIT_HTML = """
{% extends "base.html" %}
{% block content %}
  <section class="panel" style="padding:16px;">
    <div class="topbar">
      <div>Editar: {{ name }}</div>
      <div class="muted">Texto até {{ max_mb }} MB</div>
    </div>
    <form method="post">
      <textarea name="content" required>{{ content }}</textarea>
      <div class="actions" style="margin-top:12px;">
        <button class="btn" type="submit">Guardar</button>
        <a class="btn btn-secondary" href="{{ url_for('home') }}">Cancelar</a>
      </div>
    </form>
  </section>
{% endblock %}
"""

REPLACE_HTML = """
{% extends "base.html" %}
{% block content %}
  <section class="panel upload">
    <div class="topbar">
      <div>Substituir: {{ name }}</div>
    </div>
    <form method="post" enctype="multipart/form-data">
      <div class="drop" onclick="document.querySelector('#file2').click()">Clica para escolher novo ficheiro</div>
      <input id="file2" class="hidden" type="file" name="file" required />
      <div class="actions"><button class="btn" type="submit">Substituir</button></div>
    </form>
  </section>
{% endblock %}
"""

# --- Rotas -----------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    messages = get_flashed_messages(with_categories=True)
    return render_template_string(
        HOME_HTML,
        files=list_files(),
        upload_dir=UPLOAD_DIR,
        editable_exts=EDITABLE_EXTS,
        preview_img_exts=PREVIEW_IMG_EXTS,
        preview_pdf_exts=PREVIEW_PDF_EXTS,
        max_edit=MAX_EDIT_BYTES,
        max_mb=MAX_UPLOAD_MB,
        total_bytes=total_space_bytes(),
        messages=messages
    )

@app.route("/upload-inline", methods=["POST"])
def upload_inline():
    files = request.files.getlist("files")
    if not files:
        flash("Nenhum ficheiro.", "error"); return redirect(url_for("home"))

    saved = []
    for f in files:
        if not f or f.filename == "":
            continue
        if not is_allowed(f.filename):
            continue
        base_name = secure_filename(f.filename)
        dest = UPLOAD_DIR / base_name
        base, ext = os.path.splitext(base_name)
        i = 1
        while dest.exists():
            candidate = f"{base}_{i}{ext}"
            dest = UPLOAD_DIR / candidate
            i += 1
        f.save(dest)
        saved.append(dest.name)

    if not saved:
        flash("Nenhum ficheiro válido para adicionar.", "error")
    else:
        if len(saved) == 1:
            flash(f"Ficheiro adicionado: {saved[0]}")
        else:
            preview = ", ".join(saved[:3]) + ("..." if len(saved) > 3 else "")
            flash(f"{len(saved)} ficheiros adicionados: {preview}")
    return redirect(url_for("home"))

# ------- DOWNLOAD & VIEW --------
@app.route("/download/<path:name>")
def download(name):
    return send_from_directory(UPLOAD_DIR, name, as_attachment=True)

@app.route("/view/<path:name>")
def view_inline(name):
    return send_from_directory(UPLOAD_DIR, name, as_attachment=False)

# ------- EDIT / REPLACE / RENAME / DELETE --------
@app.route("/edit/<path:name>", methods=["GET","POST"])
def edit(name):
    path = existing_file_path(name)
    if not is_editable(path):
        flash("Não editável no browser. Usa Substituir.", "error")
        return redirect(url_for("home"))
    if request.method == "POST":
        content = request.form.get("content","")
        path.write_text(content, encoding="utf-8")
        flash("Guardado.")
        return redirect(url_for("home"))
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        flash("Encoding inválido para edição.", "error")
        return redirect(url_for("home"))
    return render_template_string(EDIT_HTML, name=path.name, content=content, max_mb=MAX_EDIT_BYTES//1024//1024)

@app.route("/replace/<path:name>", methods=["GET","POST"])
def replace(name):
    path = existing_file_path(name)
    if request.method == "POST":
        if "file" not in request.files or request.files["file"].filename == "":
            flash("Escolhe um ficheiro.", "error"); return redirect(request.url)
        request.files["file"].save(path)
        flash("Conteúdo substituído.")
        return redirect(url_for("home"))
    return render_template_string(REPLACE_HTML, name=path.name)

@app.route("/rename/<path:name>", methods=["POST"])
def rename(name):
    src = existing_file_path(name)
    new_name = request.form.get("new_name","").strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        flash("Novo nome inválido.", "error"); return redirect(url_for("home"))
    dst = UPLOAD_DIR / new_name
    if dst.exists():
        flash("Já existe um ficheiro com esse nome.", "error"); return redirect(url_for("home"))
    src.rename(dst)
    flash("Renomeado.")
    return redirect(url_for("home"))

@app.route("/delete/<path:name>", methods=["POST"])
def delete(name):
    try:
        path = existing_file_path(name)
    except Exception:
        flash("Ficheiro não encontrado.", "error")
        return redirect(url_for("home"))
    path.unlink()
    flash("Removido.")
    return redirect(url_for("home"))

@app.route("/health")
def health(): return {"status":"ok"}

def _require_api_key():
    if not API_KEY:
        return None
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    return None

def _file_info(p: Path):
    st = p.stat()
    return {
        "name": p.name,
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "editable": is_editable(p),
        "download": url_for("download", name=p.name, _external=False),
        "view": url_for("view_inline", name=p.name, _external=False),
    }

@app.get("/api/files")
def api_files_list():
    auth = _require_api_key()
    if auth: return auth
    items = [_file_info((UPLOAD_DIR / n)) for n in list_files()]
    return jsonify({"ok": True, "files": items})

@app.post("/api/upload")
def api_files_upload():
    auth = _require_api_key()
    if auth: return auth
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "no files"}), 400
    saved = []
    for f in files:
        if not f or not f.filename: continue
        base_name = secure_filename(f.filename)
        dest = UPLOAD_DIR / base_name
        base, ext = os.path.splitext(base_name); i = 1
        while dest.exists():
            dest = UPLOAD_DIR / f"{base}_{i}{ext}"; i += 1
        f.save(dest)
        saved.append(dest.name)
    return jsonify({"ok": True, "saved": saved})

@app.delete("/api/files/<path:name>")
def api_files_delete(name):
    auth = _require_api_key()
    if auth: return auth
    try:
        existing_file_path(name).unlink()
    except Exception:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})

@app.post("/api/files/<path:name>/rename")
def api_files_rename(name):
    auth = _require_api_key()
    if auth: return auth
    data = request.get_json(silent=True) or request.form
    new_name = (data.get("new_name") or "").strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        return jsonify({"ok": False, "error": "invalid new_name"}), 400
    src = existing_file_path(name)
    dst = UPLOAD_DIR / new_name
    if dst.exists():
        return jsonify({"ok": False, "error": "exists"}), 409
    src.rename(dst)
    return jsonify({"ok": True, "name": dst.name})

# Registrar templates inline
@app.before_request
def _register_templates():
    from jinja2 import DictLoader
    app.jinja_loader = DictLoader({
        "base.html": BASE_HTML,
        "home.html": HOME_HTML,
        "edit.html": EDIT_HTML,
        "replace.html": REPLACE_HTML,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
