"""Simule un client DAP (ce que fait VS Code) pour valider dap_server.py de bout en
bout contre un vrai URSim, sans avoir besoin de l'extension VS Code elle-même.
"""

import json
import os
import queue
import subprocess
import sys
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "test-scripts", "counter_clean.script")
DAP_SERVER = os.path.join(REPO_ROOT, "server", "dap_server.py")
PYTHON = os.path.join(REPO_ROOT, "server", ".venv", "bin", "python")


class DAPClient:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.seq = 0
        self.messages: "queue.Queue[dict]" = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        stdout = self.proc.stdout
        while True:
            line = stdout.readline()
            if not line:
                return
            if not line.strip():
                continue
            _, _, length_str = line.decode().partition(":")
            length = int(length_str.strip())
            stdout.readline()  # ligne vide séparatrice
            body = stdout.read(length)
            self.messages.put(json.loads(body.decode()))

    def send(self, msg_type: str, command: str, arguments: dict | None = None) -> int:
        self.seq += 1
        msg = {"seq": self.seq, "type": msg_type, "command": command}
        if arguments is not None:
            msg["arguments"] = arguments
        body = json.dumps(msg).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()
        return self.seq

    def wait_for(self, predicate, timeout: float = 15) -> dict:
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self.messages.get(timeout=deadline - time.time())
            except queue.Empty:
                break
            if predicate(msg):
                return msg
        raise TimeoutError(f"Timeout en attendant un message correspondant. Reçus: {list(self.messages.queue)}")


def is_event(name):
    return lambda m: m.get("type") == "event" and m.get("event") == name


def is_response(command):
    return lambda m: m.get("type") == "response" and m.get("command") == command


def main() -> None:
    proc = subprocess.Popen(
        [PYTHON, "-u", DAP_SERVER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )
    client = DAPClient(proc)

    print("-> initialize")
    client.send("request", "initialize", {"adapterID": "urscript"})
    client.wait_for(is_response("initialize"))
    client.wait_for(is_event("initialized"))
    print("   ok")

    print("-> launch")
    client.send("request", "launch", {"program": SCRIPT_PATH, "ursimHost": "127.0.0.1"})
    client.wait_for(is_response("launch"))
    print("   ok")

    print("-> setBreakpoints (ligne 5)")
    client.send(
        "request",
        "setBreakpoints",
        {"source": {"path": SCRIPT_PATH}, "breakpoints": [{"line": 5}]},
    )
    resp = client.wait_for(is_response("setBreakpoints"))
    assert resp["body"]["breakpoints"][0]["verified"], "breakpoint non vérifié"
    print("   ok")

    print("-> configurationDone")
    client.send("request", "configurationDone")
    client.wait_for(is_response("configurationDone"))
    print("   ok")

    for expected_counter in ("1", "2", "3"):
        stopped = client.wait_for(is_event("stopped"))
        assert stopped["body"]["reason"] == "breakpoint"
        print(f"-> stopped (attendu counter={expected_counter})")

        client.send("request", "stackTrace", {"threadId": 1})
        st = client.wait_for(is_response("stackTrace"))
        assert st["body"]["stackFrames"][0]["line"] == 5, st

        client.send("request", "scopes", {"frameId": 1})
        client.wait_for(is_response("scopes"))

        client.send("request", "variables", {"variablesReference": 1000})
        vars_resp = client.wait_for(is_response("variables"))
        values = {v["name"]: v["value"] for v in vars_resp["body"]["variables"]}
        assert values.get("counter") == expected_counter, f"attendu counter={expected_counter}, reçu {values}"
        print(f"   variable counter = {values['counter']} (OK)")

        client.send("request", "continue", {"threadId": 1})
        client.wait_for(is_response("continue"))

    print("-> attente terminated/exited")
    client.wait_for(is_event("terminated"))
    client.wait_for(is_event("exited"))
    print("   ok")

    client.send("request", "disconnect")
    proc.wait(timeout=5)
    print("\nTOUT LE FLUX DAP EST VALIDÉ DE BOUT EN BOUT.")


if __name__ == "__main__":
    main()
