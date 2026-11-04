"""Local-first API: no hosted model, paid API, or cloud database required."""
from contextlib import asynccontextmanager
from pathlib import Path
from threading import RLock
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .core import prepare,new_scenario,forecast_service,warning,weekly,intervene,solve,impact,STORAGE,DATA,DISHES

BUNDLE=None
LOCK=RLock()
PUBLIC=Path(__file__).resolve().parents[1]/'public'

@asynccontextmanager
async def lifespan(app):
    global BUNDLE
    BUNDLE=prepare()
    with sqlite3.connect(DATA/'baraka.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, data TEXT NOT NULL, created REAL NOT NULL)')
    yield

app=FastAPI(title='BARAKA · NNU cafeteria decision lab',lifespan=lifespan)

@app.middleware('http')
async def session_and_origin(request,call_next):
    if request.url.path.startswith('/api/') and request.method not in ['GET','HEAD','OPTIONS'] and request.url.path!='/api/telegram/webhook':
        origin=request.headers.get('origin')
        if origin and origin!=str(request.base_url).rstrip('/'):
            return JSONResponse({'detail':'Origin rejected'},status_code=403)
    sid=request.cookies.get('baraka_lab','')
    fresh=not re.fullmatch('[a-f0-9]{64}',sid)
    if fresh:sid=secrets.token_hex(32)
    request.state.sid=sid
    response=await call_next(request)
    if fresh:response.set_cookie('baraka_lab',sid,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=604800)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response

def load(request):
    with sqlite3.connect(DATA/'baraka.sqlite') as db:
        row=db.execute('SELECT data FROM sessions WHERE id=?',(request.state.sid,)).fetchone()
    return json.loads(row[0]) if row else new_scenario(BUNDLE)

def save(request,s):
    with sqlite3.connect(DATA/'baraka.sqlite') as db:
        db.execute('INSERT INTO sessions VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(request.state.sid,json.dumps(s,ensure_ascii=False)))
    return s

class Inputs(BaseModel):
    model_config=ConfigDict(extra='forbid')
    attendance:float=Field(default=.85,ge=.1,le=1)
    rain:int=Field(default=0,ge=0,le=1)
    exams:int=Field(default=0,ge=0,le=1)

class Action(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str
    remaining:list[int]|None=None
    delay:int=Field(default=45,ge=0,le=180)
    approved:bool=False

@app.get('/')
def home():return RedirectResponse('/today.html')

@app.get('/api/health')
def health():return {'ok':BUNDLE is not None,'model':'XGBoost CPU','optimizer':'OR-Tools CP-SAT','data':'synthetic seed 42','telegram_configured':bool(os.getenv('TELEGRAM_WEBHOOK_SECRET') and os.getenv('TELEGRAM_CHAT_ID'))}

@app.get('/api/lab')
def state(request:Request):
    with LOCK:return save(request,load(request))

@app.post('/api/lab/reset')
def reset(request:Request):
    with LOCK:return save(request,new_scenario(BUNDLE))

@app.post('/api/lab/forecast')
def forecast(request:Request,inputs:Inputs):
    with LOCK:
        s=new_scenario(BUNDLE);s['inputs']=inputs.model_dump();s['forecast']=forecast_service(BUNDLE,**inputs.model_dump());s['warning']=warning(BUNDLE,s['forecast']);return save(request,s)

@app.get('/api/weekly')
def week(attendance:float=.85,rain:int=0,exams:int=0):
    try:inputs=Inputs(attendance=attendance,rain=rain,exams=exams)
    except ValueError:raise HTTPException(422,'Invalid inputs')
    return {'days':weekly(BUNDLE,**inputs.model_dump()),'note':'Recursive seven-day scenario forecast, not observed sales. No live university timetable.'}

@app.post('/api/lab/action')
def action(request:Request,payload:Action):
    with LOCK:
        s=load(request);a=payload.action
        if a=='start':
            if s['stage']!='forecast':raise HTTPException(409,'Reset before starting a new service')
            s['stage']='warning'
        elif a=='quick':
            if s['stage']!='warning':raise HTTPException(409,'Quick entry is available during service')
            rs=payload.remaining
            if rs is None or len(rs)!=3 or any(v<0 or v>r['recommended'] for v,r in zip(rs,s['forecast']['rows'])):raise HTTPException(422,'Enter valid remaining portions for each dish')
            s['warning']=warning(BUNDLE,s['forecast'],rs)
        elif a=='intervene':
            if s['stage']!='warning':raise HTTPException(409,'Start service first')
            intervene(s)
        elif a=='approve':
            if s['stage']!='batches':raise HTTPException(409,'Create batches first')
            s['approvals']=payload.approved
            for b in s['batches']:b['approved']=payload.approved
        elif a=='optimize':
            if s['stage']!='batches':raise HTTPException(409,'Create batches first')
            s['initial']=solve(s['batches']);s['current']=s['initial'];s['stage']='optimized';s['impact']=impact(s)
        elif a=='delay':
            if s['stage'] not in ['optimized','reoptimized']:raise HTTPException(409,'Optimize the initial plan first')
            s['delay']=payload.delay;s['current']=solve(s['batches'],s['delay']);s['stage']='reoptimized';s['impact']=impact(s)
        else:raise HTTPException(422,'Unknown action')
        return save(request,s)

@app.get('/api/validation')
def validation(request:Request):
    s=load(request);df=BUNDLE['records']
    waste={k:int(df[k].sum()) for k in ['surplus','plate_waste','preparation_waste','spoilage']}
    return {'metrics':BUNDLE['metrics'],'waste':waste,'popular_categories':[{'dish':DISHES[int(i)],'sold':int(v)} for i,v in df.groupby('dish').sold.sum().sort_values(ascending=False).items()], 'records':df.tail(18).to_dict('records'),'policies':{p:solve(s['batches'],s['delay'],p) for p in ['optimal','first','closest']} if s['batches'] else {},'storage':STORAGE}

@app.get('/api/telegram/reports')
def reports():
    with sqlite3.connect(DATA/'baraka.sqlite') as db:rows=db.execute('SELECT data FROM reports WHERE created>? ORDER BY id DESC LIMIT 20',(time.time()-3600,)).fetchall()
    return {'reports':[json.loads(r[0]) for r in rows], 'configured':bool(os.getenv('TELEGRAM_WEBHOOK_SECRET') and os.getenv('TELEGRAM_CHAT_ID'))}

@app.post('/api/telegram/webhook')
async def telegram(request:Request):
    secret=os.getenv('TELEGRAM_WEBHOOK_SECRET','');chat=os.getenv('TELEGRAM_CHAT_ID','')
    if not secret or not chat:raise HTTPException(503,'Telegram is not configured')
    if not hmac.compare_digest(request.headers.get('X-Telegram-Bot-Api-Secret-Token',''),secret):raise HTTPException(403,'Webhook rejected')
    raw=await request.body()
    if len(raw)>16000:raise HTTPException(413,'Update too large')
    try:
        data=json.loads(raw);message=data.get('message',{});text=message.get('text','')
        if str(message.get('chat',{}).get('id',''))!=chat:raise HTTPException(403,'Chat rejected')
        # Deliberately structured: no hallucinated road news, NLP interpretation or automatic dispatch.
        match=re.fullmatch(r'/delay A (\d{1,3})',text)
        if not match or int(match[1])>180:raise HTTPException(422,'Use /delay A MINUTES, 0–180')
        ts=message.get('date',0)
        if not isinstance(ts,(int,float)) or abs(time.time()-ts)>3600:raise HTTPException(422,'Report is stale')
        report={'update_id':int(data['update_id']),'route':'A','delay':int(match[1]),'received':time.time(),'status':'unverified','source':'Telegram · operator report'}
    except (ValueError,TypeError,KeyError):raise HTTPException(422,'Invalid Telegram update')
    with sqlite3.connect(DATA/'baraka.sqlite') as db:
        db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?)',(report['update_id'],json.dumps(report),time.time()))
        db.execute('DELETE FROM reports WHERE created<?',(time.time()-86400,))
    return {'ok':True,'status':'pending operator review; no route changed'}

# Legacy dashboard remains available as a separate browser-local demo.
app.mount('/',StaticFiles(directory=PUBLIC),name='public')
