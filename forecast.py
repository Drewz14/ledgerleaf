"""Historical statistics (not predictions): seasonality and pattern-similarity projection."""
import numpy as np, pandas as pd, datetime as dt
MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

def seasonality(s):
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=30)]
    m = s.resample('ME').last().pct_change().dropna()
    m = m[m.index < pd.Timestamp(s.index[-1].year, s.index[-1].month, 1, tz=m.index.tz)]  # complete months only
    months = []
    for k in range(1, 13):
        r = m[m.index.month == k]
        months.append({'m': MON[k-1], 'avg': round(float(r.mean())*100, 2) if len(r) else None,
                       'win': round(float((r > 0).mean())*100) if len(r) else None, 'n': int(len(r))})
    years = sorted(set(m.index.year))
    # next ~3 months (63 trading days) starting on today's calendar date in past years
    today = s.index[-1]; rets = []
    for y in range(today.year - 30, today.year):
        try: start = pd.Timestamp(y, today.month, min(today.day, 28), tz=s.index.tz)
        except Exception: continue
        idx = s.index.searchsorted(start)
        if idx + 63 < len(s) and s.index[idx] - start < pd.Timedelta(days=7) and s.index[idx+63] < today - pd.Timedelta(days=1):
            rets.append(s.iloc[idx+63] / s.iloc[idx] - 1)
    valid = [x for x in months if x['avg'] is not None and x['n'] >= 5]
    best = max(valid, key=lambda x: x['avg']) if valid else None
    worst = min(valid, key=lambda x: x['avg']) if valid else None
    nxt = {'avg': round(float(np.mean(rets))*100, 2), 'median': round(float(np.median(rets))*100, 2),
           'win': round(float(np.mean(np.array(rets) > 0))*100), 'n': len(rets),
           'from': today.strftime('%b %d')} if len(rets) >= 5 else None
    return {'months': months, 'years': f"{years[0]}–{years[-1]}" if years else 'n/a', 'n_years': len(years),
            'best': best, 'worst': worst, 'next3m': nxt}

def pattern(s, L=63, H=63, max_matches=20, min_corr=0.8):
    c = s.values.astype(float); n = len(c)
    last = n - L - H - 252  # candidate windows + their forward period end before the most recent year
    if last < 50: return None
    lc = np.log(c)
    rec = lc[-L:] - lc[-L]; rz = (rec - rec.mean()) / rec.std()
    W = np.lib.stride_tricks.sliding_window_view(lc[:last + L], L)[:last]
    Wc = W - W.mean(1, keepdims=True); sd = Wc.std(1); sd[sd == 0] = np.inf
    corr = (Wc / sd[:, None]) @ rz / L
    picked = []
    for i in np.argsort(-corr):
        if corr[i] < min_corr or len(picked) >= max_matches: break
        if all(abs(i - j) >= L + H for j in picked): picked.append(int(i))
    if not picked: return {'matches': 0}
    paths = np.array([c[i+L-1:i+L+H] / c[i+L-1] for i in picked])  # forward paths, 1.0 at window end
    fwd = paths[:, -1] - 1; pb = float((fwd > 0).mean()); ac = float(corr[picked].mean())
    score = 1 + (len(picked) >= 8) + (len(picked) >= 15) + (ac >= 0.85) + (max(pb, 1 - pb) >= 0.65)
    p0 = c[-1]; dates = [d.strftime('%Y-%m-%d') for d in s.index[-L:]]
    fut = pd.bdate_range(s.index[-1] + pd.Timedelta(days=1), periods=H)
    return {'matches': len(picked), 'avg_corr': round(ac, 3), 'bull': round(pb*100), 'bear': round((1-pb)*100),
            'median': round(float(np.median(fwd))*100, 2), 'p10': round(float(np.percentile(fwd, 10))*100, 2),
            'p90': round(float(np.percentile(fwd, 90))*100, 2), 'min': round(float(fwd.min())*100, 2),
            'max': round(float(fwd.max())*100, 2), 'score': int(score), 'L': L, 'H': H,
            'match_dates': [s.index[i].strftime('%Y-%m-%d') for i in picked],
            'chart': {'d': dates + [d.strftime('%Y-%m-%d') for d in fut], 'recent': [round(float(x), 2) for x in c[-L:]],
                      'med': [round(float(x)*p0, 2) for x in np.median(paths, 0)[1:]],
                      'lo': [round(float(x)*p0, 2) for x in np.percentile(paths, 25, 0)[1:]],
                      'hi': [round(float(x)*p0, 2) for x in np.percentile(paths, 75, 0)[1:]]}}

def build_forecast(t):
    h = t.history(period='max', auto_adjust=True)
    if h.empty or len(h) < 300: return None
    s = h['Close'].dropna()
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=30)]
    return {'history': f"{s.index[0]:%Y-%m-%d} to {s.index[-1]:%Y-%m-%d}", 'seasonality': seasonality(s), 'pattern': pattern(s)}
