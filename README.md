# Locaryn Cores

> **Noyaux alternatifs pour [Locaryn](https://github.com/Locaryn/Locaryn)** :
> installez OpenClaw, Hermes Agent… comme noyau de conversation — avec leurs
> skills, leur mémoire et leurs intégrations (Home Assistant) — **sans jamais
> remplacer le noyau Locaryn**.

Locaryn reste l'hôte : mêmes API, même stockage, même interface, mêmes
permissions. Un noyau installé ici s'utilise **par session** — créez une
session avec OpenClaw pour piloter votre maison, continuez vos conversations
de code avec le noyau natif Locaryn à côté, inchangées.

## Ce que contient ce dépôt

| Chemin | Contenu |
| --- | --- |
| `cores/openclaw/` | Extension de noyau **OpenClaw** (`plugin.json` + docs) |
| `cores/hermes/` | Extension de noyau **Hermes Agent** (`plugin.json` + docs) |
| `skills/` | Index de skills par écosystème (départ, interrogés à la volée) |
| `docs/integration.md` | Comment l'intégration fonctionne (architecture) |
| `docs/drivers.md` | Contrat du pont hôte ↔ noyau (dialectes, événements, sécurité) |

## Installation

### Depuis l'application (recommandé)

1. Ouvrez **Réglages → Extensions**.
2. Onglet **Découvrir**, ou « + Depuis un dépôt GitHub » avec
   `github:Locaryn/locaryn-cores`.
3. Choisissez le noyau à installer (**OpenClaw** ou **Hermes**), accordez les
   permissions, **Activez**.
4. Locaryn télécharge le noyau, génère un jeton d'accès, le démarre et attend
   son healthcheck.
5. Onglet **Skills** de la carte du noyau : installez les skills
   (ex. `home-assistant`).
6. **Nouvelle session → Noyau : OpenClaw** (ou Hermes) → discutez.

### Depuis le terminal

```bash
locaryn plugin install github:Locaryn/locaryn-cores --pick locaryn-core-openclaw
locaryn sessions new --core openclaw
```

## Prérequis

- **Locaryn** avec le support des noyaux (Phase A — section `core` du
  manifeste, `packages/core-bridge`). Tant que le support hôte n'est pas
  publié, les manifestes s'installent mais le pilotage est inactif.
- **OpenClaw** : Node.js 20+ (installation npm `openclaw`, ou déjà installé —
  mode `existing`).
- **Hermes Agent** : Python 3.10+ (`pip install hermes-agent`, ou déjà
  installé).

Les deux noyaux tournent **en local uniquement** (loopback) et sont joints par
un jeton généré par Locaryn. Aucune donnée ne sort de la machine.

## Écosystèmes couverts

| Noyau | Driver | API pilotée | Skills | Mémoire | Home Assistant |
| --- | --- | --- | --- | --- | --- |
| OpenClaw | `responses` | OpenResponses `POST /v1/responses` (SSE) | ClawHub, `~/.openclaw/skills` | Persistante (gateway) | Oui (canal + skills) |
| Hermes Agent | `runs` | Runs API `/v1/runs` + SSE | Hub Hermes, `~/.hermes/skills` | 3 niveaux, providers | Oui (plugin de plateforme) |

## Licence

Apache-2.0 — aligné sur le cœur de Locaryn.
