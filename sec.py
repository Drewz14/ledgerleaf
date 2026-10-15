"""SEC EDGAR fallbacks (free, no key). Cached in memory."""
import time, datetime as dt, requests
import os
# SEC asks for an app name + contact email; it rejects github noreply addresses. Set SEC_USER_AGENT on Render to use a real email.
UA = {'User-Agent': os.environ.get('SEC_USER_AGENT', 'Ledgerleaf admin@ledgerleaf-ni8n.onrender.com'), 'Accept-Encoding': 'gzip'}
_C = {}
def _get(url, ttl=86400):
    c = _C.get(url)
    if c and time.time() - c[0] < ttl: return c[1]
    r = requests.get(url, headers=UA, timeout=20); r.raise_for_status()
    d = r.json(); _C[url] = (time.time(), d); return d

def cik_for(sym):
    for v in _get('https://www.sec.gov/files/company_tickers.json').values():
        if v['ticker'].upper() == sym.replace('-', '.').upper() or v['ticker'].upper() == sym.upper():
            return str(v['cik_str']).zfill(10), v['title']
    return None, None

def _d(s): return dt.date.fromisoformat(s)
def _units(facts, names, unit='USD', ns='us-gaap'):
    best = []
    for n in names:
        u = facts.get(ns, {}).get(n, {}).get('units', {}).get(unit)
        if u and (not best or max(x['end'] for x in u) > max(x['end'] for x in best)): best = u
    return best

def ttm(facts, names, unit='USD'):
    """Trailing twelve months = latest fiscal year + current YTD - prior-year YTD. Returns (ttm, latest_annual, prior_annual)."""
    u = [x for x in _units(facts, names, unit) if 'start' in x]
    for x in u: x['_days'] = (_d(x['end']) - _d(x['start'])).days
    ann = sorted({x['end']: x for x in u if 350 <= x['_days'] <= 380}.values(), key=lambda x: x['end'])
    if not ann: return None, None, None
    A = ann[-1]; prev = ann[-2]['val'] if len(ann) > 1 and (_d(A['end']) - _d(ann[-2]['end'])).days < 400 else None
    ytd = [x for x in u if _d(x['start']) > _d(A['end']) and x['_days'] < 350]
    if ytd:
        Y = max(ytd, key=lambda x: x['end'])
        P = [x for x in u if abs((_d(Y['end']) - _d(x['end'])).days - 365) < 10 and abs(x['_days'] - Y['_days']) < 10]
        if P: return A['val'] + Y['val'] - P[0]['val'], A['val'], prev
    return A['val'], A['val'], prev

def latest_instant(facts, names, unit='USD', ns='us-gaap'):
    u = [x for x in _units(facts, names, unit, ns) if 'start' not in x]
    return max(u, key=lambda x: x['end'])['val'] if u else None

def shares(f):
    # cover-page share count (sums share classes reported for the same date), else balance-sheet / weighted-average diluted shares
    for ns, n in (('dei', 'EntityCommonStockSharesOutstanding'), ('us-gaap', 'CommonStockSharesOutstanding')):
        u = f.get(ns, {}).get(n, {}).get('units', {}).get('shares', [])
        if u:
            end = max(x['end'] for x in u); acc = max((x for x in u if x['end'] == end), key=lambda x: x['filed'])['accn']
            vals = {x.get('frame') or x['val']: x['val'] for x in u if x['end'] == end and x['accn'] == acc}
            if (dt.date.today() - _d(end)).days < 400: return float(sum(vals.values()))
    u = [x for x in _units(f, ['WeightedAverageNumberOfDilutedSharesOutstanding'], 'shares') if 'start' in x]
    return float(max(u, key=lambda x: x['end'])['val']) if u else None

REV = ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerIncludingAssessedTax']
def fundamentals(sym):
    cik, title = cik_for(sym)
    if not cik: return {}
    out = {'longName': title}
    try:
        s = _get(f'https://data.sec.gov/submissions/CIK{cik}.json')
        out['longName'] = s.get('name', title).title() if s.get('name', '').isupper() else s.get('name', title)
        sic = s.get('sicDescription')
        if sic: out['sector'] = out['industry'] = sic.title()
        a = (s.get('addresses') or {}).get('business') or {}
        out['country'] = 'United States' if a.get('stateOrCountry') and len(a.get('stateOrCountry')) == 2 and not a.get('isForeignLocation') else a.get('stateOrCountryDescription')
        out['_city'] = ', '.join(x for x in [a.get('city'), a.get('stateOrCountry')] if x)
        out['_fye'] = s.get('fiscalYearEnd')
    except Exception: pass
    try: f = _get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')['facts']
    except Exception: return out
    rev, revA, revP = ttm(f, REV)
    gp = ttm(f, ['GrossProfit'])[0]
    if gp is None:
        cogs = ttm(f, ['CostOfGoodsAndServicesSold', 'CostOfRevenue'])[0]
        gp = rev - cogs if rev is not None and cogs is not None else None
    op = ttm(f, ['OperatingIncomeLoss'])[0]; ni = ttm(f, ['NetIncomeLoss'])[0]
    eps = ttm(f, ['EarningsPerShareDiluted', 'EarningsPerShareBasic'], 'USD/shares')[0]
    ocf = ttm(f, ['NetCashProvidedByUsedInOperatingActivities'])[0]; capex = ttm(f, ['PaymentsToAcquirePropertyPlantAndEquipment'])[0]
    div = lambda a, b: a / b if a is not None and b else None
    out.update({'totalRevenue': rev, 'grossMargins': div(gp, rev), 'operatingMargins': div(op, rev), 'profitMargins': div(ni, rev),
        'revenueGrowth': div(revA, revP) - 1 if revA and revP else None, '_eps': eps,
        'freeCashflow': ocf - capex if ocf is not None and capex is not None else None,
        'totalCash': latest_instant(f, ['CashAndCashEquivalentsAtCarryingValue']),
        'totalDebt': latest_instant(f, ['LongTermDebt', 'LongTermDebtNoncurrent']),
        '_shares': shares(f)})
    return {k: v for k, v in out.items() if v is not None}
