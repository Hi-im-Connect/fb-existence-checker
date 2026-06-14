# fb-existence-checker

Bulk-check whether **Facebook profiles still exist** — free, no login, no API token, **zero dependencies** (Python 3.8+ stdlib only).

It uses the public `graph.facebook.com/<id>/picture` redirect: Facebook returns a real
photo for live profiles, a default avatar for blank/restricted ones, and an HTTP 400
for IDs that don't exist.

## Status values

| Status | Meaning |
|---|---|
| `LIVE` | Profile exists and has a public profile photo |
| `NO_PHOTO` | Profile object exists but returns a default/blank avatar — **ambiguous**: active-without-photo, privacy-restricted, **or** deactivated |
| `DEAD` | Facebook returns "does not exist" (HTTP 400) — invalid / fully removed |
| `NO_ID` | Input was a vanity `/username` URL with no numeric ID (run with `--resolve` to fix) |
| `NO_ID_UNRESOLVED` | `--resolve` was on but the browser couldn't extract an ID (blocked / private / gone) |
| `UNKNOWN_*` | Transient / network / rate-limit (retried once) |

> **The fast path needs numeric Facebook IDs.** Vanity `/username` URLs return 400
> from the graph endpoint without an access token, so they're flagged `NO_ID` — use
> `--resolve` (below) to convert them.

## Resolving vanity `/username` URLs (`--resolve`)

Pass `--resolve` to convert vanity URLs to numeric IDs by rendering the real page
with a stealth browser, then checking the resolved ID:

```bash
python3 fb_check.py input.txt --resolve -o results.csv
# [resolve] https://www.facebook.com/zuck -> 4
# zuck,4,LIVE
```

This step is **optional** and lazy-imports
[`patchright`](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright), so the core tool
stays dependency-free. To enable it:

```bash
pip install patchright
patchright install chromium
```

Direct HTTP fetches of Facebook pages are blocked from datacenter IPs, which is why
resolution needs a real (stealth) browser rather than a plain request. Without
`--resolve` — or if the browser can't launch — vanity URLs simply stay `NO_ID` and
nothing else is affected.

## Usage

```bash
# text file: one id or url per line
python3 fb_check.py input.txt -o results.csv

# more parallelism
python3 fb_check.py input.txt -o results.csv -w 25

# a CSV input, pointing at the column with the id/url
python3 fb_check.py leads.csv --id-col FaceBookId -o results.csv
```

Accepted inputs (per line, mixed is fine):

```
100009082533082
https://www.facebook.com/profile.php?id=100009082533082
https://www.facebook.com/100009082533082
https://www.facebook.com/some.vanity.name      # -> NO_ID
```

## Output

CSV with `input, facebook_id, status` and a summary printed to stderr:

```
=== SUMMARY ===
  LIVE: 27754  (89.4%)
  NO_PHOTO: 3294  (10.6%)
total: 31048  ->  results.csv
```

## Notes & limits

- Facebook rate-limits bursts; the default 15 workers is a safe balance. Raise `-w`
  cautiously. Failed probes are retried once and otherwise marked `UNKNOWN_*` so you
  can re-run just those.
- `NO_PHOTO` is the honest grey zone — this method cannot distinguish "active but no
  public photo" from "deactivated". Treat it as *unconfirmed*, not dead.
- This is for legitimate list-hygiene / verification on data you're authorized to
  process. Respect Facebook's Terms and applicable privacy law.

## License

MIT
