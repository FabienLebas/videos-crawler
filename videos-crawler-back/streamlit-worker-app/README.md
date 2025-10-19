# Streamlit Worker App

## Description
Ce projet est une application Streamlit qui permet aux utilisateurs de soumettre des tâches, lesquelles sont ensuite exécutées par un worker persistant. L'application gère la soumission des tâches et communique avec le worker pour le traitement en arrière-plan.

## Structure du projet
- `src/streamlit_app.py`: Application Streamlit pour la soumission des tâches.
- `src/worker.py`: Worker persistant qui exécute les tâches soumises.
- `src/types/index.ts`: Types TypeScript pour les données de tâches et les réponses du worker.
- `requirements.txt`: Dépendances Python nécessaires.
- `package.json`: Configuration npm pour les dépendances JavaScript.
- `tsconfig.json`: Configuration TypeScript pour le projet.
- `README.md`: Documentation du projet.

## Installation
Pour installer les dépendances Python, exécutez la commande suivante :

```
pip install -r requirements.txt
```

Pour installer les dépendances JavaScript, exécutez :

```
npm install
```

## Lancer l'application
Pour démarrer l'application Streamlit, utilisez la commande suivante :

```
streamlit run src/streamlit_app.py
```

## Lancer le worker
Pour exécuter le worker de manière persistante, utilisez la commande suivante dans le terminal :

```
caffeinate python src/worker.py
```

## Gestion de version
N'oubliez pas de créer une branche Git pour vos modifications avec la commande :

```
git checkout -b feature/dissociateListingAndTranscription
```