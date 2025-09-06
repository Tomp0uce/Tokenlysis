# Tokenlysis

Simple crypto analysis backend with a minimal front-end for testing.

## Running the API

```bash
uvicorn backend.app.main:app --reload
```

## Using the front-end

Open `frontend/index.html` in a browser once the API is running. It will fetch and
display the list of cryptocurrencies with their price and global score.

## Déploiement sur un NAS Synology avec Docker

1. Installez le paquet **Docker** depuis le Centre de paquets Synology.
2. Activez l'accès SSH dans **Panneau de configuration → Terminal & SNMP** et
   connectez‑vous à votre NAS.
3. Clonez ce dépôt :
   ```bash
   git clone https://github.com/<votre-utilisateur>/Tokenlysis.git
   cd Tokenlysis
   ```
4. Construisez l'image Docker :
   ```bash
   docker build -t tokenlysis .
   ```
   ou avec Docker Compose :
   ```bash
   docker compose build
   ```
5. Lancez le conteneur :
   ```bash
   docker run -d --name tokenlysis -p 8000:8000 tokenlysis
   ```
   ou via Docker Compose :
   ```bash
   docker compose up -d
   ```
6. Depuis un navigateur du réseau local, accédez à l'interface complète sur
   `http://<ip_du_nas>:8000` (la documentation de l'API est disponible sur
   `/docs`).

### Tâche planifiée DSM

Pour redémarrer automatiquement le service (par exemple au démarrage du NAS) :

1. Ouvrez **Panneau de configuration → Planificateur de tâches**.
2. Cliquez sur **Créer → Tâche planifiée → Script défini par l'utilisateur**.
3. Donnez un nom (par ex. "Tokenlysis") et choisissez l'utilisateur `root`.
4. Dans l'onglet **Planification**, sélectionnez "Au démarrage" ou la
   fréquence désirée.
5. Dans l'onglet **Paramètres de tâche**, indiquez le script :
   ```bash
   cd /chemin/vers/Tokenlysis
   docker compose up -d
   ```
6. Validez. Le conteneur sera lancé automatiquement selon la planification.

