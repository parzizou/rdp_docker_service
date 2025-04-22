# rdp_docker_service

Service local permettant une distribution et une gestion de dockers facilement sur ton réseau.

## Prérequis

- **python3** (testé avec 3.8+)
- **docker** (et accès au daemon Docker)
- **nvidia toolkit** et **CUDA** (si tu veux utiliser des images Docker avec GPU)
- Les scripts ont besoin d’être exécutables :  
  `chmod +x *.sh`

## Structure du repo

- `app.py` : Le serveur principal à lancer. C’est une API Flask qui gère les users, les containers, etc.
- `admin_dashboard.py` : L’interface d’admin pour tout gérer facilement (users, images, ports, etc.).
- `cleanup_inactive.sh` : Script pour nettoyer les containers inactifs.
- `script.sh` : Scripts pour lancer/arrêter différents services.
- `dockerfiles/` : Mets ici tous tes Dockerfile personnalisés.
- `users.txt` : Liste des users avec leurs hash de mot de passe (à éditer avant premier run).
- `admin_password.hash` : Hash du mot de passe admin.
- `power_users.txt` : Liste des utilisateurs avec des droits avancés.
- `blocked_users.txt` : Liste des users bloqués.
- `images.txt` : Liste des images Docker autorisées/disponibles.
- `port_map.txt` : Mapping des ports utilisés/attribués.
- `password_utils.sh` : Utilitaires shell pour la gestion des mots de passe.
- `cleanup.log` : Log des actions de nettoyage.

## Installation

1. Clone ce repo :
   ```bash
   git clone https://github.com/parzizou/rdp_docker_service.git
   cd rdp_docker_service
   ```
2. (Optionnel mais conseillé) Crée un venv Python :
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Installe les dépendances Python :
   ```bash
   pip install flask
   pip install bcypt
   ```
4. Prépare les fichiers de conf :
    - Mets les users dans `users.txt` avec leur hash de mot de passe temporaire
    - Vérifie les droits d’exécution sur les scripts :  
      `chmod +x *.sh`
    - Mets à jour `images.txt` avec les images que tu veux rendre dispo.

5. Lance le service principal :
   ```bash
   python3 app.py
   ```

6. (Optionnel) Lance l’admin dashboard :
   ```bash
   python3 admin_dashboard.py
   ```
## Utilisation

- Par défaut, le service tourne sur `localhost:5000` (modifie dans le code si besoin).
- Les users se connectent via l’interface web, changent leur mot de passe temporaire.
- Les containers sont créés automatiquement selon leur login, avec l’image choisie.
- L’admin peut voir tous les users/containers/images, débloquer ou bloquer des users, changer les mappings de ports, etc.

## Gestion des utilisateurs

- Ajoute les utilisateurs dans `users.txt` au format :  
  `username:motdepasse_hash`

- Les users bloqués vont dans `blocked_users.txt`.
- Les users "power" dans `power_users.txt` (accès à plus de ressources/options).

## Gestion des images Docker

- Mets les noms des images autorisées dans `images.txt` (une par ligne).

## Scripts utiles

- `cleanup_inactive.sh` : Nettoie les containers qui dorment trop longtemps.
- `script.sh` : Script principal utilisé dans le process (voir son contenu pour détails).
- `run.sh` / `run_admin.sh` : Pour lancer rapidement les services user/admin.

## Sécurité

- Les mots de passe sont stockés hashés, mais communique toujours les mdp initiaux en privé !
- Mets à jour les dépendances régulièrement.
- Utilise un firewall et limite l’accès au port 5000 si exposé au réseau.

## Astuces

- Tu veux ajouter un user ? Mets-le dans `users.txt` puis relance le service.
- Tu veux ajouter une image Docker ? Ajoute-la dans `images.txt` et place le Dockerfile si besoin.
- Tu veux voir les logs ? Check `cleanup.log`.

## Dépannage

- Un user ne peut pas se connecter ? Vérifie s’il est bloqué ou si le hash est correct.
- Problème avec Docker ? Teste une commande Docker à la main pour voir si tout marche.
- Un port déjà utilisé ? Modifie `port_map.txt` ou relance le mapping via l’admin.
