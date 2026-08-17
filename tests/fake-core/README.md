# Fake core (tests)

Serveur HTTP autonome qui parle les dialectes **`responses`** (OpenResponses)
et **`runs`** (Runs API) de façon déterministe — le miroir Python du fake
core embarqué dans les tests du pont (`packages/core-bridge/tests/common/
fake_core.rs` du dépôt principal).

But (décision D14 du document 14 — noyaux alternatifs) : tester le pont de
Locaryn **sans réseau ni vrais noyaux**, dans la CI de ce dépôt.

## Surface

Identique au fake_core.rs :

```
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
```

Scénarios scriptés par le contenu du message (comme le fake_core.rs) :

- « ping » → réponse texte `pong from fake core` ;
- « call » → un `function_call` client (`read_file`), puis, après le renvoi
  des `function_call_output`, une réponse texte ;
- « approve » → run avec `approval.request`, qui attend la décision relayée
  par le pont avant de conclure ;
- « stop » → run qui émet des ticks indéfiniment (le pont doit demander
  l'arrêt quand le client abandonne).

## Usage

```bash
# Lancer le serveur (port libre par défaut ; l'URL est imprimée sur stdout)
python3 fake_core.py

# Pointer les tests du pont dessus, depuis le dépôt principal
LOCARYN_FAKE_CORE_URL=http://127.0.0.1:<port> cargo test -p locaryn-core-bridge

# Autotest de la surface, sans le pont (CI de ce dépôt)
python3 fake_core.py --selftest
```

Stdlib uniquement — aucun paquet à installer.
