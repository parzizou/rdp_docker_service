# rdp_docker_service
Service local permettant une distribution et une gestion de dockers

Prérequis:

Installer: python3, nvidia toolkit, cuda, docker
Dans le dossier racine : admin_dashboard.txt, app.py, cleanup_inactive.sh, images.txt,port_map.txt, power_users.txt, script.sh, users.txt
Inscrire dans le fichier users.txt la totalité des utilisateurs avec le hash de leur mot de passe temporaire, puis leur communiquer discrètement.
Vérifier que les scripts sont executables ( chmod +x )

Utilisation:

Lancer sur l'Hote app.py (environement virtuel ou non) 
Communiquer a votre réseau l'adresse localhost:5000 (ou un dns si possible)
Les Utilisateurs se rendent sur l'adresse entrent leurs information de connexion et changent leur mot de passe.

