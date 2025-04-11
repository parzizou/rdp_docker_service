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

def get_containers_info(filter_prefix="gui_user_"):
    """Récupère les informations sur les conteneurs Docker correspondant au préfixe"""
    cmd = f"docker ps -a --filter name={filter_prefix} --format '{{{{.ID}}}}'"
    container_ids = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
    
    if container_ids == ['']: 
        return []
        
    containers = []
    
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
            'is_running': is_running
        })
    
    # Trier les conteneurs par statut (En cours d'abord) puis par nom
    containers.sort(key=lambda c: (0 if c['is_running'] else 1, c['name']))
    
    return containers

def display_containers(containers):
    """Affiche un tableau formaté avec les informations des conteneurs"""
    if not containers:
        print(f"{Colors.YELLOW}Aucun conteneur trouvé.{Colors.END}")
        return
    
    # En-têtes de colonne
    headers = [
        "ID", "Utilisateur", "Status", "CPU", "Mémoire", "Uptime", "Port RDP", "Image"
    ]
    
    # Calculer la largeur de chaque colonne
    widths = [12, 15, 8, 8, 20, 12, 8, 25]
    
    # Afficher l'en-tête
    header_line = " | ".join(f"{h:{w}}" for h, w in zip(headers, widths))
    print(f"{Colors.BOLD}{header_line}{Colors.END}")
    print("-" * len(header_line))
    
    # Afficher les données de chaque conteneur
    for container in containers:
        status_color = Colors.GREEN if container['is_running'] else Colors.RED
        cpu_color = Colors.RED if container['is_running'] and float(container['cpu'].replace('%', '') or 0) > 80 else Colors.END
        mem_color = Colors.RED if container['is_running'] and float(container['mem_perc'].replace('%', '') or 0) > 80 else Colors.END
        
        cols = [
            container['id'],
            container['username'],
            f"{status_color}{container['status']}{Colors.END}",
            f"{cpu_color}{container['cpu']}{Colors.END}",
            f"{mem_color}{container['mem']}{Colors.END}",
            container['uptime'],
            container['rdp_port'],
            container['image']
        ]
        
        print(" | ".join(f"{c:{w}}" for c, w in zip(cols, widths)))
    
    print("-" * len(header_line))

def display_menu():
    """Affiche le menu des actions possibles"""
    print(f"\n{Colors.BOLD}Actions disponibles:{Colors.END}")
    print("1. Rafraîchir (ou appuyer sur Entrée)")
    print("2. Démarrer un conteneur")
    print("3. Arrêter un conteneur")
    print("4. Voir les logs d'un conteneur")
    print("5. Exécuter une commande dans un conteneur")
    print("6. Supprimer un conteneur")
    print("q. Quitter")
    print("\nEntrez votre choix : ", end="")

def start_container(container_id):
    """Démarre un conteneur Docker"""
    try:
        subprocess.run(f"docker start {container_id}", shell=True, check=True)
        print(f"{Colors.GREEN}Conteneur {container_id} démarré avec succès.{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}Erreur lors du démarrage du conteneur {container_id}.{Colors.END}")

def stop_container(container_id):
    """Arrête un conteneur Docker"""
    try:
        subprocess.run(f"docker stop {container_id}", shell=True, check=True)
        print(f"{Colors.YELLOW}Conteneur {container_id} arrêté.{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}Erreur lors de l'arrêt du conteneur {container_id}.{Colors.END}")

def show_logs(container_id, lines=50):
    """Affiche les logs d'un conteneur Docker"""
    try:
        logs = subprocess.check_output(f"docker logs --tail={lines} {container_id}", shell=True).decode()
        print(f"{Colors.CYAN}=== Dernières {lines} lignes de logs pour {container_id} ==={Colors.END}")
        print(logs)
        input(f"{Colors.BOLD}Appuyez sur Entrée pour revenir au menu...{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}Erreur lors de la récupération des logs du conteneur {container_id}.{Colors.END}")

def exec_command(container_id, command=None):
    """Exécute une commande dans un conteneur Docker"""
    if not command:
        command = input("Entrez la commande à exécuter (ex: 'ls -la /home'): ")
    
    try:
        print(f"{Colors.CYAN}=== Exécution de '{command}' dans {container_id} ==={Colors.END}")
        subprocess.run(f"docker exec {container_id} {command}", shell=True)
        input(f"{Colors.BOLD}Appuyez sur Entrée pour revenir au menu...{Colors.END}")
    except subprocess.CalledProcessError:
        print(f"{Colors.RED}Erreur lors de l'exécution de la commande dans le conteneur {container_id}.{Colors.END}")

def remove_container(container_id):
    """Supprime un conteneur Docker"""
    confirm = input(f"{Colors.RED}ATTENTION: Voulez-vous vraiment supprimer le conteneur {container_id}? (o/N): {Colors.END}")
    if confirm.lower() == 'o':
        try:
            subprocess.run(f"docker rm -f {container_id}", shell=True, check=True)
            print(f"{Colors.RED}Conteneur {container_id} supprimé.{Colors.END}")
        except subprocess.CalledProcessError:
            print(f"{Colors.RED}Erreur lors de la suppression du conteneur {container_id}.{Colors.END}")
    else:
        print("Suppression annulée.")

def select_container(containers, action_name):
    """Permet à l'utilisateur de sélectionner un conteneur par son numéro"""
    if not containers:
        print(f"{Colors.YELLOW}Aucun conteneur disponible pour cette action.{Colors.END}")
        input("Appuyez sur Entrée pour continuer...")
        return None
    
    print(f"\n{Colors.BOLD}Sélectionnez un conteneur pour {action_name}:{Colors.END}")
    for i, container in enumerate(containers):
        status = "En cours" if container['is_running'] else "Arrêté"
        status_color = Colors.GREEN if container['is_running'] else Colors.RED
        print(f"{i+1}. {container['username']} ({container['id']}) - {status_color}{status}{Colors.END}")
    
    print("0. Annuler")
    
    while True:
        try:
            choice = int(input("\nVotre choix (numéro): "))
            if choice == 0:
                return None
            if 1 <= choice <= len(containers):
                return containers[choice - 1]['id']
            print(f"{Colors.RED}Choix invalide. Veuillez saisir un numéro entre 0 et {len(containers)}.{Colors.END}")
        except ValueError:
            print(f"{Colors.RED}Veuillez saisir un numéro.{Colors.END}")

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
            print(f"{Colors.HEADER}{Colors.BOLD}TABLEAU DE BORD ADMIN - CONTENEURS DOCKER{Colors.END}")
            print(f"Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Mode: {'Rafraîchissement auto (' + str(refresh_interval) + 's)' if auto_refresh else 'Manuel'}")
            print(f"{Colors.BOLD}------------------------------------------------------{Colors.END}\n")
            
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
            
            else:
                print(f"{Colors.RED}Choix invalide. Appuyez sur Entrée pour continuer...{Colors.END}")
                input()
                
    except KeyboardInterrupt:
        print("\nArrêt du tableau de bord.")
    except Exception as e:
        print(f"{Colors.RED}Une erreur s'est produite: {e}{Colors.END}")

if __name__ == "__main__":
    main()
