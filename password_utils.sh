#!/bin/bash

USER_FILE="users.txt"

# Fonction pour chiffrer un mot de passe avec bcrypt
encrypt_password() {
    local password=$1
    
    # Vérifier que bcrypt est installé
    if ! python3 -c 'import bcrypt' 2>/dev/null; then
        if ! pip3 install bcrypt 2>/dev/null && ! sudo pip3 install bcrypt 2>/dev/null; then
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

# Vérifie si un utilisateur existe
user_exists() {
    grep -q "^$1:" "$USER_FILE"
}

# Récupère le mot de passe d'un utilisateur
get_user_password() {
    grep "^$1:" "$USER_FILE" | cut -d':' -f2
}

# Récupère l'image associée à un utilisateur
get_user_image() {
    grep "^$1:" "$USER_FILE" | cut -d':' -f3
}

# Fonction pour vérifier si un mot de passe est temporaire
is_temp_password() {
    local username=$1
    grep "^$username:" "$USER_FILE" | cut -d':' -f4 | grep -q "1"
    return $?
}

# Fonction pour changer le mot de passe
change_password() {
    local username=$1
    local new_password=$2
    local current_line=$(grep "^$username:" "$USER_FILE")
    
    if [ -n "$current_line" ]; then
        # Extraire l'image actuelle
        local image=$(echo "$current_line" | cut -d':' -f3)
        
        # Chiffrer le nouveau mot de passe
        local new_hashed_password=$(encrypt_password "$new_password")
        
        # Supprimer l'ancienne ligne
        sed -i "/^$username:/d" "$USER_FILE"
        
        # Ajouter la nouvelle ligne avec le nouveau mot de passe et le flag à 0
        echo "$username:$new_hashed_password:$image:0" >> "$USER_FILE"
        echo "Mot de passe modifié avec succès pour $username"
        return 0
    fi
    echo "Erreur: utilisateur $username non trouvé"
    return 1
}