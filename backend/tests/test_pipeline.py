import copy
import os
import time
import unittest
from fastapi.testclient import TestClient
from backend.core import *
from backend.server import app

class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.bundle=prepare()
    def batches(self):
        return [dict(id='B1',food_name='Meal',quantity=23,usable_minutes=60,approved=True,cold=True,source='unserved',cost=9,price=18),dict(id='B2',food_name='Bread',quantity=15,usable_minutes=240,approved=True,cold=False,source='unserved',cost=2,price=5)]
    def test_generated_data_reproducible_and_conserved(self):
        a=generate();self.assertTrue(a.equals(generate()));self.assertEqual(len(a),1080)
        self.assertTrue((a.prepared==a.sold+a.surplus).all());self.assertTrue((a.sold<=a.demand).all())
    def test_chronological_split_and_no_targets(self):
        m=self.bundle['metrics'];self.assertLess(m['train_dates'][1],m['calibration_dates'][0]);self.assertLess(m['calibration_dates'][1],m['test_dates'][0])
        self.assertTrue(set(SNAP_FEATURES).isdisjoint({'final_sales','surplus','demand','sold','final_surplus'}));self.assertEqual(m['snapshot_test_records'],m['test_records']*3)
        self.assertTrue(all(np.isfinite(m[k]['mae']) for k in ['demand','baseline','surplus']))
    def test_lags_only_use_past(self):
        df=generate();g=df[(df.dish==0)&(df.period==0)].reset_index(drop=True)
        for i in range(7,len(g)):
            self.assertAlmostEqual(g.iloc[i].recent,float(g.iloc[i-7:i].demand.mean()));self.assertEqual(g.iloc[i].previous_week,g.iloc[i-7].demand)
    def test_eta_and_boundary(self):
        b=self.batches()[0];a=DESTINATIONS[0]
        self.assertEqual(eligibility(b,a,45)['eta'],70);self.assertFalse(eligibility(b,a,45)['eligible'])
        self.assertTrue(eligibility(b,a,35)['eligible'])
    def test_safety_plate_waste_cold_capacity_opening(self):
        b=self.batches()[0];d=copy.deepcopy(DESTINATIONS[0])
        for update in [{'approved':False},{'source':'plate_waste'}]:self.assertFalse(eligibility({**b,**update},d)['eligible'])
        for update in [{'cold':False},{'capacity':0},{'demand':0},{'active':False},{'open_minutes':10}]:self.assertFalse(eligibility(b,{**d,**update})['eligible'])
    def test_unsafe_never_human(self):
        bs=self.batches()
        for b in bs:b['approved']=False
        p=solve(bs);self.assertEqual(p['human'],0);self.assertEqual(p['organic'],38)
    def test_every_policy_conserves_and_honors_constraints(self):
        bs=self.batches()
        for delay in [0,45,180]:
            for policy in ['optimal','first','closest']:
                p=solve(bs,delay,policy)
                for b in bs:self.assertEqual(sum(r['quantity'] for r in p['rows'] if r['batch']==b['id']),b['quantity'])
                for d in DESTINATIONS:self.assertLessEqual(sum(r['quantity'] for r in p['rows'] if r['destination']==d['id']),min(d['capacity'],d['demand']))
                self.assertTrue(all(next(e for e in p['matrix'] if e['batch']==r['batch'] and e['destination']==r['destination'])['eligible'] for r in p['rows']))
    def test_reopt_and_counterfactual_from_old_rows(self):
        bs=self.batches();old=solve(bs);new=solve(bs,45)
        expected=sum(r['quantity'] for r in old['rows'] if r['batch']=='B1' and r['destination']=='A')
        self.assertGreater(expected,0);self.assertEqual(expired(old,bs,45),expected);self.assertEqual(expired(new,bs,45),0);self.assertNotEqual(old['rows'],new['rows'])
    def test_intervention_capped_and_conserved(self):
        s=new_scenario(self.bundle);intervene(s)
        self.assertEqual(s['warning']['expected_surplus'],s['intervention']['additional_sales']+s['intervention']['final_surplus'])
        self.assertEqual(sum(b['quantity'] for b in s['batches']),s['intervention']['final_surplus']);self.assertTrue(all(not b['approved'] for b in s['batches']))
    def test_weekly_is_seven_real_outputs(self):
        w=weekly(self.bundle);self.assertEqual(len(w),7);self.assertTrue(all(len(d['rows'])==6 and d['predicted']>=0 for d in w))

class API(unittest.TestCase):
    def test_flow_reset_and_session_isolation(self):
        with TestClient(app) as c:
            base=c.get('/api/lab').json();self.assertEqual(c.post('/api/lab/action',json={'action':'delay'}).status_code,409)
            for action in ['start','intervene','approve','optimize','delay']:
                r=c.post('/api/lab/action',json={'action':action,'approved':True});self.assertEqual(r.status_code,200,r.text)
            s=r.json();self.assertEqual(s['stage'],'reoptimized');self.assertEqual(s['impact']['expired_with'],0)
            self.assertEqual(s['impact']['final_surplus'],s['impact']['human']+s['impact']['organic']+s['impact']['disposed'])
            self.assertEqual(c.get('/api/lab').json(),s)
            c.cookies.clear();self.assertEqual(c.get('/api/lab').json(),base)
            self.assertEqual(c.post('/api/lab/reset',json={}).json(),base)
    def test_inputs_quick_entry_and_cross_origin(self):
        with TestClient(app) as c:
            self.assertEqual(c.post('/api/lab/forecast',json={'attendance':5}).status_code,422)
            self.assertEqual(c.post('/api/lab/reset',json={},headers={'origin':'https://evil.example'}).status_code,403)
            c.post('/api/lab/reset',json={});c.post('/api/lab/action',json={'action':'start'})
            self.assertEqual(c.post('/api/lab/action',json={'action':'quick','remaining':[-1,2,3]}).status_code,422)
            self.assertEqual(c.post('/api/lab/action',json={'action':'quick','remaining':[0,0,0]}).json()['warning']['expected_surplus'],0)
    def test_telegram_auth_staleness_and_no_auto_apply(self):
        old={k:os.environ.get(k) for k in ['TELEGRAM_WEBHOOK_SECRET','TELEGRAM_CHAT_ID']}
        os.environ['TELEGRAM_WEBHOOK_SECRET']='unit-test-secret';os.environ['TELEGRAM_CHAT_ID']='1234'
        try:
            with TestClient(app) as c:
                payload={'update_id':99999999,'message':{'chat':{'id':1234},'date':int(time.time()),'text':'/delay A 45'}}
                self.assertEqual(c.post('/api/telegram/webhook',json=payload).status_code,403)
                headers={'X-Telegram-Bot-Api-Secret-Token':'unit-test-secret'}
                self.assertEqual(c.post('/api/telegram/webhook',json=payload,headers=headers).status_code,200)
                self.assertEqual(c.get('/api/lab').json()['delay'],0)
                payload['message']['date']=0
                self.assertEqual(c.post('/api/telegram/webhook',json=payload,headers=headers).status_code,422)
                payload['message']['chat']['id']=999
                self.assertEqual(c.post('/api/telegram/webhook',json=payload,headers=headers).status_code,403)
        finally:
            for k,v in old.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v

if __name__=='__main__':unittest.main()
