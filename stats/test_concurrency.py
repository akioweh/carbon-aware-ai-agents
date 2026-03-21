"""Test concurrent forecast requests to reproduce the timeout scenario.

Usage: PREDICTION_INTERVAL=30 PREDICTION_CACHE_TTL=45 python3 app.py
       Then in another terminal: python3 test_concurrency.py
"""

import concurrent.futures
import time

import requests

BASE = 'http://127.0.0.1:5001'


def fetch(url):
    start = time.monotonic()
    try:
        resp = requests.get(url, timeout=15)
        elapsed = time.monotonic() - start
        return url, resp.status_code, elapsed
    except requests.Timeout:
        elapsed = time.monotonic() - start
        return url, 'TIMEOUT', elapsed
    except Exception as e:
        elapsed = time.monotonic() - start
        return url, f'ERROR: {e}', elapsed


def main():
    # Step 1: Get all DCs
    print('=== Step 1: Get all datacenters ===')
    resp = requests.get(f'{BASE}/datacenters')
    dcs = resp.json()
    dc_ids = [dc['id'] for dc in dcs]
    active_ids = [dc['id'] for dc in dcs if dc['active']]
    print(f'Total DCs: {len(dc_ids)}, Active: {len(active_ids)}')

    # Step 2: Check if cache is warm (single request)
    print('\n=== Step 2: Single request warmup check ===')
    test_dc = active_ids[0] if active_ids else dc_ids[0]
    url, status, elapsed = fetch(f'{BASE}/locations/{test_dc}/metrics/forecast_load')
    print(f'  {test_dc}: {status} in {elapsed:.2f}s')
    if elapsed > 5:
        print('  WARNING: Cache is cold, background loop may not have run yet')
        print('  Waiting 30s for cache to warm up...')
        time.sleep(30)

    # Step 3: Toggle all inactive then active (reproduce teammate scenario)
    print('\n=== Step 3: Toggle all DCs inactive then active ===')
    for dc_id in dc_ids:
        requests.patch(f'{BASE}/datacenters/{dc_id}', json={'active': False})
    print(f'  Set {len(dc_ids)} DCs inactive')

    for dc_id in dc_ids:
        requests.patch(f'{BASE}/datacenters/{dc_id}', json={'active': True})
    print(f'  Set {len(dc_ids)} DCs active')

    # Step 4: Fire concurrent requests (what the scheduler does)
    print('\n=== Step 4: Concurrent forecast requests (simulating scheduler) ===')
    urls = []
    for dc_id in dc_ids:
        urls.append(f'{BASE}/locations/{dc_id}/metrics/forecast_load')
        urls.append(f'{BASE}/locations/{dc_id}/metrics/forecast_carbon_intensity')

    print(f'  Firing {len(urls)} concurrent requests...')
    overall_start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as pool:
        results = list(pool.map(fetch, urls))

    overall_elapsed = time.monotonic() - overall_start

    # Report
    print(f'\n=== Results ({overall_elapsed:.2f}s total) ===')
    slow = []
    for url, status, elapsed in sorted(results, key=lambda r: -r[2]):
        short_url = url.replace(BASE, '')
        flag = ' <<<< SLOW' if elapsed > 3 else ''
        print(f'  {elapsed:6.2f}s  {status}  {short_url}{flag}')
        if elapsed > 3:
            slow.append((url, elapsed))

    if slow:
        print(f'\n  {len(slow)} requests took >3s. Scheduler would likely timeout.')
    else:
        print('\n  All requests under 3s. Looks good.')


if __name__ == '__main__':
    main()
