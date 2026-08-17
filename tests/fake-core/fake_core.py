#!/usr/bin/env python3
"""Fake core autonome — miroir Python du fake_core.rs des tests du pont.

Parle les dialectes `responses` (OpenResponses) et `runs` (Runs API) de
façon déterministe, pour tester `locaryn-core-bridge` sans réseau ni vrais
noyaux (décision D14 du document 14).

Le pont embarqué sait viser un serveur externe via la variable
`LOCARYN_FAKE_CORE_URL` : les tests d'intégration de `locaryn-cores` (CI)
démarrent ce serveur, posent la variable, et exécutent les tests du pont du
dépôt principal contre lui — en séquentiel (`--test-threads=1`), chaque test
remettant l'état à zéro via `POST /__probe/reset` au moment de s'attacher.

Surface (identique au fake_core.rs, plus le reset) :

  GET  /health                        → {"status": "ok"}
  GET  /v1/models                     → liste de modèles
  GET  /v1/capabilities               → capacités style Hermes
  POST /v1/responses                  → SSE OpenResponses
  POST /v1/chat/completions           → JSON ou SSE
  POST /v1/runs                       → {"run_id", "status": "started"}
  GET  /v1/runs/{id}/events           → SSE d'événements
  POST /v1/runs/{id}/stop             → {"status": "stopping"}
  POST /v1/runs/{id}/approval         → {"status": "recorded"}
  GET  /__probe/state                 → état observable (réservé aux tests)
  POST /__probe/reset                 → état vierge (réservé aux tests)

Scénarios scriptés par le contenu du message (identiques au fake_core.rs) :

  « ping »     → réponse texte (`pong from fake core`) ;
  « call »     → un `function_call` client (`read_file`), puis, après le
                 renvoi des `function_call_output`, une réponse texte ;
  « approve »  → run avec `approval.request`, qui attend la décision
                 relayée par le pont avant de conclure ;
  « stop »     → run qui émet des ticks indéfiniment (le pont doit demander
                 l'arrêt quand le client abandonne).

Usage :

  python3 fake_core.py [--port 0] [--selftest]

`--port 0` (défaut) choisit un port libre et l'affiche sur stdout.
`--selftest` exerce toute la surface puis s'arrête — pour la CI sans le pont.
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# ============================================================================
# État observable, partagé entre les requêtes (miroir de `FakeState` Rust)
# ============================================================================

STATE_LOCK = threading.Lock()
STATE = {
    "users": [],                 # champs `user` reçus sur /v1/responses
    "responses_bodies": [],      # corps reçus sur /v1/responses
    "responses_count": 0,
    "run_bodies": [],            # corps reçus sur /v1/runs
    "runs_count": 0,
    "run_inputs": {},            # run_id → message d'entrée
    "stops": [],                 # run_id des arrêts demandés
    "approvals": [],             # décisions reçues sur /v1/runs/{id}/approval
}


def with_state(fn):
    """Exécute `fn(state)` sous le verrou et renvoie sa valeur."""
    with STATE_LOCK:
        return fn(STATE)


def state_snapshot():
    with STATE_LOCK:
        return json.dumps(STATE).encode()


def reset_state():
    with STATE_LOCK:
        for key in list(STATE):
            if isinstance(STATE[key], dict):
                STATE[key] = {}
            elif isinstance(STATE[key], list):
                STATE[key] = []
            else:
                STATE[key] = 0


# ============================================================================
# SSE
# ============================================================================

def se(name, payload):
    """Bloc SSE complet : `event:` + `data:`."""
    return "event: {}\ndata: {}\n\n".format(name, json.dumps(payload)).encode()


def se_data(payload):
    """Bloc SSE `data:` seul (forme minimaliste OpenResponses)."""
    return "data: {}\n\n".format(json.dumps(payload)).encode()


def send_sse(handler, blocks):
    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    # Le flux a une fin (run.completed / [DONE]) : on ferme la connexion
    # quand il est épuisé, sans quoi le client resterait bloqué en lecture
    # sur une connexion qui ne dit jamais « c'est fini ».
    handler.send_header("connection", "close")
    handler.close_connection = True
    handler.end_headers()
    for block in blocks:
        try:
            handler.wfile.write(block if isinstance(block, bytes) else block.encode())
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return  # client parti — on ferme le flux


# ============================================================================
# OpenResponses (driver `responses`)
# ============================================================================

def handle_responses(handler, body):
    try:
        val = json.loads(body)
    except ValueError:
        val = {}

    def mutate(state):
        state["responses_count"] += 1
        state["responses_bodies"].append(val)
        u = val.get("user")
        if isinstance(u, str):
            state["users"].append(u)

    with STATE_LOCK:
        mutate(STATE)
        n = STATE["responses_count"]

    is_follow_up = isinstance(val.get("input"), list)
    input_str = val.get("input") if isinstance(val.get("input"), str) else ""

    if "ping" in input_str:
        resp_id = "resp_ping_{}".format(n)
    elif "call" in input_str:
        resp_id = "resp_call_{}".format(n)
    else:
        resp_id = "resp_hi_{}".format(n)

    blocks = [
        se("response.created", {"type": "response.created", "response": {"id": resp_id}}),
        se("response.in_progress", {"type": "response.in_progress"}),
    ]

    if is_follow_up:
        # Le pont a renvoyé des `function_call_output` : le tour continue.
        blocks.append(se("response.output_item.added", {
            "type": "response.output_item.added",
            "item": {"type": "message", "role": "assistant"},
        }))
        blocks.append(se("response.output_text.delta", {
            "type": "response.output_text.delta",
            "delta": "résultat reçu par le noyau",
        }))
        blocks.append(se("response.output_text.done", {
            "type": "response.output_text.done",
            "text": "résultat reçu par le noyau",
        }))
    elif "call" in input_str:
        # Le noyau demande un outil client.
        item = {
            "type": "function_call",
            "call_id": "call_fake_1",
            "name": "read_file",
            "arguments": '{"path":"Cargo.toml"}',
        }
        blocks.append(se("response.output_item.added",
                         {"type": "response.output_item.added", "item": item}))
        blocks.append(se("response.output_item.done",
                         {"type": "response.output_item.done", "item": item}))
    elif "ping" in input_str:
        blocks.append(se("response.output_text.delta", {
            "type": "response.output_text.delta",
            "delta": "pong from fake core",
        }))
        blocks.append(se("response.output_text.done", {
            "type": "response.output_text.done",
            "text": "pong from fake core",
        }))
    else:
        blocks.append(se("response.output_text.delta", {
            "type": "response.output_text.delta",
            "delta": "bonjour depuis le fake core",
        }))

    blocks.append(se("response.completed", {
        "type": "response.completed",
        "response": {
            "id": resp_id,
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    }))
    blocks.append(b"data: [DONE]\n\n")
    send_sse(handler, blocks)


# ============================================================================
# Chat Completions (driver `chat_completions`)
# ============================================================================

def handle_chat_completions(handler, body):
    try:
        val = json.loads(body)
    except ValueError:
        val = {}
    streamed = bool(val.get("stream"))
    if not streamed:
        payload = json.dumps({
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "chat completions fake"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }).encode()
        handler.send_response(200)
        handler.send_header("content-type", "application/json")
        handler.send_header("content-length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)
        return
    send_sse(handler, [
        se_data({"id": "chatcmpl-fake", "object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": {"role": "assistant", "content": "chat completions fake"},
             "finish_reason": None}]}),
        se_data({"id": "chatcmpl-fake", "object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}),
        b"data: [DONE]\n\n",
    ])


# ============================================================================
# Runs API (driver `runs`)
# ============================================================================

def handle_create_run(handler, body):
    try:
        val = json.loads(body)
    except ValueError:
        val = {}

    def mutate(state):
        state["runs_count"] += 1
        run_id = "run_fake_{}".format(state["runs_count"])
        state["run_bodies"].append(val)
        if isinstance(val.get("input"), str):
            state["run_inputs"][run_id] = val["input"]
        return run_id

    run_id = with_state(mutate)
    payload = json.dumps({"run_id": run_id, "status": "started"}).encode()
    handler.send_response(201)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def handle_run_events(handler, run_id):
    with STATE_LOCK:
        input_str = STATE["run_inputs"].get(run_id, "")

    def emit(block):
        try:
            handler.wfile.write(block)
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False
        return True

    handler.send_response(200)
    handler.send_header("content-type", "text/event-stream")
    handler.send_header("cache-control", "no-cache")
    # Même règle que send_sse : le flux se termine par run.completed, on
    # ferme la connexion pour que le client voie la fin.
    handler.send_header("connection", "close")
    handler.close_connection = True
    handler.end_headers()

    if not emit(se("run.started", {"type": "run.started", "run_id": run_id})):
        return

    if "approve" in input_str:
        emit(se("message.delta", {"type": "message.delta", "delta": "Préparation…"}))
        emit(se("tool.start", {
            "type": "tool.start",
            "call_id": "tool_1",
            "tool": "run_command",
            "args": {"command": "echo hi"},
        }))
        emit(se("approval.request", {
            "type": "approval.request",
            "request_id": "req_1",
            "tool": "run_command",
            "args": {"command": "echo hi"},
            "message": "Exécuter la commande ?",
        }))

        # Attendre la décision relayée par le pont (au plus 20 s).
        decision = None
        for _ in range(200):
            with STATE_LOCK:
                for a in reversed(STATE["approvals"]):
                    if a.get("request_id") == "req_1":
                        decision = a
                        break
            if decision is not None:
                break
            time.sleep(0.1)

        if decision is not None:
            approved = bool(decision.get("approved"))
            emit(se("tool.complete", {
                "type": "tool.complete",
                "call_id": "tool_1",
                "tool": "run_command",
                # Même casse que le fake_core.rs : « true » / « false », pas
                # le « True »/« False » de str(bool) en Python.
                "output": "approuvé: {}".format("true" if approved else "false"),
                "ok": True,
            }))
            emit(se("message.delta", {"type": "message.delta", "delta": "Terminé"}))
        emit(se("run.completed", {
            "type": "run.completed",
            "run_id": run_id,
            "usage": {"input_tokens": 12, "output_tokens": 6},
        }))
    elif "stop" in input_str:
        # Run qui ne finit pas : le pont doit demander l'arrêt quand le
        # client abandonne le flux.
        for i in range(200):
            if not emit(se("message.delta", {
                "type": "message.delta",
                "delta": "tick {}".format(i),
            })):
                return  # client parti — on ferme le flux
            time.sleep(0.1)
        emit(se("run.completed", {"type": "run.completed", "run_id": run_id}))
    else:
        emit(se("message.delta", {
            "type": "message.delta",
            "delta": "hello from runs fake core",
        }))
        emit(se("run.completed", {
            "type": "run.completed",
            "run_id": run_id,
            "usage": {"input_tokens": 8, "output_tokens": 4},
        }))


# ============================================================================
# Serveur HTTP
# ============================================================================

class FakeCoreHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silencieux
        pass

    # -- sondes ------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok"})
        elif path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": "fake-core"}]})
        elif path == "/v1/capabilities":
            self._json(200, {
                "object": "hermes.api_server.capabilities",
                "platform": "fake-core",
                "model": "fake-core",
                "features": {
                    "chat_completions": True,
                    "responses_api": True,
                    "run_submission": True,
                    "run_status": True,
                    "run_events_sse": True,
                    "run_stop": True,
                    "run_approval": True,
                },
            })
        elif path == "/__probe/state":
            self._raw(200, "application/json", state_snapshot())
        elif path.startswith("/v1/runs/") and path.endswith("/events"):
            run_id = path[len("/v1/runs/"):-len("/events")]
            handle_run_events(self, run_id)
        else:
            self._json(404, {"error": "not found"})

    # -- actions -----------------------------------------------------------

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        if path == "/__probe/reset":
            reset_state()
            self._json(200, {"status": "reset"})
        elif path == "/v1/responses":
            handle_responses(self, body)
        elif path == "/v1/chat/completions":
            handle_chat_completions(self, body)
        elif path == "/v1/runs":
            handle_create_run(self, body)
        elif path.startswith("/v1/runs/") and path.endswith("/stop"):
            run_id = path[len("/v1/runs/"):-len("/stop")]
            with STATE_LOCK:
                STATE["stops"].append(run_id)
            self._json(200, {"status": "stopping"})
        elif path.startswith("/v1/runs/") and path.endswith("/approval"):
            try:
                val = json.loads(body)
            except ValueError:
                val = {}
            with STATE_LOCK:
                STATE["approvals"].append(val)
            self._json(200, {"status": "recorded"})
        else:
            self._json(404, {"error": "not found"})

    # -- helpers -----------------------------------------------------------

    def _json(self, status, payload):
        self._raw(status, "application/json", json.dumps(payload).encode())

    def _raw(self, status, content_type, data):
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def main():
    parser = argparse.ArgumentParser(description="Fake core Locaryn (dialectes responses/runs)")
    parser.add_argument("--port", type=int, default=0, help="port d'écoute (0 = libre)")
    parser.add_argument("--selftest", action="store_true", help="exercer la surface puis sortir")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), FakeCoreHandler)
    base = "http://127.0.0.1:{}".format(server.server_port)
    print(base, flush=True)

    if args.selftest:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            selftest(base)
        finally:
            server.shutdown()
        print("fake-core: selftest OK", file=sys.stderr)
        return

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ============================================================================
# Autotest : exerce la surface sans le pont (CI de locaryn-cores)
# ============================================================================

def _get(url, headers=None):
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=10) as r:
        return r.status, r.read()


def _post(url, payload, headers=None):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={
        "content-type": "application/json",
        **(headers or {}),
    })
    with urlopen(req, timeout=10) as r:
        return r.status, r.read()


def _read_sse(url, payload=None, timeout=5):
    """Lit un flux SSE jusqu'à la fermeture. POST quand un corps est fourni
    (/v1/responses), GET sinon (flux d'événements d'un run)."""
    if payload is None:
        with urlopen(Request(url), timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    req = Request(url, data=json.dumps(payload).encode(), headers={
        "content-type": "application/json",
    })
    with urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    return body


def selftest(base):
    status, body = _get(base + "/health")
    assert status == 200 and json.loads(body)["status"] == "ok"

    status, body = _get(base + "/v1/models")
    assert status == 200 and json.loads(body)["data"][0]["id"] == "fake-core"

    status, body = _get(base + "/v1/capabilities")
    assert status == 200 and json.loads(body)["features"]["run_events_sse"]

    # OpenResponses « ping » → réponse texte.
    sse = _read_sse(base + "/v1/responses", {"input": "ping", "user": "locaryn-test"})
    assert "pong from fake core" in sse
    assert "response.completed" in sse

    # Chat completions non streamé.
    status, body = _post(base + "/v1/chat/completions",
                         {"model": "fake", "messages": [{"role": "user", "content": "hi"}]})
    assert status == 200 and "chat.completion" in body.decode()

    # Run simple + flux d'événements (GET).
    status, body = _post(base + "/v1/runs", {"input": "bonjour"})
    run_id = json.loads(body)["run_id"]
    assert status == 201 and run_id.startswith("run_fake_")
    sse = _read_sse(base + "/v1/runs/{}/events".format(run_id))
    assert "hello from runs fake core" in sse
    assert "run.completed" in sse

    # Arrêt demandé.
    status, body = _post(base + "/v1/runs/{}/stop".format(run_id), {})
    assert status == 200 and json.loads(body)["status"] == "stopping"

    # Décision d'approbation enregistrée (le scénario « approve » du pont
    # vérifie le relais complet ; ici on contrôle juste la surface).
    status, body = _post(base + "/v1/runs/{}/approval".format(run_id),
                         {"request_id": "req_1", "approved": True})
    assert status == 200 and json.loads(body)["status"] == "recorded"

    # État observable : le user et le run sont bien remontés.
    status, body = _get(base + "/__probe/state")
    state = json.loads(body)
    assert "locaryn-test" in state["users"]
    assert state["runs_count"] >= 1
    assert run_id in state["stops"]
    assert state["approvals"][-1]["approved"] is True

    # Le reset rend l'état vierge (chaque test du pont repart de zéro).
    status, body = _post(base + "/__probe/reset", {})
    assert status == 200 and json.loads(body)["status"] == "reset"
    status, body = _get(base + "/__probe/state")
    state = json.loads(body)
    assert state["users"] == [] and state["runs_count"] == 0


if __name__ == "__main__":
    main()
