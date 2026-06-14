#!/usr/bin/env python3
"""
fb-existence-checker — bulk-check whether Facebook profiles still exist.

Uses the public graph.facebook.com profile-picture redirect. No login, no API
token, no dependencies (Python 3.8+ stdlib only).

  LIVE      profile exists and has a public profile photo
  NO_PHOTO  profile object exists but returns a default/blank avatar
            (active-without-photo, privacy-restricted, OR deactivated — ambiguous)
  DEAD      Facebook returns "does not exist" (HTTP 400) — invalid / fully removed
  UNKNOWN_* transient / network / rate-limit (retried once)

Only works with NUMERIC Facebook IDs. Vanity /username URLs cannot be resolved
this way (Facebook returns 400 without an access token) and are flagged NO_ID.

Usage:
    python3 fb_check.py input.txt [-o results.csv] [-w 15]

input.txt may contain, one per line, any of:
    1000xxxxxxxxxxx
    https://www.facebook.com/profile.php?id=1000xxxxxxxxxxx
    https://www.facebook.com/1000xxxxxxxxxxx
    https://www.facebook.com/some.vanity.name   -> NO_ID (needs a browser pass)

Or a CSV: pass --id-col to name the column holding the id/url.
"""
import argparse, csv, re, sys, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

GRAPH = "https://graph.facebook.com/{}/picture?type=normal"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # don't follow — we want the Location
        return None
_opener = urllib.request.build_opener(_NoRedirect)

ID_RE = re.compile(r"(?:profile\.php\?id=|facebook\.com/)(\d+)|^(\d+)$")

def extract_id(s):
    s = s.strip()
    m = ID_RE.search(s)
    if m:
        return m.group(1) or m.group(2)
    return None

def _probe(uid):
    req = urllib.request.Request(GRAPH.format(uid), headers={"User-Agent": UA})
    try:
        resp = _opener.open(req, timeout=25)
        code, loc = resp.getcode(), resp.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        code, loc = e.code, e.headers.get("Location", "")
    except Exception:
        return "UNKNOWN_ERR"
    if loc and "scontent" in loc:
        return "LIVE"
    if loc and any(k in loc for k in ("static.", "/rsrc.", "default")):
        return "NO_PHOTO"
    if code == 400:
        return "DEAD"
    return f"UNKNOWN_{code}"

def classify(uid):
    s = _probe(uid)
    if s.startswith("UNKNOWN"):
        s2 = _probe(uid)
        if not s2.startswith("UNKNOWN"):
            s = s2
    return s

def load_lines(path, id_col):
    if id_col is not None:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield row.get(id_col, "")
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield line.strip()

_ID_IN_HTML = re.compile(
    r'"userID":"(\d+)"|"entity_id":"(\d+)"|"delegate_page":\{"id":"(\d+)"'
    r'|fb://(?:profile|page)/(\d+)|"pageID":"(\d+)"|profile_id=(\d+)|/profile\.php\?id=(\d+)'
)

def _profile_url(raw):
    return raw if raw.startswith("http") else f"https://www.facebook.com/{raw}"

def resolve_ids(raws, attempts=3):
    """Resolve vanity /username inputs to numeric IDs — NO browser.

    Uses `curl_cffi` (lazy-imported) to impersonate a real Chrome TLS fingerprint,
    which is what gets past Facebook's edge block. A session is seeded against the
    homepage first to pick up the `datr` cookie, so Facebook serves the full public
    profile page (not the login wall); the numeric id is then read from the HTML.

    Returns {raw: id_or_None}. Needs:  pip install curl_cffi"""
    try:
        from curl_cffi import requests as creq
    except ImportError:
        print("  [--resolve] needs curl_cffi:  pip install curl_cffi", file=sys.stderr)
        return {}

    sess = creq.Session(impersonate="chrome")
    try:
        sess.get("https://www.facebook.com/", timeout=30)   # seed datr/sb cookies
    except Exception:
        pass

    def grab(url):
        r = sess.get(url, timeout=30)
        m = _ID_IN_HTML.search(r.text)
        return next((g for g in m.groups() if g), None) if m else None

    import time
    out = {}
    for raw in raws:
        url = _profile_url(raw)
        fid = None
        for attempt in range(attempts):   # FB serves a login wall (no id) on a fraction of hits
            try:
                fid = grab(url)
                if fid:
                    break
            except Exception:
                pass
            time.sleep(0.6 * (attempt + 1))   # back off a little between retries
        out[raw] = fid
        print(f"  [resolve] {raw[:45]} -> {fid or 'FAILED'}", file=sys.stderr, flush=True)
        time.sleep(0.4)                       # be gentle: avoid burst rate-limiting
    return out

def main():
    ap = argparse.ArgumentParser(description="Bulk-check Facebook profile existence (free, no login).")
    ap.add_argument("input", help="text file (one id/url per line) or CSV")
    ap.add_argument("-o", "--out", default="fb_results.csv")
    ap.add_argument("-w", "--workers", type=int, default=15)
    ap.add_argument("--id-col", help="if input is a CSV, the column holding the id/url")
    ap.add_argument("--resolve", action="store_true",
                    help="for vanity /username inputs with no numeric id, resolve the id over HTTP "
                         "via curl_cffi TLS impersonation (no browser; needs: pip install curl_cffi)")
    args = ap.parse_args()

    items = list(load_lines(args.input, args.id_col))
    total = len(items)
    results = [None] * total

    def work(i):
        uid = extract_id(items[i])
        results[i] = ("", "NO_ID") if not uid else (uid, classify(uid))
        if i and i % 500 == 0:
            print(f"  ...{i}/{total}", file=sys.stderr, flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, range(total)))

    # Second pass: resolve vanity /username inputs (NO_ID) to numeric ids, then check them.
    if args.resolve:
        no_id = [i for i in range(total) if results[i][1] == "NO_ID"]
        if no_id:
            print(f"resolving {len(no_id)} vanity URLs via curl_cffi (no browser)...", file=sys.stderr)
            mapping = resolve_ids([items[i] for i in no_id])
            for i in no_id:
                rid = mapping.get(items[i])
                results[i] = (rid, classify(rid)) if rid else ("", "NO_ID_UNRESOLVED")

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["input", "facebook_id", "status"])
        for raw, (uid, st) in zip(items, results):
            w.writerow([raw, uid, st])

    from collections import Counter
    c = Counter(st for _, st in results)
    print("=== SUMMARY ===", file=sys.stderr)
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}  ({100*v/total:.1f}%)", file=sys.stderr)
    print(f"total: {total}  ->  {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
