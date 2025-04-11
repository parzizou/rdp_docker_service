#!/bin/bash
# Variables constantes
CONTAINER_PREFIX="gui_user_"
USER_FILE="users.txt"
PORT_FILE="port_map.txt"
IMAGE_FILE="images.txt"
START_PORT=3390
MAX_PORT=3490
DATA_DIR="./user_data"
INACTIVE_TIMEOUT=3600
CLEANUP_SCRIPT="./cleanup_inactive.sh"

# Créer les répertoires et fichiers nécessaires
mkdir -p "$DATA_DIR"
mkdir -p data
touch "$USER_FILE" "$PORT_FILE"

# Fonction pour obtenir les informations de l'image depuis le fichier de configuration
get_image_info() {
    local image_name=$1
    local info_type=$2  # name, port, cpu, memory, extra, volumes, extra_ports
    local default_values=("$image_name" "3390" "1" "2g" "" "")
    local index=0
    
    # Définir l'index selon le type d'information demandé
    case "$info_type" in
        "name") index=1 ;;
        "port") index=2 ;;
        "cpu") index=3 ;;
        "memory") index=4 ;;
        "extra") index=5 ;;
        "volumes") index=6 ;;
        *) index=0 ;;  # Par défaut, renvoie l'ID de l'image
    esac
    
    # Pour les ports supplémentaires (traitement spécial)
    if [ "$info_type" = "extra_ports" ] && [ -f "$IMAGE_FILE" ]; then
        local image_line=$(grep "^$image_name:" "$IMAGE_FILE")
        if [ -n "$image_line" ]; then
            IFS=':' read -r -a image_parts <<< "$image_line"
            if [ ${#image_parts[@]} -gt 5 ] && [ -n "${image_parts[5]}" ]; then
                # Extraire les mappages de port de la forme -p XXXX:YYYY
                local extra_ports=$(echo "${image_parts[5]}" | grep -o '\-p [0-9]*:[0-9]*' | sed 's/-p //')
                echo "$extra_ports"
                return 0
            fi
        fi
        # Si aucun port supplémentaire n'est trouvé
        echo ""
        return 0
    fi
    
    # Essayer de lire depuis le fichier de configuration
    if [ -f "$IMAGE_FILE" ]; then
        local image_line=$(grep "^$image_name:" "$IMAGE_FILE")
        if [ -n "$image_line" ]; then
            IFS=':' read -r -a image_parts <<< "$image_line"
            if [ ${#image_parts[@]} -gt $index ]; then
                echo "${image_parts[$index]}"
                return 0
            fi
        fi
    fi
    
    # Fallback aux valeurs par défaut
    echo "${default_values[$index]}"
}

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
    local start_port=$1
    [ -z "$start_port" ] && start_port=$START_PORT
    local end_port=$2
    [ -z "$end_port" ] && end_port=$MAX_PORT
    
    port=$start_port
    while [ $port -le $end_port ]; do
        if ! ss -tuln | grep -q ":$port " && ! docker ps -a --format '{{.Ports}}' | grep -q ":$port->"; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
    done
    echo "Aucun port disponible entre $start_port et $end_port"
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

# Récupère l'image associée à un utilisateur
get_user_image() {
    grep "^$1:" "$USER_FILE" | cut -d':' -f3
}

# Enregistre ou met à jour l'image d'un utilisateur
set_user_image() {
    local username=$1
    local image=$2
    local hashed_password=$(get_user_password "$username")
    
    if [ -n "$hashed_password" ]; then
        # Supprime l'ancienne entrée
        sed -i "/^$username:/d" "$USER_FILE"
        # Ajoute la nouvelle entrée avec l'image
        echo "$username:$hashed_password:$image" >> "$USER_FILE"
    fi
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
    local container_image=$2
    local rdp_port=$(get_image_info "$container_image" "port")
    
    # Vérifie les connexions RDP actives
    connections=$(docker exec "$container_name" netstat -ant | grep ":$rdp_port" | grep "ESTABLISHED" | wc -l)
    
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

# Arrête un conteneur inactif
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
    local container_image=$2
    
    # Récupère les limites de ressources depuis le fichier de configuration
    local cpu_limit=$(get_image_info "$container_image" "cpu")
    local memory_limit=$(get_image_info "$container_image" "memory")
    
    echo "Application des limites de ressources pour $container_name (CPU: $cpu_limit, Mémoire: $memory_limit)"
    docker update --cpus="$cpu_limit" --memory="$memory_limit" --memory-swap="$memory_limit" "$container_name"
}

# Parse les volumes supplémentaires définis dans le fichier images.txt
parse_volumes() {
    local image_name=$1
    local volumes_str=$(get_image_info "$image_name" "volumes")
    local volumes_params=""
    
    if [ -n "$volumes_str" ]; then
        IFS=',' read -r -a volumes_array <<< "$volumes_str"
        for vol in "${volumes_array[@]}"; do
            volumes_params="$volumes_params -v $vol"
        done
    fi
    
    echo "$volumes_params"
}

# Parse les paramètres supplémentaires comme les mappages de port définis dans extra_params
parse_extra_ports() {
    local image_name=$1
    local extra_ports=$(get_image_info "$image_name" "extra_ports")
    local port_params=""
    
    if [ -n "$extra_ports" ]; then
        for port_mapping in $extra_ports; do
            host_port=$(echo $port_mapping | cut -d':' -f1)
            container_port=$(echo $port_mapping | cut -d':' -f2)
            
            # Vérifier si le port hôte est disponible
            if ! ss -tuln | grep -q ":$host_port "; then
                port_params="$port_params -p $host_port:$container_port"
            else
                # Si le port est occupé, essayer de trouver un port libre
                echo "⚠️ Port $host_port déjà utilisé, recherche d'une alternative..."
                local free_alt_port=$(find_free_port $((host_port+1)) $((host_port+100)))
                if [ $? -eq 0 ]; then
                    echo "🔄 Port alternatif trouvé: $free_alt_port:$container_port"
                    port_params="$port_params -p $free_alt_port:$container_port"
                else
                    echo "❌ Aucun port alternatif disponible pour $container_port"
                fi
            fi
        done
    fi
    
    echo "$port_params"
}

# Traite les autres paramètres supplémentaires (non ports, non volumes)
parse_other_extra_params() {
    local image_name=$1
    local extra_params=$(get_image_info "$image_name" "extra")
    local other_params=""
    
    if [ -n "$extra_params" ]; then
        # Filtrer pour enlever les mappages de ports (-p) qui sont traités séparément
        other_params=$(echo "$extra_params" | sed 's/-p [0-9]*:[0-9]* //g')
    fi
    
    echo "$other_params"
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
    connections=$(docker exec "$container" netstat -ant 2>/dev/null | grep -q ":3390" || grep -q ":3389" | grep "ESTABLISHED" | wc -l)
    
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
            
            # Arrêter le conteneur
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
    apply_resource_limits "$container_name" "$image_name"
    
    echo "Optimisation des ressources configurée"
}

# Appeler la vérification de dépendances au démarrage
check_dependencies

# Lecture des entrées utilisateur
read -p "Choix (1/2) : " choice
read -p "Nom d'utilisateur : " username
read -s -p "Mot de passe : " password
echo
read -p "Image : " image_name

# Si aucune image n'est spécifiée, utiliser la valeur par défaut
if [ -z "$image_name" ]; then
    image_name="xfce_gui_container"
fi

if [ "$choice" == "1" ]; then
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
    
    # Récupérer l'image associée à l'utilisateur
    stored_image=$(get_user_image "$username")
    if [ -n "$stored_image" ] && [ "$stored_image" != "$image_name" ]; then
        echo "⚠️ Changement d'environnement détecté : $stored_image -> $image_name"
        # Option: demander confirmation ici si nécessaire
        # Mise à jour de l'image associée à l'utilisateur
        set_user_image "$username" "$image_name"
    elif [ -z "$stored_image" ]; then
        # Si l'utilisateur n'a pas d'image associée, l'enregistrer
        set_user_image "$username" "$image_name"
    fi
    
    echo "✅ Connexion réussie."

elif [ "$choice" == "2" ]; then
    if user_exists "$username"; then
        echo "❌ Cet utilisateur existe déjà."
        exit 1
    fi
    
    # Chiffrer le mot de passe avant de le stocker
    hashed_password=$(encrypt_password "$password")
    echo "$username:$hashed_password:$image_name" >> "$USER_FILE"
    
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

# Récupération du port RDP spécifique à l'image
rdp_port=$(get_image_info "$image_name" "port")
[ -z "$rdp_port" ] && rdp_port="3390"  # Valeur par défaut si non spécifiée

# Récupération des ports et volumes supplémentaires
extra_volume_params=$(parse_volumes "$image_name")
extra_port_params=$(parse_extra_ports "$image_name")
other_params=$(parse_other_extra_params "$image_name")

if container_exists "$container_name"; then
    container_exists_flag=1
    # Récupérer l'image du conteneur existant
    existing_image=$(docker inspect --format='{{.Config.Image}}' "$container_name" 2>/dev/null)
    
    # Vérifier si l'image a changé
    if [ "$existing_image" != "$image_name" ]; then
        echo "🔄 Changement d'image détecté: $existing_image -> $image_name"
        echo "💥 Suppression du conteneur existant pour recréation avec la nouvelle image..."
        docker rm -f "$container_name" >/dev/null
        container_exists_flag=0
    else
        # Vérifier si le port assigné est toujours le même que celui utilisé par le conteneur
        current_port=$(docker port "$container_name" "$rdp_port/tcp" 2>/dev/null | cut -d':' -f2)
        
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
fi

# Obtenir le mot de passe utilisateur (pour accéder au conteneur)
user_password=$password

# Récupérer les paramètres spécifiques à l'image
cpu_limit=$(get_image_info "$image_name" "cpu")
memory_limit=$(get_image_info "$image_name" "memory")

# Démarrage du container avec port dynamique et volumes pour la persistance
if [ $container_exists_flag -eq 1 ]; then
    if container_running "$container_name"; then
        echo "📦 Le container est déjà en cours d'exécution"
    else
        # Vérifier si le conteneur est juste arrêté (et non supprimé)
        if docker ps -a --filter "name=$container_name" --filter "status=exited" --format "{{.Names}}" | grep -q "^$container_name$"; then
            echo "🔄 Redémarrage du conteneur existant..."
            docker start "$container_name" >/dev/null
            
            # Mettre à jour le mot de passe si nécessaire
            docker exec "$container_name" bash -c "echo '$username:$user_password' | chpasswd" 2>/dev/null
        else
            # Recréer le conteneur s'il n'existe pas ou a été supprimé
            echo "🔄 Recréation du conteneur..."
            
            # Créer le répertoire de données utilisateur s'il n'existe pas
            mkdir -p "$DATA_DIR/$username"
            mkdir -p "$DATA_DIR/${username}_config"
            
            docker run -dit \
                --name "$container_name" \
                -p "$user_port:$rdp_port" \
                $extra_port_params \
                -e "USERNAME=$username" \
                -e "PASSWORD=$user_password" \
                -e "SVELTE_PORT=5173" \
                -v "$DATA_DIR/$username:/home/$username" \
                -v "$DATA_DIR/${username}_config:/etc/skel" \
                $extra_volume_params \
                --restart unless-stopped \
                --cpus="$cpu_limit" \
                --memory="$memory_limit" \
                $other_params \
                "$image_name"
        fi
    fi
else
    echo "🚀 Création et démarrage du container '$container_name' sur le port $user_port avec l'image $image_name..."
    
    # Créer le répertoire de données utilisateur s'il n'existe pas
    mkdir -p "$DATA_DIR/$username"
    mkdir -p "$DATA_DIR/${username}_config"
    
    # Construire la commande docker run avec tous les paramètres
    docker run -dit \
        --name "$container_name" \
        -p "$user_port:$rdp_port" \
        $extra_port_params \
        -e "USERNAME=$username" \
        -e "PASSWORD=$user_password" \
        -e "SVELTE_PORT=5173" \
        -v "$DATA_DIR/$username:/home/$username" \
        -v "$DATA_DIR/${username}_config:/etc/skel" \
        $extra_volume_params \
        --restart unless-stopped \
        --cpus="$cpu_limit" \
        --memory="$memory_limit" \
        $other_params \
        "$image_name"
        
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
echo -e "\n TYPE DE BUREAU : $(get_image_info "$image_name" "name")"  # Affiche le nom complet de l'environnement

# Afficher les services supplémentaires si présents
if [ -n "$extra_port_params" ]; then
    echo -e "\n📱 Services supplémentaires disponibles :"
    for port_mapping in $(get_image_info "$image_name" "extra_ports"); do
        host_port=$(echo $port_mapping | cut -d':' -f1)
        container_port=$(echo $port_mapping | cut -d':' -f2)
        echo -e " • Service sur le port $container_port : $IP:$host_port"
        
        # Information spécifique pour Svelte
        if [ "$container_port" = "5173" ]; then
            echo -e "   📊 Application Svelte accessible sur : http://$IP:$host_port"
        fi
    done
fi