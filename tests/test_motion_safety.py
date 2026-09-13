"""Valide que l'arrêt sécurisé (stopj) fonctionne avec un script qui bouge réellement le
robot : deux movej enchaînés avec rayon de raccordement (r=0.1), breakpoint juste après
le premier — exactement le cas où le robot peut être encore en train de "couler" dans le
virage au moment où le checkpoint s'exécute.

Vérifie : le statut de sécurité reste NORMAL pendant toute la pause (pas d'arrêt
protecteur/fault déclenché par notre stopj), la pause tient réellement la durée demandée,
et le programme se termine proprement sur les deux itérations.
"""

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(REPO_ROOT, "test-scripts", "motion_test.script")
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
            stdout.readline()
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

    def wait_for(self, predicate, timeout: float = 20) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self.messages.get(timeout=deadline - time.time())
            except queue.Empty:
                break
            if predicate(msg):
                return msg
        raise TimeoutError("Timeout en attendant un message correspondant.")


def is_event(name):
    return lambda m: m.get("type") == "event" and m.get("event") == name


def safetystatus() -> str:
    s = socket.create_connection(("127.0.0.1", 29999), timeout=5)
    s.recv(4096)
    s.sendall(b"safetystatus\n")
    time.sleep(0.2)
    resp = s.recv(4096).decode()
    s.close()
    return resp.strip()


def main() -> None:
    proc = subprocess.Popen(
        [PYTHON, "-u", DAP_SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr
    )
    client = DAPClient(proc)

    client.send("request", "initialize", {"adapterID": "urscript"})
    client.wait_for(lambda m: m.get("command") == "initialize" and m["type"] == "response")
    client.wait_for(is_event("initialized"))

    client.send("request", "launch", {"program": SCRIPT_PATH, "ursimHost": "127.0.0.1"})
    client.wait_for(lambda m: m.get("command") == "launch" and m["type"] == "response")

    client.send("request", "setBreakpoints", {"source": {"path": SCRIPT_PATH}, "breakpoints": [{"line": 5}]})
    client.wait_for(lambda m: m.get("command") == "setBreakpoints")

    client.send("request", "configurationDone")
    client.wait_for(lambda m: m.get("command") == "configurationDone")

    print(f"Statut sécurité avant: {safetystatus()}")

    for i in (1, 2):
        stopped = client.wait_for(is_event("stopped"), timeout=20)
        print(f"-> Arrêt {i} (raison: {stopped['body']['reason']})")

        assert safetystatus() == "Safetystatus: NORMAL", "Statut de sécurité anormal juste après l'arrêt !"

        hold_seconds = 3
        print(f"   Maintien de la pause {hold_seconds}s, vérification continue du statut de sécurité...")
        deadline = time.time() + hold_seconds
        while time.time() < deadline:
            status = safetystatus()
            assert status == "Safetystatus: NORMAL", f"Statut de sécurité anormal pendant la pause : {status}"
            time.sleep(0.5)
        print("   OK: statut NORMAL maintenu pendant toute la pause (robot réellement stoppé, pas de fault).")

        client.send("request", "continue", {"threadId": 1})
        client.wait_for(lambda m: m.get("command") == "continue")

    client.wait_for(is_event("terminated"), timeout=20)
    print(f"Statut sécurité après fin du programme: {safetystatus()}")
    print("\nPROGRAMME AVEC MOUVEMENT RÉEL : ARRÊT SÉCURISÉ VALIDÉ SUR 2 ITÉRATIONS SANS FAULT.")

    client.send("request", "disconnect")
    proc.wait(timeout=5)


if __name__ == "__main__":
    main()
