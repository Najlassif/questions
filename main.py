import json, re, calendar
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
RATES = {'USD': Decimal('1'), 'EUR': Decimal('1.03'), 'INR': Decimal('0.01157')}
TZ = ZoneInfo('Asia/Kolkata')
rows = [json.loads(s) for s in Path(__file__).with_name('orders.jsonl').read_text().splitlines() if s.strip()]
current = {}
for r in rows:
    if r['id'] not in current or datetime.fromisoformat(r['updated_at'].replace('Z','+00:00')) > datetime.fromisoformat(current[r['id']]['updated_at'].replace('Z','+00:00')):
        current[r['id']] = r
orders = list(current.values())
regions = sorted({r['region'] for r in orders}, key=len, reverse=True)
products = sorted({r['product'] for r in orders}, key=len, reverse=True)
months = {m.lower(): i for i,m in enumerate(calendar.month_name) if m}
months.update({m[:3]: i for m,i in list(months.items())})

class Question(BaseModel):
    question: str

def money(v):
    return float(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def answer(q):
    s = q.lower().strip()
    data = orders
    for region in regions:
        if re.search(r'\b'+re.escape(region.lower())+r'\b', s):
            data = [r for r in data if r['region']==region]
            break
    for product in products:
        if re.search(r'\b'+re.escape(product.lower())+r'\b', s):
            data = [r for r in data if r['product']==product]
            break
    cust = re.search(r'\bC\d+\b', q, re.I)
    if cust:
        data = [r for r in data if r['customer'].lower()==cust.group().lower()]
    year = re.search(r'\b20\d{2}\b', s)
    month = next((n for m,n in months.items() if re.search(r'\b'+m+r'\b',s)),None)
    if year or month:
        def match_date(r):
            d = datetime.fromisoformat(r['created_at'].replace('Z','+00:00')).astimezone(TZ)
            return (not year or d.year==int(year.group())) and (not month or d.month==month)
        data = [r for r in data if match_date(r)]
    if 'refund' in s or 'refunded' in s:
        data = [r for r in data if r['status']=='refunded']
    elif 'void' in s or 'cancel' in s:
        data = [r for r in data if r['status']=='void']
    else:
        data = [r for r in data if r['status']=='paid']
    if re.search(r'\b(top|best|highest|most|leading|largest)\b',s) and ('product' in s or 'customer' in s or 'region' in s):
        field = 'product' if 'product' in s else 'customer' if 'customer' in s else 'region'
        groups = {}
        for r in data:
            groups.setdefault(r[field],[]).append(r)
        if not groups: return None
        if 'quantity' in s or 'units' in s:
            score = lambda rs: sum(r['qty'] for r in rs)
        elif 'order' in s or 'count' in s:
            score = len
        else:
            score = lambda rs: sum((Decimal(str(r['amount']))*RATES[r['currency']] for r in rs),Decimal(0))
        return max(sorted(groups),key=lambda k:score(groups[k]))
    if 'average' in s or 'mean' in s:
        if not data: return 0
        if 'quantity' in s or 'units' in s: return round(sum(r['qty'] for r in data)/len(data),2)
        total = sum((Decimal(str(r['amount']))*RATES[r['currency']] for r in data),Decimal(0))
        return money(total/len(data))
    if 'quantity' in s or 'units' in s or 'items sold' in s:
        return sum(r['qty'] for r in data)
    if re.search(r'\b(how many|number of|count|orders placed|orders were)\b',s) and not re.search(r'\b(revenue|sales amount|value|total amount)\b',s):
        if 'customer' in s and not cust: return len({r['customer'] for r in data})
        return len(data)
    total = sum((Decimal(str(r['amount']))*RATES[r['currency']] for r in data),Decimal(0))
    return money(total)

@app.get('/')
def home():
    return {'status':'ok','orders':len(orders),'endpoint':'POST /ask'}

@app.post('/ask')
def ask(payload: Question):
    return {'answer':answer(payload.question)}
