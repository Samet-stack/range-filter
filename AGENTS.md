# Consignes du projet

- Lire `PASSATION.md` en premier lors d'une reprise ; les détails du terminal et de l'expérience V2 sont dans `docs/kronos-local.md`.
- Le produit aide Samet à décider manuellement en spot. Aucun ordre ni connexion à un compte n'est nécessaire.
- Préserver `range-filter-spot-v4.pine` et les modèles/résultats existants.
- Le terminal reste sur `127.0.0.1:7071`. Pas de publication ni de push GitLab sans demande explicite.
- Les résultats 2026 déjà examinés sont des diagnostics réutilisés, pas un nouveau test indépendant.
- Le serveur lance la collecte spot et le journal prospectif dans `terminal/data/`. Préserver cette base ; ne pas entraîner un modèle sur les cibles utilisées ensuite pour prétendre le valider indépendamment. Voir `docs/kronos-local.md`.
- Sérialiser les calculs GPU via `kronos_runtime.gpu_slot()` pour les nouveaux scripts ; les anciens scripts ne prennent pas ce verrou.
- Avant de conclure : tests ciblés, parcours navigateur si l'interface change, puis mise à jour de la passation après une étape significative.
