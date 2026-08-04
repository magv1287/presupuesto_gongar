import os
import json
import calendar
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Presupuesto Familiar GonGar")
templates = Jinja2Templates(directory="templates")

# ---- INICIALIZACIÓN DE FIREBASE ----
fb_credentials = os.environ.get("FIREBASE_CREDENTIALS")
if fb_credentials and not firebase_admin._apps:
    try:
        cred_dict = json.loads(fb_credentials)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Error inicializando Firebase: {e}")

IS_VERCEL = os.environ.get("VERCEL", "0") == "1"
BASE_DIR = "/tmp" if IS_VERCEL or not os.access(".", os.W_OK) else "."
DATA_FILE = os.path.join(BASE_DIR, "data.json")

DEFAULT_CATEGORIES = {
    "gasto": [
        "Supermercado", "Restaurantes", "Servicios", "Vivienda", 
        "Transporte", "Entretenimiento", "Salud", "Mascota", "Otros"
    ],
    "ingreso": [
        "Sueldo", "Bono", "Inversiones", "Otros Ingresos"
    ]
}

def load_data():
    default_structure = {
        "transactions": [],
        "categories": DEFAULT_CATEGORIES.copy(),
        "limits": {
            "Supermercado": 600.0,
            "Restaurantes": 250.0,
            "Servicios": 300.0
        },
        "emergency_fund": 0.0,
        "savings_accounts": [
            {"id": 1, "name": "Cuenta Ahorro Principal", "balance": 0.0}
        ],
        "closed_months": []
    }

    # 1. Intentar cargar desde Firebase Firestore
    if firebase_admin._apps:
        try:
            db_fs = firestore.client()
            doc_ref = db_fs.collection("budget_app").document("main_data")
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                if "categories" not in data: data["categories"] = DEFAULT_CATEGORIES.copy()
                if "limits" not in data: data["limits"] = {}
                if "emergency_fund" not in data: data["emergency_fund"] = 0.0
                if "savings_accounts" not in data: data["savings_accounts"] = []
                return data
            else:
                save_data(default_structure)
                return default_structure
        except Exception as e:
            print(f"Error leyendo de Firebase: {e}")

    # 2. Fallback local data.json
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "categories" not in data: data["categories"] = DEFAULT_CATEGORIES.copy()
                if "limits" not in data: data["limits"] = {}
                if "emergency_fund" not in data: data["emergency_fund"] = 0.0
                if "savings_accounts" not in data: data["savings_accounts"] = []
                return data
        except Exception:
            pass
            
    return default_structure

def save_data(data):
    # 1. Guardar en Firebase Firestore
    if firebase_admin._apps:
        try:
            db_fs = firestore.client()
            db_fs.collection("budget_app").document("main_data").set(data)
        except Exception as e:
            print(f"Error guardando en Firebase: {e}")

    # 2. Guardar en copia local
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando copia local: {e}")

def get_calendar_month_bounds(ym_str: str):
    """Devuelve las fechas de inicio y fin del mes calendario (YYYY-MM-01 a YYYY-MM-DD)."""
    year, month = map(int, ym_str.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{ym_str}-01"
    end_date = f"{ym_str}-{last_day:02d}"
    return start_date, end_date

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, selected_month: str = None):
    data = load_data()

    current_ym = datetime.now().strftime("%Y-%m")
    available_months = sorted(list(set([t["date"][:7] for t in data.get("transactions", [])] + [current_ym])), reverse=True)
    active_month = selected_month if selected_month in available_months else current_ym

    start_date, end_date = get_calendar_month_bounds(active_month)

    # Filtrar transacciones dentro del rango del mes calendario
    month_txs = [
        t for t in data.get("transactions", []) 
        if start_date <= t["date"] <= end_date
    ]
    sorted_txs = sorted(month_txs, key=lambda x: x["date"], reverse=True)

    total_ingresos = sum(t["amount"] for t in month_txs if t["type"] == "ingreso")
    total_gastos = sum(t["amount"] for t in month_txs if t["type"] == "gasto")
    balance_neto = total_ingresos - total_gastos

    # Desglose de Gastos por Categoría
    gastos_cat = defaultdict(float)
    for t in month_txs:
        if t["type"] == "gasto":
            gastos_cat[t["category"]] += t["amount"]

    limits = data.get("limits", {})
    gastos_breakdown = []
    for cat, amount in sorted(gastos_cat.items(), key=lambda x: x[1], reverse=True):
        limit = limits.get(cat, 0.0)
        pct_of_total = (amount / total_gastos * 100) if total_gastos > 0 else 0
        pct_of_limit = (amount / limit * 100) if limit > 0 else 0
        gastos_breakdown.append({
            "category": cat,
            "amount": round(amount, 2),
            "limit": round(limit, 2),
            "pct_of_total": round(pct_of_total, 1),
            "pct_of_limit": round(pct_of_limit, 1),
            "over_limit": amount > limit if limit > 0 else False
        })

    # Desglose de Ingresos por Categoría
    ingresos_cat = defaultdict(float)
    for t in month_txs:
        if t["type"] == "ingreso":
            ingresos_cat[t["category"]] += t["amount"]

    ingresos_breakdown = []
    for cat, amount in sorted(ingresos_cat.items(), key=lambda x: x[1], reverse=True):
        pct_of_total = (amount / total_ingresos * 100) if total_ingresos > 0 else 0
        ingresos_breakdown.append({
            "category": cat,
            "amount": round(amount, 2),
            "pct_of_total": round(pct_of_total, 1)
        })

    emergency_fund = data.get("emergency_fund", 0.0)
    savings_accounts = data.get("savings_accounts", [])
    total_savings = sum(acc.get("balance", 0.0) for acc in savings_accounts)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "transactions": sorted_txs,
        "total_ingresos": round(total_ingresos, 2),
        "total_gastos": round(total_gastos, 2),
        "balance_neto": round(balance_neto, 2),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "active_month": active_month,
        "available_months": available_months,
        "categories": data.get("categories", DEFAULT_CATEGORIES),
        "gastos_breakdown": gastos_breakdown,
        "ingresos_breakdown": ingresos_breakdown,
        "emergency_fund": round(emergency_fund, 2),
        "total_savings": round(total_savings, 2),
        "savings_accounts": savings_accounts,
        "month_start": start_date,
        "month_end": end_date
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    data = load_data()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "categories": data.get("categories", DEFAULT_CATEGORIES),
        "limits": data.get("limits", {}),
        "emergency_fund": data.get("emergency_fund", 0.0),
        "savings_accounts": data.get("savings_accounts", [])
    })

@app.post("/add")
async def add_transaction(
    type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    vendor: str = Form(None)
):
    data = load_data()
    next_id = max([t.get("id", 0) for t in data.get("transactions", [])], default=0) + 1

    new_tx = {
        "id": next_id,
        "type": type.strip(),
        "amount": float(amount),
        "category": category.strip(),
        "vendor": vendor.strip() if (vendor and type == "gasto") else "-",
        "date": date.strip()
    }

    data["transactions"].append(new_tx)
    save_data(data)

    tx_month = date[:7]
    return RedirectResponse(url=f"/?selected_month={tx_month}", status_code=303)

@app.post("/delete/{tx_id}")
async def delete_transaction(tx_id: int, active_month: str = Form(None)):
    data = load_data()
    data["transactions"] = [t for t in data.get("transactions", []) if t["id"] != tx_id]
    save_data(data)
    redirect_url = f"/?selected_month={active_month}" if active_month else "/"
    return RedirectResponse(url=redirect_url, status_code=303)

# ---- ENDPOINTS CONFIGURACIÓN (SETTINGS) ----

@app.post("/settings/categories/add")
async def add_category(type: str = Form(...), category_name: str = Form(...)):
    data = load_data()
    cat_type = type.lower().strip()
    name = category_name.strip()
    if cat_type in data["categories"] and name:
        if name not in data["categories"][cat_type]:
            data["categories"][cat_type].append(name)
            save_data(data)
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/limits/update")
async def update_limits(request: Request):
    form_data = await request.form()
    data = load_data()
    new_limits = {}
    for cat in data["categories"].get("gasto", []):
        limit_val = form_data.get(f"limit_{cat}", "0")
        try:
            val = float(limit_val)
            if val > 0:
                new_limits[cat] = val
        except ValueError:
            pass
    data["limits"] = new_limits
    save_data(data)
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/emergency-fund/update")
async def update_emergency_fund(amount: float = Form(...)):
    data = load_data()
    data["emergency_fund"] = float(amount)
    save_data(data)
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/savings/add")
async def add_savings_account(name: str = Form(...), balance: float = Form(...)):
    data = load_data()
    next_id = max([a.get("id", 0) for a in data.get("savings_accounts", [])], default=0) + 1
    data["savings_accounts"].append({
        "id": next_id,
        "name": name.strip(),
        "balance": float(balance)
    })
    save_data(data)
    return RedirectResponse(url="/settings", status_code=303)

@app.post("/settings/savings/delete/{acc_id}")
async def delete_savings_account(acc_id: int):
    data = load_data()
    data["savings_accounts"] = [a for a in data.get("savings_accounts", []) if a["id"] != acc_id]
    save_data(data)
    return RedirectResponse(url="/settings", status_code=303)

@app.get("/api/chart-data")
async def get_chart_data():
    data = load_data()
    monthly_data = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})

    for t in data.get("transactions", []):
        month_key = t["date"][:7]
        if t["type"] == "ingreso":
            monthly_data[month_key]["ingresos"] += t["amount"]
        else:
            monthly_data[month_key]["gastos"] += t["amount"]

    sorted_months = sorted(list(monthly_data.keys()))
    if not sorted_months:
        sorted_months = [datetime.now().strftime("%Y-%m")]

    return JSONResponse({
        "labels": sorted_months,
        "ingresos": [round(monthly_data[m]["ingresos"], 2) for m in sorted_months],
        "gastos": [round(monthly_data[m]["gastos"], 2) for m in sorted_months]
    })
