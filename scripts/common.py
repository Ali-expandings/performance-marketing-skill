"""Shared helpers: profile/config loading, phone-to-country, channel mapping, number checks."""
import json
import os
import re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(profile_path=None):
    """config/defaults.json merged with a client profile (profile wins)."""
    cfg = read_json(os.path.join(SKILL_DIR, "config", "defaults.json"))
    if profile_path:
        cfg = deep_merge(cfg, read_json(profile_path))
    return cfg


# ---------- phone -> country ----------
CALLING_CODES = {
    "1": "USA/Canada", "7": "Russia/Kazakhstan", "20": "Egypt", "27": "South Africa", "30": "Greece",
    "31": "Netherlands", "32": "Belgium", "33": "France", "34": "Spain", "39": "Italy", "41": "Switzerland",
    "43": "Austria", "44": "UK", "46": "Sweden", "47": "Norway", "48": "Poland", "49": "Germany",
    "52": "Mexico", "54": "Argentina", "55": "Brazil", "56": "Chile", "57": "Colombia", "60": "Malaysia",
    "61": "Australia", "62": "Indonesia", "63": "Philippines", "64": "New Zealand", "65": "Singapore",
    "66": "Thailand", "81": "Japan", "82": "South Korea", "84": "Vietnam", "86": "China", "90": "Turkey",
    "91": "India", "92": "Pakistan", "93": "Afghanistan", "94": "Sri Lanka", "98": "Iran",
    "211": "South Sudan", "212": "Morocco", "213": "Algeria", "216": "Tunisia", "218": "Libya",
    "221": "Senegal", "222": "Mauritania", "225": "Ivory Coast", "233": "Ghana", "234": "Nigeria",
    "237": "Cameroon", "249": "Sudan", "251": "Ethiopia", "252": "Somalia", "253": "Djibouti",
    "254": "Kenya", "255": "Tanzania", "256": "Uganda", "269": "Comoros", "291": "Eritrea",
    "351": "Portugal", "353": "Ireland", "380": "Ukraine", "852": "Hong Kong", "880": "Bangladesh",
    "960": "Maldives", "961": "Lebanon", "962": "Jordan", "963": "Syria", "964": "Iraq", "965": "Kuwait",
    "966": "Saudi Arabia", "967": "Yemen", "968": "Oman", "970": "Palestine", "971": "UAE",
    "972": "Israel/Palestine", "973": "Bahrain", "974": "Qatar", "977": "Nepal", "994": "Azerbaijan",
    "995": "Georgia", "998": "Uzbekistan",
}
PHONE_RE = re.compile(r"(\+|00)?\s?(\d(?:[\s\-().]?\d){7,14})")


def country_from_text(text, local_patterns=None, labels=None):
    """Find the first phone number in text and return its country label, or None."""
    if not text:
        return None
    labels = labels or {}
    for m in PHONE_RE.finditer(str(text)):
        intl = bool(m.group(1))
        digits = re.sub(r"\D", "", m.group(2))
        if digits.startswith("00"):
            intl, digits = True, digits[2:]
        for lp in local_patterns or []:
            if re.fullmatch(lp["regex"], digits):
                return lp["country"]
        if not intl and len(digits) < 11:
            continue  # short local number with no known pattern
        for n in (3, 2, 1):
            code = digits[:n]
            if code in CALLING_CODES:
                name = labels.get(code, CALLING_CODES[code])
                return f"{name} (+{code})"
    return None


def map_channel(value, channel_map):
    if value is None or str(value).strip() == "" or str(value).lower() == "nan":
        return "Unknown"
    v = str(value).lower()
    for name, keys in channel_map.items():
        if any(k in v for k in keys):
            return name
    return str(value).strip()


def classify_keywords(value, mapping, default="Unclassified"):
    v = str(value or "").lower()
    for name, keys in mapping.items():
        if any(k in v for k in keys):
            return name
    return default


# ---------- number verification ----------
NUM_RE = re.compile(r"(?<![\w.])[-+]?\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?([kKmM](?![a-zA-Z])|%|x(?![a-zA-Z])|×)?")


def numbers_in(text):
    """Yield (value, raw, tolerance) for every number in a string. K/M are expanded.
    Tolerance is half of the last digit shown, so '$124.3K' matches 124,250-124,350."""
    for m in NUM_RE.finditer(str(text)):
        raw = m.group(0).strip()
        v = float((m.group(1) + (m.group(2) or "")).replace(",", ""))
        suf = (m.group(3) or "").lower()
        mult = {"k": 1_000, "m": 1_000_000}.get(suf, 1)
        decimals = len(m.group(2)) - 1 if m.group(2) else 0
        yield v * mult, raw, 0.5 * 10 ** -decimals * mult + 1e-9


def collect_numbers(obj, out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if obj == obj:  # not NaN
            out.append(float(obj))
    elif isinstance(obj, str):
        out.extend(v for v, _, _ in numbers_in(obj))
    return out


def allowed_values(values):
    allowed = set()
    for v in values:
        allowed.add(v)
        allowed.add(-v)
        if abs(v) <= 5:  # ratios may be written as percentages
            allowed.add(v * 100)
            allowed.add(-v * 100)
    return sorted(allowed)


def is_verified(n, allowed, tol=0.051):
    """True if n equals a known value within the rounding shown (tol from numbers_in)."""
    import bisect
    tol = max(tol, abs(n) * 0.0005)
    i = bisect.bisect_left(allowed, n - tol)
    return i < len(allowed) and allowed[i] <= n + tol
