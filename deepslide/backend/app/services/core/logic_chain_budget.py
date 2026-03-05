import math
import re
from typing import Any, Dict, List, Tuple


def parse_total_minutes(text: str, default: int = 10) -> int:
    s = str(text or "").strip().lower()
    if not s:
        return int(default)

    try:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2))
            ss = int(m.group(3) or "0")
            total_sec = hh * 3600 + mm * 60 + ss
            return max(1, int(round(total_sec / 60.0)))

        num_m = re.search(r"(\d+(?:\.\d+)?)", s)
        if not num_m:
            return int(default)
        num = float(num_m.group(1))

        if re.search(r"(\d+(?:\.\d+)?)\s*(hour|hours|小时|h)\b", s):
            return max(1, int(round(num * 60.0)))
        if re.search(r"(\d+(?:\.\d+)?)\s*(min|mins|minute|minutes|分钟|分)\b", s):
            return max(1, int(round(num)))
        if re.search(r"(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|秒)\b", s):
            return max(1, int(round(num / 60.0)))
        if re.search(r"(\d+(?:\.\d+)?)\s*s\b", s):
            return max(1, int(round(num / 60.0)))

        return max(1, int(round(num)))
    except Exception:
        return int(default)


def target_node_range(total_minutes: int) -> Tuple[int, int]:
    t = int(total_minutes or 0)
    if t >= 10:
        return (4, 7)
    if t >= 6:
        return (4, 6)
    if t >= 4:
        return (3, 5)
    return (2, 3)


def enforce_max_nodes(nodes: List[Dict[str, Any]], max_nodes: int) -> List[Dict[str, Any]]:
    out = [dict(x or {}) for x in (nodes or []) if isinstance(x, dict)]
    m = max(1, int(max_nodes or 1))
    while len(out) > m and len(out) >= 2:
        a = out[-2]
        b = out[-1]

        a_desc = str(a.get("description") or "").strip()
        b_desc = str(b.get("description") or "").strip()
        merged_desc = (a_desc + ("\n" if (a_desc and b_desc) else "") + b_desc).strip()

        try:
            ra = float(a.get("duration_ratio", 0.0) or 0.0)
        except Exception:
            ra = 0.0
        try:
            rb = float(b.get("duration_ratio", 0.0) or 0.0)
        except Exception:
            rb = 0.0
        a["duration_ratio"] = ra + rb
        if merged_desc:
            a["description"] = merged_desc

        out.pop()
    return out


def allocate_minutes_from_ratios(nodes: List[Dict[str, Any]], total_minutes: int) -> List[int]:
    n = len(nodes or [])
    total = max(1, int(total_minutes or 1))
    if n <= 0:
        return []

    ratios: List[float] = []
    for node in nodes:
        try:
            r = float((node or {}).get("duration_ratio", 0.0) or 0.0)
        except Exception:
            r = 0.0
        ratios.append(r if r > 0 else 0.0)

    s = sum(ratios)
    if s <= 0:
        ratios = [1.0 / n for _ in range(n)]
    else:
        ratios = [r / s for r in ratios]

    raw = [r * total for r in ratios]
    mins = [int(math.floor(x)) for x in raw]
    used = sum(mins)
    rem = total - used
    if rem > 0:
        order = sorted(range(n), key=lambda i: (raw[i] - mins[i], raw[i]), reverse=True)
        for i in order[:rem]:
            mins[i] += 1

    zeros = [i for i, v in enumerate(mins) if v < 1]
    if zeros:
        for i in zeros:
            mins[i] = 1
        need = sum(mins) - total
        if need > 0:
            donors = sorted(range(n), key=lambda i: mins[i], reverse=True)
            for _ in range(need):
                moved = False
                for d in donors:
                    if mins[d] > 1:
                        mins[d] -= 1
                        moved = True
                        break
                if not moved:
                    raise ValueError("insufficient_minutes_for_min1")

    if sum(mins) != total:
        raise ValueError("allocation_not_conservative")
    return mins

