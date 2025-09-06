# Tokenlysis

Simple crypto analysis backend with a minimal front-end for testing.

## Running the API

```bash
uvicorn backend.app.main:app --reload
```

## Using the front-end

Open `frontend/index.html` in a browser once the API is running. It will fetch and
display the list of cryptocurrencies with their price and global score.

## Déploiement sur un NAS Synology avec Container Manager

1. Installez le paquet **Container Manager** depuis le Centre de paquets Synology.
2. (Facultatif) Activez l'accès SSH dans **Panneau de configuration → Terminal & SNMP** si vous souhaitez utiliser la ligne de commande.
3. Clonez ce dépôt ou copiez le fichier `docker-compose.yml` sur votre NAS :
   ```bash
   git clone https://github.com/<votre-utilisateur>/Tokenlysis.git
   cd Tokenlysis
   ```
4. Ouvrez **Container Manager → Projet → Créer → Importer** et sélectionnez le fichier `docker-compose.yml` du dépôt.
5. Dans le projet nouvellement créé, cliquez sur **Construire** puis **Démarrer** pour lancer le conteneur.
   Vous pouvez également exécuter la commande suivante via SSH :
   ```bash
   docker compose up -d
   ```
6. Depuis un navigateur du réseau local, accédez à `http://<ip_du_nas>:8000` (la documentation de l'API est disponible sur `/docs`).

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

