#!/usr/bin/env python3
"""
Script de tableau de bord admin pour monitorer les conteneurs Docker
Exécuter avec: python3 admin_dashboard.py
"""
import os
import subprocess
import json
import time
import argparse
import shutil
import random
import string
from datetime import datetime
import threading
import bcrypt
import getpass

# Couleurs pour le terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Constantes pour les fichiers de configuration
POWER_USERS_FILE = "power_users.txt"
BLOCKED_USERS_FILE = "blocked_users.txt"
USER_FILE = "users.txt"
PORT_FILE = "port_map.txt"
START_PORT = 3390
MAX_PORT = 3490

# Cache global pour les infos GPU
_gpu_info_cache = None
_gpu_info_cache_time = 0
_gpu_info_cache_ttl = 5  # secondes

def clear_screen():
    """Efface l'écran du terminal"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_terminal_width():
    """Récupère la largeur du terminal"""
    try:
        columns, _ = shutil.get_terminal_size()
        return columns
    except:
        return 120  # Valeur par défaut si impossible de déterminer

def get_gpu_info():
    """Récupère les informations du GPU NVIDIA via nvidia-smi avec mise en cache"""
    global _gpu_info_cache, _gpu_info_cache_time
    current_time = time.time()
    
    # Utiliser le cache si disponible et récent
    if _gpu_info_cache is not None and current_time - _gpu_info_cache_time < _gpu_info_cache_ttl:
        return _gpu_info_cache
    
    try:
        cmd = "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,driver_version --format=csv,noheader,nounits"
        gpu_info = subprocess.check_output(cmd, shell=True, timeout=1).decode().strip().split('\n')
        
        gpus = []
        for line in gpu_info:
            parts = line.split(', ')
            if len(parts) >= 8:
                gpus.append({
                    'index': parts[0],
                    'name': parts[1],
                    'temp': parts[2],
                    'gpu_util': parts[3],
                    'mem_util': parts[4],
                    'mem_used': parts[5],
                    'mem_total': parts[6],
                    'driver': parts[7]
                })
        
        # Mettre en cache le résultat
        _gpu_info_cache = gpus
        _gpu_info_cache_time = current_time
        return gpus
    except Exception as e:
        return []

def get_container_gpu_usage(container_id):
    """Récupère l'utilisation GPU d'un conteneur spécifique avec timeout réduit"""
    try:
        # On récupère les PIDs du conteneur
        cmd = f"docker top {container_id} -eo pid | tail -n +2"
        container_pids_raw = subprocess.check_output(cmd, shell=True, timeout=0.5).decode().strip()
        container_pids = set(pid.strip() for pid in container_pids_raw.split('\n') if pid.strip())
        
        # On récupère les processus GPU
        cmd = "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits"
        gpu_processes_raw = subprocess.check_output(cmd, shell=True, timeout=0.5).decode().strip()
        
        # On cherche les processus GPU qui appartiennent au conteneur
        total_memory = 0
        for line in gpu_processes_raw.split('\n'):
            if not line.strip():
                continue
                
            parts = line.split(', ')
            if len(parts) >= 2:
                gpu_pid = parts[0].strip()
                if gpu_pid in container_pids:
                    total_memory += int(parts[1])
        
        return total_memory
        
    except subprocess.TimeoutExpired:
        # En cas de timeout, retourner 0 au lieu d'attendre
        return 0
    except Exception as e:
        return 0

# Nouvelles fonctions pour gérer les power users
def get_power_users():
    """Récupère la liste des power users"""
    power_users = []
    try:
        if os.path.exists(POWER_USERS_FILE):
            with open(POWER_USERS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        power_users.append(line)
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier {POWER_USERS_FILE}: {e}")
    
    return power_users

def save_power_users(power_users):
    """Sauvegarde la liste des power users dans le fichier"""
    try:
        with open(POWER_USERS_FILE, 'w') as f:
            f.write("# Liste des power users (un par ligne)\n")
            for username in power_users:
                f.write(f"{username}\n")
        return True
    except Exception as e:
        print(f"Erreur lors de l'écriture dans le fichier {POWER_USERS_FILE}: {e}")
        return False

def add_power_user(username):
    """Ajoute un utilisateur à la liste des power users"""
    power_users = get_power_users()
    if username not in power_users:
        power_users.append(username)
        return save_power_users(power_users)
    return True  # Déjà power user

def remove_power_user(username):
    """Supprime un utilisateur de la liste des power users"""
    power_users = get_power_users()
    if username in power_users:
        power_users.remove(username)
        return save_power_users(power_users)
    return True  # Déjà pas power user

def is_power_user(username):
    """Vérifie si un utilisateur est un power user"""
    power_users = get_power_users()
    return username in power_users

# Nouvelles fonctions pour gérer les utilisateurs bloqués
def get_blocked_users():
    """Récupère la liste des utilisateurs bloqués"""
    blocked_users = []
    try:
        if os.path.exists(BLOCKED_USERS_FILE):
            with open(BLOCKED_USERS_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        blocked_users.append(line)
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier {BLOCKED_USERS_FILE}: {e}")
    
    return blocked_users

def save_blocked_users(blocked_users):
    """Sauvegarde la liste des utilisateurs bloqués dans le fichier"""
    try:
        with open(BLOCKED_USERS_FILE, 'w') as f:
            f.write("# Liste des utilisateurs bloqués (un par ligne)\n")
            for username in blocked_users:
                f.write(f"{username}\n")
        return True
    except Exception as e:
        print(f"Erreur lors de l'écriture dans le fichier {BLOCKED_USERS_FILE}: {e}")
        return False

def block_user(username):
    """Bloque un utilisateur"""
    blocked_users = get_blocked_users()
    if username not in blocked_users:
        blocked_users.append(username)
        return save_blocked_users(blocked_users)
    return True  # Déjà bloqué

def unblock_user(username):
    """Débloque un utilisateur"""
    blocked_users = get_blocked_users()
    if username in blocked_users:
        blocked_users.remove(username)
        return save_blocked_users(blocked_users)
    return True  # Déjà débloqué

def is_blocked(username):
    """Vérifie si un utilisateur est bloqué"""
    blocked_users = get_blocked_users()
    return username in blocked_users

# Nouvelles fonctions pour la gestion des utilisateurs
def get_users():
    """Récupère la liste des utilisateurs depuis le fichier"""
    users = []
    try:
        if os.path.exists(USER_FILE):
            with open(USER_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(':')
                        if len(parts) >= 2:  # Au moins username:password
                            username = parts[0]
                            users.append(username)
    except Exception as e:
        print(f"Erreur lors de la lecture du fichier {USER_FILE}: {e}")
    
    return users

def user_exists(username):
    """Vérifie si un utilisateur existe"""
    try:
        if os.path.exists(USER_FILE):
            with open(USER_FILE, 'r') as f:
                for line in f:
                    if line.startswith(f"{username}:"):
                        return True
    except Exception as e:
        print(f"Erreur lors de la vérification de l'utilisateur: {e}")
    
    return False

def encrypt_password(password):
    """Chiffre un mot de passe (simulation du processus de hachage)"""
    try:
        # Essayer d'appeler la fonction de chiffrement du script initial
        result = subprocess.check_output(f"echo -n '{password}' | python3 -c 'import bcrypt, sys; print(bcrypt.hashpw(sys.stdin.read().encode(), bcrypt.gensalt()).decode())'", shell=True).decode().strip()
        return result
    except Exception as e:
        print(f"Erreur lors du chiffrement du mot de passe: {e}")
        # Fallback à une méthode simple si bcrypt échoue
        return subprocess.check_output(f"echo -n '{password}' | md5sum | awk '{{print $1}}'", shell=True).decode().strip()

def add_user(username, password):
    """Ajoute un nouvel utilisateur"""
    if user_exists(username):
        return False, "L'utilisateur existe déjà"
    
    try:
        # Chiffrer le mot de passe
        hashed_password = encrypt_password(password)
        
        # Ajouter l'utilisateur au fichier users.txt avec l'image par défaut
        with open(USER_FILE, 'a') as f:
            # Format: username:password:image:temp_password_flag
            f.write(f"{username}:{hashed_password}:xfce_gui_container:1\n")
        
        # Trouver un port disponible pour l'utilisateur
        port = find_free_port()
        if port:
            # Enregistrer le port pour l'utilisateur
            with open(PORT_FILE, 'a') as f:
                f.write(f"{username}:{port}\n")
            
            return True, f"Utilisateur {username} créé avec succès. Port assigné: {port}"
        else:
            return False, "Impossible de trouver un port disponible"
    except Exception as e:
        return False, f"Erreur lors de la création de l'utilisateur: {e}"

def find_free_port(start_port=START_PORT, end_port=MAX_PORT):
    """Trouve un port libre pour un nouvel utilisateur"""
    # Récupérer les ports déjà utilisés
    used_ports = []
    try:
        if os.path.exists(PORT_FILE):
            with open(PORT_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(':')
                        if len(parts) >= 2:
                            port = int(parts[1])
                            used_ports.append(port)
    except Exception as e:
        print(f"Erreur lors de la lecture des ports: {e}")
    
    # Trouver un port libre
    for port in range(start_port, end_port + 1):
        if port not in used_ports:
            # Vérifier si le port est réellement libre sur la machine
            try:
                cmd = f"ss -tuln | grep ':{port} '"
                result = subprocess.run(cmd, shell=True, capture_output=True)
                if result.returncode != 0:  # Le port n'est pas utilisé
                    return port
            except Exception:
                pass
    
    return None  # Aucun port libre trouvé

def reset_password(username, new_password=None):
    """Réinitialise le mot de passe d'un utilisateur"""
    if not user_exists(username):
        return False, "L'utilisateur n'existe pas"
    
    try:
        # Générer un mot de passe aléatoire si aucun n'est fourni
        if not new_password:
            new_password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        
        # Chiffrer le nouveau mot de passe
        hashed_password = encrypt_password(new_password)
        
        # Lire le fichier et mettre à jour le mot de passe
        with open(USER_FILE, 'r') as f:
            lines = f.readlines()
        
        with open(USER_FILE, 'w') as f:
            for line in lines:
                if line.startswith(f"{username}:"):
                    parts = line.strip().split(':')
                    if len(parts) >= 3:
                        # Garder l'image, mais marquer le mot de passe comme temporaire
                        image = parts[2] if len(parts) > 2 else "xfce_gui_container"
                        f.write(f"{username}:{hashed_password}:{image}:1\n")
                else:
                    f.write(line)
        
        return True, new_password
    except Exception as e:
        return False, f"Erreur lors de la réinitialisation du mot de passe: {e}"

def get_containers_basic_info(filter_prefix="gui_user_"):
    """Récupère les ID et noms des conteneurs Docker - version optimisée pour la rapidité"""
    try:
        cmd = f"docker ps -a --filter name={filter_prefix} --format '{{{{.ID}}}}|{{{{.Names}}}}|{{{{.Status}}}}|{{{{.Image}}}}'"
        containers_raw = subprocess.check_output(cmd, shell=True, timeout=1).decode().strip().split('\n')
        
        if containers_raw == ['']:
            return []
            
        containers_basic = []
        for container_line in containers_raw:
            if not container_line:
                continue
                
            parts = container_line.split('|')
            if len(parts) >= 3:
                container_id = parts[0]
                container_name = parts[1]
                status = parts[2]
                image = parts[3] if len(parts) > 3 else "N/A"
                
                username = container_name.replace(filter_prefix, '')
                is_running = status.startswith('Up')
                
                containers_basic.append({
                    'id': container_id[:12],
                    'name': container_name,
                    'username': username,
                    'is_running': is_running,
                    'image': image
                })
        
        return containers_basic
    except Exception as e:
        print(f"Erreur lors de la récupération des conteneurs: {e}")
        return []


def find_container_using_port(port):
    """Trouve le conteneur qui utilise un port spécifique"""
    try:
        # Récupère tous les conteneurs qui sont en cours d'exécution
        cmd = f"docker ps --format '{{{{.ID}}}}|{{{{.Names}}}}'"
        containers_raw = subprocess.check_output(cmd, shell=True, timeout=1).decode().strip().split('\n')
        
        for container_line in containers_raw:
            if not container_line:
                continue
                
            parts = container_line.split('|')
            if len(parts) >= 2:
                container_id = parts[0]
                container_name = parts[1]
                
                # Vérifie si ce conteneur utilise le port en question
                cmd = f"docker port {container_id}"
                try:
                    port_mappings = subprocess.check_output(cmd, shell=True, timeout=1).decode().strip()
                    if f":{port}" in port_mappings:
                        return container_id, container_name
                except:
                    # Ignorer les erreurs pour ce conteneur et passer au suivant
                    pass
                    
        return None, None
    except Exception as e:
        print(f"{Colors.RED}Erreur lors de la recherche du conteneur utilisant le port {port}: {e}{Colors.END}")
        return None, None


def get_container_details(container_basic, power_users, blocked_users):
    """Récupère les détails d'un conteneur spécifique"""
    container_id = container_basic['id']
    
    try:
        # Obtenir les informations détaillées du conteneur
        cmd = f"docker inspect {container_id}"
        container_info = json.loads(subprocess.check_output(cmd, shell=True, timeout=1).decode())[0]
        
        # Obtenir les statistiques du conteneur si en cours d'exécution
        if container_basic['is_running']:
            try:
                # Timeout de 3 secondes pour docker stats
                cmd = f"docker stats {container_id} --no-stream --format \"{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}|{{{{.MemPerc}}}}\""
                stats_raw = subprocess.check_output(cmd, shell=True, timeout=3).decode().strip()
                cpu_perc, mem_usage, mem_perc = stats_raw.split('|')
            except subprocess.TimeoutExpired:
                # Message d'erreur en cas de timeout (sans afficher les stats brutes)
                print(f"{Colors.YELLOW}Timeout pour docker stats sur {container_id}{Colors.END}")
                cpu_perc = "0%"
                mem_usage = "0B / 0B"
                mem_perc = "0%"
            except Exception as e:
                # Log l'erreur spécifique
                print(f"{Colors.RED}Erreur docker stats sur {container_id}: {str(e)}{Colors.END}")
                cpu_perc = "0%"
                mem_usage = "0B / 0B"
                mem_perc = "0%"
        else:
            cpu_perc = "0%"
            mem_usage = "0B / 0B"
            mem_perc = "0%"
        
        # Vérifier si c'est un power user
        is_power = container_basic['username'] in power_users
        
        # Vérifier si l'utilisateur est bloqué
        is_blocked_user = container_basic['username'] in blocked_users
        
        # Obtenir le temps de fonctionnement
        if container_basic['is_running']:
            started_at = datetime.fromisoformat(container_info['State']['StartedAt'].replace('Z', '+00:00'))
            uptime = datetime.now().astimezone() - started_at
            uptime_str = str(uptime).split('.')[0]  # Supprimer les microsecondes
        else:
            uptime_str = "arrêté"
        
        # Obtenir le port RDP mappé
        port_mappings = container_info['NetworkSettings']['Ports']
        rdp_port = "N/A"
        
        # Vérifier que port_mappings n'est pas None avant de l'utiliser
        if port_mappings:
            # Chercher les ports 3389 ou 3390 (RDP standard et alternatif)
            for port_key in ['3389/tcp', '3390/tcp']:
                if port_key in port_mappings and port_mappings[port_key]:
                    rdp_port = port_mappings[port_key][0]['HostPort']
                    break
        
        # Vérifier si le GPU est activé dans le conteneur
        has_gpu = False
        gpu_memory = 0

        # Vérifier les options de GPU dans le conteneur
        if 'HostConfig' in container_info and 'DeviceRequests' in container_info['HostConfig']:
            device_requests = container_info['HostConfig']['DeviceRequests']
            if device_requests is not None:  # Vérifier que DeviceRequests n'est pas None
                for device in device_requests:
                    if device and (device.get('Driver') == 'nvidia' or device.get('Count') == -1):  # -1 signifie "all GPUs"
                        has_gpu = True
                        break
        
        # Si le conteneur est en cours d'exécution et a le GPU, on calcule l'utilisation
        if container_basic['is_running'] and has_gpu:
            # Lancer le calcul d'utilisation GPU en arrière-plan pour éviter d'attendre
            gpu_memory = get_container_gpu_usage(container_id)
        
        # Obtenir les limites CPU et mémoire
        cpu_limit = "N/A"
        mem_limit = "N/A"
        
        try:
            if 'HostConfig' in container_info and container_info['HostConfig'] is not None:
                if 'NanoCpus' in container_info['HostConfig'] and container_info['HostConfig']['NanoCpus']:
                    nanoCPUs = container_info['HostConfig']['NanoCpus']
                    if nanoCPUs > 0:
                        cpu_limit = str(nanoCPUs / 1000000000)  # Convertir nanoCPUs en CPUs
                
                if 'Memory' in container_info['HostConfig'] and container_info['HostConfig']['Memory']:
                    memory_limit = container_info['HostConfig']['Memory']
                    if memory_limit > 0:
                        mem_limit = f"{memory_limit / (1024*1024)}MB"
        except Exception as e:
            print(f"{Colors.YELLOW}Erreur lors de la récupération des limites pour {container_id}: {str(e)}{Colors.END}")
        
        # Compléter les informations de base
        container_details = container_basic.copy()
        container_details.update({
            'status': 'En cours' if container_basic['is_running'] else 'Arrêté',
            'cpu': cpu_perc,
            'mem': mem_usage,
            'mem_perc': mem_perc,
            'uptime': uptime_str,
            'rdp_port': rdp_port,
            'has_gpu': has_gpu,
            'gpu_memory': gpu_memory,
            'is_power_user': is_power,
            'is_blocked': is_blocked_user,
            'cpu_limit': cpu_limit,
            'mem_limit': mem_limit
        })
        
        return container_details
    except Exception as e:
        # Log l'erreur spécifique
        print(f"{Colors.RED}Erreur lors de la récupération des détails du conteneur {container_id}: {str(e)}{Colors.END}")
        
        # En cas d'erreur, retourner les informations de base
        return {
            'id': container_basic['id'],
            'name': container_basic['name'],
            'username': container_basic['username'],
            'status': 'En cours' if container_basic['is_running'] else 'Arrêté',
            'image': container_basic['image'],
            'cpu': "0%",
            'mem': "0B / 0B",
            'mem_perc': "0%",
            'uptime': "N/A" if container_basic['is_running'] else "arrêté",
            'rdp_port': "N/A",
            'is_running': container_basic['is_running'],
            'has_gpu': False,
            'gpu_memory': 0,
            'is_power_user': container_basic['username'] in power_users,
            'is_blocked': container_basic['username'] in blocked_users,
            'cpu_limit': "N/A",
            'mem_limit': "N/A"
        }

def get_containers_parallel(filter_prefix="gui_user_"):
    """Récupère les informations sur les conteneurs Docker en parallèle pour plus de rapidité"""
    # Récupérer les informations de base rapidement
    containers_basic = get_containers_basic_info(filter_prefix)
    if not containers_basic:
        return []
    
    # Récupérer les listes des power users et utilisateurs bloqués
    power_users = get_power_users()
    blocked_users = get_blocked_users()
    
    # Créer une fonction pour récupérer les détails d'un conteneur
    def get_container_details_wrapper(container_basic, results, index):
        try:
            results[index] = get_container_details(container_basic, power_users, blocked_users)
        except Exception as e:
            print(f"{Colors.RED}Erreur dans le thread pour {container_basic['id']}: {str(e)}{Colors.END}")
            # Assurer qu'on a au moins les infos de base en cas d'erreur
            results[index] = {
                'id': container_basic['id'],
                'name': container_basic['name'],
                'username': container_basic['username'],
                'status': 'En cours' if container_basic['is_running'] else 'Arrêté',
                'image': container_basic['image'],
                'cpu': "0%",
                'mem': "0B / 0B",
                'mem_perc': "0%",
                'uptime': "N/A" if container_basic['is_running'] else "arrêté",
                'rdp_port': "N/A",
                'is_running': container_basic['is_running'],
                'has_gpu': False,
                'gpu_memory': 0,
                'is_power_user': container_basic['username'] in power_users,
                'is_blocked': container_basic['username'] in blocked_users,
                'cpu_limit': "N/A",
                'mem_limit': "N/A"
            }
    
    # Créer des threads pour récupérer les détails en parallèle
    threads = []
    container_details = [None] * len(containers_basic)
    
    for i, container_basic in enumerate(containers_basic):
        thread = threading.Thread(
            target=get_container_details_wrapper,
            args=(container_basic, container_details, i)
        )
        thread.daemon = True
        threads.append(thread)
        thread.start()
    
    # Attendre que tous les threads se terminent (avec un timeout pour éviter les blocages)
    for thread in threads:
        thread.join(timeout=5)  # Augmenté de 2 à 5 secondes
    
    # Filtrer les résultats None (en cas d'erreur) et ajouter des logs
    containers = []
    for i, container in enumerate(container_details):
        if container is not None:
            containers.append(container)
        else:
            # Cas où le conteneur n'a pas été traité à temps
            print(f"{Colors.YELLOW}Attention: le conteneur {containers_basic[i]['id']} n'a pas été traité à temps{Colors.END}")
            # Ajouter au moins les infos de base
            containers.append({
                'id': containers_basic[i]['id'],
                'name': containers_basic[i]['name'],
                'username': containers_basic[i]['username'],
                'status': 'En cours' if containers_basic[i]['is_running'] else 'Arrêté',
                'image': containers_basic[i]['image'],
                'cpu': "N/A",
                'mem': "N/A",
                'mem_perc': "N/A",
                'uptime': "N/A" if containers_basic[i]['is_running'] else "arrêté",
                'rdp_port': "N/A",
                'is_running': containers_basic[i]['is_running'],
                'has_gpu': False,
                'gpu_memory': 0,
                'is_power_user': containers_basic[i]['username'] in power_users,
                'is_blocked': containers_basic[i]['username'] in blocked_users,
                'cpu_limit': "N/A",
                'mem_limit': "N/A"
            })
    
    # Trier les conteneurs par statut (En cours d'abord) puis par nom
    containers.sort(key=lambda c: (0 if c['is_running'] else 1, c['name']))
    
    return containers

def truncate_text(text, max_length):
    """Tronque le texte s'il est trop long et ajoute '...'"""
    if len(text) > max_length:
        return text[:max_length-3] + '...'
    return text


def display_containers(containers):
    """Affiche un tableau formaté avec les informations des conteneurs"""
    if not containers:
        print(f"{Colors.YELLOW}Aucun conteneur trouvé.{Colors.END}")
        return
    
    # Obtenir la largeur du terminal et ajuster les colonnes
    term_width = get_terminal_width()
    
    # En-têtes de colonne
    headers = [
        "ID", "Utilisateur", "Status", "CPU", "Mémoire", "GPU (MiB)", "Uptime", "Port", "Image"
    ]
    
    # Calculer la largeur de chaque colonne en fonction de la largeur du terminal
    total_fixed_width = 19  # 9 colonnes = 10 séparateurs (|) + bordures gauche et droite
    widths = [12, 15, 8, 8, 20, 10, 12, 7]
    
    # La colonne Image prend l'espace restant
    remaining_width = term_width - sum(widths) - total_fixed_width
    image_width = max(15, remaining_width)
    widths.append(image_width)
    
    # Ligne de séparation
    separator = "+" + "+".join("-" * (w+2) for w in widths) + "+"
    
    # Vérifier que le séparateur n'est pas plus large que le terminal
    if len(separator) > term_width:
        # Si c'est le cas, réduire la largeur de la colonne Image
        excess = len(separator) - term_width
        widths[-1] = max(10, widths[-1] - excess)
        # Recréer le séparateur avec la bonne longueur
        separator = "+" + "+".join("-" * (w+2) for w in widths) + "+"
    
    # Afficher l'en-tête
    print(separator)
    header_cells = [f" {h:{w}} " for h, w in zip(headers, widths)]
    print(f"|{Colors.BOLD}{'|'.join(header_cells)}{Colors.END}|")
    print(separator)
    
    # Afficher les données de chaque conteneur
    gpu_color = Colors.YELLOW
    for container in containers:
        status_color = Colors.GREEN if container['is_running'] else Colors.RED
        cpu_color = Colors.RED if container['is_running'] and float(container['cpu'].replace('%', '') or 0) > 80 else Colors.END
        mem_color = Colors.RED if container['is_running'] and float(container['mem_perc'].replace('%', '') or 0) > 80 else Colors.END
        
        # Formatage de l'info GPU avec l'utilisation en MiB
        gpu_str = ""
        if container['has_gpu']:
            if container['is_running']:
                if container['gpu_memory'] > 0:
                    gpu_str = f"{container['gpu_memory']}"
                else:
                    gpu_str = "0"
                    gpu_color = Colors.YELLOW
            else:
                gpu_str = "✓ inactif"
                gpu_color = Colors.CYAN
        else:
            gpu_str = "✗"
            gpu_color = Colors.END
        
        # S'assurer que la cellule GPU a toujours la bonne largeur visible
        visible_length = len(gpu_str)  # Longueur sans les codes de couleur
        padding = widths[5] - visible_length
        gpu_info = f" {gpu_color}{gpu_str}{Colors.END}{' ' * padding} "
        
        # Tronquer le nom d'utilisateur séparément
        # CORRECTION: Réduire la taille max pour les utilisateurs avec emoji (power/blocked)
        has_emoji = container.get('is_power_user', False) or container.get('is_blocked', False)
        # Réduire de 2 caractères pour compenser l'emoji qui prend la place de 2
        username_base = truncate_text(container['username'], widths[1] - 2 if has_emoji else widths[1])
        
        # Construire la cellule username avec alignement correct
        username_cell = f" {username_base}"
        
        # Ajouter les indicateurs APRÈS le padding d'alignement
        # CORRECTION: Compter les emojis comme occupant 2 caractères
        emoji_width = 2  # Les emojis prennent la place de 2 caractères
        if container.get('is_power_user', False):
            username_cell += f"{Colors.YELLOW}⚡{Colors.END}"
            has_emoji = True
        elif container.get('is_blocked', False):
            username_cell += f"{Colors.RED}🔒{Colors.END}"
            has_emoji = True
        
        # Ajouter des espaces pour compléter la cellule
        # CORRECTION: Utiliser la largeur d'emoji correcte
        username_padding = widths[1] - len(username_base) - (emoji_width if has_emoji else 0)
        username_cell += " " * username_padding
        
        image = truncate_text(container['image'], widths[8])
        
        # Préparer les cellules
        cells = [
            f" {container['id']:{widths[0]}} ",
            username_cell + " ",
            f" {status_color}{container['status']:{widths[2]}}{Colors.END} ",
            f" {cpu_color}{container['cpu']:{widths[3]}}{Colors.END} ",
            f" {mem_color}{container['mem']:{widths[4]}}{Colors.END} ",
            gpu_info,
            f" {container['uptime']:{widths[6]}} ",
            f" {container['rdp_port']:{widths[7]}} ",
            f" {image:{widths[8]}} "
        ]
        
        # Concaténer les cellules pour former la ligne
        row = "|"
        for cell in cells:
            row += cell + "|"
        
        print(row)
    
    # Ligne de séparation finale
    print(separator)

def display_gpu_info(gpus):
    """Affiche les informations sur les GPU disponibles"""
    if not gpus:
        print(f"{Colors.YELLOW}Aucun GPU NVIDIA détecté sur ce système.{Colors.END}")
        return
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}Informations GPU NVIDIA{Colors.END}")
    
    # Obtenir la largeur du terminal
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    print(separator)
    
    for gpu in gpus:
        # Définir les couleurs selon l'utilisation
        temp_color = Colors.RED if float(gpu['temp']) > 80 else (Colors.YELLOW if float(gpu['temp']) > 70 else Colors.GREEN)
        util_color = Colors.RED if float(gpu['gpu_util']) > 80 else (Colors.YELLOW if float(gpu['gpu_util']) > 60 else Colors.GREEN)
        mem_color = Colors.RED if float(gpu['mem_util']) > 80 else (Colors.YELLOW if float(gpu['mem_util']) > 60 else Colors.GREEN)
        
        print(f"| {Colors.BOLD}GPU {gpu['index']}:{Colors.END} {gpu['name']} (Driver: {gpu['driver']})")
        print(f"| Température: {temp_color}{gpu['temp']}°C{Colors.END} | Utilisation: {util_color}{gpu['gpu_util']}%{Colors.END} | Mémoire: {mem_color}{gpu['mem_used']}MB / {gpu['mem_total']}MB ({gpu['mem_util']}%){Colors.END}")
        print(separator)
    
    print()

def display_menu():
    """Affiche le menu des actions possibles"""
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    print(separator)
    print(f"| {Colors.BOLD}Actions disponibles:{Colors.END}")
    print(f"| 1. Rafraîchir (ou appuyer sur Entrée)")
    print(f"| 2. Démarrer un conteneur")
    print(f"| 3. Arrêter un conteneur")
    print(f"| 4. Voir les logs d'un conteneur")
    print(f"| 5. Exécuter une commande dans un conteneur")
    print(f"| 6. Supprimer un conteneur")
    print(f"| 7. Tester le GPU d'un conteneur")
    print(f"| 8. Afficher le statut détaillé des GPU")
    print(f"| 9. {Colors.YELLOW}Gestion des power users{Colors.END}")
    print(f"| 0. {Colors.RED}Bloquer/débloquer un utilisateur{Colors.END}")
    print(f"| A. {Colors.CYAN}Ajouter un nouvel utilisateur{Colors.END}")
    print(f"| R. {Colors.CYAN}Réinitialiser le mot de passe d'un utilisateur{Colors.END}")
    print(f"| q. Quitter")
    print(separator)
    print("Ton choix :")

    # Afficher le nombre d'utilisateurs bloqués s'il y en a
    blocked_users = get_blocked_users()
    if blocked_users:
        # Afficher sur une nouvelle ligne
        print(f"\n{Colors.RED}⚠️ {len(blocked_users)} utilisateur(s) bloqué(s): {', '.join(blocked_users)}{Colors.END}")
        # Réafficher le prompt
        print("Ton choix : ", end="")


def start_container(container_id):
    """Démarre un conteneur Docker"""
    try:
        # Vérifier si l'utilisateur est bloqué
        cmd = f"docker inspect {container_id} --format '{{{{.Name}}}}'"
        container_name = subprocess.check_output(cmd, shell=True).decode().strip()
        username = container_name.replace('/', '').replace('gui_user_', '')
        
        if is_blocked(username):
            print(f"{Colors.RED}✗ Impossible de démarrer le conteneur car l'utilisateur {username} est bloqué.{Colors.END}")
            return False
        
        # Récupérer les ports mappés pour ce conteneur avant de le démarrer
        cmd = f"docker inspect {container_id} --format '{{{{json .HostConfig.PortBindings}}}}'"
        port_bindings_json = subprocess.check_output(cmd, shell=True).decode().strip()
        port_bindings = json.loads(port_bindings_json if port_bindings_json != "null" else "{}")
        
        # Essayer de démarrer le conteneur
        try:
            subprocess.run(f"docker start {container_id}", shell=True, check=True)
            print(f"{Colors.GREEN}✓ Conteneur {container_id} démarré avec succès.{Colors.END}")
            return True
        except subprocess.CalledProcessError as e:
            # Vérifier si l'erreur est due à un conflit de port
            error_output = str(e.stderr) if hasattr(e, 'stderr') else ""
            
            # Si on peut pas accéder à stderr, on essaie de récupérer la sortie standard
            if not error_output:
                try:
                    # Exécuter la commande à nouveau pour capturer l'erreur
                    error_output = subprocess.check_output(f"docker start {container_id} 2>&1", shell=True, stderr=subprocess.STDOUT).decode()
                except subprocess.CalledProcessError as e2:
                    error_output = e2.output.decode() if hasattr(e2, 'output') else ""
            
            # Chercher les indices d'un conflit de port dans l'erreur
            port_conflict = False
            conflicted_port = None
            
            # Différentes formes possibles du message d'erreur
            if "address already in use" in error_output.lower() or "port is already allocated" in error_output.lower():
                port_conflict = True
                
                # Essayer de trouver le port en conflit
                for tcp_port in port_bindings:
                    if port_bindings[tcp_port]:
                        host_port = port_bindings[tcp_port][0]["HostPort"]
                        # Vérifier si ce port est mentionné dans le message d'erreur
                        if host_port in error_output:
                            conflicted_port = host_port
                            break
            
            # Si on a détecté un conflit de port
            if port_conflict:
                print(f"{Colors.RED}✗ Impossible de démarrer le conteneur {container_id}.{Colors.END}")
                
                if conflicted_port:
                    print(f"{Colors.YELLOW}⚠ Le port {conflicted_port} est déjà utilisé par un autre conteneur.{Colors.END}")
                    
                    # Chercher quel conteneur utilise ce port
                    conflicting_id, conflicting_name = find_container_using_port(conflicted_port)
                    
                    if conflicting_id:
                        print(f"{Colors.YELLOW}⚠ Le port {conflicted_port} est utilisé par le conteneur {conflicting_name} ({conflicting_id}).{Colors.END}")
                        
                        # Demander à l'utilisateur s'il veut arrêter ce conteneur
                        choice = input(f"{Colors.YELLOW}Veux-tu arrêter le conteneur {conflicting_name} pour libérer le port {conflicted_port}? (o/N): {Colors.END}")
                        
                        if choice.lower() == 'o':
                            # Arrêter le conteneur en conflit
                            if stop_container(conflicting_id):
                                # Attendre un peu pour que le port soit libéré
                                time.sleep(1)
                                # Essayer de démarrer à nouveau le conteneur original
                                try:
                                    subprocess.run(f"docker start {container_id}", shell=True, check=True)
                                    print(f"{Colors.GREEN}✓ Conteneur {container_id} démarré avec succès après résolution du conflit.{Colors.END}")
                                    return True
                                except subprocess.CalledProcessError:
                                    print(f"{Colors.RED}✗ Erreur lors du démarrage du conteneur {container_id} même après résolution du conflit.{Colors.END}")
                                    return False
                        else:
                            print(f"{Colors.YELLOW}Démarrage annulé.{Colors.END}")
                            return False
                else:
                    print(f"{Colors.YELLOW}⚠ Un port est déjà utilisé par un autre conteneur, mais impossible de déterminer lequel.{Colors.END}")
                    return False
            else:
                # Autre type d'erreur
                print(f"{Colors.RED}✗ Erreur lors du démarrage du conteneur {container_id}: {error_output}{Colors.END}")
                return False
                
    except Exception as e:
        print(f"{Colors.RED}✗ Erreur lors du démarrage du conteneur {container_id}: {e}{Colors.END}")
        return False

def stop_container(container_id):
    """Arrête un conteneur Docker"""
    try:
        subprocess.run(f"docker stop {container_id}", shell=True, check=True)
        print(f"{Colors.YELLOW}⚠ Conteneur {container_id} arrêté.{Colors.END}")
        return True
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}✗ Erreur lors de l'arrêt du conteneur {container_id}.{Colors.END}")
        return False

def show_logs(container_id, lines=50):
    """Affiche les logs d'un conteneur Docker"""
    try:
        logs = subprocess.check_output(f"docker logs --tail={lines} {container_id}", shell=True).decode()
        
        term_width = get_terminal_width()
        separator = "+" + "-" * (term_width - 2) + "+"
        
        print(separator)
        print(f"| {Colors.CYAN}Dernières {lines} lignes de logs pour {container_id}{Colors.END}")
        print(separator)
        
        # Traiter et afficher les logs avec une bonne indentation
        for line in logs.split('\n'):
            if line:
                # Tronquer les lignes trop longues
                if len(line) > term_width - 4:
                    line = line[:term_width - 7] + "..."
                print(f"| {line}")
        
        print(separator)
        input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu...{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}✗ Erreur lors de la récupération des logs du conteneur {container_id}.{Colors.END}")

def exec_command(container_id, command=None):
    """Exécute une commande dans un conteneur Docker"""
    if not command:
        command = input("Entre la commande à exécuter (ex: 'ls -la /home'): ")
    
    try:
        term_width = get_terminal_width()
        separator = "+" + "-" * (term_width - 2) + "+"
        
        print(separator)
        print(f"| {Colors.CYAN}Exécution de '{command}' dans {container_id}{Colors.END}")
        print(separator)
        
        # Exécuter la commande et capturer la sortie
        output = subprocess.check_output(f"docker exec {container_id} {command}", shell=True).decode()
        
        # Afficher la sortie avec une bonne indentation
        for line in output.split('\n'):
            if line:
                # Tronquer les lignes trop longues
                if len(line) > term_width - 4:
                    line = line[:term_width - 7] + "..."
                print(f"| {line}")
                
        print(separator)
        input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu...{Colors.END}")
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}✗ Erreur lors de l'exécution de la commande: {e}{Colors.END}")
        input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu...{Colors.END}")

def remove_container(container_id):
    """Supprime un conteneur Docker"""
    confirm = input(f"{Colors.RED}⚠ ATTENTION: Tu veux vraiment supprimer le conteneur {container_id}? (o/N): {Colors.END}")
    if confirm.lower() == 'o':
        try:
            subprocess.run(f"docker rm -f {container_id}", shell=True, check=True)
            print(f"{Colors.RED}✓ Conteneur {container_id} supprimé.{Colors.END}")
        except subprocess.CalledProcessError:
            print(f"{Colors.RED}✗ Erreur lors de la suppression du conteneur {container_id}.{Colors.END}")
    else:
        print(f"{Colors.YELLOW}Suppression annulée.{Colors.END}")

def test_gpu(container_id):
    try:
        term_width = get_terminal_width()
        separator = "+" + "-" * (term_width - 2) + "+"
        
        print(separator)
        print(f"| {Colors.CYAN}Test du GPU dans {container_id}{Colors.END}")
        print(separator)
        
        # 1. Vérifier si nvidia-smi est disponible
        print(f"| {Colors.BOLD}1. Test nvidia-smi:{Colors.END}")
        nvidia_smi = subprocess.run(f"docker exec {container_id} nvidia-smi", 
                                  shell=True, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE)
        
        if nvidia_smi.returncode == 0:
            print(f"| {Colors.GREEN}✓ nvidia-smi fonctionne correctement{Colors.END}")
            # Formater la sortie de nvidia-smi
            for line in nvidia_smi.stdout.decode().split('\n'):
                if line:
                    # Tronquer les lignes trop longues
                    if len(line) > term_width - 4:
                        line = line[:term_width - 7] + "..."
                    print(f"| {line}")
        else:
            print(f"| {Colors.RED}✗ nvidia-smi n'est pas disponible{Colors.END}")
            print(f"| Erreur: {nvidia_smi.stderr.decode()}")
        
        print(separator)
        
        # 2. Vérifier les périphériques NVIDIA
        print(f"| {Colors.BOLD}2. Périphériques NVIDIA:{Colors.END}")
        
        # D'abord essayer ls -la sur /dev/nvidia*
        devices = subprocess.run(f"docker exec {container_id} ls -la /dev/nvidia*", 
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        
        if devices.returncode == 0:
            print(f"| {Colors.GREEN}✓ Périphériques NVIDIA disponibles:{Colors.END}")
            for line in devices.stdout.decode().split('\n'):
                if line:
                    print(f"| {line}")
        else:
            print(f"| {Colors.RED}✗ Aucun périphérique /dev/nvidia* trouvé{Colors.END}")
            
            # Si échec, vérifier si le conteneur a accès aux GPU via --gpus
            check_gpu_option = subprocess.run(f"docker inspect --format='{{{{.HostConfig.DeviceRequests}}}}' {container_id}", 
                                           shell=True,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
            
            if "nvidia" in check_gpu_option.stdout.decode():
                print(f"| {Colors.YELLOW}⚠️ Le conteneur a l'option --gpus mais les périphériques ne sont pas visibles{Colors.END}")
                print(f"| {Colors.YELLOW}⚠️ Vérifie que nvidia-container-toolkit est installé et fonctionne correctement{Colors.END}")
            else:
                print(f"| {Colors.YELLOW}⚠️ Le conteneur n'a probablement pas été démarré avec l'option --gpus{Colors.END}")
                print(f"| {Colors.YELLOW}⚠️ Essaie 'docker run --gpus all ...' pour donner l'accès au GPU{Colors.END}")
        
        print(separator)

        # 3. Vérifier que CUDA est disponible
        print(f"| {Colors.BOLD}3. Test de l'environnement CUDA:{Colors.END}")
        cuda_check = subprocess.run(f"docker exec {container_id} bash -c 'command -v nvidia-smi && echo \"CUDA_VERSION: $CUDA_VERSION\" && echo \"NVIDIA_DRIVER_CAPABILITIES: $NVIDIA_DRIVER_CAPABILITIES\" && find /usr -name \"*libcuda*\" 2>/dev/null || echo \"Aucune librairie CUDA trouvée\"'", 
                                  shell=True, 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE)
        
        if cuda_check.returncode == 0:
            output = cuda_check.stdout.decode()
            if "libcuda" in output:
                print(f"| {Colors.GREEN}✓ L'environnement CUDA semble correctement configuré:{Colors.END}")
            else:
                print(f"| {Colors.YELLOW}⚠️ Librairies CUDA non trouvées ou non accessibles{Colors.END}")
            
            for line in output.split('\n'):
                if line:
                    print(f"| {line}")
        else:
            print(f"| {Colors.YELLOW}⚠️ L'environnement CUDA n'est pas complètement configuré{Colors.END}")
        
        # 4. Vérification supplémentaire des configurations
        print(separator)
        print(f"| {Colors.BOLD}4. Diagnostic et suggestions:{Colors.END}")
        
        # Vérifier que le docker-compose ou docker run a bien été configuré
        print(f"| {Colors.CYAN}Recommandations:{Colors.END}")
        print(f"| 1. Vérifie que tu as bien lancé le conteneur avec: '--gpus all'")
        print(f"| 2. Pour docker-compose, assure-toi d'avoir 'deploy: resources: reservations: devices:'")
        print(f"| 3. Teste si nvidia-container-toolkit est correctement installé sur l'hôte:")
        print(f"|    sudo apt install -y nvidia-container-toolkit && sudo systemctl restart docker")
        print(f"| 4. Pour un test rapide sur l'hôte: 'docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi'")
        
        print(separator)
        input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu...{Colors.END}")
    
    except Exception as e:
        print(f"{Colors.RED}✗ Erreur lors du test GPU: {e}{Colors.END}")
        input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu...{Colors.END}")

def select_container(containers, action_name):
    """Permet à l'utilisateur de sélectionner un conteneur par son numéro"""
    if not containers:
        print(f"{Colors.YELLOW}Aucun conteneur disponible pour cette action.{Colors.END}")
        input("Appuie sur Entrée pour continuer...")
        return None
    
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    print(separator)
    print(f"| {Colors.BOLD}Sélectionne un conteneur pour {action_name}:{Colors.END}")
    
    for i, container in enumerate(containers):
        status = "En cours" if container['is_running'] else "Arrêté"
        status_color = Colors.GREEN if container['is_running'] else Colors.RED
        gpu_info = f"{Colors.CYAN}[GPU]{Colors.END}" if container.get('has_gpu', False) else ""
        power_info = f"{Colors.YELLOW}[⚡POWER]{Colors.END}" if container.get('is_power_user', False) else ""
        blocked_info = f"{Colors.RED}[🔒BLOQUÉ]{Colors.END}" if container.get('is_blocked', False) else ""
        print(f"| {i+1}. {container['username']} ({container['id']}) - {status_color}{status}{Colors.END} {gpu_info} {power_info} {blocked_info}")
    
    print(f"| 0. Annuler")
    print(separator)
    
    while True:
        try:
            choice = int(input("Ton choix (numéro): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(containers):
                return containers[choice - 1]['id']
            print(f"{Colors.RED}Choix invalide. Entre un numéro entre 0 et {len(containers)}.{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Entre un numéro, pas du texte !{Colors.END}")

def manage_power_users(containers):
    """Interface pour gérer les power users"""
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    while True:
        clear_screen()
        
        power_users = get_power_users()
        
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
        title = "GESTION DES POWER USERS"
        padding = (term_width - len(title)) // 2
        print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
        
        print(separator)
        print(f"| {Colors.BOLD}Liste des power users actuels:{Colors.END}")
        print(separator)
        
        if not power_users:
            print(f"| {Colors.YELLOW}Aucun power user défini.{Colors.END}")
        else:
            for i, username in enumerate(power_users):
                print(f"| {i+1}. {username}")
        
        print(separator)
        print(f"| {Colors.BOLD}Actions:{Colors.END}")
        print(f"| 1. Ajouter un power user")
        print(f"| 2. Supprimer un power user")
        print(f"| 0. Retour au menu principal")
        print(separator)
        
        choice = input("Ton choix: ")
        
        if choice == '0':
            break
            
        elif choice == '1':
            # Ajouter un power user
            print(separator)
            print(f"| {Colors.BOLD}Ajouter un power user{Colors.END}")
            print(separator)
            
            # Montrer la liste des utilisateurs qui ne sont pas déjà power users
            regular_users = [c['username'] for c in containers if not c.get('is_power_user', False)]
            regular_users = list(set(regular_users))  # Enlever les doublons
            
            if not regular_users:
                print(f"| {Colors.YELLOW}Tous les utilisateurs sont déjà des power users.{Colors.END}")
                input("Appuie sur Entrée pour continuer...")
                continue
            
            print(f"| Utilisateurs disponibles:")
            for i, username in enumerate(regular_users):
                print(f"| {i+1}. {username}")
                
            print(f"| 0. Annuler")
            
            try:
                user_choice = int(input("Choisis un utilisateur (numéro): "))
                if user_choice == 0:
                    continue
                if 1 <= user_choice <= len(regular_users):
                    username = regular_users[user_choice - 1]
                    
                    # Demander confirmation
                    confirm = input(f"{Colors.YELLOW}Confirmer l'ajout de {username} comme power user? (o/N): {Colors.END}")
                    if confirm.lower() != 'o':
                        print("Opération annulée.")
                        input("Appuie sur Entrée pour continuer...")
                        continue
                        
                    if add_power_user(username):
                        print(f"{Colors.GREEN}✓ {username} ajouté comme power user avec succès.{Colors.END}")
                    else:
                        print(f"{Colors.RED}✗ Erreur lors de l'ajout de {username} comme power user.{Colors.END}")
                else:
                    print(f"{Colors.RED}Choix invalide.{Colors.END}")
            except ValueError:
                print(f"{Colors.RED}Entre un numéro valide.{Colors.END}")
                
            input("Appuie sur Entrée pour continuer...")
                
        elif choice == '2':
            # Supprimer un power user
            if not power_users:
                print(f"{Colors.YELLOW}Aucun power user à supprimer.{Colors.END}")
                input("Appuie sur Entrée pour continuer...")
                continue
                
            print(separator)
            print(f"| {Colors.BOLD}Supprimer un power user{Colors.END}")
            print(separator)
            
            # Lister les power users
            for i, username in enumerate(power_users):
                print(f"| {i+1}. {username}")
                
            print(f"| 0. Annuler")
            
            try:
                user_choice = int(input("Choisis un utilisateur à supprimer (numéro): "))
                if user_choice == 0:
                    continue
                if 1 <= user_choice <= len(power_users):
                    username = power_users[user_choice - 1]
                    
                    confirm = input(f"{Colors.YELLOW}⚠️ Es-tu sûr de vouloir supprimer {username} des power users? (o/N): {Colors.END}")
                    if confirm.lower() == 'o':
                        if remove_power_user(username):
                            print(f"{Colors.GREEN}✓ {username} supprimé des power users.{Colors.END}")
                        else:
                            print(f"{Colors.RED}✗ Erreur lors de la suppression de {username}.{Colors.END}")
                    else:
                        print("Opération annulée.")
                else:
                    print(f"{Colors.RED}Choix invalide.{Colors.END}")
            except ValueError:
                print(f"{Colors.RED}Entre un numéro valide.{Colors.END}")
                
            input("Appuie sur Entrée pour continuer...")
        
        else:
            print(f"{Colors.RED}Choix invalide.{Colors.END}")
            input("Appuie sur Entrée pour continuer...")

def manage_blocked_users(containers):
    """Interface pour gérer les utilisateurs bloqués"""
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    while True:
        clear_screen()
        
        blocked_users = get_blocked_users()
        
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
        title = "GESTION DES UTILISATEURS BLOQUÉS"
        padding = (term_width - len(title)) // 2
        print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
        
        print(separator)
        print(f"| {Colors.BOLD}Liste des utilisateurs actuellement bloqués:{Colors.END}")
        print(separator)
        
        if not blocked_users:
            print(f"| {Colors.GREEN}Aucun utilisateur bloqué actuellement.{Colors.END}")
        else:
            for i, username in enumerate(blocked_users):
                # Chercher si l'utilisateur a un conteneur
                container_info = ""
                for container in containers:
                    if container['username'] == username:
                        status = "En cours" if container['is_running'] else "Arrêté"
                        status_color = Colors.GREEN if container['is_running'] else Colors.RED
                        container_info = f" - Conteneur: {container['id']} ({status_color}{status}{Colors.END})"
                        break
                
                print(f"| {i+1}. {Colors.RED}{username}{Colors.END}{container_info}")
        
        print(separator)
        print(f"| {Colors.BOLD}Actions:{Colors.END}")
        print(f"| 1. Bloquer un utilisateur")
        print(f"| 2. Débloquer un utilisateur")
        print(f"| 0. Retour au menu principal")
        print(separator)
        
        choice = input("Ton choix: ")
        
        if choice == '0':
            break
            
        elif choice == '1':
            # Bloquer un utilisateur
            print(separator)
            print(f"| {Colors.BOLD}Bloquer un utilisateur{Colors.END}")
            print(separator)
            
            # Montrer la liste des utilisateurs qui ne sont pas déjà bloqués
            unblocked_users = [c['username'] for c in containers if not c.get('is_blocked', False)]
            unblocked_users = list(set(unblocked_users))  # Enlever les doublons
            
            if not unblocked_users:
                print(f"| {Colors.YELLOW}Tous les utilisateurs sont déjà bloqués.{Colors.END}")
                input("Appuie sur Entrée pour continuer...")
                continue
            
            print(f"| Utilisateurs disponibles:")
            for i, username in enumerate(unblocked_users):
                is_power = any(c.get('is_power_user', False) for c in containers if c['username'] == username)
                power_info = f"{Colors.YELLOW}[⚡POWER]{Colors.END}" if is_power else ""
                is_active = any(c['is_running'] for c in containers if c['username'] == username)
                status_info = f"{Colors.GREEN}[En ligne]{Colors.END}" if is_active else f"{Colors.RED}[Hors ligne]{Colors.END}"
                print(f"| {i+1}. {username} {power_info} {status_info}")
                
            print(f"| 0. Annuler")
            
            try:
                user_choice = int(input("Choisis un utilisateur à bloquer (numéro): "))
                if user_choice == 0:
                    continue
                if 1 <= user_choice <= len(unblocked_users):
                    username = unblocked_users[user_choice - 1]
                    
                    # Vérifier si l'utilisateur est en ligne
                    is_active = any(c['is_running'] for c in containers if c['username'] == username)
                    if is_active:
                        stop_confirm = input(f"{Colors.YELLOW}⚠️ Cet utilisateur est actuellement en ligne. Veux-tu arrêter son conteneur? (o/N): {Colors.END}")
                        if stop_confirm.lower() == 'o':
                            # Trouver le conteneur de l'utilisateur
                            for container in containers:
                                if container['username'] == username and container['is_running']:
                                    stop_container(container['id'])
                                    break
                    
                    confirm = input(f"{Colors.YELLOW}⚠️ Es-tu sûr de vouloir bloquer l'utilisateur {username}? (o/N): {Colors.END}")
                    if confirm.lower() == 'o':
                        if block_user(username):
                            print(f"{Colors.GREEN}✓ Utilisateur {username} bloqué avec succès.{Colors.END}")
                        else:
                            print(f"{Colors.RED}✗ Erreur lors du blocage de l'utilisateur {username}.{Colors.END}")
                    else:
                        print("Opération annulée.")
                else:
                    print(f"{Colors.RED}Choix invalide.{Colors.END}")
            except ValueError:
                print(f"{Colors.RED}Entre un numéro valide.{Colors.END}")
                
            input("Appuie sur Entrée pour continuer...")
                
        elif choice == '2':
            # Débloquer un utilisateur
            if not blocked_users:
                print(f"{Colors.YELLOW}Aucun utilisateur à débloquer.{Colors.END}")
                input("Appuie sur Entrée pour continuer...")
                continue
                
            print(separator)
            print(f"| {Colors.BOLD}Débloquer un utilisateur{Colors.END}")
            print(separator)
            
            # Lister les utilisateurs bloqués
            for i, username in enumerate(blocked_users):
                print(f"| {i+1}. {username}")
                
            print(f"| 0. Annuler")
            
            try:
                user_choice = int(input("Choisis un utilisateur à débloquer (numéro): "))
                if user_choice == 0:
                    continue
                if 1 <= user_choice <= len(blocked_users):
                    username = blocked_users[user_choice - 1]
                    
                    confirm = input(f"{Colors.YELLOW}⚠️ Es-tu sûr de vouloir débloquer l'utilisateur {username}? (o/N): {Colors.END}")
                    if confirm.lower() == 'o':
                        if unblock_user(username):
                            print(f"{Colors.GREEN}✓ Utilisateur {username} débloqué avec succès.{Colors.END}")
                        else:
                            print(f"{Colors.RED}✗ Erreur lors du déblocage de l'utilisateur {username}.{Colors.END}")
                    else:
                        print("Opération annulée.")
                else:
                    print(f"{Colors.RED}Choix invalide.{Colors.END}")
            except ValueError:
                print(f"{Colors.RED}Entre un numéro valide.{Colors.END}")
                
            input("Appuie sur Entrée pour continuer...")
        
        else:
            print(f"{Colors.RED}Choix invalide.{Colors.END}")
            input("Appuie sur Entrée pour continuer...")

# Nouvelles fonctions pour les options additionnelles
def add_new_user():
    """Interface pour ajouter un nouvel utilisateur"""
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    clear_screen()
    
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
    title = "AJOUT D'UN NOUVEL UTILISATEUR"
    padding = (term_width - len(title)) // 2
    print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
    
    print(separator)
    print(f"| {Colors.BOLD}Entrez les informations du nouvel utilisateur:{Colors.END}")
    print(separator)
    
    # Demander les informations de l'utilisateur
    username = input("Nom d'utilisateur: ")
    
    # Vérifier si l'utilisateur existe déjà
    if user_exists(username):
        print(f"{Colors.RED}✗ L'utilisateur {username} existe déjà.{Colors.END}")
        input("Appuie sur Entrée pour revenir au menu...")
        return
    
    # Demander le mot de passe ou en générer un
    generate_pwd = input("Générer un mot de passe aléatoire? (O/n): ")
    if generate_pwd.lower() in ['n', 'non']:
        password = ""
        while not password:
            password = input("Mot de passe: ")
            if not password:
                print(f"{Colors.RED}Le mot de passe ne peut pas être vide.{Colors.END}")
    else:
        # Générer un mot de passe aléatoire
        password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        print(f"Mot de passe généré: {Colors.GREEN}{password}{Colors.END}")
    
    # Confirmation
    print(separator)
    print(f"| {Colors.BOLD}Résumé:{Colors.END}")
    print(f"| Nom d'utilisateur: {username}")
    print(f"| Mot de passe: {password}")
    print(separator)
    
    confirm = input(f"{Colors.YELLOW}Confirmer la création de l'utilisateur? (O/n): {Colors.END}")
    if confirm.lower() in ['n', 'non']:
        print("Création annulée.")
        input("Appuie sur Entrée pour revenir au menu...")
        return
    
    # Créer l'utilisateur
    success, message = add_user(username, password)
    
    if success:
        print(f"{Colors.GREEN}✓ {message}{Colors.END}")
        
        # Demander si l'utilisateur doit être un power user
        power_user_choice = input(f"{Colors.YELLOW}Faire de {username} un power user? (o/N): {Colors.END}")
        if power_user_choice.lower() == 'o':
            if add_power_user(username):
                print(f"{Colors.GREEN}✓ {username} ajouté comme power user avec succès.{Colors.END}")
            else:
                print(f"{Colors.RED}✗ Erreur lors de l'ajout de {username} comme power user.{Colors.END}")

    input("Appuie sur Entrée pour revenir au menu...")

# Fonction pour la réinitialisation de mot de passe
def reset_user_password():
    """Interface pour réinitialiser le mot de passe d'un utilisateur"""
    term_width = get_terminal_width()
    separator = "+" + "-" * (term_width - 2) + "+"
    
    clear_screen()
    
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
    title = "RÉINITIALISATION DE MOT DE PASSE"
    padding = (term_width - len(title)) // 2
    print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
    
    # Récupérer la liste des utilisateurs
    users = get_users()
    
    if not users:
        print(f"{Colors.YELLOW}Aucun utilisateur trouvé.{Colors.END}")
        input("Appuie sur Entrée pour revenir au menu...")
        return
    
    print(separator)
    print(f"| {Colors.BOLD}Sélectionne un utilisateur:{Colors.END}")
    print(separator)
    
    # Afficher la liste des utilisateurs
    for i, username in enumerate(users):
        is_power = is_power_user(username)
        is_blocked_user = is_blocked(username)
        
        power_info = f"{Colors.YELLOW}[⚡POWER]{Colors.END}" if is_power else ""
        blocked_info = f"{Colors.RED}[🔒BLOQUÉ]{Colors.END}" if is_blocked_user else ""
        
        print(f"| {i+1}. {username} {power_info} {blocked_info}")
    
    print(f"| 0. Annuler")
    print(separator)
    
    try:
        choice = int(input("Choisis un utilisateur (numéro): "))
        if choice == 0:
            return
        
        if 1 <= choice <= len(users):
            username = users[choice - 1]
            
            # Demander si on veut spécifier un mot de passe ou en générer un aléatoire
            generate_pwd = input("Générer un mot de passe aléatoire? (O/n): ")
            
            if generate_pwd.lower() in ['n', 'non']:
                password = ""
                while not password:
                    password = input("Nouveau mot de passe: ")
                    if not password:
                        print(f"{Colors.RED}Le mot de passe ne peut pas être vide.{Colors.END}")
                
                # Réinitialiser le mot de passe avec celui fourni
                success, message = reset_password(username, password)
            else:
                # Réinitialiser le mot de passe avec un mot de passe aléatoire
                success, new_password = reset_password(username)
                
                if success:
                    message = f"Nouveau mot de passe pour {username}: {Colors.GREEN}{new_password}{Colors.END}"
            
            if success:
                print(f"{Colors.GREEN}✓ Mot de passe réinitialisé avec succès.{Colors.END}")
                print(message)
            else:
                print(f"{Colors.RED}✗ {message}{Colors.END}")
        else:
            print(f"{Colors.RED}Choix invalide.{Colors.END}")
    except ValueError:
        print(f"{Colors.RED}Entre un numéro valide.{Colors.END}")
    
    input("Appuie sur Entrée pour revenir au menu...")








def main():
    """Fonction principale du tableau de bord"""
    parser = argparse.ArgumentParser(description="Tableau de bord admin pour conteneurs Docker")
    parser.add_argument('-i', '--interval', type=int, default=200, help='Intervalle de rafraîchissement en secondes (0 pour désactiver)')
    args = parser.parse_args()


    # Vérification du mot de passe admin
    PASSWORD_FILE = "admin_password.hash"
    
    # Créer le fichier de mot de passe s'il n'existe pas
    if not os.path.exists(PASSWORD_FILE):
        import hashlib
        import getpass
        print(f"{Colors.YELLOW}Configuration initiale du mot de passe admin{Colors.END}")
        admin_password = getpass.getpass("Choisis un mot de passe admin: ")
        confirm_password = getpass.getpass("Confirme le mot de passe: ")
        
        if admin_password != confirm_password:
            print(f"{Colors.RED}Les mots de passe ne correspondent pas. Essaie à nouveau.{Colors.END}")
            sys.exit(1)
        
        # Hasher le mot de passe avec sel
        import secrets
        salt = secrets.token_hex(8)
        password_hash = hashlib.sha256((admin_password + salt).encode()).hexdigest()
        
        # Sauvegarder le hash et le sel dans le fichier
        with open(PASSWORD_FILE, 'w') as f:
            f.write(f"{salt}:{password_hash}")
        
        print(f"{Colors.GREEN}Mot de passe admin configuré avec succès !{Colors.END}")
    
    # Vérifier le mot de passe
    import hashlib
    import getpass
    
    # Lire le hash et le sel du fichier
    with open(PASSWORD_FILE, 'r') as f:
        stored_data = f.read().strip()
        
    salt, stored_hash = stored_data.split(':')
    
    # Demander le mot de passe
    password_attempts = 0
    max_attempts = 3
    
    while password_attempts < max_attempts:
        entered_password = getpass.getpass("Mot de passe admin: ")
        calculated_hash = hashlib.sha256((entered_password + salt).encode()).hexdigest()
        
        if calculated_hash == stored_hash:
            break
        else:
            password_attempts += 1
            remaining = max_attempts - password_attempts
            if remaining > 0:
                print(f"{Colors.RED}Mot de passe incorrect ! {remaining} tentative(s) restante(s).{Colors.END}")
            else:
                print(f"{Colors.RED}Trop de tentatives incorrectes. Fermeture du programme.{Colors.END}")
                sys.exit(1)
    
    refresh_interval = args.interval
    auto_refresh = refresh_interval > 0
    
    # Vérifier si le fichier power_users.txt existe, sinon le créer
    if not os.path.exists(POWER_USERS_FILE):
        with open(POWER_USERS_FILE, 'w') as f:
            f.write("# Format: username:cpu_limit:memory_limit:gpu_memory_limit\n")
            
    # Vérifier si le fichier blocked_users.txt existe, sinon le créer
    if not os.path.exists(BLOCKED_USERS_FILE):
        with open(BLOCKED_USERS_FILE, 'w') as f:
            f.write("# Liste des utilisateurs bloqués (un par ligne)\n")
    
    try:
        while True:
            clear_screen()
            term_width = get_terminal_width()
            
            # En-tête stylisé
            print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
            title = "TABLEAU DE BORD ADMIN - CONTENEURS DOCKER"
            padding = (term_width - len(title)) // 2
            print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
            print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
            
            # Infos de mise à jour
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            refresh_mode = f"Rafraîchissement auto ({refresh_interval}s)" if auto_refresh else "Manuel"
            print(f"Dernière mise à jour: {now} | Mode: {refresh_mode}")
            
            # Récupérer les infos GPU du système - optimisé avec cache
            gpus = get_gpu_info()
            if gpus:
                separator = "+" + "-" * (term_width - 2) + "+"
                print(separator)
                gpu_info = [f"{gpu['name']} ({gpu['mem_util']}%)" for gpu in gpus]
                gpu_summary = f"{Colors.GREEN}✓{Colors.END} {len(gpus)} GPU(s) détecté(s): {', '.join(gpu_info)}"
                print(f"| {gpu_summary}")
            
            # Récupérer les infos conteneurs - en parallèle pour améliorer la performance
            containers = get_containers_parallel("gui_user_")
            display_containers(containers)
            display_menu()
            
            # Attente de l'input utilisateur avec timeout si auto-refresh est activé
            if auto_refresh:
                import select
                import sys
                # Limiter le timeout pour éviter une attente trop longue
                actual_refresh = min(refresh_interval, 60)  # Maximum 60 secondes
                # Attente de l'input avec timeout
                rlist, _, _ = select.select([sys.stdin], [], [], actual_refresh)
                if rlist:
                    # L'utilisateur a saisi quelque chose
                    choice = sys.stdin.readline().strip()
                else:
                    # Timeout - rafraîchissement automatique
                    continue
            else:
                choice = input()
            
            if not choice:
                # Entrée vide = rafraîchir
                continue
            
            if choice.lower() == 'q':
                break
            
            if choice == '1':
                # Rafraîchir - rien à faire, la boucle s'en charge
                pass
            
            elif choice == '2':
                # Démarrer un conteneur
                containers_stopped = [c for c in containers if not c['is_running'] and not c.get('is_blocked', False)]
                container_id = select_container(containers_stopped, "démarrer")
                if container_id:
                    start_container(container_id)
                    time.sleep(1)  # Réduit de 5s à 1s pour plus de réactivité
            
            elif choice == '3':
                # Arrêter un conteneur
                containers_running = [c for c in containers if c['is_running']]
                container_id = select_container(containers_running, "arrêter")
                if container_id:
                    stop_container(container_id)
                    time.sleep(1)  # Réduit de 5s à 1s
            
            elif choice == '4':
                # Voir les logs d'un conteneur
                container_id = select_container(containers, "voir les logs")
                if container_id:
                    show_logs(container_id)
            
            elif choice == '5':
                # Exécuter une commande
                containers_running = [c for c in containers if c['is_running']]
                container_id = select_container(containers_running, "exécuter une commande")
                if container_id:
                    exec_command(container_id)
            
            elif choice == '6':
                # Supprimer un conteneur
                container_id = select_container(containers, "supprimer")
                if container_id:
                    remove_container(container_id)
                    time.sleep(1)  # Réduit de 5s à 1s
            
            elif choice == '7':
                # Tester le GPU d'un conteneur
                containers_running_with_gpu = [c for c in containers if c['is_running'] and c.get('has_gpu', False)]
                container_id = select_container(containers_running_with_gpu, "tester le GPU")
                if container_id:
                    test_gpu(container_id)
                    
            elif choice == '8':
                # Afficher les détails des GPU
                clear_screen()
                term_width = get_terminal_width()
                
                # En-tête stylisé
                print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
                title = "STATUT DÉTAILLÉ DES GPU"
                padding = (term_width - len(title)) // 2
                print(f"{Colors.HEADER}{Colors.BOLD}{' ' * padding}{title}{Colors.END}")
                print(f"{Colors.HEADER}{Colors.BOLD}{'=' * term_width}{Colors.END}")
                
                gpus = get_gpu_info()
                display_gpu_info(gpus)
                
                # Afficher les processus utilisant le GPU
                try:
                    separator = "+" + "-" * (term_width - 2) + "+"
                    print(separator)
                    print(f"| {Colors.BOLD}Processus utilisant le GPU:{Colors.END}")
                    print(separator)
                    
                    # Ajouter un timeout pour éviter le blocage
                    nvidia_smi_proc = subprocess.check_output("nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv", 
                                                            shell=True, 
                                                            timeout=1).decode()
                    for line in nvidia_smi_proc.split('\n'):
                        if line:
                            print(f"| {line}")
                    
                    print(separator)
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    print(f"{Colors.YELLOW}| Impossible de récupérer les processus GPU.{Colors.END}")
                
                input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu principal...{Colors.END}")
            
            elif choice == '9':
                # Gestion des power users
                manage_power_users(containers)
                
            elif choice == '0':
                # Bloquer/débloquer un utilisateur
                manage_blocked_users(containers)
                
            elif choice.lower() == 'a':
                # Ajouter un nouvel utilisateur
                add_new_user()
                
            elif choice.lower() == 'r':
                # Réinitialiser le mot de passe d'un utilisateur
                reset_user_password()
            
            else:
                print(f"{Colors.RED}Choix invalide. Appuie sur Entrée pour continuer...{Colors.END}")
                input()
                
    except KeyboardInterrupt:
        print("\nArrêt du tableau de bord. À bientôt !")
    except Exception as e:
        print(f"{Colors.RED}Une erreur s'est produite: {e}{Colors.END}")

if __name__ == "__main__":
    main()