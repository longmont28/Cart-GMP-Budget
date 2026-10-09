"""GMP CAR-T budget v3. Target is 12 successful infusions.
Planning uses a binomial target-confidence constraint, not just an expected value.
Unquoted costs cannot be interpreted as free or as an approved total.
"""
import csv,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def records(filename):
 with (ROOT/'data'/filename).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def binomial_tail(n,k,p):
 return sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(k,n+1))
def minimum_enrollment(target,p,confidence=.9):
 if not 0<p<=1 or not 0<confidence<1:raise ValueError('Invalid probability')
 n=target
 while binomial_tail(n,target,p)<confidence:
  n+=1
  if n>100000:raise RuntimeError('Target infeasible')
 return n
def run(case='base'):
 a=json.loads((ROOT/'config/scenarios.json').read_text())[case]
 n=a['target_infused'];prob=math.prod(a[x] for x in ['eligible_rate','collection_rate','manufacturing_success','qc_release_rate','lymphodepletion_to_infusion'])
 confidence=a.get('target_confidence',.9)
 enrolled=minimum_enrollment(n,prob,confidence)
 expected={'screened':enrolled,'eligible':enrolled*a['eligible_rate']}
 expected['collections']=expected['eligible']*a['collection_rate']
 expected['starts']=expected['collections']
 expected['manufactured']=expected['starts']*a['manufacturing_success']
 expected['released']=expected['manufactured']*a['qc_release_rate']
 expected['lymphodepleted']=expected['released']
 expected['infused']=expected['lymphodepleted']*a['lymphodepletion_to_infusion']
 capacity={k:math.ceil(v) for k,v in expected.items()}
 # One common vector construct and ONE planned GMP vector lot in every scenario.
 # Additional lots are a separately authorized exception, not automatic scenario scaling.
 capacity['vector_constructs']=1
 capacity['vector_attempts']=a['planned_gmp_vector_lots']+a['vector_extra_lots_authorized']
 capacity['vector_nominal_supply']=capacity['vector_attempts']*a['vector_capacity_per_released_lot']
 capacity['vector_demand_gap']=max(0,capacity['starts']-capacity['vector_nominal_supply'])
 capacity['vector_one_lot_sufficient']=capacity['vector_demand_gap']==0
 capacity['vector_supply_status']='CAPACITY_NOT_CONFIRMED' if capacity['vector_demand_gap'] else 'NOMINAL_CAPACITY_ONLY_NOT_VERIFIED'
 quantities={**capacity,'program':1}
 lines=[];missing=[]
 for r in records('work_packages.csv'):
  q=quantities[r['driver']];verified=r['evidence_status']=='VERIFIED' and bool(r['unit_cost_sek'].strip())
  value=q*float(r['unit_cost_sek']) if verified else None
  lines.append({'wbs':r['wbs'],'stream':r['stream'],'quantity':q,'amount_sek':value,'verified':verified})
  if not verified:missing.append(r['wbs'])
 assays=[]
 for r in records('assays.csv'):
  fields=['dev_hours','validation_hours','routine_hours','staff_sek_per_hour','kit_sek_per_run','consumables_sek_per_run']
  verified=r['evidence_status']=='VERIFIED' and all(r[x].strip() for x in fields)
  q=quantities[r['driver']]*float(r['runs_per_unit'])
  amount=((float(r['dev_hours'])+float(r['validation_hours'])+q*float(r['routine_hours']))*float(r['staff_sek_per_hour'])+q*(float(r['kit_sek_per_run'])+float(r['consumables_sek_per_run']))) if verified else None
  assays.append({'id':r['assay_id'],'amount_sek':amount,'verified':verified})
  if not verified:missing.append(r['assay_id'])
 partial=sum(x['amount_sek'] or 0 for x in lines+assays)
 complete=not missing
 return {'case':case,'target_infused':n,'confidence':confidence,'planned_screened':enrolled,'probability_at_least_target':binomial_tail(enrolled,n,prob),'expected':expected,'capacity':capacity,'lines':lines,'assays':assays,'verified_partial_sek':partial,'approved_total_sek':partial*(1+a['contingency']) if complete and capacity['vector_one_lot_sufficient'] else None,'missing':missing,'complete':complete and capacity['vector_one_lot_sufficient'],'vector_capacity_warning':not capacity['vector_one_lot_sufficient']}
if __name__=='__main__':
 for case in ('low','base','high'):
  r=run(case);print(case,'screened',r['planned_screened'],'expected infused',round(r['expected']['infused'],2),'assurance',round(r['probability_at_least_target'],3),'vector lots',r['capacity']['vector_attempts'],'approved total',r['approved_total_sek'])
