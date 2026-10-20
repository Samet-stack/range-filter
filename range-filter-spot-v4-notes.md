# Range Filter Spot V4 — notes (2026-10-20)

Script : `~/Documents/range-filter-spot-v4.pine`. **Pas compilé de notre côté, aucun backtest lancé, donc aucun résultat chiffré ici.**

## 1. Diagnostic de la V3.1 (par priorité)

### Bugs démontrables (pour un usage spot)
1. **Une sortie peut arriver sur une autre alerte que « Bearish ».** Un pas baissier fait passer l'état de 1 à −1 (alerte SHORT, sans NEUTRE). Mais si le filtre HTF bloque le short, l'état passe de 1 à 0 et seule l'alerte NEUTRE part. Quelqu'un abonné seulement à « Bearish » rate donc la sortie, et justement quand l'HTF est haussier, c'est-à-dire quand il détient le plus souvent.
2. **« SHORT » n'a pas de sens au comptant.** Le retournement direct L→S, sans état intermédiaire, mélange deux décisions : vendre ce qu'on a, et ouvrir un short (impossible en spot).
3. **Rachat après une phase neutre.** Après N bougies plates, l'état revient à 0. Le pas haussier suivant redonne un L dans le même sens. Si le neutre est traité comme une sortie, on paie un aller-retour complet sans qu'aucune inversion ait eu lieu.

### Comportements intentionnels (documentés, mais trompeurs en spot)
- **ER sans veto en Réactif.** ER est calculé et affiché, mais `ranging and not refined` est toujours faux en Réactif : ER ne change rien aux signaux. C'est voulu (tooltip).
- **Couleur, état et entrée divergent.** La ligne suit `filterDirection`, les triangles suivent `signalState`. Avec l'HTF actif, la ligne peut être verte sans L. Un L bloqué peut aussi arriver plus tard, sur un pas de continuation, en plein milieu du mouvement.
- **ER et adaptation sont indépendants.** `useAdaptive` lit l'ER même quand « Utiliser l'efficacité » est décoché. Désactiver l'ER ne supprime donc pas tous ses effets. La V4 supprime l'adaptation.
- **HTF.** `close[1]` et `lookahead_on` donnent la bougie HTF terminée précédente : pas de repainting. Correct.

### Retard structurel (le point le plus important pour la rentabilité)
Un pas haussier exige `close − largeur > filtre`. En baisse, le filtre traîne à environ (plus basse clôture + largeur). Un achat demande donc environ **2 largeurs de hausse depuis le creux**. Une invalidation demande de même environ 2 largeurs de baisse depuis le sommet. Avec mult = 3, une largeur vaut à peu près 1,5 à 2 ATR (estimation, à mesurer dans la fenêtre de données). Un trade ne gagne donc que si le mouvement dépasse **environ 4 largeurs plus les coûts**. À cela s'ajoute l'exécution à l'ouverture suivante. Les « mouvements courts » ne sont captables que si 4 largeurs restent grandes devant les coûts. C'est ce que mesure le filtre « largeur / coût ».

### Protection contre la contraction de largeur
Deux gardes existent déjà : un pas exige une clôture qui progresse, et une continuation exige un nouvel extrême. Il reste un cas : un pas d'un tick de prix peut être amplifié par une baisse de la largeur. Avec des EMA 100 et 199, la largeur varie de moins de 1 % par bougie, sauf quand le plancher ATR s'applique. Je le classe comme risque résiduel faible, pas comme bug démontré.

## 2. Changements retenus et compromis

| Changement | Problème visé | Coût / retard | Comment vérifier |
|---|---|---|---|
| États À PLAT / EN POSITION, VENTE seulement si détenu | Bugs 1–3 | aucun | aucune VENTE à plat, aucune 2ᵉ entrée |
| Plat prolongé : sortie **seulement si pas de gain net** (défaut) | Allers-retours payés sans inversion | peut garder une position qui stagne au-dessus du point mort | comparer les 3 options de « Plat prolongé » |
| Filtre largeur ≥ k × coût AR (**ON**, k = 3) | Trades dont le bruit du filtre est petit devant les coûts | aucun retard, mais supprime des trades (souvent toute une UT courte) | compteur « refusés : coûts » + test ON/OFF |
| Stop de protection figé (**ON**) = invalidation − 0,25 ATR | Chute dans la bougie, gap | des mèches peuvent sortir une position que la clôture aurait gardée | sorties « stop » vs « inval. », test ON/OFF |
| Sortie suiveuse (OFF) | Le filtre rend environ 2 largeurs depuis le sommet | plus de sorties sur repli | test ON/OFF, D ∈ {1,5 ; 2 ; 3} |
| ER minimal (OFF), dépassement max (OFF), HTF (OFF), pause (0) | Marchés plats, entrée tardive, contre-tendance, alternances | retard ou trades manqués | un seul à la fois, ON/OFF |

**Pas de prise de profit fixe.** Un suiveur de tendance paie ses nombreuses petites pertes avec quelques grands mouvements. Un objectif fixe coupe justement ces mouvements. Il crée aussi une ambiguïté stop/objectif sur la même bougie OHLC.

**Témoin** = V3.1 Réactif sans HTF, traduit en spot. Il utilise les mêmes coûts, le même montant et la même exécution, mais aucun stop ni filtre.

### Règles de la machine à états
- **ACHAT** : uniquement à plat, à la clôture d'un pas haussier, filtres passés. Ordre au marché exécuté à l'**ouverture suivante**.
- **Priorité sur une bougie** : stop touché dans la bougie (déjà exécuté) > invalidation > stagnation > fin de fenêtre. Une seule VENTE. Jamais d'achat sur la bougie d'une sortie.
- **Les sorties ignorent les filtres d'entrée** (ER, HTF, coûts).
- **Nouvelle entrée** : nouveau pas haussier (donc nouvel extrême si le dernier pas était haussier), sur une bougie postérieure à la sortie et après la pause éventuelle.
- **Niveaux figés à l'entrée** : référence = clôture du signal, ATR, quantité, stop initial.
- **Niveaux mobiles** : uniquement le stop, via le suiveur, recalculé à chaque clôture et actif dès la bougie suivante. `max()` garantit qu'il ne descend jamais.
- **Activation du stop** : dès l'exécution de l'entrée (ouverture suivante). Si l'ouverture est déjà sous le stop, sortie immédiate au prix d'ouverture.

### Dimensionnement
Montant = min(budget € × taux, disponible saisi). Avec « perte max au stop », la quantité est aussi limitée à perte / (entrée − stop + coûts AR). Le budget reste un plafond. La quantité est arrondie **vers le bas** au pas de l'actif, et l'achat est refusé si le montant tombe sous le minimum d'ordre. La perte au stop est théorique : un gap ou un glissement peut la dépasser.

## 3. Hyperliquid : faits vérifiés le 2026-10-20

| Point | Valeur | Source |
|---|---|---|
| Frais spot, palier de base | taker 0,070 %, maker 0,040 % | [doc Fees](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees) (pas de date sur la page) |
| Remises | staking HYPE 5–40 %, parrainage, volume | idem, non modélisées |
| Paires spot (API `spotMeta`) | HYPE/USDC `@107`, **UBTC**/USDC `@142` (Unit Bitcoin), **UETH**/USDC `@151` (Unit Ethereum), **UZEC**/USDC `@272` (Unit Zcash) | API publique `info` |
| Piège ZEC | d'autres ZEC existent aussi : IZEC, BZEC, ZEC1. Ce ne sont pas les mêmes tokens. | idem |
| Décimales de quantité | UBTC 5, UETH 4, HYPE 2, UZEC 4 | idem |
| Prix | 5 chiffres significatifs, 8 − décimales de quantité au maximum | [doc Tick and lot size](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size) |
| Ordre minimal | 10 USDC | **source secondaire seulement** ([Chainstack](https://docs.chainstack.com/docs/hyperliquid-order-precision)), non confirmé |
| Spread (photo unique) | BTC 0,12 pb, ETH 0,42 pb, HYPE 0,76 pb, UZEC 1,77 pb ; coût de profondeur pour ~700 USDC ≤ 3,4 pb | `l2Book`, une seule photo : ne représente pas un marché agité |

BTC, ETH et ZEC sont des **tokens enveloppés (Unit)**. Leur prix suit l'actif natif, mais ce n'est pas le même actif : il y a un risque de pont et des frais de dépôt et de retrait. Ce sont des coûts ponctuels, pas des coûts par trade.

**Symbole TradingView non vérifié.** Je n'ai pas confirmé qu'un flux spot Hyperliquid existe sur TradingView. Si seuls les perpétuels (`.P`) existent, teste sur un spot liquide équivalent (BINANCE, COINBASE…) et note l'écart.

### Scénarios de coûts (par côté, à reporter dans Propriétés > Commission, glissement = 0)
- **Référence : 0,10 %** (0,07 de frais + 0,03 de demi-spread, glissement et délai). Aller-retour 0,20 %.
- **Défavorable : 0,27 %** (0,07 + 0,20). Aller-retour 0,54 %.

Le spread est compté **une seule fois**, dans la commission. Le glissement en ticks reste à 0, car un tick n'a pas le même poids en BTC et en HYPE. La ligne 16 du tableau signale si Propriétés ne correspond pas aux entrées du script.

## 4. Procédure de test dans TradingView
1. Graphique en bougies **standard**. Coller le script, Propriétés : commission 0,10 %, glissement 0. Le « Bar Magnifier » (Premium) limite l'ambiguïté du stop dans la bougie.
2. **Unités de temps** : seulement 15 min, 1 h et 4 h, avec les paramètres par défaut. Rejeter d'emblée une UT où la plupart des achats sont refusés pour « coûts » ou où l'aller-retour mange plus de 50 % du brut.
3. **Fenêtres** : développement jusqu'au 2025-06-30, hors échantillon du 2025-07-01 à aujourd'hui. Ne régler qu'en développement. HYPE spot n'existe que depuis fin 2024 : son historique est court.
4. Pour chaque actif et chaque UT : relever le Témoin puis l'Amélioré (lignes 7 à 18 du tableau), en coûts de référence **et** défavorables.
5. **Ablation** : partir de l'Amélioré, couper un ajout à la fois (stop, filtre coûts, règle de plat). Ne garder un ajout que s'il aide **hors échantillon et en coûts défavorables** sur la majorité des 4 actifs.
6. **Sensibilité** : période {70, 100, 140} × mult {2,5 ; 3 ; 3,5}. Garder un réglage entouré de voisins corrects, pas le meilleur isolé.
7. **Régimes** : définir à l'œil sur le daily des sous-fenêtres de hausse, baisse, range et forte volatilité, puis les rejouer avec Début/Fin.
8. **Puissance statistique** : regarder le t de la ligne 9. Avec 30 à 100 trades, seul un écart large est détectable. Un t < 2 ne prouve rien, dans un sens comme dans l'autre.

Tableau à remplir : actif × UT × version × coûts × fenêtre → net, DD, trades, espérance %, t, PF, exposition, part des coûts, achat-conservation.

## 5. Limites pour un usage réel
- La position est **simulée**. Le script ne lit pas le portefeuille et ne passe aucun ordre.
- Les alertes sont des **signaux de clôture** (JSON `kind: signal_at_close_not_an_order`). Un système externe doit :
  - dédupliquer par `symbol` + `bar_time` ;
  - lire le solde réel via l'API Hyperliquid avant d'agir ;
  - vérifier le remplissage après l'ordre ;
  - recalculer la quantité au pas réel.
- Le stop n'agit **dans la bougie** que dans le simulateur. L'alerte `SIM_STOP_TOUCHED` n'arrive qu'à la clôture : elle ne protège pas. Une vraie protection demande un ordre déclencheur sur Hyperliquid. Sa disponibilité en spot n'est pas vérifiée. Un stop ne garantit pas son prix.
- Les bougies OHLC ne reproduisent pas le carnet d'ordres. Le délai alerte → exécution n'est modélisé que par le coût par côté.
- Le taux EURUSD de la veille suppose USDC = USD. Les frais de conversion et de dépôt sont exclus.
