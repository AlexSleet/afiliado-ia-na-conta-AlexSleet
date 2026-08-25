from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import sqlite3
import os
import secrets
import json
from functools import wraps
from datetime import datetime

app = Flask(__name__)

# =========================================================
# CONFIGURAÇÕES
# =========================================================

app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

DB = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "afiliado_ia.db")
)

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "troque-esta-senha")

# Token opcional para proteger o webhook
KIWIFY_WEBHOOK_TOKEN = os.getenv("KIWIFY_WEBHOOK_TOKEN", "")


# =========================================================
# BANCO DE DADOS
# =========================================================

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

    CREATE TABLE IF NOT EXISTS webhook_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        event_id TEXT,
        event_type TEXT,
        payload TEXT,
        created_at TEXT NOT NULL
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_unique_event
    ON webhook_events(provider, event_id)
    WHERE event_id IS NOT NULL AND event_id <> '';
    """)

    con.commit()
    con.close()


init_db()


# =========================================================
# LOGIN
# =========================================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):

        if not session.get("admin"):
            return redirect(
                url_for(
                    "login",
                    next=request.path
                )
            )

        return fn(*args, **kwargs)

    return wrapper


@app.context_processor
def inject_now():
    return {
        "year": datetime.now().year
    }


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        user = request.form.get("username", "")
        password = request.form.get("password", "")

        if (
            secrets.compare_digest(user, ADMIN_USER)
            and secrets.compare_digest(password, ADMIN_PASSWORD)
        ):

            session["admin"] = True

            return redirect(
                request.args.get("next")
                or url_for("dashboard")
            )

        flash("Usuário ou senha inválidos.")

    return render_template("login.html")


@app.post("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
@login_required
def dashboard():

    con = db()

    products_count = con.execute(
        "SELECT COUNT(*) c FROM products"
    ).fetchone()["c"]

    leads_count = con.execute(
        "SELECT COUNT(*) c FROM leads"
    ).fetchone()["c"]

    clicks_count = con.execute(
        "SELECT COUNT(*) c FROM clicks"
    ).fetchone()["c"]

    sales_data = con.execute("""
        SELECT
            COUNT(*) c,
            COALESCE(SUM(commission),0) commission
        FROM sales
    """).fetchone()

    best = con.execute("""
        SELECT
            p.id,
            p.name,
            COUNT(c.id) clicks,
            (
                SELECT COUNT(*)
                FROM sales s
                WHERE s.product_id = p.id
            ) sales

        FROM products p

        LEFT JOIN clicks c
            ON c.product_id = p.id

        GROUP BY p.id

        ORDER BY
            sales DESC,
            clicks DESC

        LIMIT 5
    """).fetchall()

    con.close()

    return render_template(
        "dashboard.html",
        products=products_count,
        leads=leads_count,
        clicks=clicks_count,
        sales=sales_data["c"],
        commission=sales_data["commission"],
        best=best
    )


# =========================================================
# PRODUTOS
# =========================================================

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():

    con = db()

    if request.method == "POST":

        name = request.form["name"].strip()
        niche = request.form.get("niche", "").strip()

        try:
            commission = float(
                request.form.get("commission") or 0
            )
        except ValueError:
            commission = 0

        affiliate_url = request.form["affiliate_url"].strip()

        con.execute("""
            INSERT INTO products(
                name,
                niche,
                commission,
                affiliate_url,
                created_at
            )
            VALUES(?,?,?,?,?)
        """, (
            name,
            niche,
            commission,
            affiliate_url,
            datetime.now().isoformat(timespec="seconds")
        ))

        con.commit()
        con.close()

        return redirect(
            url_for("products")
        )

    rows = con.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    con.close()

    return render_template(
        "products.html",
        products=rows
    )


@app.post("/products/<int:pid>/delete")
@login_required
def delete_product(pid):

    con = db()

    con.execute(
        "DELETE FROM products WHERE id=?",
        (pid,)
    )

    con.commit()
    con.close()

    return redirect(
        url_for("products")
    )


# =========================================================
# LANDING PAGE
# =========================================================

@app.route("/landing/<int:pid>")
def landing(pid):

    con = db()

    product = con.execute(
        "SELECT * FROM products WHERE id=?",
        (pid,)
    ).fetchone()

    con.close()

    if not product:
        return "Produto não encontrado", 404

    return render_template(
        "landing.html",
        p=product
    )


# =========================================================
# LEADS
# =========================================================

@app.post("/lead/<int:pid>")
def add_lead(pid):

    con = db()

    con.execute("""
        INSERT INTO leads(
            name,
            email,
            whatsapp,
            product_id,
            source,
            created_at
        )
        VALUES(?,?,?,?,?,?)
    """, (
        request.form.get("name", ""),
        request.form.get("email", ""),
        request.form.get("whatsapp", ""),
        pid,
        request.form.get("source", "landing"),
        datetime.now().isoformat(timespec="seconds")
    ))

    con.commit()
    con.close()

    return redirect(
        url_for(
            "go",
            pid=pid,
            source="lead"
        )
    )


@app.route("/leads")
@login_required
def leads():

    con = db()

    rows = con.execute("""
        SELECT
            l.*,
            p.name product_name

        FROM leads l

        LEFT JOIN products p
            ON p.id = l.product_id

        ORDER BY l.id DESC
    """).fetchall()

    con.close()

    return render_template(
        "leads.html",
        leads=rows
    )


# =========================================================
# CLIQUES
# =========================================================

@app.route("/go/<int:pid>")
def go(pid):

    source = request.args.get("source", "direct")
    campaign = request.args.get("campaign", "")

    con = db()

    product = con.execute(
        "SELECT * FROM products WHERE id=?",
        (pid,)
    ).fetchone()

    if not product:

        con.close()

        return "Produto não encontrado", 404

    con.execute("""
        INSERT INTO clicks(
            product_id,
            source,
            campaign,
            created_at
        )
        VALUES(?,?,?,?)
    """, (
        pid,
        source,
        campaign,
        datetime.now().isoformat(timespec="seconds")
    ))

    con.commit()
    con.close()

    return redirect(
        product["affiliate_url"]
    )


# =========================================================
# VENDAS
# =========================================================

@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():

    con = db()

    if request.method == "POST":

        try:
            product_id = int(
                request.form["product_id"]
            )

            amount = float(
                request.form.get("amount") or 0
            )

            commission = float(
                request.form.get("commission") or 0
            )

        except (ValueError, KeyError):

            con.close()

            flash("Dados da venda inválidos.")

            return redirect(
                url_for("sales")
            )

        con.execute("""
            INSERT INTO sales(
                product_id,
                amount,
                commission,
                source,
                created_at
            )
            VALUES(?,?,?,?,?)
        """, (
            product_id,
            amount,
            commission,
            request.form.get("source", "manual"),
            datetime.now().isoformat(timespec="seconds")
        ))

        con.commit()
        con.close()

        return redirect(
            url_for("sales")
        )

    rows = con.execute("""
        SELECT
            s.*,
            p.name product_name

        FROM sales s

        LEFT JOIN products p
            ON p.id = s.product_id

        ORDER BY s.id DESC
    """).fetchall()

    prods = con.execute("""
        SELECT *
        FROM products
        ORDER BY name
    """).fetchall()

    con.close()

    return render_template(
        "sales.html",
        sales=rows,
        products=prods
    )


# =========================================================
# WEBHOOK KIWIFY
# =========================================================

@app.post("/webhook/kiwify")
def webhook_kiwify():

    # Se você configurar um token no Railway,
    # a URL deve conter ?token=SEU_TOKEN
    if KIWIFY_WEBHOOK_TOKEN:
        token_recebido = request.args.get("token", "")

        if not secrets.compare_digest(
            token_recebido,
            KIWIFY_WEBHOOK_TOKEN
        ):
            return jsonify({
                "ok": False,
                "error": "unauthorized"
            }), 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "ok": False,
            "error": "invalid_json"
        }), 400

    # Guarda campos comuns sem assumir um payload único.
    event_id = str(
        data.get("id")
        or data.get("event_id")
        or data.get("order_id")
        or data.get("transaction_id")
        or ""
    )

    event_type = str(
        data.get("event")
        or data.get("event_type")
        or data.get("status")
        or ""
    ).strip().lower()

    con = db()

    # Evita processar duas vezes o mesmo evento.
    if event_id:

        existing = con.execute("""
            SELECT id
            FROM webhook_events
            WHERE provider = ?
              AND event_id = ?
            LIMIT 1
        """, (
            "kiwify",
            event_id
        )).fetchone()

        if existing:

            con.close()

            return jsonify({
                "ok": True,
                "duplicate": True
            }), 200

    con.execute("""
        INSERT INTO webhook_events(
            provider,
            event_id,
            event_type,
            payload,
            created_at
        )
        VALUES(?,?,?,?,?)
    """, (
        "kiwify",
        event_id or None,
        event_type,
        json.dumps(
            data,
            ensure_ascii=False
        ),
        datetime.now().isoformat(
            timespec="seconds"
        )
    ))

    # Só registramos automaticamente como venda
    # quando reconhecemos explicitamente um status aprovado.
    approved_events = {
        "approved",
        "paid",
        "purchase_approved",
        "order_approved",
        "compra_aprovada",
        "venda_aprovada"
    }

    if event_type in approved_events:

        # Nesta primeira versão vinculamos ao
        # produto mais recente cadastrado.
        product = con.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if product:

            raw_amount = (
                data.get("amount")
                or data.get("price")
                or data.get("value")
                or 0
            )

            try:
                amount = float(raw_amount)
            except (TypeError, ValueError):
                amount = 0

            con.execute("""
                INSERT INTO sales(
                    product_id,
                    amount,
                    commission,
                    source,
                    created_at
                )
                VALUES(?,?,?,?,?)
            """, (
                product["id"],
                amount,
                product["commission"],
                "kiwify-webhook",
                datetime.now().isoformat(
                    timespec="seconds"
                )
            ))

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "event_type": event_type
    }), 200


# =========================================================
# IA
# =========================================================

@app.route("/ai")
@login_required
def ai():

    con = db()

    products_list = con.execute("""
        SELECT *
        FROM products
        ORDER BY id DESC
    """).fetchall()

    con.close()

    return render_template(
        "ai.html",
        products=products_list
    )


@app.post("/api/ai-copy")
@login_required
def ai_copy():

    data = request.get_json(force=True)

    name = data.get("name", "Produto")
    niche = data.get("niche", "")

    headline = (
        f"Descubra uma forma mais simples "
        f"de avançar em {niche or 'seu objetivo'}"
    )

    body = (
        f"{name} pode ser uma opção para quem "
        "procura uma solução prática. "
        "Veja os detalhes, benefícios e condições "
        "e avalie se faz sentido para você."
    )

    cta = "Ver oferta e detalhes"

    return jsonify({
        "headline": headline,
        "body": body,
        "cta": cta,
        "note":
            "Texto gerado localmente. "
            "Conecte sua API de IA para "
            "variações avançadas."
    })


# =========================================================
# CONFIGURAÇÕES
# =========================================================

@app.route("/settings")
@login_required
def settings():

    return render_template(
        "settings.html"
    )


# =========================================================
# EXECUÇÃO LOCAL
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                5000
            )
        ),
        debug=False
    )
