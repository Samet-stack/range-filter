# Passation : Range Filter, Kronos, terminal (2026-10-21)

À lire en premier par tout agent (Codex, Claude, Gemini) qui reprend ce dossier.

## Qui et quoi
- **Samet** trade en spot, à la main, devant l'écran : ETH, HYPE, BTC, ZEC et d'autres, sur Hyperliquid.
  - Il veut des **indicateurs pour décider**, **pas un bot**. Il décide lui-même de ses sorties et de ses stops.
  - Il écrit vite, avec des fautes : interpréter l'intention. Répondre en français simple et court.
  - **Ne jamais lui imposer de chiffres fixes** (« +3 % », etc.). Ses exemples sont des exemples, pas des règles. Il l'a reproché explicitement.
  - Il veut **la meilleure solution**, pas la première qui marche, et qu'on avance en autonomie.
- **Règles de collaboration** (voir `~/AGENTS.md`) :
  - ne jamais transmettre de secret à Gemini (`/home/9lx7/.local/bin/agy`) ;
  - n'utiliser Gemini que si Samet le demande ;
  - **ne jamais pousser sur GitLab sans sa validation**.

## État du dépôt `~/range-filter` (branche `main`)
- **GitHub devient la destination principale à la demande de Samet le 21 octobre 2026** : [Samet-stack/range-filter](https://github.com/Samet-stack/range-filter), dépôt **public**, créé et poussé avec l'historique complet. Accès anonyme vérifié via l'API GitHub (`private=false`, `visibility=public`).
  - Remote `github` ; `main` suit `github/main`. Les prochains pushes autorisés vers GitHub se font avec `git push github main`.
  - GitHub CLI local (`gh` 2.92.0) authentifié en `Samet-stack`. Le connecteur GitHub de la conversation peut être lié à un autre compte : vérifier l'identité avant toute écriture.
  - Remote `origin` conservé pour GitLab ; aucun dépôt distant supprimé. La demande de publication publique se poursuit désormais sur GitHub, sans attendre de changement de visibilité GitLab.
- **Publication autorisée explicitement par Samet le 21 octobre 2026**, y compris le passage en public. Les 18 commits précédemment locaux et le commit `f27b0ce` (terminal, V2, collecte et tests) ont été poussés sur `origin/main`, dépôt [samet.reyhan/range-filter](https://gitlab.com/samet.reyhan/range-filter).
  - Accès Git vérifié via le gestionnaire d'identifiants de **Git Windows**, sans enregistrer de secret dans le dépôt ni modifier la configuration globale. Commande : `git -c "credential.helper=!'/mnt/c/Program Files/Git/mingw64/bin/git-credential-manager.exe'" push origin main`.
  - Tentative de passage en public GitLab refusée : l'accès existant permet le push, mais l'API de modification du projet répond `403 insufficient_scope`. Ce blocage a précédé le choix de publier sur GitHub.
  - Avant publication : 28 tests réussis, diff relu, recherche de secrets sans résultat dans les 55 versions de fichiers de l'historique et les 44 fichiers de travail. Les données, poids, caches et journaux restent ignorés et locaux.
  - Un jeton d'accès (PAT) collé dans un ancien chat **doit être révoqué** par Samet. Il n'est stocké nulle part.
- Commits signés `samet.reyhan <samet.reyhan@functori.com>` via `git -c user.name=... -c user.email=...`. Ne pas modifier la configuration git globale.

## Ce qui existe
| Fichier | Rôle |
|---|---|
| `range-filter-manuel.pine` | **Indicateur TradingView principal** (Pine v6, `indicator`). États en direct : ACHAT, ACHAT ? (BUY en formation), EN COURS, FIN ?, PAS D'ACHAT, ATTENTE, **FOND BAISSIER** (jour sous sa moyenne 50 jours). Il affiche les niveaux exacts « BUY si clôture > » et « FIN si clôture < », le montant selon le wallet, et une ligne d'honnêteté (BUY contre hasard). Thème sombre demandé. |
| `range-filter-spot-v4.pine` | La stratégie d'origine. Son moteur est copié tel quel dans l'indicateur. **Ne pas la modifier.** |
| `terminal/` | **Terminal local** (Flask + Lightweight Charts) : liste de cryptos, graphique en direct, signaux Range Filter, feu journalier, fourchette simple, futurs Kronos en option. Source au choix en haut de la page : **Hyperliquid spot** par défaut (UETH, UBTC, USOL, UZEC, HYPE… contre USDC, avec repli sur le perp s'il n'y a pas de spot), Hyperliquid perp, ou Binance (puis Bybit, puis Hyperliquid). Écoute uniquement sur `127.0.0.1:7071`. |
| `kronos_live.py` | Génère un Pine qui dessine la prévision Kronos dans TradingView, pour n'importe quelle crypto. C'est une image, pas un signal. |
| `backtest/` | Toutes les vérifications, détaillées ci-dessous. `data/` (4h) et `data1h/` sont ignorés par git ; on les régénère avec `fetch.py` et `fetch1h.py`. |

### Lancer
```bash
# Terminal : lance en arriere-plan et ouvre le navigateur (arret : stop.sh ; journal : terminal/server.log)
~/range-filter/terminal/start.sh
# Prévision Kronos dessinée dans TradingView (fichiers kronos-<SYM>-<tf>.pine, ignorés par git)
cd ~/range-filter && ~/kronos/.venv/bin/python -I kronos_live.py ETH,HYPE,PURR 1h
```
- Le venv `~/kronos/.venv` contient torch CUDA, pandas et flask.
- La machine a une RTX 4070 Super. Deux calculs Kronos en même temps saturent ses 12 Go et deviennent très lents.

## Conclusions mesurées : ne pas les refaire sans raison
Méthode commune à tous les tests :
- **Test « +x % avant −x % »**, partant de la clôture d'un BUY, comparé à une bougie sur 5.
- **Écart en z** (test de deux proportions). Le test a été calibré sur des marches aléatoires.
- **Frais** de 0,10 à 0,27 % par côté.
- Période **2026 hors apprentissage** pour les essais décrits ; déjà examinée, elle ne constitue plus un test aveugle pour choisir de nouveaux réglages.

1. **Range Filter (15m à 4h) : aucun avantage directionnel.** Après un BUY, le prix fait +x % avant −x % aussi souvent que depuis n'importe quelle bougie, sur BTC, ETH, ZEC et HYPE, en 1h et en 4h. Les gains en 4h sur ZEC et HYPE viennent de la tendance du marché, et garder sans rien faire faisait mieux. Voir `AUDIT-2026-10-20.md` et `backtest/up_before_down.py`.
2. **Le Range Filter ne réduit pas la pire chute** en 1h et 4h. Il fait des allers-retours dans les phases plates.
3. **Le feu journalier (clôture au-dessus de la moyenne 50 jours) réduit la pire chute**, 2024-2026 (`backtest/regime_daily.py`) :
   - BTC passe de −53 % à −27 % ;
   - ETH de −68 % à −38 % ;
   - HYPE de −64 % à −41 % ;
   - ZEC de −72 % à −64 %.

   Le gain est similaire ou meilleur sur BTC et ETH, moindre sur ZEC et HYPE. C'est le seul filtre utile mesuré. Peu de grosses chutes dans l'échantillon : rester prudent.
4. **Kronos-small (`~/kronos`), sur 2026 :**
   - **Direction** (`backtest/kronos_test.py`) : 49 à 50 %, soit le hasard, seul comme en filtre des BUY.
   - **Fourchette** (`backtest/kronos_range_test.py`) : elle est cassée environ 30 % du temps au lieu de 10 %. Son erreur est environ 1,6 fois celle de la méthode simple (quantiles passés × volatilité récente).
   - **Corrigé** en élargissant sa fourchette (`kronos_fix_test.py`) : toujours derrière la méthode simple.
   - **Ré-entraîné** sur nos cryptos avant 2026 (`kronos_finetune.py`, modèle dans `~/kronos/finetuned/crypto/best`) : il imite mieux nos graphiques (erreur de validation 1,438 → 1,372), mais sa fourchette sur 2026 reste derrière la méthode simple (4h : 290 contre 197 ; 1h : 147 contre 92).
   - **Direction avec le modèle ré-entraîné** (`KRONOS_MODEL=~/kronos/finetuned/crypto/best`, cache `backtest/kronos_cache_ft/`) : toujours le hasard.
     - Points de départ quelconques : « Kronos dit hausse » gagne 48 à 49 % contre 50 à 54 % pour « baisse » (1h, ±3 % : z = −2,6). C'est légèrement à l'envers et inexploitable après frais.
     - BUY filtrés par Kronos : z entre −1,0 et +1,4, sous le seuil fixé à l'avance (z ≥ 2).
     - **Kronos est donc abandonné comme signal**, sous toutes ses formes testées.
5. **Le post X « REA + Kronos = terminal Bloomberg »** (@carm1nee) promet exactement ce qui a été testé ici, et ça échoue. Le seul bon conseil du post est « backtest avant de faire confiance ».

## Autres éléments sur le PC
- `~/kronos` : clone de `shiyu-coder/Kronos` (licence MIT). Les poids locaux utilisés ici sont au format safetensors. Les données de marché et le chargement initial des modèles utilisent le réseau ; ne pas généraliser l'ancienne note d'audit à tout le dépôt (les exemples Qlib officiels utilisent notamment des fichiers pickle).
  - L'interface web d'origine (`webui`) écoutait sur `0.0.0.0` avec le mode debug actif. Si on la relance : `host=127.0.0.1`, `debug=False`.
- `~/rea` : clone de `morluto/rea`, « Reverse Engineer Anything » (MIT, officiel).
  - **Téléchargé seulement, rien n'a été exécuté ni installé** : Samet craint un virus.
  - Une lecture rapide du code n'a rien trouvé de suspect, mais ce n'était pas un audit complet.
  - Ne pas lancer `npx rea-agents setup` sans son accord : ça modifie la configuration des agents, et le paquet npm peut différer du code lu. Si on l'installe un jour : le construire depuis le code source lu, dans un environnement isolé.

## Reste à faire et idées
- **Collecte autorisée et activée le 21 octobre 2026** : le serveur archive BTC/ETH/HYPE/ZEC en spot Hyperliquid, 1h/4h, dans `terminal/data/hyperliquid.sqlite3` (ignoré par Git). Premier relevé : **32 703 bougies**, huit séries sans trous internes ; huit comparaisons Original/V2 figées avant leurs clôtures cibles. Collecte chaque minute tant que serveur/WSL tournent, reprise vérifiée après redémarrage. Carte « Collecte & validation » sur localhost et export CSV documenté dans `docs/kronos-local.md`. Aucun réentraînement automatique. Premières évaluations attendues le 22 octobre à 07:00 Paris (1h), le 23 à 18:00 (4h) ; aucun résultat réel de ce suivi encore disponible à la mise en place.
- **Reprise Codex du 21 octobre 2026 autorisée par Samet** : terminal corrigé (requêtes dédupliquées, réponses obsolètes rejetées), horizon commun 12 bougies, choix original/V1/V2, tableau de résultats. V2 entraîné avec volumes sur BTC/ETH/HYPE/ZEC ; époque 1 retenue après trois époques. Sur le diagnostic pilote de 96 départs, erreurs V2 1h/4h = 142,2/227,4 contre 106,6/219,4 pour la méthode simple ; pas d'avantage directionnel établi. Poids et rapport dans `backtest/experiments/crypto-volume-v2/`. Lire `docs/kronos-local.md` pour les commandes et limites. Les résultats 2026 réutilisés ne sont pas un test indépendant.
- Faire valider par Samet le rendu du terminal et de l'indicateur Pine. Je ne peux pas compiler le Pine ici : il le colle dans TradingView et renvoie les erreurs.
- Proposé, pas encore demandé :
  - alertes Telegram du terminal : Samet crée le bot avec @BotFather, le jeton reste dans un fichier local, jamais dans le chat ;
  - déploiement sur un petit serveur loué (VPS), protégé par mot de passe ;
  - journal de trades : c'est la gestion de Samet qui fait ses résultats, et il faut la mesurer.
- Publication publique GitHub réalisée et vérifiée ; GitLab conservé comme dépôt secondaire (voir l'état Git ci-dessus).
