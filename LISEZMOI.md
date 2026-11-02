# Assistant FM Dofus 3 (temps réel)

Une petite fenêtre reste au-dessus du jeu. Elle lit les stats de ton objet dans la fenêtre de forgemagie et te dit quelle rune passer.

**Ce qu'il fait :** des captures d'écran d'une zone que tu choisis, puis la lecture du texte (OCR).
**Ce qu'il ne fait pas :** il ne touche ni à la mémoire du jeu, ni au réseau, ni aux fichiers, et ne clique ni ne tape jamais à ta place.

## Installation (Windows, une seule fois)

1. **Python** : https://www.python.org/downloads/. Pendant l'installation, coche **« Add Python to PATH »**.
2. **Tesseract** (le moteur qui lit le texte) : https://github.com/UB-Mannheim/tesseract/wiki
   Pendant l'installation, dans *Additional language data*, coche **French**. Garde le dossier proposé (`C:\Program Files\Tesseract-OCR`).
3. Double-clique sur **`lancer.bat`**. Il installe ce qui manque, puis ouvre l'assistant.

## Utilisation

1. Dans Dofus, ouvre l'atelier de forgemagie et pose ton objet.
2. Dans l'assistant, clique sur **📐 Zone** et encadre **toute la fenêtre de forgemagie** : l'historique à gauche, le reliquat et le tableau. Le programme repère tout seul les colonnes « Min » et « Modif. ». Il lit séparément l'historique (le nom de l'objet et le résultat de chaque rune) et le tableau (les valeurs, les max et le reliquat), et ignore les colonnes de runes.
   *(Le bouton 📜 Histo reste disponible si tu préfères encadrer l'historique à part.)*
3. Choisis ton objectif : Jet parfait, Exo PA / PM / PO ou Over. Pour un over, choisis la ligne et la valeur visée. **% Dommages aux sorts** est toujours proposé, même si l'objet ne l'a pas.
4. Les max sont lus dans la colonne Max. Si l'un d'eux est faux, corrige-le dans la petite case, puis appuie sur Entrée.
5. Passe la rune affichée en doré. L'assistant voit le changement, met à jour le puits, note le résultat et affiche la rune suivante.

- **⏸** met la lecture en pause, par exemple pendant que tu changes d'objet.
- Quand tu poses un nouvel objet, il est détecté et le puits repart à 0.

## Si la lecture se trompe

Fais une capture de la zone des stats, puis lance :

```
python fm_live.py --test capture.png
```

Tu verras le texte lu et les stats reconnues. Envoie-moi le résultat : j'ajusterai les réglages pour ton interface.

## Limites

- Si le reliquat n'est pas dans la zone encadrée, le puits n'est qu'une estimation. Le bas de la fenêtre te dit si le reliquat est bien lu.
- Les **poids des runes** viennent de Dofus 2 et peuvent différer légèrement dans Dofus 3. Tu peux les modifier dans `fm_core.py`, dans le tableau `STATS`.
- Ankama ne valide aucun outil tiers. Cet outil reste dans ce qui est toléré (pas d'interaction avec le jeu), mais il est utilisé à tes risques.

## Chances de réussite (formule calée sur DoFocus)

Sous la rune conseillée, l'assistant affiche les chances de **SC** (succès critique), **SN** (succès neutre) et **EC** (échec critique). La colonne **SC** du tableau donne aussi la chance de la meilleure rune sur chaque ligne.

La formule part de la vidéo « J'ai CRACKÉ le secret de la forgemagie DOFUS » (environ 225 000 clics analysés). Elle a ensuite été calée sur les pourcentages du simulateur dofocus.fr : sur 19 runes testées, l'écart est de 3 points au maximum. Ce n'est **pas** la formule officielle d'Ankama.

- La difficulté part de 5, puis :
  - **+45** si, *après* la rune, la ligne est à 80 % ou plus de son jet (entre Min et Max) ;
  - **+30, plus 4 par point de poids au-dessus du max** (over) ;
  - **+10,5 par cran au-delà de 14 ×** (valeur de la ligne / valeur de la rune) ;
  - **+60 × (qualité des autres lignes)¹²** : un objet presque parfait est beaucoup plus dur à FM, et un exo PA/PM/PO le rend « parfait » d'office ;
  - **−20** si l'objet est sous le niveau 170 (le niveau se règle en bas de la fenêtre).
- SC = (100 − difficulté) / 2, jamais sous 2 %. EC = difficulté / 2. SN = le reste.

Ce que l'assistant en tire :
- **Il monte d'abord les lignes qui restent sous 80 % de leur jet après la rune** : environ 45 % de SC, contre 25 % au-dessus.
- **Il choisit la qualité de rune avec le plus de SC**, puis celle qui a le moins d'EC.
