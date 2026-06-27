# Comprendre le projet rPPG — Guide de révision

> Document de mentorat. Objectif : comprendre **en profondeur** chaque concept et chaque choix technique du projet, pour pouvoir en parler avec assurance en entretien.
> Lis-le calmement, plusieurs fois. À la fin de chaque partie, il y a un encadré **🎤 En entretien** avec les questions typiques.

---

## Partie 0 — La vue d'ensemble en une phrase

> « J'ai construit une application web qui mesure la fréquence cardiaque **sans contact**, à partir du flux d'une webcam, en analysant les **micro-variations de couleur de la peau** causées par les battements du cœur. C'est du traitement du signal + de la vision par ordinateur + de l'ingénierie temps réel (FastAPI/WebSocket/Docker). »

Si tu retiens **une seule** chose : le cœur fait circuler le sang → le volume de sang dans la peau change à chaque battement → ça change *très légèrement* la couleur de la peau → une caméra peut capter ce changement → on en déduit le rythme.

---

## Partie 1 — La science : qu'est-ce que la rPPG ?

### 1.1 PPG (avec contact)
La **photopléthysmographie (PPG)** est la techno dans les oxymètres (la pince au bout du doigt) et les montres connectées. Principe :
- une LED éclaire la peau,
- à chaque battement, le cœur envoie du sang dans les capillaires → plus de sang = plus de lumière absorbée,
- un capteur mesure la lumière restante → on voit une oscillation au rythme du cœur.

### 1.2 rPPG (remote = sans contact)
La **rPPG** fait pareil **sans toucher**, avec une caméra normale et la lumière ambiante. La peau réfléchit la lumière de la pièce ; cette lumière réfléchie est, elle aussi, modulée par le sang qui va et vient. La caméra voit donc une infime oscillation de couleur.

**Analogie** : imagine un mur peint qui change de teinte de façon imperceptible quand on allume/éteint une lampe derrière. Le « mur » c'est ta joue, la « lampe » c'est ton pouls.

### 1.3 Pourquoi le canal VERT ?
Une caméra capte 3 couleurs : Rouge, Vert, Bleu (RGB). Le signal de pouls est **le plus fort dans le vert**. Pourquoi ?
- Le sang contient de l'**hémoglobine**, qui **absorbe fortement la lumière verte** (~540 nm).
- Donc quand le volume de sang augmente, l'absorption du vert augmente nettement → le vert réfléchi baisse → grande variation.
- Le rouge est peu absorbé (la lumière rouge pénètre profond et est peu sensible au sang superficiel), le bleu pénètre peu et est bruité.

➡️ **Le vert porte le meilleur rapport signal/bruit pour le pouls.**

### 🎤 En entretien
- *« Comment une caméra mesure le pouls ? »* → variation du volume sanguin → variation de couleur de la peau.
- *« Pourquoi le vert ? »* → l'hémoglobine absorbe fortement le vert, donc c'est le canal le plus sensible aux variations de sang.

---

## Partie 2 — Pourquoi c'est difficile

Trois ennemis :

1. **Le signal est minuscule** : 1 à 2 niveaux de couleur sur 255. C'est dans le bruit du capteur et de la compression JPEG.
2. **Le bruit de mouvement** : si tu bouges la tête ou parles, la luminosité de ta peau change de 10 à 20 niveaux — soit **10× plus fort que le pouls**. Pire : un mouvement peut avoir une fréquence proche de celle du cœur, donc un simple filtre ne l'élimine pas.
3. **Le teint de peau** : la mélanine absorbe la lumière différemment selon les personnes → le rapport signal/bruit varie d'un individu à l'autre.

**La clé à comprendre** : le défi n°1 de la rPPG n'est PAS de filtrer les fréquences, c'est de **séparer le pouls du mouvement**. C'est exactement ce que résolvent CHROM et POS (Partie 3).

### 🎤 En entretien
- *« Quel est le principal défi ? »* → le bruit de mouvement, qui est bien plus fort que le signal et peut avoir une fréquence proche.

---

## Partie 3 — Le cœur algorithmique : CHROM et POS

### 3.1 L'idée géniale
Comment distinguer un battement de cœur d'un mouvement de tête ?

- **Un mouvement** (ou un changement de lumière) affecte les 3 canaux R, G, B **de la même façon, proportionnellement** (tout devient plus clair ou plus sombre ensemble).
- **Un battement de cœur** affecte **surtout le vert** (cf. Partie 1.3), pas proportionnellement aux autres.

➡️ Donc si on **combine intelligemment** les canaux R, G, B, on peut faire une combinaison qui **s'annule pour le mouvement** mais **garde le pouls**. C'est ça, CHROM et POS.

**Analogie** : deux micros enregistrent une conversation + le même bruit de fond. Si tu soustrais un micro de l'autre, la conversation reste (différente sur chaque micro) mais le bruit de fond (identique) s'annule. CHROM/POS font une « soustraction maligne » des canaux de couleur.

### 3.2 CHROM (de Haan & Jeanne, 2013)
Étapes (dans `signal_processor.py`, fonction `_chrom`) :
1. **Normaliser** chaque canal par sa moyenne (enlève le niveau de base, garde les variations).
2. Construire deux signaux de « chrominance » :
   - `Xs = 3·R − 2·G`
   - `Ys = 1.5·R + G − 1.5·B`
   (ces coefficients viennent d'un modèle du ton de peau standard)
3. Combiner : `bvp = Xs − α·Ys`, où `α = écart-type(Xs) / écart-type(Ys)`.
   - Ce `α` est l'astuce : il **ajuste automatiquement** le mélange pour annuler le mouvement.

### 3.3 POS (Wang et al., 2017) — notre méthode par défaut
POS = *Plane-Orthogonal-to-Skin*. Même philosophie, projection différente (fonction `_pos`) :
- `S1 = G − B`
- `S2 = G + B − 2·R`
- `bvp = S1 + α·S2`, avec `α = std(S1)/std(S2)`.

POS projette le signal dans un **plan orthogonal à la direction du ton de peau** dans l'espace RGB. Concrètement : on enlève la composante « couleur de peau / mouvement » et on garde ce qui pulse.

### 3.4 CHROM vs POS — lequel choisir ?
On a **mesuré** (benchmark UBFC) : **POS est plus robuste** (MAE 4.4 vs 5.0 BPM). POS est plus récent et gère mieux des conditions variées. → **POS par défaut**, CHROM disponible en option (`RPPG_METHOD` dans `config.py`).

### 🎤 En entretien
- *« Pourquoi combiner les canaux au lieu de juste prendre le vert ? »* → pour annuler le bruit de mouvement, qui affecte les 3 canaux proportionnellement alors que le pouls non.
- *« Différence CHROM/POS ? »* → même principe (projection des canaux), formules différentes ; POS plus robuste, choisi après benchmark.
- *« C'est quoi α ? »* → un facteur calculé sur les écarts-types qui ajuste le mélange pour annuler le mouvement.

---

## Partie 4 — Le traitement du signal (du RGB au BPM)

Une fois qu'on a le signal `bvp` (le pouls brut), il faut en sortir un chiffre : les BPM.

### 4.1 Le buffer glissant
On accumule les valeurs RGB dans une **fenêtre glissante de ~10 secondes** (un `deque` en Python, taille fixe). Pourquoi 10 s ?
- Trop court → pas assez de battements pour une mesure fiable (à 60 BPM, 10 s = 10 battements).
- Trop long → réagit lentement aux changements.
- 10 s est le compromis classique en rPPG.

On **recalcule le BPM toutes les ~1.5 s**, pas à chaque frame (inutile et coûteux).

### 4.2 Le filtre passe-bande (Butterworth, 0.65–4 Hz)
On ne garde que les fréquences **physiologiquement plausibles** :
- 0.65 Hz = 39 BPM (limite basse)
- 4 Hz = 240 BPM (limite haute)
- Tout le reste (dérive lente de la lumière, bruit haute fréquence) est coupé.

Un **filtre de Butterworth** est un filtre « doux » sans ondulation dans la bande passante. On l'applique avec `scipy.signal`.

**Conversion Hz ↔ BPM** : `BPM = Hz × 60`. (1 battement/seconde = 60 BPM.)

### 4.3 La FFT : trouver la fréquence dominante
La **transformée de Fourier (FFT)** décompose le signal en ses fréquences. On cherche le **pic** dans la bande cardiaque : la fréquence la plus forte = le rythme du cœur.

Détails d'implémentation qui améliorent la précision :
- **Fenêtre de Hann** avant la FFT : réduit les « fuites spectrales » (artefacts dus au fait qu'on coupe le signal).
- **Zero-padding (NFFT=2048)** : interpole le spectre pour une résolution plus fine.
- **Interpolation parabolique** du pic : précision sous la résolution de la FFT (on ajuste une parabole sur les 3 points autour du pic).

### 4.4 Le piège des HARMONIQUES (très important à comprendre)
Un signal périodique a des **harmoniques** : si ton cœur bat à 75 BPM (fondamentale), le spectre a aussi de l'énergie à 150 BPM (×2) et parfois 37 BPM (½). La FFT peut **se tromper de pic** et choisir une harmonique → BPM faux (tu voyais 44 ou 150 au lieu de 75).

**Notre solution : le lissage par médiane.** On garde les 7 derniers BPM calculés et on prend la **médiane**. Un saut isolé (44 ou 150) est un outlier que la médiane écarte automatiquement. C'est simple et très efficace.

> Pourquoi la médiane et pas la moyenne ? La moyenne serait tirée par les valeurs aberrantes (75,75,150 → moyenne 100). La médiane les ignore (75,75,150 → médiane 75).

### 4.5 Le SNR (qualité du signal)
On calcule un **rapport signal/bruit** : la puissance dans la bande cardiaque / puissance totale. Si le SNR est trop bas, on **n'intègre pas** ce BPM dans l'historique (gating). Ça évite de polluer la mesure quand le visage bouge ou est mal éclairé.

### 🎤 En entretien
- *« Pourquoi un buffer de 10 s ? »* → assez de battements pour une mesure fiable, sans trop de latence.
- *« Comment tu passes du signal au BPM ? »* → FFT, on cherche le pic de fréquence dans la bande 0.65–4 Hz, ×60.
- *« C'est quoi le problème des harmoniques et comment tu l'as réglé ? »* → la FFT peut choisir ×2 ou ½ de la vraie fréquence ; lissage médiane des derniers BPM pour rejeter les sauts.
- *« Pourquoi un filtre passe-bande ? »* → garder seulement les fréquences cardiaques humaines (39–240 BPM), couper dérive et bruit.

---

## Partie 5 — Vision : détecter le visage et la zone de peau (ROI)

ROI = *Region Of Interest* = la zone de peau dont on mesure la couleur (front + joues, riches en capillaires).

### 5.1 L'évolution (et c'est une belle histoire à raconter)
1. **MediaPipe Python** (prévu au départ) → cassé sur Mac Apple Silicon → abandonné côté backend.
2. **Haar Cascade** (OpenCV) → détecte juste un **rectangle** autour du visage, on devine front/joues par pourcentages. Grossier → précision médiocre (MAE ~10–25 BPM).
3. **dlib (68 landmarks)** → trouve 68 points précis (yeux, sourcils, nez, mâchoire) → ROI **exacte et stable** → précision **MAE 4.4 BPM**.

➡️ **La leçon clé du projet** : la précision ne venait pas de l'algorithme (POS/CHROM marchaient déjà), mais de la **qualité de la ROI**. C'est un point fort à mentionner : tu as diagnostiqué que le goulot d'étranglement était la ROI, pas l'algo.

### 5.2 La segmentation de peau (YCrCb)
Même avec une bonne ROI, on peut capter des pixels non-peau (cheveux, ombres). On convertit en espace **YCrCb** et on ne garde que les pixels dont la chrominance (Cr, Cb) est dans la plage « peau ». Avantage : robuste aux différents teints (mieux que des seuils RGB bruts).

### 5.3 Deux détecteurs, deux rôles (à bien distinguer !)
- **dlib** (Python, backend) → calcule la ROI pour **le BPM**.
- **MediaPipe** (JavaScript, navigateur) → dessine le **masque visuel 468 points** à l'écran (effet, pas de calcul).

Ils coexistent : l'un calcule, l'autre décore. C'est un point qu'un recruteur peut creuser (« pourquoi deux ? ») → réponse : MediaPipe Python est cassé sur Mac, mais sa version JS marche dans le navigateur pour l'affichage ; le calcul lui se fait côté serveur avec dlib.

### 🎤 En entretien
- *« C'est quoi la ROI ? »* → la zone de peau (front/joues) dont on moyenne la couleur.
- *« Pourquoi dlib plutôt que Haar ? »* → Haar donne un rectangle grossier et instable ; dlib donne 68 points précis → ROI stable → MAE divisé par ~2.
- *« Qu'est-ce qui a le plus amélioré la précision ? »* → la qualité de la ROI, pas l'algo rPPG.

---

## Partie 6 — L'architecture backend (l'ingénierie temps réel)

C'est la partie « ingénieur » qui impressionne autant que la science.

### 6.1 FastAPI + WebSocket
- **HTTP classique** = une requête → une réponse, puis on coupe. Inadapté à un flux continu.
- **WebSocket** = un tuyau **bidirectionnel permanent** entre navigateur et serveur. Parfait pour envoyer des frames en continu et recevoir des BPM en continu.
- Endpoint : `/ws/rppg` dans `ws_router.py`.

### 6.2 État PAR connexion (pas de variable globale !)
Chaque utilisateur connecté a **son propre** buffer et son propre détecteur (classe `WebSocketSession`). 

**Pourquoi c'est crucial ?** Si on utilisait une variable globale partagée, les frames de plusieurs utilisateurs simultanés se mélangeraient → BPM faux pour tout le monde. C'est une question d'entretien classique sur la **gestion d'état** et la **concurrence**.

### 6.3 Le piège de l'asynchrone : `run_in_executor`
FastAPI tourne sur une **boucle asyncio** (mono-thread, gère plein de connexions en alternant). Problème : le décodage d'image, dlib et le calcul du signal sont **bloquants et lourds en CPU**. Si on les lance directement dans la fonction `async`, ils **bloquent toute la boucle** → tous les autres utilisateurs gèlent.

**Solution** : `run_in_executor` envoie ces tâches lourdes dans un **pool de threads** séparé. La boucle asyncio reste libre de gérer les autres connexions pendant ce temps.

**Analogie** : un serveur de restaurant (la boucle asyncio) ne reste pas planté à la cuisine pendant la cuisson ; il délègue au cuisinier (le thread pool) et continue de servir les autres tables.

### 6.4 Le protocole de communication
- **Client → serveur** : frames JPEG en **binaire** (pas base64, qui gonfle de 33 %), à 10 fps.
- **Serveur → client** : messages JSON (`{type: "bpm_update", bpm: 72, confidence, bvp_signal...}`).
- 10 fps (et pas 30) : compromis entre précision du signal et charge réseau/CPU.

### 🎤 En entretien
- *« Pourquoi WebSocket et pas HTTP ? »* → flux continu bidirectionnel temps réel.
- *« Comment tu gères plusieurs utilisateurs ? »* → état isolé par connexion (classe Session), jamais de variable globale partagée.
- *« Comment tu évites de bloquer le serveur avec des calculs lourds ? »* → `run_in_executor` (thread pool) pour sortir le CPU-intensif de la boucle asyncio.

---

## Partie 7 — Le frontend

JavaScript vanilla (pas de framework, pour rester léger) :
- **`getUserMedia`** : accès webcam.
- **`<canvas>`** : on dessine la frame, on l'exporte en JPEG (`toBlob`), on l'envoie via WebSocket.
- **Courbe BVP** : dessinée sur un canvas natif (le signal de pouls en temps réel).
- **Son cardiaque** : Web Audio API, un « lub-dub » synthétique cadencé sur le BPM.
- **Retry WebSocket** : si la connexion échoue (ex. serveur Fly endormi), on réessaie automatiquement (réveil à froid géré proprement).

**Détail sécurité** : `getUserMedia` n'autorise la webcam que sur **HTTPS ou localhost** (contexte sécurisé). En prod (HTTPS), le WebSocket passe en `wss://` automatiquement.

### 🎤 En entretien
- *« Pourquoi pas de framework JS ? »* → projet simple, vanilla suffit, moins de dépendances.
- *« Comment tu envoies la vidéo ? »* → capture canvas → JPEG binaire → WebSocket à 10 fps.

---

## Partie 8 — La validation scientifique (benchmark)

C'est ce qui transforme un « ça a l'air de marcher » en « voici mes chiffres ».

### 8.1 Le dataset UBFC-rPPG
Vidéos de visages + **vérité terrain** (la vraie HR mesurée par un oxymètre de contact). On compare notre estimation à la vérité.

### 8.2 Les métriques
- **MAE** (Mean Absolute Error) : erreur absolue moyenne en BPM. *« En moyenne, je me trompe de X BPM. »* → **4.4 BPM** (POS).
- **RMSE** (Root Mean Square Error) : comme MAE mais pénalise plus les grosses erreurs.
- **Pearson r** : corrélation (est-ce que l'estimation **suit** les variations de la vraie HR ?).

### 8.3 La rigueur : l'outlier subject11
Un sujet donnait MAE 40. Diagnostic : sa **vérité terrain était corrompue** (HR descendant à 1 BPM, impossible — l'oxymètre avait décroché). On l'a **écarté avec justification** et ajouté un filtre (ignorer les HR hors [40,200]).

➡️ **Point fort en entretien** : tu n'as pas masqué un mauvais chiffre, tu as **inspecté les données**, identifié un problème de qualité, et pris une décision méthodologique. C'est exactement ce qu'on attend d'un data scientist sérieux.

### 8.4 Le résultat
- **POS : MAE 4.4 BPM** sur les 8 sujets exploitables → **niveau de la littérature scientifique** (les papers publient MAE 4–7 BPM).
- Progression documentée : Haar 25.7 → +lissage 13.8 → +skin 10.5 → +dlib **4.4**.

### 🎤 En entretien
- *« Comment tu as validé ta précision ? »* → benchmark sur UBFC-rPPG (vérité terrain oxymètre), métriques MAE/RMSE/Pearson.
- *« C'est quoi le MAE ? »* → erreur absolue moyenne ; le mien est 4.4 BPM.
- *« Tu as eu un sujet à 40 BPM d'erreur, c'est nul non ? »* → non, sa vérité terrain était corrompue (HR à 1 BPM), je l'ai diagnostiqué et écarté proprement.

---

## Partie 9 — Récap des choix techniques (le « pourquoi » de chaque décision)

| Décision | Pourquoi |
|---|---|
| **POS** par défaut | Plus robuste que CHROM, **mesuré** au benchmark (4.4 vs 5.0) |
| **dlib** pour la ROI | Landmarks précis → ROI stable → précision ×2 vs Haar |
| **Segmentation YCrCb** | Robuste aux teints (mieux que seuils RGB) |
| **Buffer 10 s** | Assez de battements, latence raisonnable |
| **Filtre 0.65–4 Hz** | Plage cardiaque humaine (39–240 BPM) |
| **Lissage médiane** | Tue les sauts harmoniques (44/150) |
| **WebSocket** | Flux temps réel bidirectionnel |
| **État par session** | Pas de mélange entre utilisateurs |
| **`run_in_executor`** | Ne pas bloquer la boucle asyncio avec le CPU |
| **JPEG binaire 10 fps** | Compromis bande passante / précision |
| **Docker multi-stage** | Compiler dlib sans alourdir l'image finale |
| **Fly.io** | Supporte WebSocket + processus long (vs Render qui dort 15 min) |
| **Retry WebSocket** | Gère le réveil à froid de la machine Fly |

---

## Partie 10 — Les questions « pièges » et tes réponses honnêtes

- *« C'est pas juste un import de pyVHR ? »*
  → Non. pyVHR ne tourne pas sur Mac (dépendance CUDA). J'ai **implémenté CHROM et POS moi-même** depuis les papiers originaux. Une vingtaine de lignes de NumPy chacun.

- *« Quelles sont les limites de ton système ? »*
  → Sensible aux mouvements brusques et aux changements d'éclairage. Validé sur 9 sujets (pas tout le dataset). ROI calculée deux fois (dlib serveur + MediaPipe navigateur) — une refonte pourrait l'unifier côté client.

- *« Comment tu améliorerais ? »*
  → Faire l'extraction ROI côté navigateur (MediaPipe JS) pour n'envoyer que les RGB (moins de bande passante, backend plus léger) ; ajouter une compensation de mouvement ; valider sur plus de sujets.

- *« Pourquoi 10 fps et pas 30 ? »*
  → Compromis. À 10 fps on a Nyquist = 5 Hz > 4 Hz (la HR max), donc on capte tout le spectre utile, avec 3× moins de données réseau/CPU.

---

## Comment réviser avec ce document

1. Lis une partie, ferme le document, **réexplique-la à voix haute** avec tes mots.
2. Si tu bloques, relis. Recommence jusqu'à ce que ça coule.
3. Les encadrés **🎤 En entretien** = tes flashcards. Entraîne-toi à y répondre sans regarder.
4. Quand tu te sens prêt, demande-moi de passer en **mode recruteur sévère**.

Tu n'as pas besoin de connaître le code par cœur. Tu dois savoir **expliquer les concepts et justifier les choix**. C'est ça qu'un bon recruteur cherche.
