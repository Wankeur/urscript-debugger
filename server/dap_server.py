"""Adaptateur Debug Adapter Protocol (DAP) pour URScript.

Traduit les requêtes standard de VS Code (setBreakpoints, continue, stackTrace,
variables...) vers le mécanisme d'instrumentation + rendez-vous socket validé
manuellement (instrument.py + serveur de rendez-vous). Donne accès à toute l'UI de
débogage de VS Code sans construire d'interface graphique.

Chaque ligne exécutable du script est instrumentée avec un checkpoint (voir
instrument.py) : le serveur décide, à chaque ligne, de suspendre réellement
l'exécution (vrai breakpoint, ou pas-à-pas demandé via "next") ou de laisser passer
immédiatement. Ça permet de supporter breakpoints ET step-over avec un seul mécanisme.

Avant d'annoncer un arrêt à VS Code, le robot est explicitement stoppé (stopj) et
confirme lui-même qu'il est à l'arrêt — jamais d'annonce "stopped" avant confirmation
physique réelle (voir _rendezvous_loop et instrument.py).

Portée volontairement limitée pour le MVP : un seul fichier, une seule "frame" et un
seul scope "Locals".
"""

import json
import logging
import os
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from instrument import instrument  # noqa: E402

DASHBOARD_PORT = 29999
SECONDARY_PORT = 30002
BREAKPOINT_SERVER_PORT = 29998

logging.basicConfig(
    filename="/tmp/urscript_dap_server.log",
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
)
log = logging.getLogger("dap")


class DAPServer:
    def __init__(self):
        self.seq = 0
        self.write_lock = threading.Lock()
        self.breakpoints: dict[str, set[int]] = {}
        self.program_path: str | None = None
        self.ursim_host = "127.0.0.1"
        self.current_hit: dict | None = None
        self.pending_conn: socket.socket | None = None
        self.rendezvous_socket: socket.socket | None = None
        self.terminated = False
        self.step_mode = False  # True: le prochain checkpoint doit arrêter, même sans breakpoint explicite
        self.licensed = os.environ.get("URSCRIPT_LICENSED") == "1"

    # --- framing DAP (Content-Length headers + JSON) ---
    def send(self, message: dict) -> None:
        self.seq += 1
        message["seq"] = self.seq
        body = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        with self.write_lock:
            sys.stdout.buffer.write(header + body)
            sys.stdout.buffer.flush()

    def send_response(self, request: dict, success: bool = True, body: dict | None = None, message: str | None = None) -> None:
        resp = {
            "type": "response",
            "request_seq": request["seq"],
            "success": success,
            "command": request["command"],
        }
        if body is not None:
            resp["body"] = body
        if message is not None:
            resp["message"] = message
        self.send(resp)

    def send_event(self, event: str, body: dict | None = None) -> None:
        msg = {"type": "event", "event": event}
        if body is not None:
            msg["body"] = body
        self.send(msg)

    def read_message(self) -> dict | None:
        headers = {}
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        while line.strip():
            key, _, value = line.decode("utf-8").partition(":")
            headers[key.strip()] = value.strip()
            line = sys.stdin.buffer.readline()
        length = int(headers.get("Content-Length", 0))
        body = sys.stdin.buffer.read(length)
        return json.loads(body.decode("utf-8"))

    def run(self) -> None:
        while True:
            msg = self.read_message()
            if msg is None:
                break
            if msg.get("type") == "request":
                self._handle_request(msg)

    def _handle_request(self, req: dict) -> None:
        handler = getattr(self, f"cmd_{req['command']}", None)
        if handler is None:
            self.send_response(req, success=False, message=f"Commande non supportée: {req['command']}")
            return
        try:
            handler(req)
        except Exception as exc:
            self.send_response(req, success=False, message=str(exc))

    # --- commandes DAP ---
    def cmd_initialize(self, req: dict) -> None:
        self.send_response(
            req,
            body={
                "supportsConfigurationDoneRequest": True,
                "supportsSetVariable": True,
                "supportsEvaluateForHovers": True,
            },
        )
        self.send_event("initialized")

    def cmd_launch(self, req: dict) -> None:
        args = req.get("arguments", {})
        self.program_path = args["program"]
        self.ursim_host = args.get("ursimHost", "127.0.0.1")
        self.send_response(req)

    def cmd_setBreakpoints(self, req: dict) -> None:
        args = req["arguments"]
        path = args["source"]["path"]
        lines = [bp["line"] for bp in args.get("breakpoints", [])]

        if self.licensed:
            allowed = set(lines)
        else:
            allowed = set(lines[:1])  # version gratuite : un seul breakpoint actif

        self.breakpoints[path] = allowed
        body_breakpoints = []
        for l in lines:
            if l in allowed:
                body_breakpoints.append({"verified": True, "line": l})
            else:
                body_breakpoints.append(
                    {
                        "verified": False,
                        "line": l,
                        "message": "Free version is limited to 1 breakpoint. A license unlocks unlimited breakpoints.",
                    }
                )
        self.send_response(req, body={"breakpoints": body_breakpoints})

    def cmd_configurationDone(self, req: dict) -> None:
        self.send_response(req)
        log.info("configurationDone reçu, démarrage du thread _start_program")
        threading.Thread(target=self._start_program_safe, daemon=True).start()

    def cmd_threads(self, req: dict) -> None:
        self.send_response(req, body={"threads": [{"id": 1, "name": "URScript"}]})

    def cmd_stackTrace(self, req: dict) -> None:
        line = self.current_hit["line"] if self.current_hit else 1
        self.send_response(
            req,
            body={
                "stackFrames": [
                    {"id": 1, "name": "program", "line": line, "column": 1, "source": {"path": self.program_path}}
                ],
                "totalFrames": 1,
            },
        )

    def cmd_scopes(self, req: dict) -> None:
        self.send_response(req, body={"scopes": [{"name": "Locals", "variablesReference": 1000, "expensive": False}]})

    def cmd_variables(self, req: dict) -> None:
        variables = []
        if self.current_hit:
            for name, value in self.current_hit["vars"].items():
                variables.append({"name": name, "value": value, "variablesReference": 0})
        self.send_response(req, body={"variables": variables})

    def cmd_setVariable(self, req: dict) -> None:
        if not self.licensed:
            self.send_response(
                req, success=False, message="Editing variables is a premium feature. Enter a license key to unlock it."
            )
            return

        args = req["arguments"]
        name = args["name"]
        raw_value = args["value"]

        if self.current_hit is None or self.pending_conn is None:
            self.send_response(req, success=False, message="The program is not currently paused.")
            return

        names = list(self.current_hit["vars"].keys())
        if name not in names:
            self.send_response(req, success=False, message=f"Unknown variable at this point in the program: {name}")
            return

        try:
            value = float(raw_value)
        except ValueError:
            self.send_response(
                req, success=False, message="Only numeric values are editable for now."
            )
            return

        index = names.index(name)
        try:
            self.pending_conn.sendall(bytes([1, index]) + f"({value})".encode("utf-8"))
            ack = self.pending_conn.recv(64)
            log.info(f"setVariable {name}={value} (index {index}) -> ack={ack!r}")
        except OSError as exc:
            self.send_response(req, success=False, message=f"Erreur de communication avec le robot : {exc}")
            return

        formatted = str(value)
        self.current_hit["vars"][name] = formatted
        self.send_response(req, body={"value": formatted})

    def cmd_evaluate(self, req: dict) -> None:
        expression = req["arguments"]["expression"].strip()
        if self.current_hit and expression in self.current_hit["vars"]:
            value = self.current_hit["vars"][expression]
            self.send_response(req, body={"result": value, "variablesReference": 0})
        else:
            self.send_response(
                req,
                success=False,
                message="Seules les variables locales connues à ce point sont évaluables (pas d'expressions arbitraires).",
            )

    def cmd_continue(self, req: dict) -> None:
        self.step_mode = False
        self.send_response(req, body={"allThreadsContinued": True})
        self._resume_robot()

    def cmd_next(self, req: dict) -> None:
        self.step_mode = True
        self.send_response(req)
        self._resume_robot()

    # stepIn/stepOut : pas de notion de pile d'appels dans ce MVP (une seule frame),
    # donc traités comme "next" pour l'instant.
    cmd_stepIn = cmd_next
    cmd_stepOut = cmd_next

    def cmd_disconnect(self, req: dict) -> None:
        self.send_response(req)
        self._cleanup()
        sys.exit(0)

    # --- logique métier ---
    def _start_program_safe(self) -> None:
        try:
            self._start_program()
        except Exception as exc:
            log.exception("Exception dans _start_program")
            self.send_event(
                "output",
                {
                    "category": "stderr",
                    "output": (
                        f"[urscript-debugger] Échec du démarrage : {exc}\n"
                        "Le port de rendez-vous (29998) est peut-être déjà utilisé par une session "
                        "précédente non arrêtée proprement. Arrête toute session de débogage encore "
                        "active puis réessaie.\n"
                    ),
                },
            )
            self.send_event("terminated")

    def _start_program(self) -> None:
        log.info(f"Lecture du programme {self.program_path}")
        with open(self.program_path) as f:
            source = f.read()
        lines = self.breakpoints.get(self.program_path, set())
        log.info(f"Breakpoints demandés: {lines}")
        instrumented = instrument(source, lines)
        log.debug(f"Script instrumenté:\n{instrumented}")

        self.rendezvous_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rendezvous_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rendezvous_socket.bind(("0.0.0.0", BREAKPOINT_SERVER_PORT))
        self.rendezvous_socket.listen(1)
        log.info(f"Serveur de rendez-vous lié sur le port {BREAKPOINT_SERVER_PORT}")
        threading.Thread(target=self._rendezvous_loop_safe, daemon=True).start()

        log.info(f"Connexion à {self.ursim_host}:{SECONDARY_PORT}")
        with socket.create_connection((self.ursim_host, SECONDARY_PORT), timeout=5) as s:
            payload = instrumented.encode("utf-8")
            if not payload.endswith(b"\n"):
                payload += b"\n"
            s.sendall(payload)
        log.info("Script envoyé à URSim")

        self.send_event("process", {"name": self.program_path})

    def _rendezvous_loop_safe(self) -> None:
        try:
            self._rendezvous_loop()
        except Exception:
            log.exception("Exception dans _rendezvous_loop")

    def _rendezvous_loop(self) -> None:
        while not self.terminated:
            log.info("En attente d'une connexion sur le port de rendez-vous...")
            try:
                conn, addr = self.rendezvous_socket.accept()
            except OSError:
                log.info("rendezvous_socket fermé, arrêt de la boucle")
                return

            try:
                if self._handle_checkpoint_connection(conn, addr):
                    return  # fin de programme signalée, plus rien à traiter
            except Exception:
                # Une connexion malformée (ex: script d'une session précédente pas
                # complètement arrêtée) ne doit jamais tuer toute la boucle de rendez-vous.
                log.exception(f"Erreur en traitant la connexion {addr}, ignorée")
                try:
                    conn.close()
                except OSError:
                    pass

    def _handle_checkpoint_connection(self, conn: socket.socket, addr) -> bool:
        """Traite une connexion de checkpoint. Retourne True si c'était le signal de fin
        de programme (la boucle appelante doit alors s'arrêter)."""
        log.info(f"Connexion acceptée depuis {addr}")
        payload = conn.recv(4096).decode("utf-8")
        log.info(f"Payload reçu: {payload!r}")

        if payload == "PROGRAM_DONE":
            conn.close()
            log.info("Signal de fin de programme reçu du script")
            self.terminated = True
            self.send_event("terminated")
            self.send_event("exited", {"exitCode": 0})
            return True

        if not payload:
            log.warning(f"Connexion vide/invalide depuis {addr}, ignorée (probablement une session précédente)")
            conn.close()
            return False

        label, _, rest = payload.partition("|")
        is_breakpoint_str, _, vars_raw = rest.partition("|")
        line = int(label.replace("cp_line_", "").replace("bp_line_", ""))
        is_breakpoint = is_breakpoint_str == "1"

        should_stop = is_breakpoint or self.step_mode
        if not should_stop:
            # Simple passage : pas un breakpoint, pas de step en cours. On ne bloque pas,
            # et surtout on ne commande AUCUN arrêt moteur (ne pas casser un mouvement en cours).
            try:
                conn.sendall(bytes([0]))
            except OSError:
                log.exception("Erreur en laissant passer un checkpoint")
            conn.close()
            return False

        self.step_mode = False
        # On dit au robot de s'arrêter (stopj côté script), puis on attend SA confirmation
        # qu'il est physiquement à l'arrêt avant de prévenir VS Code — jamais annoncer
        # "stopped" avant un arrêt réellement confirmé par le robot.
        try:
            conn.sendall(bytes([1]))
            ready = conn.recv(64)
            log.info(f"Confirmation d'arrêt reçue du robot: {ready!r}")
        except OSError:
            log.exception("Erreur en attendant la confirmation d'arrêt du robot")
            conn.close()
            return False

        variables = {}
        if vars_raw:
            for part in vars_raw.split(";"):
                name, _, value = part.partition("=")
                variables[name] = value

        self.current_hit = {"line": line, "vars": variables}
        self.pending_conn = conn
        reason = "breakpoint" if is_breakpoint else "step"
        log.info(f"Robot confirmé à l'arrêt, envoi de l'événement stopped ({reason}, ligne {line}, vars={variables})")
        self.send_event("stopped", {"reason": reason, "threadId": 1, "allThreadsStopped": True})
        return False

    def _resume_robot(self) -> None:
        log.info(f"_resume_robot appelé, pending_conn={self.pending_conn}")
        if self.pending_conn is not None:
            try:
                self.pending_conn.sendall(bytes([0]))
                self.pending_conn.close()
                log.info("Signal de reprise envoyé au robot")
            except OSError:
                log.exception("Erreur en envoyant le signal de reprise")
            self.pending_conn = None

    def _cleanup(self) -> None:
        self.terminated = True

        if self.pending_conn is not None:
            try:
                self.pending_conn.close()
            except OSError:
                pass
            self.pending_conn = None

        # Arrête explicitement le programme côté contrôleur : sans ça, un script encore en
        # cours (ex: bloqué sur un checkpoint) peut continuer de tourner et venir perturber
        # la session de débogage suivante (port de rendez-vous, connexions fantômes).
        try:
            with socket.create_connection((self.ursim_host, DASHBOARD_PORT), timeout=2) as s:
                s.recv(4096)
                s.sendall(b"stop\n")
                s.recv(4096)
            log.info("Programme arrêté côté contrôleur (dashboard stop)")
        except OSError:
            log.exception("Impossible d'arrêter le programme via le dashboard")

        if self.rendezvous_socket:
            try:
                self.rendezvous_socket.close()
            except OSError:
                pass


if __name__ == "__main__":
    DAPServer().run()
