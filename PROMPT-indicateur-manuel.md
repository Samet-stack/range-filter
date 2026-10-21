# Prompt : indicateur Range Filter pour trading manuel (2026-10-21)

**Contexte.** Samet trade à la main en spot (ETH, HYPE, BTC, ZEC sur Hyperliquid). Quand le filtre passe en BUY et qu'il voit que ça monte, il achète. Il sort lui-même, au moment qu'il juge bon (souvent vers +3/+4 %, mais c'est variable). Les stops sont décidés par lui. Ce n'est pas un bot : le script ne doit imposer **aucun objectif, aucun stop, aucune règle de sortie**.

Les audits du 2026-10-20 montrent que, comme stratégie automatique, le filtre n'a pas d'avantage après coûts. En revanche, après un BUY, le prix monte un peu plus souvent qu'au hasard. L'indicateur doit donc **montrer honnêtement ce que les BUY ont donné sur l'actif et l'unité affichés**, pour que Samet sache où le range est fiable.

**À livrer : `range-filter-manuel.pine`** (`indicator`, Pine v6). La V4 reste intacte.

1. **Moteur identique à la V4** (filtre, garde de progression, nouvel extrême, plat prolongé). Ce moteur est validé contre TradingView.
2. **Signaux** (comme le Témoin V3.1 spot) :
   - BUY au premier pas haussier, à la clôture, quand aucun mouvement n'est en cours ;
   - FIN du mouvement au premier pas baissier, ou après N bougies plates.
   - FIN est une information, pas un ordre de vente.
3. **Pendant un mouvement** : ligne du prix de référence (clôture du BUY) et ligne du maximum atteint. Le tableau affiche le gain actuel, le max atteint et la pire baisse.
4. **À la fin d'un mouvement** : l'étiquette BUY affiche le max atteint. Le tooltip donne le max, la baisse avant le max, le résultat à FIN après frais et la durée.
5. **Montant** : wallet saisi × % par trade, donnant le montant et la quantité au prix actuel. Pas de valeur imposée (wallet 0 = ligne masquée).
6. **Tableau de statistiques** sur l'historique chargé, depuis une date réglable :
   - nombre de BUY ;
   - max atteint médian ;
   - % de BUY qui montent d'au moins S1/S2/S3 (seuils réglables) ;
   - baisse médiane avant le max ;
   - résultat moyen si on avait vendu à FIN ;
   - durée médiane.
   **Chaque chiffre est comparé au hasard** : mêmes durées, débuts tirés dans l'historique, générateur déterministe.
7. **Alertes** BUY et FIN, une fois par clôture.

**Interdits** : objectif ou stop fixe, promesse de gain, chiffre non mesuré, modifier la V4.

**Vérification** : une réplique Python des mêmes statistiques sur les données Binance/Bybit (1h, 4h). Le nombre de BUY doit être identique aux entrées du Témoin de `backtest/rf_bt.py`. Les chiffres attendus sont fournis pour comparaison avec le tableau TradingView.
