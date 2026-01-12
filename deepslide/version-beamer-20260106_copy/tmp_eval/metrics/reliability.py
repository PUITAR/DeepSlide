import math

def acsr(success, attempts):
    a = int(attempts)
    if a <= 0:
        return 0.0
    return max(0.0, min(1.0, float(success) / float(a)))

def _tokenize(x):
    return [t for t in (x or "").lower().split() if t]

def _rouge1(a, b):
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not tb:
        return 0.0
    sb = {}
    for t in tb:
        sb[t] = sb.get(t, 0) + 1
    overlap = 0
    for t in ta:
        if sb.get(t, 0) > 0:
            overlap += 1
            sb[t] -= 1
    return overlap / float(len(tb))

def _jaccard(a, b):
    sa = set(_tokenize(a))
    sb = set(_tokenize(b))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / float(union)

def textual_fidelity(frames_text, paras_text, refs_text, w_rouge=0.5, w_bert=0.5):
    n = min(len(frames_text or []), len(paras_text or []), len(refs_text or []))
    if n <= 0:
        return 0.0
    s_rouge = 0.0
    s_bert = 0.0
    for k in range(n):
        r1 = _rouge1(paras_text[k], refs_text[k])
        r2 = _rouge1(frames_text[k], refs_text[k])
        s_rouge += 0.5 * (r1 + r2)
        b1 = _jaccard(paras_text[k], refs_text[k])
        b2 = _jaccard(frames_text[k], refs_text[k])
        s_bert += 0.5 * (b1 + b2)
    s_rouge /= float(n)
    s_bert /= float(n)
    return w_rouge * s_rouge + w_bert * s_bert

def visual_fidelity(source_fig_count, slide_fig_count):
    a = int(source_fig_count)
    if a <= 0:
        return 0.0
    return max(0.0, min(1.0, float(slide_fig_count) / float(a)))

