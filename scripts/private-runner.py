"""Run source-aware work with closed output channels and fixed public status."""
import os
from pathlib import Path
import signal
import subprocess
import sys


def worker_environment(action):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('GIT_TRACE', 'PYTHON'))
           and key not in ('GH_DEBUG', 'GH_HTTP_DEBUG', 'GIT_CURL_VERBOSE', 'BASH_ENV', 'ENV')}
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONBREAKPOINT='0',
               PYTHONFAULTHANDLER='0', PYTHONWARNINGS='ignore',
               GH_PROMPT_DISABLED='1', GIT_TERMINAL_PROMPT='0')
    # Child processes must not bypass the closed stdout/stderr via runner files.
    for key in ('GITHUB_OUTPUT', 'GITHUB_ENV', 'GITHUB_STATE', 'GITHUB_STEP_SUMMARY'):
        env[key] = os.devnull
    if action != 'sync':
        env.pop('SOURCE_CHANGELOG', None)
        env.pop('SOURCE_DOWNLOAD_TEMPLATE', None)
    return env


def private_call(command, env, *, timeout, cwd):
    process = None
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, close_fds=True)
        return process.wait(timeout=timeout) == 0
    except BaseException:
        # Timeout/cancellation: terminate the entire worker group, including gh/git.
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except BaseException:
                pass
        return False


def interrupted(_number, _frame):
    raise InterruptedError()


def main():
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action not in ('sync', 'keepalive'):
        print('Mirror: invalid action.', flush=True)
        return 1
    if (os.environ.get('RUNNER_DEBUG') == '1' or
            any(os.environ.get(key, '').lower() == 'true'
                for key in ('ACTIONS_STEP_DEBUG', 'ACTIONS_RUNNER_DEBUG'))):
        print('Mirror: debug mode disabled.', flush=True)
        return 1
    root = Path(__file__).resolve().parents[1]
    env = worker_environment(action)
    if action == 'keepalive' and not private_call(['gh', 'auth', 'setup-git'], env, timeout=30, cwd=root):
        print('Mirror keepalive: failed; details suppressed.', flush=True)
        return 1
    ok = private_call([sys.executable, '-I', '-B', str(root / 'scripts/mirror.py'), action],
                      env, timeout=1200 if action == 'sync' else 120, cwd=root)
    print('Mirror ' + action + (': succeeded.' if ok else ': failed; details suppressed.'), flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        result = main()
    except BaseException:
        print('Mirror: failed; details suppressed.', flush=True)
        result = 1
    raise SystemExit(result)
