# Noyau Hermes Agent pour Locaryn

Extension de noyau : pilote le **gateway Hermes Agent** (Nous Research) depuis
Locaryn via sa **Runs API** (`/v1/runs` + événements SSE, `stop`, `approval`).

## Ce que ça apporte

- **Mémoire à trois niveaux** : la mémoire d'Hermes (faits, préférences,
  profil) vit côté Hermes et suit chaque session Locaryn routée vers une
  conversation nommée stable.
- **Boucle d'apprentissage** : Hermes crée et améliore ses skills pendant
  l'usage — tout reste actif à travers Locaryn.
- **Skills** : onglet « Skills » dans la carte du noyau — skills fournis,
  skills optionnels officiels, hub.
- **Home Assistant** : plugin de plateforme `homeassistant` fourni par Hermes.
- **Sub-agents, cron, MCP** : visibles dans l'UI Locaryn (événements
  `subagent.start` / `subagent.complete`, cartes d'outils).

## Configuration

Le manifeste installe le paquet pip `hermes-agent` (ou réutilise une
installation existante). Locaryn :

1. génère un jeton (CSPRNG) et le passe en `API_SERVER_KEY` ;
2. lance `hermes gateway` avec `API_SERVER_ENABLED=true`,
   `API_SERVER_HOST=127.0.0.1`, `API_SERVER_PORT=8642` ;
3. attend `GET /health` → `{"status":"ok"}` et négocie via
   `GET /v1/capabilities` ;
4. mappe chaque session Locaryn → conversation nommée Hermes.

## Outils

- **Outils Hermes** (terminal, fichiers, web, mémoire, skills…) : exécutés par
  le gateway, visibles en streaming (`hermes.tool.progress`) et comme cartes
  d'outils dans l'UI.
- **Approbation** : les appels d'outils en attente de décision sont relayés
  vers l'UI Locaryn via `POST /v1/runs/{id}/approval`.

## Voir aussi

- [docs/integration.md](../../docs/integration.md) — l'architecture
- [docs/drivers.md](../../docs/drivers.md) — le contrat du pont (dialecte `runs`)
- [skills/hermes-index.json](../../skills/hermes-index.json) — index de départ
