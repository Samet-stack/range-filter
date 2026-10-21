# Prompt de challenge : visuel de `range-filter-manuel.pine` (2026-10-21)

**Retour de Samet :** « on voit pas trop ». Il trade à la main, devant l'écran : il doit comprendre le graphique en **une seconde**, sans lire de tableau.

## Les 5 questions auxquelles le graphique doit répondre seul
1. **Tendance** : est-ce que ça monte, baisse ou range maintenant ? Il faut le voir de loin, sur thème clair comme sombre.
2. **Signal** : où sont les BUY ? Ils doivent sauter aux yeux, avec le prix du BUY.
3. **Trade en cours** : depuis le BUY, combien je gagne maintenant, et combien j'ai eu au mieux ? Lisible à côté du prix, pas dans un coin.
4. **Historique** : pour chaque BUY passé, jusqu'où ça a monté et combien ça a baissé d'abord ? Le « range précis » doit se voir sur le graphique.
5. **Verdict** : sur cet actif et cette unité de temps, est-ce que le BUY fait mieux que le hasard ? Une ligne, une couleur, un mot.

## Grille de challenge (chaque point à cocher, sinon corriger)
- [ ] **Contraste** : texte des tableaux lisible en thème clair **et** sombre (couleurs du graphique, pas gris sur noir).
- [ ] **Hiérarchie** : le filtre et les BUY dominent ; FIN et les détails restent discrets.
- [ ] **Pas de surcharge** : chaque nouvel élément a une option pour le masquer ; on ne cache pas les bougies.
- [ ] **Tailles réglables** (étiquettes, tableaux) : un écran portable n'est pas un 27 pouces.
- [ ] **Honnêteté** : le verdict repose sur un test chiffré (écart au hasard rapporté au bruit, avec n), pas sur une impression. Pas de « OUI » vert avec 15 trades.
- [ ] **Aucun objectif ni stop imposé** : on montre ce qui s'est passé, on ne dit pas quoi faire.
- [ ] **Pine v6 valide** : signatures exactes (`box.new`, `fill`, `label`, `chart.fg_color`) ; limites de 500 boîtes et étiquettes ; pas de repaint (boîtes figées seulement à la clôture).
- [ ] **Moteur et statistiques inchangés** : les BUY restent identiques au Témoin, et la réplique Python reste valable.
- [ ] **Relecture indépendante** par un agent qui n'a pas écrit le code : compilation, visuel, honnêteté. Corriger tout ce qui est fondé.

## Comment savoir si on a le meilleur
- Comparer à ce qui est standard sur TradingView pour un filtre de tendance : ligne épaisse colorée, nuage de tendance, étiquettes claires, panneau d'état. Garder seulement ce qui répond à une des 5 questions.
- Une seule chose ne se vérifie pas d'ici : le rendu réel. Il faut la capture d'écran de Samet, en thème clair et sombre si possible.
