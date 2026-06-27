# Projet rPPG — Détection de fréquence cardiaque par webcam (sans contact)

## Contexte

Projet personnel de Bilal, étudiant en M2 Intelligence Artificielle (Université de Bordeaux), destiné à être publié sur LinkedIn et inclus dans son CV/portfolio. L'objectif est de démontrer une vraie compréhension technique (traitement du signal + vision par ordinateur + ingénierie backend temps réel) plutôt qu'une simple démo "j'ai branché un modèle préfait".

Ce document explique le problème à résoudre et la stack retenue. **La décomposition en architecture détaillée (structure des fichiers, modules, classes) n'est pas encore faite — c'est l'étape suivante, à réaliser avec Claude Code.**

---

## Le problème : qu'est-ce que la rPPG ?

La **photoplethysmographie (PPG)** classique mesure le pouls avec un capteur de contact (ex. oxymètre de pouls) : une LED envoie de la lumière dans la peau, un capteur mesure l'absorption, qui varie légèrement à chaque battement cardiaque (le volume sanguin dans les capillaires change).

La **remote PPG (rPPG)** fait la même mesure sans contact, avec une caméra classique. La lumière ambiante réfléchie par la peau est elle aussi modulée par ces variations de volume sanguin. Le canal vert est le plus sensible (l'hémoglobine absorbe fortement cette longueur d'onde).

**Objectif du projet** : à partir du flux vidéo d'une webcam, détecter le visage, isoler une zone d'intérêt (front/joues), et en déduire la fréquence cardiaque (BPM) en temps réel, affichée en direct dans une interface web.

## Pourquoi c'est difficile

- **Signal minuscule** : la variation de couleur de peau due au pouls représente seulement 1-2 niveaux sur 255, noyée dans le bruit du capteur et la compression vidéo de la webcam.
- **Bande de fréquence ciblée** : le rythme cardiaque humain se situe entre 0.7 et 4 Hz (42-240 BPM) — il faut isoler précisément cette plage du reste (dérive lumineuse, bruit capteur).
- **Bruit de mouvement** : un mouvement de tête ou le fait de parler change la luminosité de 10 à 20 niveaux — bien plus que le signal du pouls — et peut avoir une fréquence proche de celle du cœur, donc un simple filtre fréquentiel ne suffit pas à l'éliminer.
- **Variation de teinte de peau** : la mélanine absorbe différemment la lumière selon les individus, ce qui affecte le rapport signal/bruit.

C'est pour cette dernière raison (bruit de mouvement) que les algorithmes modernes (CHROM, POS) ne se contentent pas de filtrer en fréquence : ils combinent les 3 canaux R, G, B entre eux, car un mouvement affecte les trois canaux de façon à peu près proportionnelle (la combinaison l'annule), alors qu'un battement cardiaque affecte le vert bien plus que le rouge et le bleu (la combinaison le préserve).

## Pipeline conceptuel

1. Capture vidéo (webcam)
2. Détection du visage et extraction d'une ROI (région d'intérêt : front ou joues)
3. Extraction de la moyenne R, G, B de la ROI à chaque frame → série temporelle
4. Combinaison des canaux (CHROM/POS) pour annuler le bruit de mouvement
5. Filtrage passe-bande (0.7-4 Hz)
6. FFT pour trouver la fréquence dominante → BPM

---

## Approche algorithmique retenue : pyVHR

[pyVHR](https://github.com/phuselab/pyVHR) est un framework Python de référence pour la rPPG (Boccignone et al., IEEE Access 2020 ; PeerJ Computer Science 2022). Il implémente de façon validée scientifiquement : GREEN, CHROM, ICA, PCA, POS, SSR, LGI, PBV, OMIT, ainsi qu'un modèle deep learning (MTTS-CAN).

**Méthode ciblée pour ce projet : CHROM ou POS** (les plus robustes au mouvement parmi les méthodes "classiques", non deep learning).

**⚠️ Point d'attention important pour l'implémentation** : pyVHR est nativement conçu pour une utilisation *analyse/benchmark hors-ligne* — son API principale (`Pipeline.run_on_video()`) prend en entrée un **fichier vidéo complet**, pas un flux webcam en direct. Pour notre cas d'usage temps réel (frames qui arrivent en continu via WebSocket), il faudra probablement :
- soit utiliser directement les fonctions de méthode individuelles de pyVHR (le calcul CHROM/POS lui-même, qui prend une fenêtre de signaux RGB en entrée) sur nos propres buffers glissants, plutôt que la Pipeline complète,
- soit explorer si une utilisation détournée de la Pipeline sur de courts clips successifs est viable.

C'est un point à investiguer et clarifier en tout début d'implémentation, idéalement avant de figer l'architecture.

**Licence** : pyVHR est sous licence GPL-3.0 — à mentionner si le code est publié publiquement sur GitHub.

**Détection visage / ROI** : Mediapipe Face Mesh (indépendant de pyVHR, à intégrer nous-mêmes pour le pipeline temps réel).

---

## Stack technique retenue

| Composant | Choix |
|---|---|
| Backend | FastAPI, endpoint WebSocket pour le streaming temps réel |
| Capture vidéo (client) | JS `getUserMedia` + `<canvas>`, envoi des frames via WebSocket |
| Décodage image | OpenCV |
| Détection visage / ROI | Mediapipe Face Mesh |
| Algorithme rPPG | pyVHR (CHROM ou POS) |
| Filtrage signal | SciPy (`scipy.signal` — passe-bande Butterworth, FFT) |
| Conteneurisation | Docker |
| Déploiement | Render ou Fly.io (support WebSocket + processus long-running) |

Niveau d'ambition choisi : **projet complet** (pas un MVP Gradio rapide) — l'objectif est de mobiliser et démontrer des compétences FastAPI/Docker/temps réel, pas juste de produire une démo.

---

## Contraintes techniques identifiées (à respecter dans l'architecture)

1. **État par connexion, pas de variable globale** : chaque utilisateur connecté en WebSocket doit avoir son propre buffer glissant (deque de ~10s de frames). Une variable globale partagée mélangerait les données de plusieurs utilisateurs simultanés.
2. **Traitement CPU-intensif et synchrone** : Mediapipe + pyVHR + filtrage bloquent la boucle asyncio de FastAPI s'ils sont exécutés directement dans une fonction `async def`. Prévoir `run_in_executor` (thread pool) ou une limitation du débit de frames réellement traitées (ex. 1 frame sur 2).
3. **Dépendances système dans Docker** : OpenCV et Mediapipe nécessitent des paquets système absents d'une image Python `slim` de base (`libgl1`, `libglib2.0-0`, notamment) — à déclarer explicitement dans le Dockerfile, sinon le conteneur plante au démarrage sur l'import.
4. **Fenêtre glissante** : ~10 secondes de buffer (soit ~300 frames à 30fps, moins si on sous-échantillonne), avec un recalcul du BPM toutes les 1-2 secondes plutôt qu'à chaque frame.

---

## Ce qui reste à décider (rôle attendu de Claude Code)

- Structure des fichiers et organisation du repo
- Plan d'architecture détaillé : modules, classes, séparation des responsabilités (ex. classe de session WebSocket, module de traitement du signal, etc.)
- Stratégie précise d'intégration de pyVHR dans un contexte temps réel (cf. point d'attention ci-dessus)
- Stratégie de test / validation de la précision du BPM (éventuellement comparaison avec un dataset public comme UBFC-rPPG, ou mesure empirique avec une montre connectée)
- Détails d'implémentation du frontend (JS vanilla suffit probablement, pas besoin de framework lourd)
- Configuration Docker complète et choix final entre Render/Fly.io selon les contraintes WebSocket de chacun

---

## Papiers et ressources de référence

- Verkruysse, Svaasand & Nelson (2008) — méthode naïve canal vert, *Optics Express*
- de Haan & Jeanne (2013) — CHROM, *IEEE Trans. Biomed. Eng.* 60(10)
- Wang, den Brinker, Stuijk & de Haan (2017) — POS, *IEEE Trans. Biomed. Eng.* 64(7)
- Poh, McDuff & Picard (2010) — ICA, *Optics Express* 18(10) (historique, moins robuste au mouvement, pour contexte)
- Boccignone et al. (2020) — *An Open Framework for Remote-PPG Methods and their Assessment*, IEEE Access — papier fondateur de pyVHR
- Boccignone et al. (2022) — *pyVHR: a Python framework for remote photoplethysmography*, PeerJ Computer Science

---

## Vision finale du projet

Démo web fonctionnelle et déployée publiquement : webcam → détection visage → calcul BPM en direct → affichage avec courbe en temps réel. Code source sur GitHub avec README clair (explication accessible du principe rPPG, captures/gif de démo, métriques de précision si validées). Accompagné d'un post LinkedIn expliquant le principe de façon pédagogique, et d'une entrée CV mettant en avant FastAPI/WebSocket/Docker/traitement du signal.
