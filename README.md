# Tokenlysis

Simple crypto analysis backend with a minimal front-end for testing.

## Running the API

```bash
uvicorn backend.app.main:app --reload
```

## Using the front-end

Open `frontend/index.html` in a browser once the API is running. It will fetch and
display the list of cryptocurrencies with their price and global score.

## Installation sur un NAS Synology

1. Installez Python 3 via le Centre de paquets Synology (ou Docker si disponible).
2. Activez l'accès SSH dans **Panneau de configuration → Terminal & SNMP**.
3. Connectez‑vous au NAS en SSH puis clonez ce dépôt :
   ```bash
   git clone https://github.com/<votre-utilisateur>/Tokenlysis.git
   cd Tokenlysis
   ```
4. (Optionnel) Créez un environnement virtuel :
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
5. Installez les dépendances Python :
   ```bash
   pip install -r backend/requirements.txt
   ```
6. Lancez l'API :
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
   ```
7. Dans une seconde session, servez le front‑end statique :
   ```bash
   python3 -m http.server 8080 --directory frontend
   ```
8. Depuis un navigateur du réseau local, accédez à l'API sur `http://<ip_du_nas>:8000/docs`
   et à l'interface web sur `http://<ip_du_nas>:8080`.

