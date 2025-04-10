#!/bin/bash

# Récupérer les variables d'environnement passées par docker run
USERNAME=${USERNAME:-xuser}
PASSWORD=${PASSWORD:-password}

# Créer ou mettre à jour l'utilisateur
if id "$USERNAME" &>/dev/null; then
    echo "Utilisateur $USERNAME existe déjà, mise à jour du mot de passe"
    echo "$USERNAME:$PASSWORD" | chpasswd
else
    echo "Création de l'utilisateur $USERNAME"
    useradd -m -s /bin/bash "$USERNAME"
    echo "$USERNAME:$PASSWORD" | chpasswd
    usermod -aG sudo "$USERNAME"
    
    # Copie des fichiers skel si nécessaire (monté comme volume)
    if [ -d "/etc/skel" ] && [ "$(ls -A /etc/skel)" ]; then
        echo "Copie des fichiers skel vers le répertoire home"
        cp -r /etc/skel/. "/home/$USERNAME/"
    fi
fi

# S'assurer que les bonnes permissions sont appliquées au répertoire home
# Important car il est monté en volume depuis l'hôte
chown -R "$USERNAME:$USERNAME" "/home/$USERNAME"

# Configurer XRDP
cat > /etc/xrdp/xrdp.ini << EOF
[Globals]
ini_version=1
port=3390
max_bpp=24
xserverbpp=24
crypt_level=low
security_layer=rdp
fork=true

[Xorg]
name=Xorg
lib=libxup.so
username=ask
password=ask
ip=127.0.0.1
port=-1
code=20
EOF

# Configuration de startwm.sh simplifiée
cat > /etc/xrdp/startwm.sh << EOF
#!/bin/sh
startxfce4
EOF
chmod +x /etc/xrdp/startwm.sh

# Créer un fichier de dernière activité comme le fait le script.sh
echo "$(date +%s)" > "/home/$USERNAME/.last_activity"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.last_activity"

# Démarrer les services
mkdir -p /var/run/dbus
dbus-daemon --system
service dbus start
/usr/sbin/xrdp-sesman
exec /usr/sbin/xrdp --nodaemon
