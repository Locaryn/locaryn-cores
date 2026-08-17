# Noyau OpenClaw pour Locaryn

Extension de noyau : pilote le **gateway OpenClaw** depuis Locaryn via son API
**OpenResponses** (`POST /v1/responses`, streaming SSE, continuité de session).

## Ce que ça apporte

- **Mémoire persistante** : chaque session Locaryn est routée vers une session
  stable du gateway (`user` stable) — les faits, préférences et pensées
  d'OpenClaw suivent la conversation.
- **Skills ClawHub** : onglet « Skills » dans la carte du noyau — chercher,
  installer, désactiver (`openclaw skills install @owner/<slug>`).
- **Home Assistant** : le gateway OpenClaw s'y connecte (canal HA, skills,
  MCP ha-mcp) — vous pilotez votre maison depuis l'interface Locaryn.
- **Sub-agents, cron, canaux** : tout ce que le gateway sait faire reste
  disponible, dans l'UI Locaryn.

## Configuration

Le manifeste installe le paquet npm `openclaw` (ou réutilise une installation
existante). Locaryn :

1. génère un jeton (CSPRNG) et le passe en `OPENCLAW_GATEWAY_PASSWORD` ;
2. lance `openclaw gateway --port 18789` (loopback) ;
3. attend que `GET /v1/models` réponde ;
4. mappe chaque session Locaryn → session gateway via le champ `user`.

## Outils

- **Outils Locaryn** (`read_file`, `run_command`, MCP…) déclarés au gateway
  comme *client function tools* : exécutés par Locaryn, avec le gating
  d'approbation habituel.
- **Outils OpenClaw** (mémoire, Home Assistant, navigateur…) : exécutés par le
  gateway, visibles dans l'UI comme des cartes d'outils.

## Voir aussi

- [docs/integration.md](../../docs/integration.md) — l'architecture
- [docs/drivers.md](../../docs/drivers.md) — le contrat du pont (dialecte `responses`)
- [skills/openclaw-index.json](../../skills/openclaw-index.json) — index de départ
