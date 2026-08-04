from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from collections import defaultdict

app = FastAPI(title="Presupuesto Familiar GonGar")
templates = Jinja2Templates(directory="templates")

# Almacenamiento en memoria (compatible con despliegue sin estado en Vercel;
# fácilmente migrable a Supabase / SQLite / Vercel KV para persistencia permanente)
transactions = [
    {"id": 1, "type": "ingreso", "amount": 3200.00, "category": "Sueldo Quincenal", "vendor": "-", "date": "2026-07-01"},
    {"id": 2, "type": "gasto", "amount": 140.50, "category": "Supermercado", "vendor": "Costco", "date": "2026-07-03"},
    {"id": 3, "type": "gasto", "amount": 65.00, "category": "Comida fuera", "vendor": "Restaurante", "date": "2026-07-10"},
    {"id": 4, "type": "ingreso", "amount": 3200.00, "category": "Sueldo Quincenal", "vendor": "-", "date": "2026-07-15"},
    {"id": 5, "type": "ingreso", "amount": 1500.00, "category": "Bono Mitad de Año", "vendor": "Empresa", "date": "2026-07-20"},
    {"id": 6, "type": "ingreso", "amount": 3200.00, "category": "Sueldo Quincenal", "vendor": "-", "date": "2026-08-01"},
    {"id": 7, "type": "gasto", "amount": 210.00, "category": "Supermercado", "vendor": "Costco", "date": "2026-08-02"},
]
counter = 8

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    total_ingresos = sum(t["amount"] for t in transactions if t["type"] == "ingreso")
    total_gastos = sum(t["amount"] for t in transactions if t["type"] == "gasto")
    balance_neto = total_ingresos - total_gastos
    
    # Ordenar transacciones por fecha descendente
    sorted_transactions = sorted(transactions, key=lambda x: x["date"], reverse=True)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "transactions": sorted_transactions,
        "total_ingresos": round(total_ingresos, 2),
        "total_gastos": round(total_gastos, 2),
        "balance_neto": round(balance_neto, 2),
        "today": datetime.now().strftime("%Y-%m-%d")
    })

@app.post("/add")
async def add_transaction(
    type: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    vendor: str = Form(None)
):
    global counter
    transactions.append({
        "id": counter,
        "type": type.strip(),
        "amount": float(amount),
        "category": category.strip(),
        "vendor": vendor.strip() if (vendor and type == "gasto") else "-",
        "date": date.strip()
    })
    counter += 1
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete/{tx_id}")
async def delete_transaction(tx_id: int):
    global transactions
    transactions = [t for t in transactions if t["id"] != tx_id]
    return RedirectResponse(url="/", status_code=303)

@app.get("/api/chart-data")
async def get_chart_data():
    monthly_data = defaultdict(lambda: {"ingresos": 0.0, "gastos": 0.0})
    
    for t in transactions:
        # Extraer YYYY-MM
        month_key = t["date"][:7]
        if t["type"] == "ingreso":
            monthly_data[month_key]["ingresos"] += t["amount"]
        else:
            monthly_data[month_key]["gastos"] += t["amount"]
            
    sorted_months = sorted(monthly_data.keys())
    labels = sorted_months
    ingresos = [round(monthly_data[m]["ingresos"], 2) for m in sorted_months]
    gastos = [round(monthly_data[m]["gastos"], 2) for m in sorted_months]
    
    return JSONResponse({
        "labels": labels,
        "ingresos": ingresos,
        "gastos": gastos
    })