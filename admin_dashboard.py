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
from datetime import datetime

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
    """Récupère les informations du GPU NVIDIA via nvidia-smi"""
    try:
        cmd = "nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,driver_version --format=csv,noheader,nounits"
        gpu_info = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
        
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
        return gpus
    except Exception as e:
        return []

def get_container_gpu_usage(container_id):
    """Récupère l'utilisation GPU d'un conteneur spécifique"""
    try:
        # Méthode 1: Utiliser nvidia-smi dans le conteneur
        cmd = f"docker exec {container_id} nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
        
        if output:
            # Calculer l'utilisation totale
            total_memory = 0
            for line in output.split('\n'):
                if line.strip():
                    parts = line.split(', ')
                    if len(parts) >= 2:
                        total_memory += int(parts[1])
            
            return "Active", f"{total_memory}MB"
        
        # Méthode 2: Vérifier les PID du conteneur dans nvidia-smi
        # Récupérer tous les PIDs du conteneur
        cmd = f"docker top {container_id} -eo pid | tail -n +2"
        container_pids = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
        
        # Récupérer tous les processus GPU
        cmd = "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits"
        gpu_processes = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
        
        # Vérifier si un PID du conteneur utilise le GPU
        total_memory = 0
        for gpu_proc in gpu_processes:
            if not gpu_proc.strip():
                continue
                
            parts = gpu_proc.split(', ')
            if len(parts) >= 2:
                pid = parts[0].strip()
                if pid in container_pids:
                    total_memory += int(parts[1])
        
        if total_memory > 0:
            return "Active", f"{total_memory}MB"
        
        # Méthode 3: Vérifier si les ressources GPU sont allouées mais pas utilisées
        # Cette partie est un peu plus complexe à implémenter, mais tu pourrais utiliser nvidia-smi -q
        # pour obtenir des informations détaillées sur l'allocation de mémoire par GPU
        
        # Si on arrive ici, le GPU est accessible mais pas utilisé activement
        return "Idle", "0MB"
            
    except Exception as e:
        # print(f"Erreur dans get_container_gpu_usage: {e}")  # Pour debug
        return "N/A", "N/A"

def get_containers_info(filter_prefix="gui_user_"):
    """Récupère les informations sur les conteneurs Docker correspondant au préfixe"""
    cmd = f"docker ps -a --filter name={filter_prefix} --format '{{{{.ID}}}}'"
    container_ids = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
    
    if container_ids == ['']: 
        return []
        
    containers = []
    
    # Récupérer les informations GPU pour les comparer plus tard
    gpu_info = get_gpu_info()
    gpu_available = len(gpu_info) > 0
    
    for container_id in container_ids:
        # Obtenir les informations de base du conteneur
        cmd = f"docker inspect {container_id}"
        container_info = json.loads(subprocess.check_output(cmd, shell=True).decode())
        
        if not container_info:
            continue
            
        container_info = container_info[0]
        
        # Obtenir les statistiques du conteneur
        cmd = f"docker stats {container_id} --no-stream --format \"{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}|{{{{.MemPerc}}}}\""
        try:
            stats_raw = subprocess.check_output(cmd, shell=True).decode().strip()
            cpu_perc, mem_usage, mem_perc = stats_raw.split('|')
        except:
            # Si le conteneur n'est pas en cours d'exécution
            cpu_perc = "0%"
            mem_usage = "0B / 0B"
            mem_perc = "0%"
            
        # Obtenir le nom d'utilisateur à partir du nom du conteneur
        username = container_info['Name'].replace('/', '').replace(filter_prefix, '')
        
        # Vérifier si le conteneur est en cours d'exécution
        is_running = container_info['State']['Status'] == 'running'
        
        # Obtenir le temps de fonctionnement
        if is_running:
            started_at = datetime.fromisoformat(container_info['State']['StartedAt'].replace('Z', '+00:00'))
            uptime = datetime.now().astimezone() - started_at
            uptime_str = str(uptime).split('.')[0]  # Supprimer les microsecondes
        else:
            uptime_str = "arrêté"
        
        # Obtenir le port RDP mappé
        port_mappings = container_info['NetworkSettings']['Ports']
        rdp_port = "N/A"
        
        # Chercher les ports 3389 ou 3390 (RDP standard et alternatif)
        for port_key in ['3389/tcp', '3390/tcp']:
            if port_key in port_mappings and port_mappings[port_key]:
                rdp_port = port_mappings[port_key][0]['HostPort']
                break
        
        # Vérifier si le GPU est activé dans le conteneur
        has_gpu = False
        gpu_util = "N/A"
        gpu_mem = "N/A"

        try:
            # Vérifier les options de GPU dans le conteneur
            if 'HostConfig' in container_info and 'DeviceRequests' in container_info['HostConfig']:
                for device in container_info['HostConfig']['DeviceRequests']:
                    if device.get('Driver') == 'nvidia' or device.get('Count') == -1:  # -1 signifie "all GPUs"
                        has_gpu = True
            
            # Si le GPU est disponible et le conteneur est en cours d'exécution, obtenir l'utilisation
            if gpu_available and is_running and has_gpu:
                gpu_util, gpu_mem = get_container_gpu_usage(container_id)
        except Exception as e:
            pass
        
        # Ajouter les informations du conteneur à la liste
        containers.append({
            'id': container_id[:12],
            'name': container_info['Name'].replace('/', ''),
            'username': username,
            'status': 'En cours' if is_running else 'Arrêté',
            'image': container_info['Config']['Image'],
            'cpu': cpu_perc,
            'mem': mem_usage,
            'mem_perc': mem_perc,
            'uptime': uptime_str,
            'rdp_port': rdp_port,
            'is_running': is_running,
            'has_gpu': has_gpu,
            'gpu_util': gpu_util,
            'gpu_mem': gpu_mem
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
        "ID", "Utilisateur", "Status", "CPU", "Mémoire", "GPU", "Uptime", "Port", "Image"
    ]
    
    # Calculer la largeur de chaque colonne en fonction de la largeur du terminal
    total_fixed_width = 25  # Espace pour les séparateurs et la marge
    widths = [12, 15, 8, 8, 20, 12, 12, 7]
    
    # La colonne Image prend l'espace restant
    image_width = max(15, term_width - sum(widths) - total_fixed_width)
    widths.append(image_width)
    
    # Ligne de séparation
    separator = "+" + "+".join("-" * (w+2) for w in widths) + "+"
    
    # Afficher l'en-tête
    print(separator)
    header_cells = [f" {h:{w}} " for h, w in zip(headers, widths)]
    print(f"|{Colors.BOLD}{'|'.join(header_cells)}{Colors.END}|")
    print(separator)
    
    # Afficher les données de chaque conteneur
    for container in containers:
        status_color = Colors.GREEN if container['is_running'] else Colors.RED
        cpu_color = Colors.RED if container['is_running'] and float(container['cpu'].replace('%', '') or 0) > 80 else Colors.END
        mem_color = Colors.RED if container['is_running'] and float(container['mem_perc'].replace('%', '') or 0) > 80 else Colors.END
        
        # Formatage de l'info GPU
        if container['has_gpu']:
            if container['is_running']:
                if container['gpu_mem'] == "0MB":
                    gpu_info = f"{Colors.CYAN}✓{Colors.END} {Colors.YELLOW}Idle{Colors.END}"
                else:
                    gpu_info = f"{Colors.CYAN}✓{Colors.END} {container['gpu_mem']}"
            else:
                gpu_info = f"{Colors.CYAN}✓{Colors.END} inactif"
        else:
            gpu_info = "✗"
        
        # Tronquer les valeurs trop longues
        username = truncate_text(container['username'], widths[1])
        image = truncate_text(container['image'], widths[8])
        
        # Préparer les cellules
        cells = [
            f" {container['id']:{widths[0]}} ",
            f" {username:{widths[1]}} ",
            f" {status_color}{container['status']:{widths[2]}}{Colors.END} ",
            f" {cpu_color}{container['cpu']:{widths[3]}}{Colors.END} ",
            f" {mem_color}{container['mem']:{widths[4]}}{Colors.END} ",
            f" {gpu_info:{widths[5]}} ",
            f" {container['uptime']:{widths[6]}} ",
            f" {container['rdp_port']:{widths[7]}} ",
            f" {image:{widths[8]}} "
        ]
        
        print(f"|{'|'.join(cells)}|")
    
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
    print(f"| q. Quitter")
    print(separator)
    print("Ton choix : ", end="")

def start_container(container_id):
    """Démarre un conteneur Docker"""
    try:
        subprocess.run(f"docker start {container_id}", shell=True, check=True)
        print(f"{Colors.GREEN}✓ Conteneur {container_id} démarré avec succès.{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}✗ Erreur lors du démarrage du conteneur {container_id}.{Colors.END}")

def stop_container(container_id):
    """Arrête un conteneur Docker"""
    try:
        subprocess.run(f"docker stop {container_id}", shell=True, check=True)
        print(f"{Colors.YELLOW}⚠ Conteneur {container_id} arrêté.{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}✗ Erreur lors de l'arrêt du conteneur {container_id}.{Colors.END}")

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
        gpu_info = f"{Colors.CYAN}[GPU]" if container['has_gpu'] else ""
        print(f"| {i+1}. {container['username']} ({container['id']}) - {status_color}{status}{Colors.END} {gpu_info}")
    
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

def main():
    """Fonction principale du tableau de bord"""
    parser = argparse.ArgumentParser(description="Tableau de bord admin pour conteneurs Docker")
    parser.add_argument('-i', '--interval', type=int, default=60, help='Intervalle de rafraîchissement en secondes (0 pour désactiver)')
    args = parser.parse_args()
    
    refresh_interval = args.interval
    auto_refresh = refresh_interval > 0
    
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
            
            # Récupérer les infos GPU du système
            gpus = get_gpu_info()
            if gpus:
                separator = "+" + "-" * (term_width - 2) + "+"
                print(separator)
                gpu_info = [f"{gpu['name']} ({gpu['mem_util']}%)" for gpu in gpus]
                gpu_summary = f"{Colors.GREEN}✓{Colors.END} {len(gpus)} GPU(s) détecté(s): {', '.join(gpu_info)}"
                print(f"| {gpu_summary}")
            
            # Récupérer les infos conteneurs
            containers = get_containers_info("gui_user_")
            display_containers(containers)
            display_menu()
            
            # Attente de l'input utilisateur avec timeout si auto-refresh est activé
            if auto_refresh:
                import select
                import sys
                # Attente de l'input avec timeout
                rlist, _, _ = select.select([sys.stdin], [], [], refresh_interval)
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
                containers_stopped = [c for c in containers if not c['is_running']]
                container_id = select_container(containers_stopped, "démarrer")
                if container_id:
                    start_container(container_id)
                    time.sleep(1)  # Pause pour voir le message
            
            elif choice == '3':
                # Arrêter un conteneur
                containers_running = [c for c in containers if c['is_running']]
                container_id = select_container(containers_running, "arrêter")
                if container_id:
                    stop_container(container_id)
                    time.sleep(1)
            
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
                    time.sleep(1)
            
            elif choice == '7':
                # Tester le GPU d'un conteneur
                containers_running_with_gpu = [c for c in containers if c['is_running'] and c['has_gpu']]
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
                    
                    nvidia_smi_proc = subprocess.check_output("nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv", shell=True).decode()
                    for line in nvidia_smi_proc.split('\n'):
                        if line:
                            print(f"| {line}")
                    
                    print(separator)
                except:
                    print(f"{Colors.YELLOW}| Impossible de récupérer les processus GPU.{Colors.END}")
                
                input(f"{Colors.BOLD}Appuie sur Entrée pour revenir au menu principal...{Colors.END}")
            
            else:
                print(f"{Colors.RED}Choix invalide. Appuie sur Entrée pour continuer...{Colors.END}")
                input()
                
    except KeyboardInterrupt:
        print("\nArrêt du tableau de bord. À bientôt !")
    except Exception as e:
        print(f"{Colors.RED}Une erreur s'est produite: {e}{Colors.END}")

if __name__ == "__main__":
    main()
