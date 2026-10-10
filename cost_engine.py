"""CAR-T transparent research-cost model. No scraped price is automatically approved."""
import os,re,json,time,math,datetime,collections,urllib.parse,xml.etree.ElementTree as ET
from pathlib import Path
import requests,pandas as pd
from bs4 import BeautifulSoup

ROOT=Path.cwd()
SEARCH_LIMIT=int(os.getenv('SEARCH_LIMIT','136'))
REQUEST_DELAY=float(os.getenv('REQUEST_DELAY','0.6'))
HTTP_TIMEOUT=12
HEAD={'User-Agent':'Mozilla/5.0 (compatible; ResearchPriceEvidence/1.0; academic budget research)'}
FX_URL='https://api.frankfurter.dev/v1/latest?base=SEK'
PRICING_TYPES={'Material','Consumable','Equipment','Equipment service','QC','QC outsourced','QC stability','Logistics'}
CURRENCIES={'SEK':1.0}

def fetch_fx():
    try:
        j=requests.get(FX_URL,timeout=HTTP_TIMEOUT,headers=HEAD).json()
        if 'rates' not in j: raise ValueError(str(j)[:140])
        rates=j['rates']
        fx={c:1/float(rates[c]) for c in ['EUR','USD','GBP'] if c in rates}
        fx['SEK']=1.0
        if not {'EUR','USD','GBP'}.issubset(fx): raise ValueError('Missing exchange rates')
        return fx,str(j.get('date','')),FX_URL,'OK'
    except Exception as e:
        return {'SEK':1.0},'',FX_URL,'FX_UNAVAILABLE: '+str(e)[:160]

def classifier(row):
    cat=str(row.get('Cost category','')); name=str(row.get('Item / test','')).lower()
    if cat=='Release-associated donor/patient safety': return 'RFQ_CLINICAL', 'Patient/donor safety: not final drug-product release testing'
    if cat not in PRICING_TYPES: return 'RFQ_SERVICE','Non-catalog service / contract / staff cost'
    if not str(row.get('SKU / catalog','')).strip() and not str(row.get('Vendor','')).strip(): return 'RFQ_OR_SEARCH','Unspecified product; obtain pack/grade and vendor before accepting price'
    if any(x in name for x in ['viral vector','retroviral vector','gmp manufacturing service']): return 'RFQ_SERVICE','Custom GMP service / vector'
    return 'SEARCH_CATALOG','Catalog product candidate (grade and pack verification needed)'

def search_urls(query):
    # Two independent no-key public search routes. Search access may be blocked.
    urls=[]; failures=[]
    try:
        q=urllib.parse.quote(query)
        res=requests.get('https://www.bing.com/search',params={'q':query,'format':'rss'},headers=HEAD,timeout=HTTP_TIMEOUT)
        res.raise_for_status()
        root=ET.fromstring(res.text)
        for n in root.findall('.//item')[:6]:
            t=n.findtext('link')
            if t and t.startswith('http'): urls.append(t)
    except Exception as e: failures.append('BING_RSS:'+str(e)[:80])
    if len(urls)<3:
        try:
            res=requests.get('https://www.google.com/search',params={'q':query,'num':7},headers=HEAD,timeout=HTTP_TIMEOUT)
            res.raise_for_status()
            soup=BeautifulSoup(res.text,'html.parser')
            for a in soup.select('a[href]'):
                h=a.get('href','')
                if h.startswith('/url?q='): h=urllib.parse.unquote(h[7:].split('&')[0])
                if h.startswith('https://') and not any(z in h for z in ['google.com','googleusercontent','accounts.google']): urls.append(h)
        except Exception as e: failures.append('GOOGLE:'+str(e)[:80])
    return list(dict.fromkeys(urls))[:3],'; '.join(failures)

PRICE_PATTERNS=[
 re.compile(r'(?P<currency>SEK|EUR|USD|GBP|kr|€|\$|£)\s*(?P<value>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d{2,8}(?:[.,]\d{1,2})?)',re.I),
 re.compile(r'(?P<value>\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d{1,2})?|\d{2,8}(?:[.,]\d{1,2})?)\s*(?P<currency>SEK|EUR|USD|GBP|kr|€|£)',re.I)]

def number(s):
    s=re.sub(r'\s','',str(s))
    if ',' in s and '.' in s:
        s=s.replace(',','') if s.rfind('.')>s.rfind(',') else s.replace('.','').replace(',','.')
    elif ',' in s: s=s.replace(',','.') if len(s.split(',')[-1]) in (1,2) else s.replace(',','')
    elif '.' in s and len(s.split('.')[-1])==3: s=s.replace('.','')
    return float(s)

def currency(t):
    return {'€':'EUR','$':'USD','£':'GBP','KR':'SEK','KR.':'SEK'}.get(t.upper(),t.upper())

def structured_prices(soup):
    out=[]
    def recurse(obj):
        if isinstance(obj,dict):
            if 'price' in obj and ('priceCurrency' in obj or 'priceSpecification' in obj):
                try:
                    cur=str(obj.get('priceCurrency','')).upper(); val=number(obj['price'])
                    if cur in ('SEK','EUR','USD','GBP') and 0<val<1e7: out.append((val,cur,'JSON_LD'))
                except (ValueError,TypeError,KeyError): pass
            for v in obj.values(): recurse(v)
        elif isinstance(obj,list):
            for v in obj: recurse(v)
    for el in soup.select('script[type="application/ld+json"]'):
        try: recurse(json.loads(el.string or el.get_text()))
        except (ValueError,TypeError): pass
    return out

def get_page(url,sku):
    try:
        r=requests.get(url,headers=HEAD,timeout=HTTP_TIMEOUT);r.raise_for_status()
        if 'html' not in r.headers.get('content-type','').lower(): return [],'NON_HTML'
        s=BeautifulSoup(r.text[:1_500_000],'html.parser')
        txt=s.get_text(' ',strip=True)
        if sku and sku.lower() not in txt.lower() and sku.lower() not in r.text.lower(): return [],'SKU_NOT_FOUND_ON_PAGE'
        vals=structured_prices(s)
        # Regex prices only when close to price words, to avoid catalog numbers/dates.
        for pattern in PRICE_PATTERNS:
            for m in list(pattern.finditer(txt))[:150]:
                left=txt[max(0,m.start()-80):m.start()].lower()
                right=txt[m.end():m.end()+50].lower()
                if not any(z in left+' '+right for z in ('price','pris','our price','excl','inkl','vat','each','per pack','/pack','cost')): continue
                try:
                    val=number(m.group('value'));cur=currency(m.group('currency'))
                    if cur in ('SEK','USD','EUR','GBP') and 0<val<1e7: vals.append((val,cur,'PRICE_TEXT'))
                except (ValueError,TypeError): pass
        return list(dict.fromkeys(vals))[:5], 'OK' if vals else 'NO_PUBLIC_PRICE_FOUND'
    except Exception as e: return [],'ACCESS_ERROR:'+str(e)[:130]

def research(cat,fx,fx_date,online=True,max_items=136):
    evid=[]; searchlog=[]
    for idx,(_,row) in enumerate(cat.head(max_items).iterrows(),start=1):
        item_id=row['Item ID']; cls,why=classifier(row)
        vendor=str(row.get('Vendor','')).strip(); sku=str(row.get('SKU / catalog','')).strip()
        name=str(row.get('Item / test','')).strip()
        if cls=='SEARCH_CATALOG' or cls=='RFQ_OR_SEARCH':
            query=' '.join(z for z in [vendor,sku,name,'price EUR SEK'] if z)
        else: query=''
        links=[];error='NOT_SEARCHED_SERVICE'
        if online and query: links,error=search_urls(query)
        elif query: error='SEARCH_DISABLED'
        found=0
        for url in links:
            val,diag=get_page(url,sku)
            searchlog.append({'Item ID':item_id,'Query':query,'URL':url,'Fetch result':diag})
            for price,cur,method in val:
                evid.append({'Item ID':item_id,'Item / test':name,'Vendor':vendor,'SKU':sku,'Source URL':url,'Price original':price,'Currency':cur,'Price SEK':round(price*fx[cur],2) if cur in fx else None,'FX SEK per unit':fx.get(cur),'FX date':fx_date,'Capture date (UTC)':datetime.datetime.now(datetime.timezone.utc).date().isoformat(),'Extraction':method,'Pack match':'UNVERIFIED','GMP grade match':'UNVERIFIED','VAT/shipping':'UNKNOWN','Approval':'CANDIDATE_REVIEW','Note':'Not automatically included in approved budget'}); found+=1
        searchlog.append({'Item ID':item_id,'Query':query,'URL':'','Fetch result':f'{cls} | {why} | result_count={found} | search_error={error}'})
        if idx%10==0: print(f'Processed {idx}/{min(max_items,len(cat))} | candidates: {len(evid)}')
        if online and links: time.sleep(REQUEST_DELAY)
    return pd.DataFrame(evid),pd.DataFrame(searchlog)

def scenarios(cat,approved,inputs):
    target=int(inputs.get('successful_infusions',12)); conf=float(inputs.get('planning_confidence',0.90)); scenarios=[];details=[]
    # P(screening->collection) and P(start->released), plus independently tracked post-release infusion.
    for p in [0.50,0.70,0.90]:
        q=float(inputs.get('collection_to_start',1.0)); release_to_inf=float(inputs.get('release_to_infusion',1.0))
        effective=p*p*q*release_to_inf
        n=target
        from scipy.stats import binom
        while binom.sf(target-1,n,effective)<conf and n<100000: n+=1
        # Planning conservatively budgets at planned screening volume, models expected later-stage volumes.
        volumes={'per screened':n,'per collection':n*p,'per start':n*p*q,'per completed':n*p*q,'per released':n*p*q*p,'per lymphodepleted':n*p*q*p,'per infused':target,'per program':1,'per vector lot':int(inputs.get('vector_lots',1)),'per year':float(inputs.get('program_years',1)),'per month':float(inputs.get('program_months',12))}
        fixed=variable=0.0;missing=0;included=0
        for _,r in cat.iterrows():
            quote=approved.get(str(r['Item ID']))
            unit=quote['unit_price'] if quote else None
            drv=str(r.get('Cost driver','')).strip(); mult=volumes.get(drv,0)
            try: qty=float(r.get('Qty per event',1))
            except (TypeError,ValueError): qty=float('nan')
            cost=None
            if unit is not None and math.isfinite(qty):
                cost=qty*unit*mult
                # Pack quotes use discrete purchase rounding at program level.
                if quote.get('scope')=='PACK':
                    pack_qty=quote.get('pack_qty',0)
                    if pack_qty>0: cost=math.ceil(qty*mult/pack_qty)*unit
                    else: cost=None
                if cost is None:
                    missing+=1
                    details.append({'Scenario':f'{int(p*100)}%','Item ID':r['Item ID'],'Stage':r['Stage'],'Item':r['Item / test'],'Driver':drv,'Events planned/expected':mult,'Qty per event':qty,'Approved SEK per unit':unit,'Subtotal SEK':None,'Cost status':'INVALID_PACK_QUOTE'})
                    continue
                if drv in ['per program','per year','per month','per vector lot']: fixed+=cost
                else: variable+=cost
                included+=1
            else: missing+=1
            details.append({'Scenario':f'{int(p*100)}%','Item ID':r['Item ID'],'Stage':r['Stage'],'Item':r['Item / test'],'Driver':drv,'Events planned/expected':mult,'Qty per event':qty if math.isfinite(qty) else None,'Approved SEK per unit':unit,'Subtotal SEK':cost,'Cost status':'APPROVED' if cost is not None else 'UNPRICED'})
        scenarios.append({'Screening probability':p,'Manufacturing release probability':p,'Target infused':target,'Confidence':conf,'Screened planned':n,'Collections expected':round(volumes['per collection'],2),'Manufacturing starts expected':round(volumes['per start'],2),'Released expected':round(volumes['per released'],2),'Quoted coverage items':included,'Missing/invalid cost items':missing,'Priced subtotal SEK (LOWER BOUND)':round(fixed+variable,2),'Full total SEK':'INCOMPLETE' if missing else round(fixed+variable,2),'Cost per 12 infused SEK':'INCOMPLETE' if missing else round((fixed+variable)/target,2)})
    return pd.DataFrame(scenarios),pd.DataFrame(details)

def read_approved(path='approved_quotes.csv'):
    df=pd.read_csv(path,keep_default_na=False);out={};errors=[]
    for _,r in df.iterrows():
        if str(r.get('Approval','')).upper()!='APPROVED': continue
        ident=str(r['Item ID']); amount=r.get('Approved SEK per unit','')
        try:
            n=float(amount)
            if n<=0: raise ValueError('Price must be positive')
            if not str(r.get('Source / Quote ID','')).strip():raise ValueError('Missing quote evidence')
            if not str(r.get('Approved by','')).strip():raise ValueError('Missing reviewer')
            if ident in out:raise ValueError('Duplicate item approval')
            scope=str(r.get('Price scope','UNIT')).strip().upper() or 'UNIT'
            if scope not in ('UNIT','PACK'): raise ValueError('Price scope must be UNIT or PACK')
            pack_qty=float(r.get('Pack quantity','') or 0)
            if scope=='PACK' and pack_qty<=0:raise ValueError('PACK requires positive pack quantity')
            out[ident]={'unit_price':n,'scope':scope,'pack_qty':pack_qty}
        except Exception as e: errors.append(f'{ident}: {e}')
    return out,errors

def export_workbook(path,tables):
    with pd.ExcelWriter(path,engine='xlsxwriter') as writer:
        for name,df in tables.items():
            safe=df.copy()
            safe.to_excel(writer,sheet_name=name[:31],index=False)
            ws=writer.sheets[name[:31]];ws.freeze_panes(1,0); ws.autofilter(0,0,len(safe),max(0,len(safe.columns)-1))
            ws.set_row(0,26,writer.book.add_format({'bold':True,'font_color':'#FFFFFF','bg_color':'#17365D','text_wrap':True,'valign':'vcenter'}))
            for i,col in enumerate(safe.columns):
                width=min(45,max(13,len(str(col))+3))
                ws.set_column(i,i,width)

def run(online=True,max_items=136):
    cat=pd.read_csv('timeline_cost_catalog.csv',keep_default_na=False)
    cat.insert(0,'Item ID',[f'CT-{i:03d}' for i in range(1,len(cat)+1)])
    fx,fx_date,fx_source,fx_status=fetch_fx()
    print('FX',fx_date,fx_status,fx)
    cclasses=[classifier(r) for _,r in cat.iterrows()]
    cat.insert(1,'Price sourcing route',[z[0] for z in cclasses]);cat.insert(2,'Classification notes',[z[1] for z in cclasses])
    evidence,log=research(cat,fx,fx_date,online,max_items)
    # When recomputing without search, retain prior research evidence instead of clearing it.
    if not online and Path('price_evidence_v11.csv').exists() and Path('price_evidence_v11.csv').stat().st_size>5:
        evidence=pd.read_csv('price_evidence_v11.csv',keep_default_na=False)
    if not online and Path('search_diagnostics_v11.csv').exists() and Path('search_diagnostics_v11.csv').stat().st_size>5:
        log=pd.read_csv('search_diagnostics_v11.csv',keep_default_na=False)
    approval_path=Path('approved_quotes.csv')
    if not approval_path.exists():
        pd.DataFrame({'Item ID':cat['Item ID'],'Approved SEK per unit':['']*len(cat),'Approval':['UNQUOTED']*len(cat),'Source / Quote ID':['']*len(cat),'Approved by':['']*len(cat),'Approval date':['']*len(cat),'Pack quantity':['']*len(cat),'Price scope':['']*len(cat)}).to_csv(approval_path,index=False)
    approved,errors=read_approved(str(approval_path))
    inputs={'successful_infusions':12,'planning_confidence':0.9,'collection_to_start':1.0,'release_to_infusion':1.0,'vector_lots':1,'program_years':1,'program_months':12}
    f=Path('assumptions.json')
    if f.exists():inputs.update(json.loads(f.read_text(encoding='utf-8')))
    else:f.write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    scenario,detail=scenarios(cat,approved,inputs)
    request=cat[cat['Price sourcing route'].str.startswith('RFQ') | ~cat['Item ID'].isin(approved)].copy()
    request['RFQ status']='QUOTE_REQUIRED';request['Requested vendor']='';request['Quote contact']='';request['Due date']=''
    audit=pd.DataFrame([{'Check':'Source items','Value':len(cat)},{'Check':'Candidates extracted','Value':len(evidence)},{'Check':'Approved entries','Value':len(approved)},{'Check':'Approval errors','Value':len(errors)},{'Check':'FX status','Value':fx_status},{'Check':'FX date','Value':fx_date},{'Check':'Price approval policy','Value':'CANDIDATE_REVIEW never flows to Budget'}]+[{'Check':'Approval error','Value':x} for x in errors])
    fx_df=pd.DataFrame([{'Currency':k,'SEK per unit':v,'Date':fx_date,'Source':fx_source,'Status':fx_status} for k,v in fx.items()])
    export_workbook('CAR_T_Budget_v11.xlsx',{'Budget scenarios':scenario,'Line item costs':detail,'Catalog classification':cat,'Web price evidence':evidence,'RFQ register':request,'Search diagnostics':log,'Approved quotes':pd.read_csv(approval_path,keep_default_na=False),'FX rates':fx_df,'Audit':audit})
    for name,df in [('price_evidence_v11.csv',evidence),('rfq_register_v11.csv',request),('search_diagnostics_v11.csv',log),('scenario_budget_v11.csv',scenario)]:df.to_csv(name,index=False)
    print('Created CAR_T_Budget_v11.xlsx. Prices not QA-approved are excluded.');print(scenario.to_string(index=False))
    return scenario

if __name__=='__main__':run(online=os.getenv('ONLINE','1')=='1',max_items=SEARCH_LIMIT)
