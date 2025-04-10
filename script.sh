#!/bin/bash
IMAGE_NAME="xfce_gui_container"
CONTAINER_PREFIX="gui_user_"
USER_FILE="users.txt"
PORT_FILE="port_map.txt"
START_PORT=3390
MAX_PORT=3490
DATA_DIR="./user_data"  # Répertoire pour les données persistantes
INACTIVE_TIMEOUT=3600   # Temps en secondes avant de considérer un conteneur comme inactif (1 heure)
CPU_LIMIT="1"           # Limite CPU (nombre de cœurs)
MEMORY_LIMIT="2g"       # Limite de mémoire
CLEANUP_SCRIPT="./cleanup_inactive.sh"

# Créer les répertoires et fichiers nécessaires
mkdir -p "$DATA_DIR"
mkdir -p data
touch "$USER_FILE" "$PORT_FILE"

# Fonction pour chiffrer un mot de passe avec bcrypt
encrypt_password() {
    local password=$1
    # Utilise python3 pour la compatibilité universelle
    echo -n "$password" | python3 -c 'import bcrypt, sys; print(bcrypt.hashpw(sys.stdin.read().encode(), bcrypt.gensalt()).decode())'
}

# Fonction pour vérifier un mot de passe
verify_password() {
    local password=$1
    local hashed_password=$2
    python3 -c "import bcrypt, sys; sys.exit(0 if bcrypt.checkpw('$password'.encode(), '$hashed_password'.encode()) else 1)" && echo "true" || echo "false"
}

# Vérifie si le paquet bcrypt est installé pour Python, sinon l'installe
check_bcrypt() {
    if ! python3 -c "import bcrypt" 2>/dev/null; then
        echo "Installation du module bcrypt pour Python..."
        pip3 install bcrypt || sudo pip3 install bcrypt
    fi
}

# Vérifie les dépendances nécessaires
check_dependencies() {
    # Vérifie si Python est installé
    if ! command -v python3 &> /dev/null; then
        echo "Python3 n'est pas installé. Installation en cours..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip
    fi
    
    # Vérifie le module bcrypt
    check_bcrypt
}

# Cherche un port libre sur la machine et vérifie aussi qu'il n'est pas déjà utilisé par Docker
find_free_port() {
    port=$START_PORT
    while [ $port -le $MAX_PORT ]; do
        if ! ss -tuln | grep -q ":$port " && ! docker ps -a --format '{{.Ports}}' | grep -q ":$port->"; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
    done
    echo "Aucun port disponible entre $START_PORT et $MAX_PORT"
    return 1
}

# Vérifie si un utilisateur existe
user_exists() {
    grep -q "^$1:" "$USER_FILE"
}

# Récupère le port associé à un utilisateur
get_user_port() {
    grep "^$1:" "$PORT_FILE" | cut -d':' -f2
}

# Enregistre ou met à jour le port d'un utilisateur
set_user_port() {
    # Supprime l'ancienne entrée si elle existe
    sed -i "/^$1:/d" "$PORT_FILE"
    # Ajoute la nouvelle entrée
    echo "$1:$2" >> "$PORT_FILE"
}

# Récupère le mot de passe d'un utilisateur
get_user_password() {
    grep "^$1:" "$USER_FILE" | cut -d':' -f2
}

# Vérifie si un conteneur existe et est en cours d'exécution
container_running() {
    docker ps --format '{{.Names}}' | grep -q "^$1$"
}

# Vérifie si un conteneur existe
container_exists() {
    docker ps -a --format '{{.Names}}' | grep -q "^$1$"
}

# Vérifie l'activité du conteneur via les connexions RDP
check_container_activity() {
    local container_name=$1
    # Vérifie les connexions RDP actives
    connections=$(docker exec "$container_name" netstat -ant | grep ":3390" | grep "ESTABLISHED" | wc -l)
    
    if [ "$connections" -gt 0 ]; then
        return 0  # Connexions actives
    else
        # Vérifie depuis quand le conteneur n'a pas eu de connexion
        last_activity=$(docker inspect --format='{{.State.StartedAt}}' "$container_name")
        last_timestamp=$(date -d "$last_activity" +%s)
        current_timestamp=$(date +%s)
        inactive_time=$((current_timestamp - last_timestamp))
        
        if [ "$inactive_time" -gt "$INACTIVE_TIMEOUT" ]; then
            return 1  # Inactif depuis trop longtemps
        else
            return 0  # Pas encore assez inactif pour agir
        fi
    fi
}

# Arrête un conteneur inactif (au lieu de le suspendre)
stop_inactive_container() {
    local container_name=$1
    echo "Arrêt du conteneur inactif: $container_name"
    docker stop "$container_name"
    
    # Enregistrer l'état pour pouvoir le reprendre plus tard
    echo "$container_name" >> "suspended_containers.txt"
}

# Ajoute des limites de ressources aux conteneurs
apply_resource_limits() {
    local container_name=$1
    
    echo "Application des limites de ressources pour $container_name"
    docker update --cpus="$CPU_LIMIT" --memory="$MEMORY_LIMIT" --memory-swap="$MEMORY_LIMIT" "$container_name"
}

# Création du script de nettoyage périodique
create_cleanup_script() {
    cat > "$CLEANUP_SCRIPT" << 'EOL'
#!/bin/bash
CONTAINER_PREFIX="gui_user_"
INACTIVE_TIMEOUT=3600  # 1 heure
LOG_FILE="cleanup.log"
SUSPENDED_FILE="suspended_containers.txt"
DATA_DIR="./user_data"

echo "$(date) - Démarrage du nettoyage des conteneurs inactifs" | tee -a "$LOG_FILE"

# Parcourir tous les conteneurs actifs
for container in $(docker ps --filter "name=$CONTAINER_PREFIX" --format "{{.Names}}"); do
    username=${container#${CONTAINER_PREFIX}}
    
    # Vérifier l'activité RDP
    connections=$(docker exec "$container" netstat -ant 2>/dev/null | grep ":3390" | grep "ESTABLISHED" | wc -l)
    
    if [ "$connections" -eq 0 ]; then
        # Créer un fichier de timestamp pour la dernière activité si nécessaire
        activity_file="$DATA_DIR/$username/.last_activity"
        
        # Si fichier d'activité n'existe pas, le créer avec le timestamp actuel
        if ! docker exec "$container" test -f "/home/$username/.last_activity" 2>/dev/null; then
            docker exec "$container" bash -c "echo $(date +%s) > /home/$username/.last_activity" 2>/dev/null
            continue  # Passer à l'itération suivante car nous venons de créer le fichier
        fi
        
        # Récupérer le timestamp de dernière activité
        last_timestamp=$(docker exec "$container" cat "/home/$username/.last_activity" 2>/dev/null)
        current_timestamp=$(date +%s)
        
        # Si la récupération a échoué, utiliser la date de démarrage du conteneur
        if [ -z "$last_timestamp" ] || ! [[ "$last_timestamp" =~ ^[0-9]+$ ]]; then
            last_activity=$(docker inspect --format='{{.State.StartedAt}}' "$container")
            last_timestamp=$(date -d "$last_activity" +%s)
        fi
        
        inactive_time=$((current_timestamp - last_timestamp))
        
        if [ "$inactive_time" -gt "$INACTIVE_TIMEOUT" ]; then
            echo "Conteneur $container inactif depuis $(($inactive_time / 60)) minutes, arrêt..." | tee -a "$LOG_FILE"
            
            # Arrêter le conteneur (au lieu de le mettre en pause)
            docker stop "$container" >> "$LOG_FILE" 2>&1
            
            # Enregistrer le conteneur comme suspendu
            grep -q "^$container$" "$SUSPENDED_FILE" || echo "$container" >> "$SUSPENDED_FILE"
        else
            echo "Conteneur $container inactif depuis $(($inactive_time / 60)) minutes, en attente..." | tee -a "$LOG_FILE"
        fi
    else
        # Mettre à jour le timestamp de dernière activité
        docker exec "$container" bash -c "echo $(date +%s) > /home/$username/.last_activity" 2>/dev/null
        echo "Conteneur $container actif avec $connections connexion(s)" | tee -a "$LOG_FILE"
    fi
done

echo "$(date) - Fin du nettoyage" | tee -a "$LOG_FILE"
EOL

    chmod +x "$CLEANUP_SCRIPT"
    
    # Vérifier si la tâche cron existe déjà
    if ! (crontab -l 2>/dev/null | grep -q "$CLEANUP_SCRIPT"); then
    # Ajouter la tâche cron pour exécuter le script toutes les heures
    (crontab -l 2>/dev/null || echo "") | { cat; echo "0 * * * * $PWD/$CLEANUP_SCRIPT >> $PWD/cleanup.log 2>&1"; } | crontab -
    echo "Tâche cron ajoutée pour le nettoyage automatique"
    fi
}

# Initialiser les fonctionnalités d'optimisation
initialize_optimization() {
    # Créer le script de nettoyage
    create_cleanup_script
    
    # Appliquer les limites de ressources au conteneur actuel
    apply_resource_limits "$container_name"
    
    echo "Optimisation des ressources configurée"
}

# Appeler la vérification de dépendances au démarrage
check_dependencies

read -p "Choix (1/2) : " choice

if [ "$choice" == "1" ]; then
    read -p "Nom d'utilisateur : " username
    read -s -p "Mot de passe : " password
    echo
    
    if ! user_exists "$username"; then
        echo "❌ Utilisateur inconnu."
        exit 1
    fi
    
    stored_hash=$(get_user_password "$username")
    is_valid=$(verify_password "$password" "$stored_hash")
    
    if [ "$is_valid" != "true" ]; then
        echo "❌ Mot de passe incorrect."
        exit 1
    fi
    
    echo "✅ Connexion réussie."

elif [ "$choice" == "2" ]; then
    read -p "Choisir un nom d'utilisateur : " username
    
    if user_exists "$username"; then
        echo "❌ Cet utilisateur existe déjà."
        exit 1
    fi
    
    read -s -p "Choisir un mot de passe : " password
    echo
    
    # Chiffrer le mot de passe avant de le stocker
    hashed_password=$(encrypt_password "$password")
    echo "$username:$hashed_password" >> "$USER_FILE"
    
    # Trouver un port libre et l'enregistrer
    free_port=$(find_free_port)
    if [ $? -ne 0 ]; then
        echo "❌ $free_port"
        exit 1
    fi
    
    set_user_port "$username" "$free_port"
    echo "✅ Compte '$username' créé avec succès (port $free_port)"
else
    echo "❌ Choix invalide"
    exit 1
fi

# Container associé à l'utilisateur
container_name="${CONTAINER_PREFIX}${username}"

# Vérifier si le port est toujours disponible, sinon en attribuer un nouveau
user_port=$(get_user_port "$username")
container_exists_flag=0

if container_exists "$container_name"; then
    container_exists_flag=1
    # Vérifier si le port assigné est toujours le même que celui utilisé par le conteneur
    current_port=$(docker port "$container_name" 3390/tcp 2>/dev/null | cut -d':' -f2)
    
    if [ -z "$current_port" ] || [ "$current_port" != "$user_port" ]; then
        # Le port a changé ou le conteneur n'est pas en marche
        if ! ss -tuln | grep -q ":$user_port "; then
            # Le port est libre, on peut l'utiliser
            echo "📝 Mise à jour du port pour le conteneur existant..."
        else
            # Le port n'est plus disponible, il faut en trouver un nouveau
            echo "⚠️ Le port assigné n'est plus disponible, recherche d'un nouveau port..."
            free_port=$(find_free_port)
            if [ $? -ne 0 ]; then
                echo "❌ $free_port"
                exit 1
            fi
            user_port=$free_port
            set_user_port "$username" "$user_port"
            echo "📝 Nouveau port assigné: $user_port"
        fi
    fi
fi

# Obtenir le mot de passe utilisateur (pour accéder au conteneur)
user_password=$password

# Démarrage du container avec port dynamique et volumes pour la persistance
if [ $container_exists_flag -eq 1 ]; then
    if container_running "$container_name"; then
        echo "📦 Le container est déjà en cours d'exécution"
    else
        # Vérifier si le conteneur est juste arrêté (et non supprimé)
        if docker ps -a --filter "name=$container_name" --filter "status=exited" --format "{{.Names}}" | grep -q "^$container_name$"; then
            # Arrêter et supprimer le conteneur existant pour le recréer
            echo "🔄 Recréation du conteneur avec le port correct..."
            docker rm -f "$container_name" >/dev/null
            
            # Créer le répertoire de données utilisateur s'il n'existe pas
            mkdir -p "$DATA_DIR/$username"
            
            docker run -dit \
                --name "$container_name" \
                -p "$user_port:3390" \
                -e "USERNAME=$username" \
                -e "PASSWORD=$user_password" \
                -v "$DATA_DIR/$username:/home/$username" \
                -v "$DATA_DIR/${username}_config:/etc/skel" \
                --restart unless-stopped \
                "$IMAGE_NAME"
            
            # Mettre à jour le port si nécessaire
            current_port=$(docker port "$container_name" 3390/tcp 2>/dev/null | cut -d':' -f2)
            if [ "$current_port" != "$user_port" ]; then
                echo "🔄 Recréation du conteneur avec le nouveau port..."
                docker rm -f "$container_name" >/dev/null
                
                docker run -dit \
                    --name "$container_name" \
                    -p "$user_port:3390" \
                    -e "USERNAME=$username" \
                    -e "PASSWORD=$user_password" \
                    -v "$DATA_DIR/$username:/home/$username" \
                    -v "$DATA_DIR/${username}_config:/etc/skel" \
                    --restart unless-stopped \
                    "$IMAGE_NAME"
            fi
        else
            # Arrêter et supprimer le conteneur existant pour le recréer avec le bon port
            echo "🔄 Recréation du conteneur avec le port correct..."
            docker rm -f "$container_name" >/dev/null
            
            # Créer le répertoire de données utilisateur s'il n'existe pas
            mkdir -p "$DATA_DIR/$username"
            
            docker run -dit \
                --name "$container_name" \
                -p "$user_port:3390" \
                -e "USERNAME=$username" \
                -e "PASSWORD=$user_password" \
                -v "$DATA_DIR/$username:/home/$username" \
                -v "$DATA_DIR/${username}_config:/etc/skel" \
                --restart unless-stopped \
                "$IMAGE_NAME"
        fi
    fi
else
    echo "🚀 Création et démarrage du container '$container_name' sur le port $user_port..."
    
    # Créer le répertoire de données utilisateur s'il n'existe pas
    mkdir -p "$DATA_DIR/$username"
    mkdir -p "$DATA_DIR/${username}_config"
    
    docker run -dit \
        --name "$container_name" \
        -p "$user_port:3390" \
        -e "USERNAME=$username" \
        -e "PASSWORD=$user_password" \
        -v "$DATA_DIR/$username:/home/$username" \
        -v "$DATA_DIR/${username}_config:/etc/skel" \
        --restart unless-stopped \
        "$IMAGE_NAME"
        
    # Initialiser le fichier d'activité
    sleep 2  # Attendre un peu que le conteneur démarre
    docker exec "$container_name" bash -c "echo $(date +%s) > /home/$username/.last_activity" 2>/dev/null
fi

# Initialiser l'optimisation des ressources
initialize_optimization

# Affiche les infos de connexion
IP=$(hostname -I | awk '{print $1}')
echo -e "\n🖥️  Connecte-toi avec Remmina (RDP) sur : $IP:$user_port"
echo -e "\n USER : $username"
echo -e "\n MOT DE PASSE : $user_password"
