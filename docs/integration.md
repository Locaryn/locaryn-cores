# Intégration des noyaux alternatifs — architecture publique

Locaryn est un hôte. Un **noyau alternatif** (OpenClaw, Hermes Agent…) est une
extension qui apporte un autre *cerveau* : sa boucle, sa mémoire, ses skills,
ses intégrations. Le noyau Locaryn n'est jamais remplacé : chaque session
choisit le sien, et les conversations ordinaires continuent inchangées.

## Principe

Les noyaux cibles exposent une **API HTTP locale, OpenAI-compatible, avec
streaming SSE et continuité de session** :

| Noyau | Surface pilotée | Port (défaut) |
| --- | --- | --- |
| OpenClaw | OpenResponses `POST /v1/responses` (SSE), `/v1/models`, `/v1/chat/completions` | 18789 |
| Hermes Agent | `/v1/chat/completions`, `/v1/responses`, **Runs API** `/v1/runs` + `/v1/runs/{id}/events` (SSE), `stop`, `approval`, `/v1/capabilities` | 8642 |

Locaryn ne réimplémente donc rien : il **pilote** le noyau comme un processus
local (téléchargement, jeton, démarrage, healthcheck — le métier déjà connu du
provider-supervisor), puis le branche sur son propre trait `Agent`.

## Où vit le pont

Le pont (`packages/core-bridge` dans le dépôt principal Locaryn) comprend :

- **`CoreManager`** — installation du binaire/paquet, génération du jeton,
  démarrage/supervision/arrêt, healthcheck, mappage des sessions
  (session Locaryn → session/conversation du noyau).
- **`CoreDriver`** (trait) — `health()`, `send()`, `stop()`, `approve()`.
- **Drivers par dialecte** — `responses` (OpenClaw), `runs` (Hermes),
  `chat_completions` (générique).
- **`ExternalCoreAgent`** — implémente le trait `Agent` existant de Locaryn :
  tout l'aval (SSE vers l'UI, persistance SQLite, tool cards, annulation,
  métriques) fonctionne sans modification.

## Cycle de vie d'une session

```
Réglages → Extensions → installer le noyau → Activer
  └─ Locaryn télécharge le noyau, génère un jeton (CSPRNG),
     lance le processus (loopback), attend le healthcheck.
Nouvelle session → Noyau : OpenClaw
  └─ session.core_id = <extension>
Message → ExternalCoreAgent → CoreDriver.send(session, input, tools)
  └─ stream SSE → StreamEvent (tokens, ToolCall, ToolResult) → UI Locaryn
```

La colonne `core_id` (NULL = noyau natif) rend le choix **par session** et
réversible à tout moment.

## Partage des outils

| Outil | Exécution | Gating |
| --- | --- | --- |
| Outils Locaryn (`read_file`, `write_file`, `run_command`, `search`, `list_dir`, MCP) | Locaryn (déclarés au noyau comme *client function tools*) | Approbation Locaryn |
| Outils du noyau (mémoire, skills, Home Assistant, navigateur) | Le noyau | Garde-fous du noyau ; Locaryn peut refuser de relayer |
| Appels en attente de décision (Hermes) | — | Relayés à l'UI via `approval` |

## Skills

Les skills d'un écosystème s'installent **depuis Locaryn** (onglet « Skills »
de la carte du noyau) mais **tournent dans leur écosystème** — pas de
conversion perdue, pas de double maintien. Format commun `SKILL.md`
(frontmatter YAML), le même que celui de Locaryn.

## Mémoire et pensée

La mémoire (faits, préférences, pensées) vit dans le noyau (`~/.openclaw`,
`~/.hermes`). Locaryn la relie : une session Locaryn est routée vers une
session stable du noyau, donc la mémoire suit la conversation. Les événements
de progression (raisonnement OpenClaw, `hermes.tool.progress`, sub-agents)
sont traduits en événements Locaryn existants.

## Sécurité

- Loopback uniquement : Locaryn refuse une URL non-loopback à l'installation.
- Jeton CSPRNG généré par Locaryn, injecté dans la configuration du noyau.
- Permissions du manifeste (`network`, `shell`, `env`) via la fenêtre de
  permissions existante.
- Outils sensibles : approbation Locaryn.
- Désinstallation : arrêt du processus + retrait des fichiers.

## État du support hôte

Le support hôte (section `core` du `plugin.json`, `packages/core-bridge`,
migration `core_id`, UI) est la **Phase A** du dépôt principal. Les manifestes
de ce dépôt sont prêts et rétro-compatibles : installables dès aujourd'hui,
pilotés dès la Phase A publiée.
