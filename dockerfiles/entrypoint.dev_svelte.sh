#!/bin/bash
set -e

# Récupération des variables d'environnement
USERNAME=${USERNAME:-xuser}
PASSWORD=${PASSWORD:-password}
SVELTE_PORT=${SVELTE_PORT:-5173}
RDP_PORT=3390  # Port fixé pour la compatibilité avec le reste du système

# Nettoyage des fichiers PID s'ils existent
PID_FILE="/var/run/xrdp/xrdp-sesman.pid"
if [ -f "$PID_FILE" ]; then
    echo "Removing existing xrdp-sesman.pid file..."
    rm -f "$PID_FILE"
fi

PID_FILE2="/var/run/xrdp/xrdp.pid"
if [ -f "$PID_FILE2" ]; then
    echo "Removing existing xrdp.pid file..."
    rm -f "$PID_FILE2"
fi

# Création/mise à jour de l'utilisateur
if id "$USERNAME" &>/dev/null; then
    echo "Utilisateur $USERNAME existe déjà, mise à jour du mot de passe"
    echo "$USERNAME:$PASSWORD" | chpasswd
else
    echo "Création de l'utilisateur $USERNAME"
    groupadd -r -g 1000 ${USERNAME} 2>/dev/null || true
    useradd -u 1000 -r -g ${USERNAME} -d /home/${USERNAME} -s /bin/bash -c "${USERNAME}" ${USERNAME} 2>/dev/null || true
    usermod -aG sudo ${USERNAME}
    usermod -aG video ${USERNAME}
    mkdir -p /home/${USERNAME}
    chown -R 1000:1000 /home/${USERNAME}
    echo ${USERNAME}':'${PASSWORD} | chpasswd
    echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
fi

# Copie de la configuration bash
cp /root/.bashrc /home/${USERNAME}/.bashrc

# Configuration de Bun
if [ -d "/root/.bun" ]; then
    mkdir -p /home/${USERNAME}/.bun
    cp -r /root/.bun/* /home/${USERNAME}/.bun/
    chmod 777 /root/.bun/bin/bun 2>/dev/null || true
    chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/.bun
fi

# Ajout de Bun au PATH
if ! grep -Fxq "export PATH=/home/${USERNAME}/.bun/bin:/opt/venv/bin:\$PATH" /home/${USERNAME}/.bashrc; then
    echo "export PATH=/home/${USERNAME}/.bun/bin:/opt/venv/bin:\$PATH" >> /home/${USERNAME}/.bashrc
fi

# Configuration de docker_shared
mkdir -p /home/${USERNAME}/docker_shared
if [ -d "/home/${USERNAME}/docker_shared" ]; then
    chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}/docker_shared
fi

# Création d'un projet Svelte de démonstration si le dossier partagé est vide
if [ -d "/home/${USERNAME}/docker_shared" ] && [ -z "$(ls -A /home/${USERNAME}/docker_shared)" ]; then
    echo "Initialisation d'un projet Svelte de démonstration..."
    su - ${USERNAME} -c "cd /home/${USERNAME}/docker_shared && git clone https://github.com/sveltejs/realworld.git"
    su - ${USERNAME} -c "cd /home/${USERNAME}/docker_shared/realworld && export PATH=/home/${USERNAME}/.bun/bin:\$PATH && bun install"
fi

# Démarrage du serveur Svelte dans un screen
echo "Démarrage de l'application Svelte en arrière-plan..."
su - ${USERNAME} -c "cd /home/${USERNAME}/docker_shared/realworld && screen -d -m -S SvelteApp bash -c 'export PATH=/home/${USERNAME}/.bun/bin:/opt/venv/bin:\$PATH && bun run dev --host'"

# Création du fichier de dernière activité
echo "$(date +%s)" > "/home/${USERNAME}/.last_activity"
chown ${USERNAME}:${USERNAME} "/home/${USERNAME}/.last_activity"

# Démarrage des services XRDP
echo "Démarrage des services XRDP..."
/usr/sbin/xrdp-sesman
exec /usr/sbin/xrdp --nodaemon