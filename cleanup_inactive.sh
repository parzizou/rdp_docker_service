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
