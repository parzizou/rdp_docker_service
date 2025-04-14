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
    local info_type=$2  # name, port, cpu, memory, extra, volumes, extra_ports, gpu
    local default_values=("$image_name" "3390" "1" "2g" "" "" "" "true")
    local index=0
    
    # Définir l'index selon le type d'information demandé
    case "$info_type" in
        "name") index=1 ;;
        "port") index=2 ;;
        "cpu") index=3 ;;
        "memory") index=4 ;;
        "extra") index=5 ;;
        "volumes") index=6 ;;
        "gpu") index=7 ;;
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
    
    # Vérifier que bcrypt est installé
    if ! python3 -c 'import bcrypt' 2>/dev/null; then
        echo "Installation du module bcrypt pour Python..."
        if ! pip3 install bcrypt 2>/dev/null && ! sudo pip3 install bcrypt 2>/dev/null; then
            echo "Erreur: Impossible d'installer bcrypt. Utilisation d'une méthode alternative."
            # Méthode alternative: utiliser un hash simple (moins sécurisé mais fonctionnel)
            echo -n "$password" | md5sum | awk '{print $1}'
            return
        fi
    fi
    
    echo -n "$password" | python3 -c 'import bcrypt, sys; print(bcrypt.hashpw(sys.stdin.read().encode(), bcrypt.gensalt()).decode())'
}

# Fonction pour vérifier un mot de passe
verify_password() {
    local password=$1
    local hashed_password=$2
    
    # Vérifier si le hash ressemble à un hash bcrypt ou à un hash MD5 (méthode alternative)
    if [[ "$hashed_password" =~ ^\$2[ayb]\$ ]]; then
        # C'est un hash bcrypt
        python3 -c "import bcrypt, sys; sys.exit(0 if bcrypt.checkpw('$password'.encode(), '$hashed_password'.encode()) else 1)" && echo "true" || echo "false"
    else
        # C'est probablement un hash MD5 (méthode alternative)
        local password_hash=$(echo -n "$password" | md5sum | awk '{print $1}')
        if [ "$password_hash" = "$hashed_password" ]; then
            echo "true"
        else
            echo "false"
        fi
    fi
}

# Vérifie si le paquet bcrypt est installé pour Python, sinon l'installe
check_bcrypt() {
    if ! python3 -c "import bcrypt" 2>/dev/null; then
        echo "Installation du module bcrypt pour Python..."
        pip3 install bcrypt 2>/dev/null || sudo pip3 install bcrypt 2>/dev/null || echo "Avertissement: Impossible d'installer bcrypt. La gestion des mots de passe sera moins sécurisée."
    fi
}

# Vérifie les dépendances nécessaires
check_dependencies() {
    # Vérifie si Python est installé
    if ! command -v python3 &> /dev/null; then
        echo "Python3 n'est pas installé. Installation en cours..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip
        if [ $? -ne 0 ]; then
            echo "Erreur: Impossible d'installer Python3. Veuillez l'installer manuellement."
            exit 1
        fi
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

# Vérifie si un port est disponible (pour les nouveaux ports uniquement)
port_is_available() {
    local port=$1
    ! ss -tuln | grep -q ":$port " && ! docker ps -a --format '{{.Ports}}' | grep -q ":$port->"
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
    
    # Vérifie les connexions RDP actives (corrigé pour supporter les ports 3389 et 3390)
    connections=$(docker exec "$container_name" netstat -ant 2>/dev/null | grep -E ":(3389|$rdp_port)" | grep "ESTABLISHED" | wc -l)
    
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
            
            # On force l'utilisation du port spécifié
            port_params="$port_params -p $host_port:$container_port"
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

# Fonction pour vérifier quels périphériques NVIDIA sont disponibles
check_nvidia_devices() {
    local devices=""
    
    # Vérification de la présence des périphériques NVIDIA standard
    if [ -e "/dev/nvidia0" ]; then
        devices="$devices --device /dev/nvidia0:/dev/nvidia0"
    fi
    
    if [ -e "/dev/nvidiactl" ]; then
        devices="$devices --device /dev/nvidiactl:/dev/nvidiactl"
    fi
    
    if [ -e "/dev/nvidia-uvm" ]; then
        devices="$devices --device /dev/nvidia-uvm:/dev/nvidia-uvm"
    fi
    
    # Vérification des périphériques supplémentaires (nvidia1, nvidia2, etc.)
    for i in {1..9}; do
        if [ -e "/dev/nvidia$i" ]; then
            devices="$devices --device /dev/nvidia$i:/dev/nvidia$i"
        fi
    done
    
    echo "$devices"
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
    connections=$(docker exec "$container" netstat -ant 2>/dev/null | grep -E ":(3389|3390)" | grep "ESTABLISHED" | wc -l)
    
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
        fi
    else
        # Mettre à jour le timestamp de dernière activité
        docker exec "$container" bash -c "echo $(date +%s) > /home/$username/.last_activity" 2>/dev/null
    fi
done

echo "$(date) - Fin du nettoyage" | tee -a "$LOG_FILE"
EOL

    chmod +x "$CLEANUP_SCRIPT"
    
    # Vérifier si la tâche cron existe déjà
    if ! (crontab -l 2>/dev/null | grep -q "$CLEANUP_SCRIPT"); then
    # Ajouter la tâche cron pour exécuter le script toutes les heures
    (crontab -l 2>/dev/null || echo "") | { cat; echo "0 * * * * $PWD/$CLEANUP_SCRIPT >> $PWD/cleanup.log 2>&1"; } | crontab -
    fi
}


# Créer un script de test GPU à l'intérieur du conteneur
create_gpu_test_script() {
    local container_name=$1
    local username=$2
    
    # Chemin du script à l'intérieur du conteneur
    local script_path="/home/$username/test_gpu.sh"
    
    # Contenu du script
    docker exec "$container_name" bash -c "cat > $script_path << 'EOF'
#!/bin/bash
echo \"==== Test GPU avec CuPy ====\"
echo \"Date: \$(date)\"
echo \"Utilisateur: \$(whoami)\"
echo \"\" 

# Vérifier si pip3 est disponible, sinon essayer de l'installer
if ! command -v pip3 &> /dev/null; then
    echo \"pip3 n'est pas installé, tentative d'installation...\"
    
    # Détecter le gestionnaire de paquets
    if command -v apt-get &> /dev/null; then
        echo \"Utilisation d'apt-get pour installer pip3...\"
        apt-get update && apt-get install -y python3-pip
    elif command -v apk &> /dev/null; then
        echo \"Utilisation d'apk (Alpine) pour installer pip3...\"
        apk add --no-cache python3 py3-pip
    elif command -v yum &> /dev/null; then
        echo \"Utilisation de yum pour installer pip3...\"
        yum install -y python3-pip
    elif command -v dnf &> /dev/null; then
        echo \"Utilisation de dnf pour installer pip3...\"
        dnf install -y python3-pip
    else
        echo \"❌ Je n'ai pas pu détecter le gestionnaire de paquets. Installation manuelle requise.\"
        echo \"Commandes possibles selon ton système:\"
        echo \"- Debian/Ubuntu: apt-get update && apt-get install -y python3-pip\"
        echo \"- Alpine: apk add --no-cache python3 py3-pip\"
        echo \"- CentOS/RHEL: yum install -y python3-pip\"
        echo \"- Fedora: dnf install -y python3-pip\"
    fi
fi

# Vérifier à nouveau si pip3 est disponible
if ! command -v pip3 &> /dev/null; then
    echo \"❌ pip3 n'a pas pu être installé. Utilisation de nvidia-smi seulement.\"
    
    # On va quand même tester nvidia-smi
    echo \"Test de nvidia-smi (infos basiques du GPU)\"
    nvidia-smi
    
    echo \"\"
    echo \"==== Test terminé (limité) ====\"
    exit 1
fi

# À partir d'ici, on a pip3 disponible
echo \"1. Test de nvidia-smi (infos basiques du GPU)\"
nvidia-smi

if [ \$? -ne 0 ]; then
  echo \"❌ PROBLÈME: nvidia-smi ne fonctionne pas. Le GPU n'est probablement pas accessible.\"
  exit 1
fi

echo \"\"
echo \"2. Test d'allocation mémoire GPU avec CuPy\"
echo \"Je vais lancer un processus qui va occuper le GPU en continu...\"

# On va créer un petit script Python qui va juste allouer de la mémoire GPU
cat > /tmp/gpu_alloc.py << 'PYEOF'
import os
import time
import sys

# Vérifier si cupy est installé, sinon l'installer
try:
    import cupy
except ImportError:
    print(\"CuPy n'est pas installé, tentative d'installation...\")
    os.system(f\"{sys.executable} -m pip install cupy-cuda11x\")
    print(\"Installation terminée, essayons à nouveau...\")

# Essaie d'allouer de la mémoire GPU
print(\"Test d'allocation GPU...\")

try:
    # Méthode 1: Essayer avec CuPy
    print(\"Essai avec CuPy...\")
    import cupy as cp
    x = cp.zeros((1000, 1000))
    print(\"✅ CuPy fonctionne! Mémoire GPU allouée.\")
    
    # Boucle continue pour occuper le GPU
    print(\"Maintenant je vais faire une boucle pour occuper le GPU...\")
    print(\"Ctrl+C pour arrêter\")
    try:
        i = 0
        while True:
            # Faire des opérations sur le GPU
            a = cp.random.random((2000, 2000))
            b = cp.random.random((2000, 2000))
            c = cp.matmul(a, b)  # Multiplication matricielle (lourde pour le GPU)
            
            # Forcer la synchronisation pour s'assurer que le GPU travaille
            c.sum()
            
            i += 1
            if i % 10 == 0:
                print(f\"Itération {i} - GPU en activité...\")
                
            # Petite pause pour ne pas saturer le CPU
            time.sleep(0.1)
    except KeyboardInterrupt:
        print(\"\\nTest arrêté manuellement.\")
except ImportError:
    try:
        # Méthode 2: Essayer avec PyTorch (souvent préinstallé)
        print(\"CuPy n'a pas pu être installé. Essai avec PyTorch...\")
        
        # Tenter d'installer PyTorch si pas déjà fait
        try:
            import torch
        except ImportError:
            print(\"PyTorch n'est pas installé, tentative d'installation...\")
            os.system(f\"{sys.executable} -m pip install torch\")
            
            try:
                import torch
            except ImportError:
                print(\"❌ Impossible d'installer PyTorch\")
                sys.exit(1)
        
        if torch.cuda.is_available():
            x = torch.zeros(1000, 1000, device='cuda')
            print(\"✅ PyTorch fonctionne! Mémoire GPU allouée.\")
            
            # Boucle continue pour occuper le GPU
            print(\"Maintenant je vais faire une boucle pour occuper le GPU...\")
            print(\"Ctrl+C pour arrêter\")
            try:
                i = 0
                while True:
                    # Faire des opérations sur le GPU
                    a = torch.randn(2000, 2000, device='cuda')
                    b = torch.randn(2000, 2000, device='cuda')
                    c = torch.matmul(a, b)  # Multiplication matricielle
                    
                    # Forcer la synchronisation
                    c.sum().item()
                    
                    i += 1
                    if i % 10 == 0:
                        print(f\"Itération {i} - GPU en activité...\")
                    
                    # Petite pause
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print(\"\\nTest arrêté manuellement.\")
        else:
            print(\"❌ PyTorch est installé mais ne détecte pas de GPU.\")
    except Exception as e:
        print(f\"❌ Erreur lors du test GPU: {e}\")
PYEOF

# Essayer d'exécuter le script pour tester le GPU
echo \"Lancement du test d'allocation mémoire GPU...\"
python3 /tmp/gpu_alloc.py

echo \"\"
echo \"Si le test ci-dessus ne marche pas, essaie cette commande:\"
echo \"nvidia-smi -l 1\"
echo \"Ctrl+C pour arrêter\"
echo \"\"
echo \"Test GPU terminé.\"
EOF"
    
    # Rendre le script exécutable
    docker exec "$container_name" bash -c "chmod +x $script_path && chown $username:$username $script_path"
}

# Fonction pour lancer un conteneur avec ou sans GPU
run_container() {
    local container_name=$1
    local username=$2
    local user_password=$3
    local image_name=$4
    local user_port=$5
    local rdp_port=$6
    local use_gpu=$7  # Nouveau paramètre pour spécifier si on utilise le GPU
    
    # Vérifier si le conteneur existe déjà et le supprimer si c'est le cas
    if container_exists "$container_name"; then
        echo "Le conteneur ${container_name} existe déjà, suppression en cours..."
        docker stop ${container_name} >/dev/null 2>&1 || true
        docker rm ${container_name} >/dev/null 2>&1 || true
        
        # Petite pause pour s'assurer que le système a libéré le port
        sleep 1
    fi
    
    # Récupérer les paramètres supplémentaires
    local extra_port_params=$(parse_extra_ports "$image_name")
    local extra_volume_params=$(parse_volumes "$image_name")
    local other_params=$(parse_other_extra_params "$image_name")
    local cpu_limit=$(get_image_info "$image_name" "cpu")
    local memory_limit=$(get_image_info "$image_name" "memory")
    
    # Créer le répertoire de données utilisateur s'il n'existe pas
    mkdir -p "$DATA_DIR/$username"
    mkdir -p "$DATA_DIR/${username}_config"
    
    # Message différent selon si on utilise le GPU ou non
    if [ "$use_gpu" = "true" ]; then
        echo "Lancement d'un nouveau conteneur ${container_name} avec GPU..."
    else
        echo "Lancement d'un nouveau conteneur ${container_name} sans GPU..."
    fi
    
    # Construire la commande docker différemment selon si on utilise le GPU ou non
    local gpu_params=""
    if [ "$use_gpu" = "true" ]; then
        gpu_params="--gpus all -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all,compute,utility,graphics"
        
        # Ajouter les périphériques NVIDIA
        if [ -e "/dev/nvidia0" ]; then
            gpu_params="$gpu_params --device /dev/nvidia0:/dev/nvidia0"
        fi
        if [ -e "/dev/nvidiactl" ]; then
            gpu_params="$gpu_params --device /dev/nvidiactl:/dev/nvidiactl"
        fi
        
        # Ajouter d'autres périphériques NVIDIA s'ils existent
        if [ -e "/dev/nvidia-modeset" ]; then
            gpu_params="$gpu_params --device /dev/nvidia-modeset:/dev/nvidia-modeset"
        fi
        if [ -e "/dev/nvidia-uvm" ]; then
            gpu_params="$gpu_params --device /dev/nvidia-uvm:/dev/nvidia-uvm"
        fi
        if [ -e "/dev/nvidia-uvm-tools" ]; then
            gpu_params="$gpu_params --device /dev/nvidia-uvm-tools:/dev/nvidia-uvm-tools"
        fi
    fi
    
    # Lancer le conteneur avec ou sans GPU
    docker run -dit \
        --name "$container_name" \
        $gpu_params \
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
    
    # Vérifier si le conteneur a bien démarré
    if [ $? -eq 0 ]; then
        echo "✅ Conteneur ${container_name} démarré avec succès !"
        echo "🔄 Attente que le service soit prêt..."
        sleep 3
        
        # Créer le script de test GPU uniquement si on utilise le GPU
        if [ "$use_gpu" = "true" ]; then
            create_gpu_test_script "$container_name" "$username"
        fi
    else
        echo "❌ Échec du démarrage du conteneur ${container_name}."
    fi
}

# Ancienne fonction maintenue pour compatibilité, appelle la nouvelle fonction
run_container_with_gpu() {
    run_container "$1" "$2" "$3" "$4" "$5" "$6" "true"
}

# Appeler la vérification de dépendances au démarrage
check_dependencies

# Lecture des entrées utilisateur
echo "1: Connexion / 2: Création de compte"
read -p "Choix (1/2) : " choice
read -p "Nom d'utilisateur : " username
read -s -p "Mot de passe : " password
echo
read -p "Image (laisser vide pour défaut) : " image_name

# Si aucune image n'est spécifiée, utiliser la valeur par défaut
if [ -z "$image_name" ]; then
    image_name="xfce_gui_container"
fi

# Demander si l'utilisateur souhaite utiliser le GPU
read -p "Voulez-vous utiliser le GPU? (o/n) : " use_gpu_choice
use_gpu="false"
if [[ "$use_gpu_choice" =~ ^[oOyY]$ ]]; then
    use_gpu="true"
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
    echo "✅ Compte '$username' créé avec succès"
else
    echo "❌ Choix invalide"
    exit 1
fi

# Container associé à l'utilisateur
container_name="${CONTAINER_PREFIX}${username}"

# Récupérer le port associé à l'utilisateur
user_port=$(get_user_port "$username")

# Pour un NOUVEAU conteneur uniquement, vérifier si le port est disponible
if ! container_exists "$container_name" && ! port_is_available "$user_port"; then
    echo "⚠️ Le port $user_port n'est plus disponible, recherche d'un nouveau port..."
    new_port=$(find_free_port)
    if [ $? -eq 0 ]; then
        set_user_port "$username" "$new_port"
        user_port="$new_port"
        echo "✅ Nouveau port attribué: $user_port"
    else
        echo "❌ $new_port"
        exit 1
    fi
fi

# Récupération du port RDP spécifique à l'image
rdp_port=$(get_image_info "$image_name" "port")
[ -z "$rdp_port" ] && rdp_port="3390"  # Valeur par défaut si non spécifiée

# Message différent selon que le conteneur existe déjà ou non
if container_exists "$container_name"; then
    echo "🔄 Conteneur existant, redémarrage pour appliquer les changements..."
else
    echo "🆕 Création d'un nouveau conteneur..."
fi

# Lancer ou redémarrer le conteneur (toujours avec la même méthode)
run_container "$container_name" "$username" "$password" "$image_name" "$user_port" "$rdp_port" "$use_gpu"

# Créer le script de nettoyage
create_cleanup_script

# Affiche les infos de connexion
IP=$(hostname -I | awk '{print $1}')
echo -e "\n🖥️  Connecte-toi avec RDP sur : $IP:$user_port"
echo -e "👤 USER : $username"
echo -e "🔑 MOT DE PASSE : $password"

# Afficher les services supplémentaires si présents
for port_mapping in $(get_image_info "$image_name" "extra_ports"); do
    host_port=$(echo $port_mapping | cut -d':' -f1)
    container_port=$(echo $port_mapping | cut -d':' -f2)
    
    if [ "$container_port" = "5173" ]; then
        echo -e "📊 Application Web : http://$IP:$host_port"
    fi
done

# N'afficher l'info sur le script GPU que si le GPU est activé
if [ "$use_gpu" = "true" ]; then
    echo -e "\n🎮 Pour tester le GPU : sudo ./test_gpu.sh"
fi