import os
import json
from datetime import datetime
from collections import defaultdict
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Presupuesto Familiar GonGar")
templates = Jinja2Templates(directory="templates")

# En Vercel Serverless, el único directorio con permiso de escritura es /tmp/
IS_VERCEL = os.environ.get("VERCEL", "0") == "1"
BASE_DIR = "/tmp" if IS_VERCEL or not os.access(".", os.W_OK) else "."

DATA_FILE = os.path.join(BASE_DIR, "data.json")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

os.makedirs(BACKUP_DIR, exist_ok=True)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"transactions": [], "closed_months": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"transactions": [], "closed_months": []}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando en {DATA_FILE}: {e}")

def check_and_close_months(data):
    current_ym = datetime.now().strftime("%Y-%m")
    closed = set(data.get("closed_months", []))
    updated = False

    months_in_data = set(t["date"][:7] for t in data.get("transactions", []) if "date" in t)

    for ym in months_in_data:
        if ym < current_ym and ym not in closed:
            month_txs = [t for t in data["transactions"] if t["date"][:7] == ym]
            backup_filename = os.path.join(BACKUP_DIR, f"backup_{ym.replace('-', '_')}.json")
            
            backup_payload = {
                "month": ym,
                "closed_at": datetime.now().isoformat(),
                "transactions_count": len(month_txs),
                "transactions": month_txs
            }
            try:
                with open(backup_filename, "w", encoding="utf-8") as bf:
                    json.dump(backup_payload, bf, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error creando backup en /tmp: {e}")
            
            closed.add(ym)
            updated = True

    if updated:
        data["closed_months"] = list(closed)
        save_data(data)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, selected_month: str = None):
    data = load_data()
    check_and_close_months(data)

    current_ym = datetime.now().strftime("%Y-%m")
    
    # Extraer todos los meses disponibles desde Agosto 2026
    available_months = sorted(list(set([t["date"][:7] for t in data.get("transactions", [])] + [current_ym, "2026-08"])), reverse=True)
    
    active_month = selected_month if selected_month in available_months else current_ym

    month_txs = [t for t in data.get("transactions", []) if t["date"][:7] == active_month]
    sorted_txs = sorted(month_txs, key=lambda x: x["date"], reverse=True)

    total_ingresos = sum(t["amount"] for t in month_txs if t["type"] == "ingreso")
    total_gastos = sum(t["amount"] for t in month_txs if t["type"] == "gasto")
    balance_neto = total_ingresos - total_gastos

    return templates.TemplateResponse("index.html", {
        "request": request,
        "transactions": sorted_txs,
        "total_ingresos": round(total_ingresos, 2),
        "total_gastos": round(total_gastos, 2),
        "balance_neto": round(balance_neto, 2),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "active_month": active_month,
        "available_months": available_months,
        "is_closed": active_month in data.get("closed_months", [])
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
    check_and_close_months(data)

    tx_month = date[:7]
    return RedirectResponse(url=f"/?selected_month={tx_month}", status_code=303)

@app.post("/delete/{tx_id}")
async def delete_transaction(tx_id: int, active_month: str = Form(None)):
    data = load_data()
    data["transactions"] = [t for t in data.get("transactions", []) if t["id"] != tx_id]
    save_data(data)
    
    redirect_url = f"/?selected_month={active_month}" if active_month else "/"
    return RedirectResponse(url=redirect_url, status_code=303)

@app.post("/api/sync")
async def sync_data(request: Request):
    try:
        body = await request.json()
        incoming_txs = body.get("transactions", [])
        if incoming_txs:
            data = load_data()
            existing_ids = {t["id"] for t in data.get("transactions", [])}
            added = False
            for tx in incoming_txs:
                if tx["id"] not in existing_ids:
                    data["transactions"].append(tx)
                    added = True
            if added:
                save_data(data)
            return JSONResponse({"status": "synced", "total": len(data["transactions"])})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    return JSONResponse({"status": "ok"})

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

    sorted_months = sorted([m for m in monthly_data.keys() if m >= "2026-08"])
    if not sorted_months:
        sorted_months = ["2026-08"]

    return JSONResponse({
        "labels": sorted_months,
        "ingresos": [round(monthly_data[m]["ingresos"], 2) for m in sorted_months],
        "gastos": [round(monthly_data[m]["gastos"], 2) for m in sorted_months]
    })

@app.get("/api/download-backup")
async def download_backup():
    data = load_data()
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename=gongar_backup_{datetime.now().strftime('%Y%m%d')}.json"}
    )
