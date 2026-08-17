# Contrat du pont hôte ↔ noyau

Ce document est le **contrat** entre le support hôte de Locaryn
(`packages/core-bridge`, dépôt principal) et les extensions de ce dépôt. Il
fixe les dialectes, la négociation, les événements et les règles de sécurité.
Version du contrat : **0.1** (pré-Phase A — peut bouger tant que le support
hôte n'est pas publié).

## 1. Manifeste — section `core`

La section `core` du `plugin.json` décrit tout ce dont le pont a besoin.
Champs requis :

| Champ | Rôle |
| --- | --- |
| `driver` | Dialecte : `responses` \| `runs` \| `chat_completions` |
| `api_url` | URL de base de l'API du noyau (loopback obligatoire) |
| `port` | Port local attendu |
| `install` | `kind`: `binary` \| `npm` \| `pip` \| `existing` ; `package`/`source` ; `fallback` |
| `lifecycle.start` | Commande de lancement (tokens `{{port}}`, `{{token}}`, `{{data_dir}}`) |
| `lifecycle.env` | Variables d'environnement injectées |
| `lifecycle.health` | Probe : `method`, `url`, `retries`, `interval_ms` |
| `auth` | `scheme` (`bearer`), `secret_source` (`env`/`file`), `env_key` |
| `session.routing` | `user` (champ `user` stable) \| `conversation` (nom stable) \| `response` (`previous_response_id`) |
| `skills` | `registry`, `query`/`install` (commandes), `install_dir`, `native` |
| `tools` | `client_tools` (bool), `approval` (`locaryn` \| `core`) |

Le pont **ignore les champs inconnus** : une extension peut ajouter des
métadonnées sans casser la validation.

## 2. Dialectes

### 2.1 `responses` (OpenClaw — OpenResponses)

- `POST {api_url}/v1/responses` — corps OpenAI Responses :
  `input`, `instructions`, `tools` (fonctions client), `stream: true`.
- Continuité de session : champ `user` (clé stable dérivée de la session
  Locaryn) ou `previous_response_id`.
- Outils **client** (turn-based) : le noyau renvoie des items
  `function_call` ; le pont exécute (ou refuse) puis renvoie un item
  `function_call_output` dans la requête suivante.
- SSE : `response.created`, `response.in_progress`, `response.output_item.added`,
  `response.output_text.delta`, `response.output_text.done`,
  `response.content_part.done`, `response.output_item.done`,
  `response.completed`, `response.failed`.
- Auth : `Authorization: Bearer <token>`.

### 2.2 `runs` (Hermes — Runs API)

- `POST /v1/runs` → `{ run_id, status }` ; `GET /v1/runs/{id}/events` (SSE) ;
  `POST /v1/runs/{id}/stop` ; `POST /v1/runs/{id}/approval`.
- Continuité : `session_id` / `conversation` / `previous_response_id`.
- Outils **serveur** : exécutés par Hermes, répliqués en streaming
  (`hermes.tool.progress`, items `function_call`/`function_call_output`).
- Négociation : `GET /v1/capabilities` (vérifier `run_approval` avant
  d'afficher l'approbation dans l'UI).
- Auth : `Authorization: Bearer <API_SERVER_KEY>`.

### 2.3 `chat_completions` (générique)

- `POST /v1/chat/completions`, `stream: true` (SSE OpenAI standard).
- Pour tout noyau OpenAI-compatible sans surface plus riche.

## 3. Correspondance des événements

| Événement du noyau | `StreamEvent` Locaryn |
| --- | --- |
| `response.output_text.delta` / chunk `content` | `Token` |
| `function_call` (noyau → Locaryn) | `ToolCall` puis dispatch Locaryn |
| `function_call_output` / résultat d'outil | `ToolResult` |
| `hermes.tool.progress` | `ToolCall` (début) — carte d'outil |
| items `reasoning` / pensée OpenClaw | Token de raisonnement replié |
| `subagent.start` / `subagent.complete` | `Log` (source `subagent`) |
| `response.failed` / erreur | `Log` (Warn/Error) puis `MessageEnd` |

## 4. Mappage de session

Le pont maintient `locaryn_session_uuid → { clé noyau, dernier response_id }`
dans une table locale (migration hôte). La clé noyau est dérivée
déterministiquement : `locaryn-{session_uuid}`. La suppression d'une session
Locaryn peut fermer la session noyau si le dialecte le permet.

## 5. Approbation

- `tools.approval = "locaryn"` : tout outil client ou appel en attente passe
  par le gating Locaryn (`ApprovalHandle` existant). Refus → `ToolResult`
  avec motif, transmis au noyau.
- `tools.approval = "core"` : le noyau gère ses propres décisions ; Locaryn
  n'affiche que la progression.

## 6. Sécurité (invariants)

1. `api_url` doit être sur **loopback** (127.0.0.1/8, ::1) — sinon refus
   d'installation.
2. Le jeton est généré par Locaryn (CSPRNG), jamais stocké dans le
   `plugin.json`, injecté via env ou fichier avec permissions 0600.
3. Le processus noyau tourne avec les droits de l'utilisateur, jamais en
   élévation.
4. Les skills installés sont traités comme **données non fiables** (règle
   Locaryn existante pour les bundles).
5. Arrêt à la désinstallation : kill du processus, retrait des fichiers
   d'installation et du jeton.

## 7. Versionnage

- `core.contract` (optionnel) : version du contrat attendue par l'extension.
  Absent = 0.1. Le pont refuse une extension dont le contrat est plus récent
  que le sien, avec un message clair (« mise à jour de Locaryn requise »).
