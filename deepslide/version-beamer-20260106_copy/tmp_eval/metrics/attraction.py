import math

def _bool_seq(frames, paras, rule_fns):
    n = min(len(frames), len(paras))
    s = []
    for k in range(n):
        v = 0
        for fn in rule_fns:
            try:
                if fn(frames[k], paras[k]):
                    v = 1
                    break
            except Exception:
                v = v
        s.append(v)
    return s

def ohs(frames, paras, m, rule_fns, weights=None):
    m = min(m, len(frames), len(paras))
    if weights is None:
        weights = [1.0 / max(1, len(rule_fns))] * len(rule_fns)
    tot = 0.0
    for k in range(m):
        for i, fn in enumerate(rule_fns):
            try:
                if fn(frames[k], paras[k]):
                    tot += weights[i]
            except Exception:
                tot += 0.0
    return tot

def sf(frames, paras, rule_fns):
    s = _bool_seq(frames, paras, rule_fns)
    return sum(s)

def mp(frames, paras, rule_fns):
    s = _bool_seq(frames, paras, rule_fns)
    best = 0
    cur = 0
    for v in s:
        if v == 0:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best

def _rho(s, L):
    n = len(s)
    if n == 0 or L <= 0 or L >= n:
        return 0.0
    mean = sum(s) / float(n)
    num = 0.0
    den = 0.0
    for k in range(n - L):
        num += (s[k] - mean) * (s[k + L] - mean)
    for k in range(n):
        den += (s[k] - mean) * (s[k] - mean)
    if den == 0.0:
        return 0.0
    return num / den

def rr(frames, paras, rule_fns):
    s = _bool_seq(frames, paras, rule_fns)
    r2 = _rho(s, 2)
    r1 = _rho(s, 1)
    return 0.5 * (((r2 + 1.0) / 2.0) + ((1.0 - r1) / 2.0))

def rs(frames, paras, rule_fns, w_sf=0.34, w_mp=0.33, w_rr=0.33):
    n = max(1, min(len(frames), len(paras)))
    s_sf = sf(frames, paras, rule_fns)
    s_mp = mp(frames, paras, rule_fns)
    s_rr = rr(frames, paras, rule_fns)
    return w_sf * s_sf + w_mp * (1.0 - (s_mp / float(n))) + w_rr * s_rr

def clc(n, edges, W=3, w_lcr=0.5, w_ars=0.5):
    if not edges:
        return 0.0
    total = float(len(edges))
    acc_span = 0.0
    acc_local = 0.0
    for k, j in edges:
        d = abs(int(k) - int(j))
        acc_span += d
        if d <= int(W):
            acc_local += 1.0
    ars = acc_span / total
    ars_norm = ars / float(max(1, n - 1))
    lcr = acc_local / total
    return (w_lcr * lcr + w_ars * (1.0 - ars_norm)) / (w_lcr + w_ars)

