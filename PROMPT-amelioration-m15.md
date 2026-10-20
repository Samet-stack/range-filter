# Prompt : améliorer l'algo Range Filter Spot en 15 min

**But.** Rendre la stratégie `range-filter-spot-v4.pine` rentable après coûts en **15 min**, en spot long uniquement sur Hyperliquid (BTC, ETH, HYPE, ZEC). Elle ne doit pas rater les grands mouvements visibles. Si c'est impossible, le prouver avec des chiffres et le dire.

**Point de départ (audit du 2026-10-20).**
- Une réplique Python du script existe. Elle est validée sur deux captures HYPE (30 min et 15 min).
- En 15 min, le signal brut ne rapporte que +0,01 à +0,09 % par trade sur BTC, ETH et ZEC, et il est négatif sur HYPE. Un aller-retour coûte 0,20 %. Aucun réglage période/multiplicateur ne corrige ça.
- Le filtre de coûts compare le coût à une largeur lente (EMA 100 et 199). En sortie de calme, il refuse donc les départs de tendance. Exemple : la montée de HYPE du 18 au 19 octobre, de 77,6 à 80,4, refusée avec un rapport de 2,9 à 3,0 pour un seuil de 3.
- Retard structurel : on achète après environ 2 largeurs de hausse depuis le creux, et on revend après environ 2 largeurs de baisse depuis le sommet.

**Ce qu'il faut faire, dans l'ordre.**
1. **Diagnostiquer avant de corriger.** Sur les trades du Témoin en 15 min, mesurer d'où vient la perte :
   - le retard à l'entrée (l'écart entre le creux et le prix d'entrée) ;
   - ce qui est rendu à la sortie (l'écart entre le sommet et le prix de sortie) ;
   - les allers-retours perdants ;
   - les coûts.
   Les résultats sont à donner en % par trade.
2. **Proposer au plus 3 changements**, chacun visant la cause principale trouvée. Pistes à évaluer, pas à empiler :
   - un filtre de coûts fondé sur la volatilité **actuelle** (ATR court, ou largeur de la bougie de cassure) au lieu de la largeur lente, ou bien la suppression de ce filtre ;
   - une entrée plus précoce (par exemple sur la cassure de la bande haute, ou avec un multiplicateur d'entrée plus petit que celui de sortie) ;
   - une sortie qui rend moins (suiveuse fondée sur l'ATR court, seulement si le diagnostic montre que le rendu domine) ;
   - un seul candidat d'achat par jambe haussière, au lieu de dizaines de points gris.
3. **Tester chaque changement seul** puis la combinaison retenue, avec la réplique Python :
   - sur les 4 actifs ;
   - en développement (jusqu'au 31/12/2025) et hors échantillon (2026) ;
   - avec les coûts de référence (0,10 % par côté) **et** défavorables (0,27 %).
   Chaque changement est comparé au Témoin.
4. **Critères pour garder un changement :**
   - espérance par trade **après coûts de référence** > 0 hors échantillon sur au moins 3 actifs sur 4 ;
   - pas d'effondrement en coûts défavorables ;
   - stable sur les réglages voisins ;
   - sur des montées comme celle de HYPE du 18 au 19 octobre, l'achat doit être pris.
   Toujours comparer à l'achat-conservation, et regarder le t : moins de 2 ne prouve rien.
5. **Si aucun changement ne passe en 15 min**, le dire clairement, puis donner la plus petite unité de temps où ça passe.
6. **Seulement ensuite**, reporter le changement retenu dans le Pine, en modification chirurgicale. Vérifier sur une capture que la réplique et TradingView donnent les mêmes trades.

**Interdits.**
- Régler sur la période hors échantillon.
- Retenir le meilleur réglage isolé.
- Ajouter un filtre juste pour embellir un backtest.
- Annoncer un résultat non mesuré.

**Livrable.** Un tableau avant/après (Témoin, chaque changement, combinaison) × actif × période × coûts, le verdict en 5 lignes, puis le Pine modifié si un changement est retenu.
