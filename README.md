# Range Filter Trend — versions de travail

Dérivé de *Range Filter Trend* [QuantAlgo], © QuantAlgo, sous licence
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Aucune affiliation.

| Fichier | Contenu |
|---|---|
| `range-filter-v3.1.pine` | Indicateur V3.1 Réactif (base) |
| `range-filter-v3.2.pine` | V3.1 + sessions, bougies d'annonce, score apparié (or M5) |
| `range-filter-spot-v4.pine` | Stratégie `strategy()` spot long uniquement (Hyperliquid : ETH, BTC, HYPE, ZEC), version Témoin V3.1 incluse |
| `range-filter-spot-v4-notes.md` | Diagnostic, coûts Hyperliquid datés, procédure de test, limites |

Le Pine n'est pas compilé hors TradingView. Les audits et résultats locaux sont décrits dans [PASSATION.md](PASSATION.md). Aucun ordre n'est passé.

Le terminal local se lance avec `./terminal/start.sh`, puis s'utilise sur http://localhost:7071. Les modèles Kronos, les vérifications et l'expérience de réentraînement sont documentés dans [docs/kronos-local.md](docs/kronos-local.md).

Le lancement suppose ce dépôt dans `~/range-filter` et [Kronos](https://github.com/shiyu-coder/Kronos) installé dans `~/kronos`, avec son environnement Python `.venv` et Flask. Le dépôt contient le code, les tests et les résultats documentés ; les données collectées, les poids réentraînés, les caches et les journaux restent locaux. Les modèles V1/V2 seront indisponibles sur un nouveau clone tant que leurs fichiers locaux n'auront pas été préparés.
