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

Pass `--resolve` to convert vanity URLs to numeric IDs, then check the resolved ID.
**No browser** — it uses [`curl_cffi`](https://github.com/lexiforest/curl_cffi) to
impersonate a real Chrome TLS fingerprint (that's what gets past Facebook's edge
block), seeds a `datr` cookie from the homepage so FB serves the full public page,
and reads the numeric id out of the HTML:

```bash
python3 fb_check.py input.txt --resolve -o results.csv
# [resolve] https://www.facebook.com/zuck -> 4
# zuck,4,LIVE
```

This step is **optional** and lazy-imports `curl_cffi`, so the core tool stays
dependency-free. To enable it:

```bash
pip install curl_cffi
```

Plain `requests`/`curl` get blocked by Facebook at the **TLS-fingerprint** level
(a 1.5 KB error page), which is why a normal HTTP request can't resolve usernames
but `curl_cffi` (impersonating Chrome) can — no browser required. Facebook still
serves a login wall on a fraction of hits, so each input is retried; anything that
can't be resolved stays `NO_ID_UNRESOLVED` and can simply be re-run.

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
