# Kronos dans le terminal local

État de travail du 21 octobre 2026. Autorisation de Samet : poursuivre et améliorer le projet sur localhost.

## Résultat attendu

Comparer des scénarios Kronos sur BTC, ETH, HYPE et ZEC dans le terminal existant, sans transformer ces courbes en ordres ou en promesses de rendement. L'horizon commun de la nouvelle expérience, des scénarios et de la fourchette simple est **12 bougies**.

## Architecture et décisions

- Flask et Lightweight Charts 4.2.3 conservés ; aucune nouvelle dépendance.
- `kronos_runtime.py` : contexte de 400 bougies, horizon de 12, chemins des modèles et verrou GPU interprocessus WSL (`flock`).
- `terminal/kronos_service.py` : sélection explicite du modèle, un seul prédicteur actif, cache LRU de 64 résultats, chargement et calcul sérialisés. La clé distingue modèle, révision des poids, marché, unité et bougies clôturées. Les 50 trajectoires sont calculées en lots de 10 pour limiter la mémoire.
- `terminal/static/kronos-overlay.js` : une seule requête par sélection ; annulation et rejet des réponses obsolètes, remplacement des courbes au lieu d'empilement, temporisation des nouvelles tentatives après erreur. Une sélection comprend aussi le marché réellement utilisé, pour détecter un changement de source de repli.
- Modèles : `original` (Kronos-small), `crypto-v1` (ancien réentraînement, conservé), `crypto-v2` (nouvelle expérience avec volumes). V2 est disponible seulement après la fin du diagnostic. Aucun changement automatique du modèle par défaut.
- La correction multiplicative de `kronos_fix_test.py` reste une expérience historique. Elle n'est pas présentée comme une fourchette fiable en direct. La fourchette simple reste affichée séparément.

## API locale

- `GET /api/kronos/models` : `{horizon, models:[{id,label,note,available}], experiment}` ; le rapport d'expérience peut être absent.
- `GET /api/kronos?sym=ETH&tf=1h&src=hl_spot&model=crypto-v1` : conserve `start`, `times`, `paths`, ajoute `sym`, `tf`, `source` (choix demandé), `src` (marché réellement utilisé), `model`, `model_label`, `horizon`, `context`, `generated_at`.
- Les 50 listes de clôtures ont chacune 12 valeurs. `start.time` est l'ouverture de la dernière bougie clôturée ; `times[0]` est l'ouverture de la suivante. Horodatages Unix en secondes dans la réponse.
- Erreurs JSON `{error: message}` : 400 paramètres/historique invalides, 404 modèle ou marché indisponible, 503 autre processus GPU actif (`Retry-After: 15`), 500 échec de calcul.
- Un historique troué ou trop court est refusé. Les symboles, sources et unités sont validés à l'entrée.

## Collecte Hyperliquid et journal prospectif

Demandés par Samet le 21 octobre 2026. `terminal/collection.py` démarre avec le serveur, dans un thread ; le navigateur peut être fermé. Arrêter le serveur ou la WSL arrête aussi la collecte. Aucun service Windows ni démarrage automatique du PC ajouté. Les données sont dans `terminal/data/hyperliquid.sqlite3`, ignorées par Git, avec transactions SQLite/WAL. Aucune dépendance supplémentaire.

- Huit séries : BTC, ETH, HYPE, ZEC × 1h/4h. Marchés **spot USDC stricts**, identifiés par l'API (`@142` UBTC, `@151` UETH, `@107` HYPE, `@272` UZEC lors de la vérification). Aucun repli perp pour cet archivage.
- Première récupération : historique disponible via `candleSnapshot` (API limitée aux 5 000 dernières bougies). Puis nouvelles requêtes chaque minute, reprise depuis les dernières bougies archivées avec chevauchement de deux bougies. Après une très longue interruption, les données sorties de la rétention de l'API peuvent rester manquantes ; elles ne sont pas inventées.
- Uniquement des bougies clôturées depuis au moins cinq secondes. Validation des prix/volumes, de l'intervalle et du marché ; déduplication par marché/unité/ouverture. Conservation du JSON fournisseur, des premières/dernières dates d'observation et du volume. Le montant coté est une **estimation OHLC × volume**, explicitement identifiée dans l'export.
- À chaque départ admissible : paire Original/V2 sur les mêmes 400 bougies, 50 chemins par modèle, SHA-256 des poids, paramètres d'échantillonnage, contexte complet et heures de génération/enregistrement sauvegardés. Le GPU est partagé avec l'interface via le service/verrou existant ; un calcul occupé est retenté au cycle suivant.
- La paire entière doit être enregistrée **avant la première clôture cible**. La première bougie cible peut déjà être en formation : seul le contexte clôturé est fourni au modèle. Ce protocole mesure des **clôtures futures**, pas la totalité des hauts/bas d'une bougie partiellement écoulée. Aucune prévision historique ajoutée après coup.
- Les 12 bougies cibles d'un nouveau départ ne chevauchent pas celles du départ précédent dans la même série. La base conserve cette contrainte au redémarrage. Des marchés et unités différents restent corrélés.
- Évaluation après les 12 clôtures, uniquement si toutes sont reçues sur le même marché. Erreur finale : `abs(moyenne des 50 clôtures finales prévues − clôture réelle) / clôture d’ancrage × 10 000`. Comparateur naïf : prix inchangé depuis l'ancrage. La direction est aussi conservée. Ce score ne remplace pas l'ancien score de **fourchette**, ni un résultat de trading avec frais. Prévisions et évaluations ne sont pas réécrites après coup ; les observations utilisées pour le score sont figées avec celui-ci.
- `GET /api/collection` retourne état/phase, fraîcheur et compte des huit séries, trous/erreurs, nombres de paires enregistrées/en attente/évaluées, prochaine échéance et scores par modèle/unité/révision. Affichage dans la carte **Collecte & validation**, actualisée toutes les 15 secondes.

Premier relevé réel à 17:05 UTC le 21 octobre 2026 : **32 703 bougies**, zéro trou interne ; 5 000 en 1h pour chaque crypto, et en 4h BTC 3 754, ETH 3 445, HYPE 4 149, ZEC 1 355. Huit paires enregistrées, soit 16 prévisions, aucune encore évaluable. Premières échéances : **22 octobre 07:00 Paris** pour les 1h et **23 octobre 18:00 Paris** pour les 4h. Ces heures sont les clôtures des horizons ; l'évaluation suit la réception des bougies.

Export vérifié : `terminal/data/exports/2026-10-21-initial/` contient les huit CSV OHLCVA et un manifeste avec marché, dates, trous, empreinte SHA-256 et méthode d'estimation du montant. L'export utilise une vue cohérente de la base et refuse d'écraser un dossier. Ces données permettent de préparer une expérience ultérieure ; **aucun réentraînement automatique**. Il faudra définir une nouvelle séparation chronologique et préserver des cibles futures jamais utilisées pour ajuster le modèle avant de conclure à un gain.

## Expérience V2

`backtest/crypto_data.py` télécharge les données publiques, sans clé : BTC/ETH/ZEC sur Binance spot, HYPE sur Bybit spot. Les CSV originaux ne sont pas écrasés. Historique 1h à partir d'août 2023, HYPE disponible à partir de juillet 2025 dans cette source. Les 4h sont agrégées uniquement depuis quatre bougies horaires complètes. Manifestes avec dates, trous et SHA-256 dans `backtest/data_ohlcv/manifest.json`.

Les prix, volumes et montants sont conservés. Hyperliquid ne fournit pas le montant coté dans les bougies : le terminal l'estime par volume × moyenne OHLC, comme le repli de Kronos. **Les résultats Binance/Bybit ne valident donc pas automatiquement Hyperliquid spot.**

`backtest/kronos_experiment.py` :

- démarre de Kronos-small, tokenizer d'origine figé ; adaptation du tokenizer laissée à une expérience séparée pour ne pas multiplier les changements ;
- apprentissage uniquement avant novembre 2025 ; choix du checkpoint sur novembre–décembre 2025 ;
- trois époques maximum, 4 096 fenêtres par époque, lots de 16, taux d'apprentissage 4e-6, graine 42 ;
- tirage équilibré entre les huit groupes crypto/unité, pour ne pas noyer HYPE dans les historiques plus longs ;
- normalisation sur les 400 bougies observées, sans statistiques des bougies futures ; perte concentrée sur les 12 prochains tokens ;
- choix de la sauvegarde par l'erreur de quantiles des **prévisions générées**, avec arrêt après deux époques sans amélioration ; l'époque zéro peut rester la meilleure ;
- validation pilote : 4 départs par groupe ; diagnostic : 12 départs par groupe, soit 96 au total, cibles sans chevauchement dans chaque série ; 20 trajectoires par départ, T=1, top-p=0,9 ;
- comparaison sur les mêmes départs : original sans volume, original avec volume, V1, V2, méthode simple ;
- enregistre les prévisions brutes, les poids et un `report.json` atomique dans `backtest/experiments/crypto-volume-v2/` (ignoré par Git).

Les fenêtres 1h et 4h peuvent se chevaucher en temps réel entre groupes : **ne pas traiter ces 96 observations comme 96 paris indépendants**. 2026 a déjà été consulté ; ce diagnostic est exploratoire et ne donne pas une preuve indépendante d'avantage. Aucun calcul de performance nette de trading n'est ajouté dans cette expérience.

## Commandes

Depuis `/home/9lx7/range-filter` :

```bash
# Terminal et navigateur Windows
./terminal/start.sh
# Arrêt
./terminal/stop.sh

# Vérifications sans charger les modèles
~/kronos/.venv/bin/python -I terminal/test_kronos.py
~/kronos/.venv/bin/python -I terminal/test_collection.py
node --test terminal/test_kronos_overlay.cjs
~/kronos/.venv/bin/python -I backtest/test_kronos_experiment.py

# Données de l'expérience (fin exclusive, date fixée pour la reproductibilité)
~/kronos/.venv/bin/python -I backtest/crypto_data.py --start 2023-08-01 --end 2026-10-21
# Expérience initiale ; refuse d'écraser un dossier existant
~/kronos/.venv/bin/python -I backtest/kronos_experiment.py
# Un essai ultérieur doit choisir un autre dossier, sans promotion automatique dans le terminal
~/kronos/.venv/bin/python -I backtest/kronos_experiment.py --output backtest/experiments/autre-essai

# Export de la collecte locale, choisir un nouveau dossier à chaque fois
~/kronos/.venv/bin/python -I terminal/collection.py --export terminal/data/exports/mon-prochain-export
```

## Pièges confirmés

- Un `drawKronos()` déclenché à chaque rafraîchissement pendant le calcul produisait 102 courbes et deux moyennes. Les tests vérifient la déduplication, les changements de marché/modèle et la désactivation pendant un calcul.
- PyTorch 2.6.0 : `torch.inference_mode()` pendant la validation crée des caches RoPE inutilisables ensuite pour le backward à longueur identique. Utiliser `torch.no_grad()` pour un modèle qui repart à l'entraînement. L'essai interrompu avant l'apprentissage est conservé dans `crypto-volume-v2-attempt1/`.
- Bybit a renvoyé une erreur transitoire `internal error` pendant la pagination : nouvelles tentatives limitées, puis échec explicite ; aucun remplacement silencieux de HYPE par un autre marché.
- Pandas 2.2.2 / NumPy 2.5.4 affichent un avertissement de dépréciation sur certains `Timedelta`, sans empêcher les contrôles ni l'exécution observée. Pas de migration de dépendances pour ce seul avertissement.
- Les anciens scripts ne prennent pas le verrou GPU. Ne pas les lancer simultanément avec cette expérience ou une prévision du terminal.

## Vérifications réalisées et état

Les **18 tests** passent : 8 tests API/service, 6 tests de concurrence de l'interface, 4 tests d'isolation des périodes/normalisation. Vérification réelle des trois modèles dans le navigateur : chacun affiche 51 séries (50 trajectoires et une moyenne), 13 points avec l'ancrage, horizon commun 12 bougies, sans erreur JavaScript. Le tableau affiché correspond au rapport. Changements ETH/HYPE, 1h/4h et Hyperliquid/Binance vérifiés ; le message de GPU occupé a été observé pendant l'entraînement. Rendu inspecté à 1600×1000 et 390×844 ; aucun débordement horizontal mobile observé. Serveur laissé actif sur `127.0.0.1:7071`, HTTP 200. Diff relu, `git diff --check` sans erreur. Pour la publication GitLab ultérieure et son état vérifié, voir `PASSATION.md`.

Collecte ajoutée ensuite : **10 tests supplémentaires passent**, couvrant clôture/déduplication/provenance, lots invalides, persistance et immutabilité, prévisions tardives ou mauvais marché, calcul du score et données manquantes, fraîcheur/trous/erreurs, absence de repli perp et reprise, GPU occupé, export et API. Les 8 tests API/service et 6 tests d'interface ont aussi été relancés avec succès. Vérification réelle : intégrité SQLite `ok`, 8 paires de 2 × 50 chemins, enregistrement avant première clôture cible, empreintes des huit CSV conformes. Redémarrage du serveur effectué : même empreinte du journal, mêmes comptes, nouveau cycle réussi. Carte inspectée à 1600×1000 et 390×844, sans débordement ; affichage des futurs scores et d'une panne API vérifié par réponses simulées dans le navigateur de test, puis retour aux données réelles. **Les scores réels attendent encore leurs clôtures futures.**

L'expérience est terminée, avec l'époque **1** retenue parmi les trois époques entraînées. Erreur moyenne de validation des fourchettes (1h/4h) : origine avec volumes 249,63 ; époque 1 : 176,12 ; époque 2 : 188,76 ; époque 3 : 183,12. Une perte d'apprentissage plus faible n'a donc pas suffi à améliorer la validation.

Diagnostic 2026 enregistré dans `backtest/experiments/crypto-volume-v2/report.json` :

| Méthode | Erreur fourchette 1h ↓ | Erreur fourchette 4h ↓ | Direction 1h | Direction 4h |
|---|---:|---:|---:|---:|
| Méthode simple | 106,6 | 219,4 | — | — |
| Kronos original, sans volumes | 158,4 | 275,1 | 52,1 % | 41,7 % |
| Kronos original, avec volumes | 144,0 | 257,8 | 58,3 % | 31,2 % |
| Crypto V1 | 153,3 | 268,0 | 58,3 % | 50,0 % |
| Crypto V2 | 142,2 | 227,4 | 47,9 % | 41,7 % |

Chaque colonne repose sur 48 départs, regroupant quatre cryptos. L'erreur est la somme des pertes quantiles 0,9/0,1, multipliée par 10 000. La direction compare le signe du rendement prévu et réel après 12 bougies ; elle ne mesure pas une stratégie de trading. Les scores de V1 dans ce petit échantillon ne remplacent pas ses résultats historiques plus larges.

V2 réduit cette erreur de fourchette de 10,2 % en 1h et 17,4 % en 4h par rapport à l'original sans volumes. **La méthode simple reste meilleure et aucun avantage directionnel n'est établi.** L'effet propre des volumes, de la normalisation et de la nouvelle perte n'est pas isolé par cet essai. Aucune promotion automatique.

Le suivi prospectif est maintenant lancé. Attendre ses premières observations, puis un échantillon suffisant avant de choisir les expériences suivantes. Ne pas multiplier les réglages en présentant 2026 comme un nouveau test aveugle.

## Références consultées

- [Kronos, adaptation CSV officielle](https://github.com/shiyu-coder/Kronos/tree/master/finetune_csv)
- [Binance, données de marché](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
- [Bybit, Kline spot et volumes](https://bybit-exchange.github.io/docs/v5/market/kline)
- [Hyperliquid, endpoint info et candleSnapshot](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
- [Lightweight Charts 4.2, API des séries](https://tradingview.github.io/lightweight-charts/docs/4.2/api/interfaces/ISeriesApi)
