"""Prune completed Actions history without touching releases or source secrets."""
import json
import os
import subprocess

REPOSITORY = 'LOVECHEN/cleanshotx-release'


def api(method, path):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('SOURCE_', 'GIT_TRACE', 'PYTHON'))
           and key not in ('GH_DEBUG', 'GH_HTTP_DEBUG', 'GIT_CURL_VERBOSE')}
    result = subprocess.run(['gh', 'api', '--method', method, path],
                            env=env, stdin=subprocess.DEVNULL, capture_output=True,
                            check=True, timeout=60)
    return json.loads(result.stdout) if result.stdout.strip() else None


def candidates(runs, current_id):
    # Run IDs are monotonic: never delete this run or a newer concurrent run.
    return sorted({int(run['id']) for run in runs
                   if run['status'] == 'completed' and 0 < int(run['id']) < current_id})


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise ValueError('Unexpected repository')
    current_id = int(os.environ['GITHUB_RUN_ID'])
    runs = []
    page = 1
    # Collect every page before deleting so pagination cannot skip shifted entries.
    while True:
        batch = api('GET', f'repos/{REPOSITORY}/actions/runs?per_page=100&page={page}')['workflow_runs']
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    deleted = 0
    for run_id in candidates(runs, current_id):
        path = f'repos/{REPOSITORY}/actions/runs/{int(run_id)}'
        # A user may have re-run a historical job after the listing was taken.
        latest = api('GET', path)
        if latest['status'] != 'completed':
            continue
        api('DELETE', path)
        deleted += 1
    print(f'Actions cleanup: deleted {deleted} previous completed runs; current and active runs preserved.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Actions cleanup: failed; details suppressed.', flush=True)
        raise SystemExit(1)
