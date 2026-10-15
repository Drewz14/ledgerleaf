import math, time, yfinance as yf
from forecast import build_forecast
from flask import Flask, jsonify, send_from_directory
app = Flask(__name__, static_folder='static')
CACHE = {}
app.json.sort_keys = False

def g(i, k):
    v = i.get(k)
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v
def pct(x): return None if x is None else f"{x*100:.1f}%"
def money(x):
    if x is None: return "n/a"
    a = abs(x)
    for d, s in ((1e12,'T'),(1e9,'B'),(1e6,'M')):
        if a >= d: return f"${x/d:.2f}{s}"
    return f"${x:,.2f}"
def na(x): return "n/a" if x is None else x

def safe_fc(t):
    try: return build_forecast(t)
    except Exception as e: return {'error': str(e)}

def build(sym):
    t = yf.Ticker(sym); i = t.info or {}
    h = t.history(period='1y')
    if h.empty and not g(i,'currentPrice'): return None
    closes = [round(float(c),2) for c in h['Close']]
    dates = [d.strftime('%Y-%m-%d') for d in h.index]
    price = g(i,'currentPrice') or g(i,'regularMarketPrice') or (closes[-1] if closes else None)
    name = g(i,'longName') or g(i,'shortName') or sym
    sector, industry = g(i,'sector') or 'n/a', g(i,'industry') or 'n/a'
    mcap, pe, fpe = g(i,'marketCap'), g(i,'trailingPE'), g(i,'forwardPE')
    rev, rg, gm, om, pm = g(i,'totalRevenue'), g(i,'revenueGrowth'), g(i,'grossMargins'), g(i,'operatingMargins'), g(i,'profitMargins')
    cash, debt, fcf, de, cr = g(i,'totalCash'), g(i,'totalDebt'), g(i,'freeCashflow'), g(i,'debtToEquity'), g(i,'currentRatio')
    beta, emp, roe = g(i,'beta'), g(i,'fullTimeEmployees'), g(i,'returnOnEquity')
    lo, hi = g(i,'fiftyTwoWeekLow'), g(i,'fiftyTwoWeekHigh')
    country = g(i,'country') or 'n/a'
    summary = g(i,'longBusinessSummary') or 'No company description available from the data source.'
    # volatility
    vol = None
    if len(closes) > 30:
        r = [math.log(closes[k]/closes[k-1]) for k in range(1,len(closes))]
        m = sum(r)/len(r); vol = math.sqrt(sum((x-m)**2 for x in r)/(len(r)-1))*math.sqrt(252)
    ret1y = (closes[-1]/closes[0]-1) if len(closes)>1 else None
    sz = 'mega-cap' if mcap and mcap>2e11 else 'large-cap' if mcap and mcap>1e10 else 'mid-cap' if mcap and mcap>2e9 else 'small-cap' if mcap and mcap>3e8 else 'micro-cap' if mcap else 'unknown-size'
    sents = [s.strip() for s in summary.split('. ') if s.strip()]
    def para(*xs): return ' '.join(x for x in xs if x)
    def fmt(x,f="{:.1f}"): return "n/a" if x is None else f.format(x)

    deep = {
      'Executive Summary': para(f"{name} ({sym}) is a {sz} company in {industry} ({sector}), with a market value of {money(mcap)}.",
          f"Over the past year the stock moved {pct(ret1y)}." if ret1y is not None else None,
          f"Trailing revenue is {money(rev)} with a net margin of {na(pct(pm))}." ),
      'Company Background': '. '.join(sents[:3]) + ('.' if sents else ''),
      'Strategy & Innovation': para('. '.join(sents[3:6]) + '.' if len(sents)>3 else None,
          f"Gross margin of {pct(gm)} suggests {'strong pricing power or a differentiated product' if gm and gm>0.5 else 'a more competitive or cost-heavy business' if gm is not None else 'n/a'}."),
      'Global Footprint': para(f"Headquartered in {country}.", f"Employs about {emp:,} people." if emp else "Employee count: n/a."),
    }
    pos = 'a dominant scale player' if mcap and mcap>2e11 else 'an established player' if mcap and mcap>1e10 else 'a smaller challenger'
    comp = {
      'Market Position': f"By market value, {name} is {pos} in {industry}.",
      'Competitive Edges': para(
          f"Operating margin of {pct(om)} {'is well above typical levels, a sign of scale or moat' if om and om>0.2 else 'is modest, so execution matters' if om is not None and om>0 else 'is negative, meaning the core business is not yet profitable' if om is not None else 'is n/a'}.",
          f"Return on equity of {pct(roe)}." if roe is not None else None),
      'Key Risks': para(f"Beta of {fmt(beta,'{:.2f}')} means the stock tends to move {'more' if beta and beta>1 else 'less'} than the market." if beta else None,
          f"Revenue growth of {pct(rg)} year over year {'is a warning sign' if rg is not None and rg<0 else ''}." if rg is not None else "Revenue growth: n/a."),
      'Outlook': f"{'Growing revenue and positive margins support a steady outlook' if (rg or 0)>0 and (pm or 0)>0 else 'Mixed growth and profitability signals call for caution'}. Peer comparison should be checked against companies in {industry}.",
    }
    mkt = {
      'Macro & Regulatory': f"As a {sector} company, {name} is exposed to interest rates, consumer and business spending, and sector-specific regulation in {country} and its export markets.",
      'Industry Trends': f"Valuation context: trailing P/E {fmt(pe)}, forward P/E {fmt(fpe)}. " + ("A lower forward P/E implies analysts expect earnings to grow." if pe and fpe and fpe<pe else "A higher or missing forward P/E means growth expectations are flat or unclear." ),
      'Opportunities & Risks': f"The stock sits {pct((price-lo)/(hi-lo)) if price and lo and hi and hi>lo else 'n/a'} of the way between its 52-week low ({money(lo)}) and high ({money(hi)}).",
    }
    net = (cash - debt) if cash is not None and debt is not None else None
    thesis = {
      'Financial Strength': para(f"Cash {money(cash)} vs. debt {money(debt)} — net {'cash' if net and net>0 else 'debt'} of {money(abs(net)) if net is not None else 'n/a'}.",
          f"Current ratio {fmt(cr,'{:.2f}')}; debt-to-equity {fmt(de)}."),
      'Cash Generation': f"Free cash flow: {money(fcf)}." + (" Positive FCF gives room for buybacks, dividends or reinvestment." if fcf and fcf>0 else " Negative or missing FCF means the company may rely on outside funding." ),
      'Growth & Profitability': f"Revenue growth {na(pct(rg))}; gross {na(pct(gm))}, operating {na(pct(om))}, net {na(pct(pm))} margins.",
      'Diversification': f"Sector: {sector}; industry: {industry}. Details on revenue mix by segment are in the company's 10-K filing on SEC EDGAR.",
    }
    # scenarios: 1-year range from historical volatility, plus analyst targets
    scen = None
    if price and vol:
        def r(a,b): return [round(price*a,2), round(price*b,2)]
        scen = {'method': f"Ranges = current price ${price:.2f} × (1 ± multiples of 1-year historical volatility {vol*100:.1f}%). Bull: +0.5σ to +1σ. Base: −0.5σ to +0.5σ. Bear: −1σ to −0.5σ (floored at 5%).",
          'bull': r(1+0.5*vol, 1+vol), 'base': r(1-0.5*vol, 1+0.5*vol), 'bear': r(max(0.05,1-vol), max(0.05,1-0.5*vol)),
          'analyst': {'low': g(i,'targetLowPrice'), 'mean': g(i,'targetMeanPrice'), 'high': g(i,'targetHighPrice'), 'n': g(i,'numberOfAnalystOpinions')}}
    stats = [('Price', money(price)), ('Market cap', money(mcap)), ('P/E (ttm)', fmt(pe)), ('52w range', f"{money(lo)} – {money(hi)}"),
             ('Revenue', money(rev)), ('Gross margin', na(pct(gm))), ('Op. margin', na(pct(om))), ('Net margin', na(pct(pm)))]
    return dict(symbol=sym, name=name, sector=sector, industry=industry, stats=stats, chart={'d':dates,'c':closes},
      sections=[['The Deep Dive',deep],['Competitive Environment',comp],['Overall Market Environment',mkt],['Investment Thesis',thesis]],
      scenarios=scen, forecast=safe_fc(t), asof=time.strftime('%Y-%m-%d %H:%M ET'))

@app.route('/api/report/<sym>')
def report(sym):
    sym = sym.upper().strip()[:10]
    c = CACHE.get(sym)
    if c and time.time()-c[0] < 900: return jsonify(c[1])
    try: d = build(sym)
    except Exception as e: return jsonify(error=f"Could not load data: {e}"), 502
    if not d: return jsonify(error=f"No data found for '{sym}'."), 404
    CACHE[sym] = (time.time(), d); return jsonify(d)

@app.route('/')
def index(): return send_from_directory('static','index.html')
if __name__ == '__main__':
    import os; app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8787)))
