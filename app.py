
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import sqlite3, os, secrets
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
DB = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "afiliado_ia.db"))
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "troque-esta-senha")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        niche TEXT,
        commission REAL DEFAULT 0,
        affiliate_url TEXT NOT NULL,
        status TEXT DEFAULT 'Ativo',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS leads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        whatsapp TEXT,
        product_id INTEGER,
        source TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS clicks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        source TEXT,
        campaign TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        amount REAL DEFAULT 0,
        commission REAL DEFAULT 0,
        source TEXT,
        created_at TEXT NOT NULL
    );
    """)
    con.commit()
    con.close()

@app.context_processor
def inject_now():
    return {"year": datetime.now().year}


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username","")
        password = request.form.get("password","")
        if secrets.compare_digest(user, ADMIN_USER) and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuário ou senha inválidos.")
    return render_template("login.html")

@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    con = db()
    p = con.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    leads = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    clicks = con.execute("SELECT COUNT(*) c FROM clicks").fetchone()["c"]
    sales = con.execute("SELECT COUNT(*) c, COALESCE(SUM(commission),0) commission FROM sales").fetchone()
    best = con.execute("""
        SELECT p.id,p.name,COUNT(c.id) clicks,
               (SELECT COUNT(*) FROM sales s WHERE s.product_id=p.id) sales
        FROM products p LEFT JOIN clicks c ON c.product_id=p.id
        GROUP BY p.id ORDER BY sales DESC, clicks DESC LIMIT 5
    """).fetchall()
    con.close()
    return render_template("dashboard.html", products=p, leads=leads, clicks=clicks,
                           sales=sales["c"], commission=sales["commission"], best=best)

@app.route("/products", methods=["GET","POST"])
@login_required
def products():
    con = db()
    if request.method == "POST":
        name = request.form["name"].strip()
        niche = request.form.get("niche","").strip()
        commission = float(request.form.get("commission") or 0)
        affiliate_url = request.form["affiliate_url"].strip()
        con.execute("INSERT INTO products(name,niche,commission,affiliate_url,created_at) VALUES(?,?,?,?,?)",
                    (name,niche,commission,affiliate_url,datetime.now().isoformat(timespec="seconds")))
        con.commit()
        con.close()
        return redirect(url_for("products"))
    rows = con.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    con.close()
    return render_template("products.html", products=rows)

@app.post("/products/<int:pid>/delete")
@login_required
def delete_product(pid):
    con = db()
    con.execute("DELETE FROM products WHERE id=?", (pid,))
    con.commit(); con.close()
    return redirect(url_for("products"))

@app.route("/landing/<int:pid>")
def landing(pid):
    con = db()
    p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    con.close()
    if not p: return "Produto não encontrado", 404
    return render_template("landing.html", p=p)

@app.post("/lead/<int:pid>")
def add_lead(pid):
    con = db()
    con.execute("INSERT INTO leads(name,email,whatsapp,product_id,source,created_at) VALUES(?,?,?,?,?,?)",
                (request.form.get("name",""), request.form.get("email",""), request.form.get("whatsapp",""),
                 pid, request.form.get("source","landing"), datetime.now().isoformat(timespec="seconds")))
    con.commit(); con.close()
    return redirect(url_for("go", pid=pid, source="lead"))

@app.route("/go/<int:pid>")
def go(pid):
    source = request.args.get("source","direct")
    campaign = request.args.get("campaign","")
    con = db()
    p = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        con.close(); return "Produto não encontrado", 404
    con.execute("INSERT INTO clicks(product_id,source,campaign,created_at) VALUES(?,?,?,?)",
                (pid,source,campaign,datetime.now().isoformat(timespec="seconds")))
    con.commit(); con.close()
    return redirect(p["affiliate_url"])

@app.route("/leads")
@login_required
def leads():
    con = db()
    rows = con.execute("""
        SELECT l.*,p.name product_name FROM leads l
        LEFT JOIN products p ON p.id=l.product_id
        ORDER BY l.id DESC
    """).fetchall()
    con.close()
    return render_template("leads.html", leads=rows)

@app.route("/sales", methods=["GET","POST"])
@login_required
def sales():
    con = db()
    if request.method == "POST":
        con.execute("INSERT INTO sales(product_id,amount,commission,source,created_at) VALUES(?,?,?,?,?)",
                    (int(request.form["product_id"]), float(request.form.get("amount") or 0),
                     float(request.form.get("commission") or 0), request.form.get("source","manual"),
                     datetime.now().isoformat(timespec="seconds")))
        con.commit()
        con.close()
        return redirect(url_for("sales"))
    rows = con.execute("""
        SELECT s.*,p.name product_name FROM sales s
        LEFT JOIN products p ON p.id=s.product_id ORDER BY s.id DESC
    """).fetchall()
    prods = con.execute("SELECT * FROM products ORDER BY name").fetchall()
    con.close()
    return render_template("sales.html", sales=rows, products=prods)

@app.route("/ai")
@login_required
def ai():
    con = db()
    products = con.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    con.close()
    return render_template("ai.html", products=products)

@app.post("/api/ai-copy")
def ai_copy():
    data = request.get_json(force=True)
    name = data.get("name","Produto")
    niche = data.get("niche","")
    # Placeholder local seguro para funcionar sem API externa.
    headline = f"Descubra uma forma mais simples de avançar em {niche or 'seu objetivo'}"
    body = f"{name} pode ser uma opção para quem procura uma solução prática. Veja os detalhes, benefícios, condições e avalie se faz sentido para você."
    cta = "Ver oferta e detalhes"
    return jsonify({"headline":headline,"body":body,"cta":cta,
                    "note":"Texto gerado localmente. Conecte sua API de IA para variações avançadas."})

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)), debug=True)
