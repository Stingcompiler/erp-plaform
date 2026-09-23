"""Load test for the two paths a shop leans on hardest: POS checkout and the
offline sync push (build plan M12).

Runs against a live server — local (`python manage.py runserver`) or a
staging copy, never production data — as a real till would: signs in with a
device id, then N workers each ring up sales, half of them straight to
/api/pos/checkout/ and half queued and pushed through /api/sync/push/, and
every sale is REPLAYED once more with the same client_uuid, the way a till
retries after a dropped connection.

What it proves, beyond timings:
  * no replay ever creates a second invoice (idempotency under load), and
  * the stock ledger moved by exactly the quantity that was sold.

    python scripts/load_test_pos.py --base http://127.0.0.1:8000 \\
        --email owner@example.com --password '…' --workers 8 --sales 25

Exit code is non-zero when any request fails or an invariant is broken.
"""
import argparse
import http.cookiejar
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid


class Session:
    """A signed-in browser: cookie auth plus the CSRF header the API wants."""

    def __init__(self, base, email, password, device_id):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        status, body = self.call(
            "POST", "/api/auth/login/",
            {"email": email, "password": password, "device_id": device_id},
        )
        if status != 200:
            raise RuntimeError(f"sign-in refused ({status}): {body}")

    def _csrf(self):
        return next((c.value for c in self.jar if c.name == "csrftoken"), "")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        request.add_header("Referer", self.base + "/")
        if self._csrf():
            request.add_header("X-CSRFToken", self._csrf())
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode(errors="replace")[:300]


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))] if ordered else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--sales", type=int, default=25, help="sales per worker")
    parser.add_argument(
        "--devices", type=int, default=0,
        help="distinct till devices the workers share (default: one per worker). "
             "Every device counts against the company plan's device limit.",
    )
    args = parser.parse_args()

    try:
        admin = Session(args.base, args.email, args.password, "LOADTEST-TILL-0")
    except RuntimeError as error:
        raise SystemExit(str(error))
    status, me = admin.call("GET", "/api/auth/me/")
    if status != 200:
        raise SystemExit(f"Could not read the signed-in user ({status}).")
    status, warehouses = admin.call("GET", "/api/warehouses/?page_size=1")
    status_p, products = admin.call("GET", "/api/products/?page_size=50")
    if status != 200 or status_p != 200:
        raise SystemExit("Could not list warehouses/products.")
    warehouse = (warehouses.get("results") or warehouses)[0]["id"]
    product = next(p for p in (products.get("results") or products) if p.get("is_stock_tracked"))
    price = product["sale_price"]

    def on_hand():
        _s, data = admin.call("GET", f"/api/products/{product['id']}/")
        return float(data.get("on_hand") or 0)

    before = on_hand()
    latencies = {"checkout": [], "sync": []}
    failures = []
    created = []
    lock = threading.Lock()

    # Each till device signs in once, before the clock starts, the way a shop
    # opens its tills in the morning. Sign-in is rate limited per address, so
    # a refusal with 429 is waited out; any other refusal (most often the
    # plan's device limit) stops the run — it is not a load result.
    devices = args.devices or args.workers
    tills = [admin]
    for number in range(1, devices):
        while True:
            try:
                tills.append(Session(
                    args.base, args.email, args.password, f"LOADTEST-TILL-{number}"
                ))
                break
            except RuntimeError as error:
                if "(429)" not in str(error):
                    raise SystemExit(f"Till {number}: {error}")
                time.sleep(5)

    def worker(index):
        till = tills[index % devices]
        for n in range(args.sales):
            client_uuid = str(uuid.uuid4())
            sale = {
                "warehouse": warehouse,
                "lines": [{"product": product["id"], "quantity": "1"}],
                "payment": {"method": "cash", "amount": str(price)},
            }
            via_sync = n % 2 == 1
            for attempt in (1, 2):  # the second is the retry after a dropped reply
                started = time.perf_counter()
                if via_sync:
                    status, body = till.call("POST", "/api/sync/push/", {
                        "batch_uuid": str(uuid.uuid4()),
                        "expected_company": me.get("company"),
                        "expected_user": me.get("id"),
                        "expected_branch": me.get("branch"),
                        "operations": [{
                            "op_type": "pos_checkout", "client_uuid": client_uuid,
                            "payload": sale,
                        }],
                    })
                    ok = status in (200, 201)
                else:
                    status, body = till.call(
                        "POST", "/api/pos/checkout/", {"client_uuid": client_uuid, **sale}
                    )
                    ok = status in (200, 201)
                elapsed = time.perf_counter() - started
                with lock:
                    latencies["sync" if via_sync else "checkout"].append(elapsed)
                    if not ok:
                        failures.append((status, str(body)[:200]))
            with lock:
                created.append(client_uuid)

    started = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(args.workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started

    expected = args.workers * args.sales
    sold = len(created)
    moved = before - on_hand()
    requests_total = sum(len(v) for v in latencies.values())
    print(f"workers={args.workers} sales={sold} requests={requests_total} "
          f"wall={wall:.1f}s throughput={requests_total / wall:.1f} req/s")
    for path, values in latencies.items():
        if values:
            print(f"  {path:8} n={len(values):4} p50={statistics.median(values) * 1000:.0f}ms "
                  f"p95={percentile(values, 0.95) * 1000:.0f}ms max={max(values) * 1000:.0f}ms")
    print(f"  stock moved by {moved:g} for {sold} sales (each also replayed once)")
    print(f"  failed requests: {len(failures)}")
    for status, body in failures[:5]:
        print(f"    {status}: {body}")

    broken = []
    if failures:
        broken.append("some requests failed")
    if sold != expected:
        broken.append(f"only {sold} of {expected} sales ran")
    if abs(moved - sold) > 1e-9:
        broken.append(f"ledger moved {moved:g}, expected {sold} (a replay double-applied?)")
    if broken:
        print("FAIL: " + "; ".join(broken))
        return 1
    print("OK: every replay was absorbed and the ledger matches the sales")
    return 0


if __name__ == "__main__":
    sys.exit(main())
