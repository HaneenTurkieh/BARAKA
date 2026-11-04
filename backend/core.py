"""Deterministic simulated cafeteria, chronological ML and constrained allocation."""
from pathlib import Path
import json
import math
import sqlite3
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from xgboost import XGBRegressor
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
DISHES = ['أرز ودجاج', 'معجنات زعتر', 'خبز وسلطات']
FEATURES = ['dow', 'period', 'dish', 'recent', 'previous_week', 'attendance', 'promotion', 'event', 'rain', 'exams']
SNAP_FEATURES = FEATURES + ['prepared', 'sold_so_far', 'minutes_remaining', 'velocity', 'forecast']
COSTS = [9, 3, 2]
PRICES = [18, 7, 5]

def generate(seed=42):
    rng = np.random.default_rng(seed)
    rows, histories = [], {(p, d): [] for p in range(2) for d in range(3)}
    for day, date in enumerate(pd.date_range('2026-01-01', periods=180)):
        dow = date.day_of_week
        attendance = float(rng.uniform(.65, 1) if dow < 4 or dow == 6 else rng.uniform(.2, .4))
        exams = int(45 <= day < 58 or 145 <= day < 158)
        rain, event, promotion = int(rng.random() < .2), int(rng.random() < .08), int(rng.random() < .18)
        anomaly = float(rng.uniform(.35, .65)) if rng.random() < .04 else 1
        for period in range(2):
            for dish, base in enumerate([150, 110, 90]):
                history = histories[period, dish]
                recent = float(np.mean(history[-7:])) if history else base
                week = history[-7] if len(history) >= 7 else recent
                demand = max(0, round(base * (.7 if period else 1) * (.35 + .65 * attendance) * (1+.15*promotion+.25*event-.1*rain-.12*exams) * anomaly + rng.normal(0, base*.07)))
                prepared = max(0, round(recent*1.13+rng.normal(0, 5)))
                sold = min(demand, prepared)
                rows.append(dict(date=str(date.date()), dow=dow, period=period, dish=dish, recent=recent, previous_week=week, attendance=attendance, promotion=promotion, event=event, rain=rain, exams=exams, demand=demand, prepared=prepared, sold=sold, surplus=prepared-sold, plate_waste=round(sold*rng.uniform(.03,.08)), preparation_waste=round(prepared*rng.uniform(.02,.05)), spoilage=round(prepared*rng.uniform(0,.025)), anomaly=anomaly!=1))
                history.append(demand)
    return pd.DataFrame(rows)

def scores(y, p):
    return {'mae': round(float(mean_absolute_error(y,p)),3), 'rmse': round(float(root_mean_squared_error(y,p)),3)}

def estimator():
    return XGBRegressor(n_estimators=110, max_depth=3, learning_rate=.06, subsample=.9, random_state=42, n_jobs=2, objective='reg:squarederror')

def prepare(force=False):
    artifact = DATA / 'models.joblib'
    if artifact.exists() and not force:
        return joblib.load(artifact)
    df = generate()
    # Train / calibration / test are disjoint complete dates. No test data fits model or interval.
    dates = sorted(df.date.unique())
    train, cal, test = [df[df.date.isin(ds)].copy() for ds in [dates[:126], dates[126:144], dates[144:]]]
    model = estimator().fit(train[FEATURES], train.demand)
    baseline = train.groupby(['dish','period','dow']).demand.mean()
    bp = [baseline.loc[(r.dish,r.period,r.dow)] for r in test.itertuples()]
    pred = np.maximum(0,model.predict(test[FEATURES]))
    residual = np.abs(cal.demand-model.predict(cal[FEATURES]))
    radius = float(np.quantile(residual, min(1, math.ceil((len(residual)+1)*.9)/len(residual)), method='higher'))
    snaps=[]
    rng=np.random.default_rng(43)
    for r in df.to_dict('records'):
        for remaining in [120,60,30]:
            elapsed=180-remaining
            sold_so_far=min(r['sold'],max(0,round(r['sold']*(elapsed/180)+rng.normal(0,2))))
            snaps.append({**r,'sold_so_far':sold_so_far,'minutes_remaining':remaining,'velocity':sold_so_far/elapsed,'final_sales':r['sold']})
    sf=pd.DataFrame(snaps)
    # Out-of-time pre-service predictions: train snapshots use training-window-only lag baseline.
    sf['forecast']=sf.recent
    sf.loc[sf.date.isin(dates[126:]),'forecast']=model.predict(sf[sf.date.isin(dates[126:])][FEATURES])
    st=sf[sf.date.isin(dates[:126])]
    se=sf[sf.date.isin(dates[144:])]
    surplus=estimator().fit(st[SNAP_FEATURES],st.final_sales)
    sp=np.clip(surplus.predict(se[SNAP_FEATURES]),se.sold_so_far,se.prepared)
    metrics={'demand':scores(test.demand,pred),'baseline':scores(test.demand,bp),'surplus':scores(se.final_sales,sp),'surplus_error':scores(se.surplus,se.prepared-sp), 'interval_radius':radius,'interval_coverage':float(np.mean(np.abs(test.demand-pred)<=radius)), 'train_dates':[dates[0],dates[125]],'calibration_dates':[dates[126],dates[143]],'test_dates':[dates[144],dates[-1]], 'train_records':len(train),'test_records':len(test),'snapshot_test_records':len(se),'features':FEATURES,'snapshot_features':SNAP_FEATURES,'comparison':[{'actual':int(a),'predicted':round(float(p),1),'baseline':round(float(b),1)} for a,p,b in zip(test.demand.iloc[:36],pred[:36],bp[:36])]}
    df.to_csv(DATA/'services.csv',index=False)
    sf.to_csv(DATA/'snapshots.csv',index=False)
    with sqlite3.connect(DATA/'baraka.sqlite') as db:
        df.to_sql('services',db,if_exists='replace',index=False)
        sf.to_sql('snapshots',db,if_exists='replace',index=False)
        db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    out={'model':model,'surplus':surplus,'metrics':metrics,'records':df,'snapshots':sf}
    joblib.dump(out,artifact)
    (DATA/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    return out

def forecast_service(bundle, attendance=.85, rain=0, exams=0):
    df=bundle['records']
    # Select a held-out dinner with surplus; selection is disclosed, not evaluation evidence.
    pool=df[(df.date>=bundle['metrics']['test_dates'][0]) & (df.period==1)].copy()
    pool['predicted']=np.maximum(0,bundle['model'].predict(pool[FEATURES]))
    # Choose using unmodified stored conditions, then let user scenarios change the output.
    totals=pool.groupby('date').agg(predicted=('predicted','sum'),traditional=('prepared','sum'))
    candidates=totals[totals.traditional>totals.predicted*1.05]
    date=min(candidates.index if len(candidates) else totals.index,key=lambda d:abs(totals.loc[d,'predicted']-275)+abs(totals.loc[d,'traditional']-320))
    group=pool[pool.date==date].copy()
    group['attendance']=attendance;group['rain']=rain;group['exams']=exams
    predictions=np.maximum(0,bundle['model'].predict(group[FEATURES]))
    rows=[]
    for r,p in zip(group.to_dict('records'),predictions):
        rows.append({**r,'food_name':DISHES[r['dish']],'predicted':round(float(p),1),'recommended':math.ceil(float(p)*1.05),'lower':max(0,round(float(p)-bundle['metrics']['interval_radius'])),'upper':math.ceil(float(p)+bundle['metrics']['interval_radius'])})
    return {'date':date,'rows':rows,'predicted':round(sum(r['predicted'] for r in rows),1),'traditional':sum(r['prepared'] for r in rows),'recommended':sum(r['recommended'] for r in rows),'prevented':sum(max(0,r['prepared']-r['recommended']) for r in rows)}

def weekly(bundle, attendance=.85, rain=0, exams=0):
    df=bundle['records']; history={(p,d):df[(df.period==p)&(df.dish==d)].demand.tolist() for p in range(2) for d in range(3)}
    start=pd.Timestamp(df.date.max())+pd.Timedelta(days=1); result=[]
    for day in range(7):
        date=start+pd.Timedelta(days=day); rows=[]
        for period in range(2):
            for dish in range(3):
                h=history[period,dish]
                r=dict(dow=date.day_of_week,period=period,dish=dish,recent=float(np.mean(h[-7:])),previous_week=h[-7],attendance=attendance if date.day_of_week<4 or date.day_of_week==6 else attendance*.35,promotion=0,event=0,rain=rain,exams=exams)
                p=max(0,float(bundle['model'].predict(pd.DataFrame([r])[FEATURES])[0]));h.append(p)
                rows.append({'dish':DISHES[dish],'period':period,'predicted':round(p,1)})
        result.append({'date':str(date.date()),'predicted':round(sum(r['predicted'] for r in rows)), 'rows':rows})
    return result

def warning(bundle,forecast,remaining=None):
    rows=[]
    for i,r in enumerate(forecast['rows']):
        sold=max(0,round(r['recommended']*.6)) if remaining is None else max(0,r['recommended']-min(r['recommended'],remaining[i]))
        x={**r,'prepared':r['recommended'],'sold_so_far':sold,'minutes_remaining':30,'velocity':sold/150,'forecast':r['predicted']}
        p=float(np.clip(bundle['surplus'].predict(pd.DataFrame([x])[SNAP_FEATURES])[0],sold,r['recommended']))
        expected=max(0,round(r['recommended']-p))
        rows.append({'dish':r['dish'],'food_name':r['food_name'],'prepared':r['recommended'],'sold_so_far':sold,'remaining':r['recommended']-sold,'minutes_remaining':30,'velocity':round(sold/150,2),'predicted_final_sales':round(p,1),'expected_surplus':expected})
    total=sum(r['expected_surplus'] for r in rows); prepared=sum(r['prepared'] for r in rows)
    return {'rows':rows,'expected_surplus':total,'risk':'مرتفع' if total/max(1,prepared)>.15 else 'متوسط' if total/max(1,prepared)>.05 else 'منخفض'}

DESTINATIONS=[dict(id='A',name='جمعية أ · افتراضية',type='charity',capacity=20,demand=20,eta=25,cold=True,active=True,cost=8,open_minutes=300),dict(id='B',name='جمعية ب · افتراضية',type='charity',capacity=30,demand=30,eta=70,cold=True,active=True,cost=12,open_minutes=300),dict(id='sale',name='بيع مخفّض · افتراضي',type='discount',capacity=15,demand=15,eta=55,cold=True,active=True,cost=3,open_minutes=180),dict(id='compost',name='استرداد عضوي · افتراضي',type='compost',capacity=10000,demand=10000,eta=30,cold=False,active=True,cost=5,open_minutes=1440),dict(id='disposal',name='تخلّص آمن',type='disposal',capacity=10000,demand=10000,eta=0,cold=False,active=True,cost=0,open_minutes=1440)]
HUMAN={'charity','discount'}

def eligibility(b,d,delay=0):
    eta=d['eta']+(delay if d['id']=='A' else 0)
    reason='مؤهل: الوقت والسلامة والسعة والنقل متوافقة'
    if not d['active']: reason='الجهة غير متاحة'
    elif d['capacity']<=0 or d['demand']<=0: reason='لا سعة أو طلب متاح'
    elif d['type'] in HUMAN:
        if not b['approved']: reason='لا يوجد اعتماد بشري لسلامة الطعام'
        elif b.get('source')=='plate_waste': reason='بقايا الأطباق ممنوعة للاستهلاك البشري'
        elif b['cold'] and not d['cold']: reason='النقل المبرد غير متاح'
        elif eta>b['usable_minutes']: reason=f"الوصول {eta} دقيقة يتجاوز المهلة {b['usable_minutes']} دقيقة"
        elif eta>d['open_minutes']: reason='الجهة مغلقة عند الوصول'
    return {'eligible':reason.startswith('مؤهل'),'reason':reason,'eta':eta,'batch':b['id'],'destination':d['id']}

def solve(batches,delay=0,policy='optimal',destinations=None):
    ds=destinations or DESTINATIONS
    matrix=[eligibility(b,d,delay) for b in batches for d in ds]
    allowed={(v['batch'],v['destination']):v for v in matrix}
    assignments=[]
    if policy!='optimal':
        capacities={d['id']:min(d['capacity'],d['demand']) for d in ds}
        for b in batches:
            left=b['quantity']
            order=sorted(ds,key=lambda d:allowed[b['id'],d['id']]['eta']) if policy=='closest' else ds
            for d in order:
                e=allowed[b['id'],d['id']]
                if not e['eligible']: continue
                q=min(left,capacities[d['id']]);left-=q;capacities[d['id']]-=q
                if q: assignments.append((b,d,q,e))
    else:
        model=cp_model.CpModel();xs={};used={}
        for d in ds:used[d['id']]=model.new_bool_var('used_'+d['id'])
        for b in batches:
            for d in ds:
                e=allowed[b['id'],d['id']]
                x=model.new_int_var(0,b['quantity'] if e['eligible'] else 0,b['id']+'_'+d['id']);xs[b['id'],d['id']]=x
                model.add(x<=b['quantity']*used[d['id']])
            model.add(sum(xs[b['id'],d['id']] for d in ds)==b['quantity'])
        for d in ds:model.add(sum(xs[b['id'],d['id']] for b in batches)<=min(d['capacity'],d['demand']))
        human=sum(xs[b['id'],d['id']] for b in batches for d in ds if d['type'] in HUMAN)
        recovery=sum(xs[b['id'],d['id']] for b in batches for d in ds if d['type']!='disposal')
        logistics=sum(used[d['id']]*d['cost'] for d in ds)
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.random_seed=42;solver.parameters.max_time_in_seconds=5
        # True lexicographic optimization, no arbitrary weights that fail at larger quantities.
        for objective in [human,recovery,-logistics]:
            model.maximize(objective);status=solver.solve(model)
            if status!=cp_model.OPTIMAL: raise RuntimeError('لم يكتمل إثبات الحل الأمثل؛ أعد المحاولة')
            model.add(objective==solver.value(objective))
        for b in batches:
            for d in ds:
                q=solver.value(xs[b['id'],d['id']])
                if q: assignments.append((b,d,q,allowed[b['id'],d['id']]))
    rows=[dict(batch=b['id'],food_name=b['food_name'],destination=d['id'],name=d['name'],type=d['type'],quantity=q,eta=e['eta'],reason=e['reason'],value=q*b['price']*.5 if d['type']=='discount' else 0) for b,d,q,e in assignments]
    return {'rows':rows,'matrix':matrix,'human':sum(r['quantity'] for r in rows if r['type'] in HUMAN),'organic':sum(r['quantity'] for r in rows if r['type']=='compost'),'disposed':sum(r['quantity'] for r in rows if r['type']=='disposal'),'logistics':sum(d['cost'] for d in ds if any(r['destination']==d['id'] for r in rows)),'discount_revenue':sum(r['value'] for r in rows),'policy':policy,'status':'OPTIMAL' if policy=='optimal' else 'GREEDY'}

def expired(plan,batches,delay):
    byid={b['id']:b for b in batches}
    return sum(r['quantity'] for r in plan['rows'] if r['type'] in HUMAN and next(d for d in DESTINATIONS if d['id']==r['destination'])['eta']+(delay if r['destination']=='A' else 0)>byid[r['batch']]['usable_minutes'])

def new_scenario(bundle):
    f=forecast_service(bundle)
    return {'stage':'forecast','forecast':f,'warning':warning(bundle,f),'intervention':None,'batches':[],'initial':None,'current':None,'delay':0,'impact':None,'approvals':False,'reports':[]}

def intervene(s):
    rows=[]
    for r in s['warning']['rows']:
        additional=min(r['remaining'],r['expected_surplus'],round(r['expected_surplus']*.16))
        rows.append({**r,'additional_sales':additional,'final_surplus':r['expected_surplus']-additional})
    s['intervention']={'rows':rows,'additional_sales':sum(r['additional_sales'] for r in rows),'final_surplus':sum(r['final_surplus'] for r in rows),'uplift':.16,'kind':'simulation'}
    s['batches']=[dict(id=f"B{i+1}",food_name=r['food_name'],quantity=r['final_surplus'],usable_minutes=60 if r['dish']==0 else 240,approved=False,cold=r['dish'] in [0,2],source='unserved',cost=COSTS[r['dish']],price=PRICES[r['dish']]) for i,r in enumerate(rows) if r['final_surplus']>0]
    s['stage']='batches'

def impact(s):
    p=s['current'];f=s['forecast']
    prevented_value=sum(max(0,r['prepared']-r['recommended'])*COSTS[r['dish']] for r in f['rows'])
    early_value=sum(r['additional_sales']*PRICES[r['dish']]*.5 for r in s['intervention']['rows'])
    return {'prevented':f['prevented'],'additional_sales':s['intervention']['additional_sales'],'human':p['human'],'organic':p['organic'],'disposed':p['disposed'],'expired_without':expired(s['initial'],s['batches'],s['delay']),'expired_with':expired(p,s['batches'],s['delay']),'prevented_value':prevented_value,'early_discount_revenue':early_value,'allocation_discount_revenue':p['discount_revenue'],'logistics':p['logistics'],'estimated_net_value':prevented_value+early_value+p['discount_revenue']-p['logistics'],'final_surplus':s['intervention']['final_surplus']}

STORAGE={
 'أرز ودجاج':{'method':'حفظ ساخن عند 60°م أو أعلى، أو تبريد سريع وحفظ عند 5°م أو أقل؛ فصل النيّئ عن المطبوخ.','cold':True},
 'معجنات زعتر':{'method':'غطاء نظيف وحماية من التلوث؛ الحشوات القابلة للتلف تحتاج حفظًا مبردًا عند 5°م أو أقل.','cold':False},
 'خبز وسلطات':{'method':'افصل الخبز الجاف عن السلطة. السلطة المقطعة تحفظ عند 5°م أو أقل، والخبز مغطى في مكان جاف.','cold':True}}

if __name__=='__main__':
    b=prepare(force=True);print(json.dumps(b['metrics'],ensure_ascii=False,indent=2))
