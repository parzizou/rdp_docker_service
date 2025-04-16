from flask import Flask, request, render_template_string, jsonify
import subprocess
import tempfile
import os
import re
import bcrypt  
import shlex

app = Flask(__name__)

# Constantes pour les fichiers de configuration
POWER_USERS_FILE = "power_users.txt"
USER_FILE = "users.txt"  # Ajout de cette constante pour le fichier utilisateurs

def is_power_user(username):
    """Vérifie si un utilisateur est un power user"""
    try:
        if os.path.exists(POWER_USERS_FILE):
            with open(POWER_USERS_FILE, 'r') as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        parts = line.strip().split(':')
                        if parts[0] == username:
                            return True
    except Exception as e:
        print(f"Erreur lors de la vérification du statut power user: {str(e)}")
    return False

def get_power_user_limits(username):
    """Récupère les limites d'un power user"""
    try:
        if os.path.exists(POWER_USERS_FILE):
            with open(POWER_USERS_FILE, 'r') as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        parts = line.strip().split(':')
                        if parts[0] == username and len(parts) >= 4:
                            return {
                                'cpu': "unlimited",
                                'memory': "unlimited",
                                'gpu_memory': "unlimited"
                            }
    except Exception as e:
        print(f"Erreur lors de la récupération des limites du power user: {str(e)}")
    return None

def get_available_images():
    """Récupère la liste des images disponibles depuis le fichier images.txt"""
    images = []
    try:
        with open('images.txt', 'r') as f:
            for line in f:
                if line.strip() and not line.strip().startswith('#'):
                    parts = line.strip().split(':')
                    if len(parts) >= 2:
                        images.append({
                            'id': parts[0],
                            'name': parts[1]
                        })
    except Exception as e:
        print(f"Erreur lors de la lecture des images: {str(e)}")
        # Fallback à une liste par défaut
        images = [
            {'id': 'xfce_gui_container', 'name': 'Bureau XFCE (Léger)'}
        ]
    return images

def get_system_resources():
    """Récupère les ressources disponibles sur le système"""
    cpu_cores = 0
    memory_gb = 0
    gpu_count = 0
    gpus_info = []
    
    try:
        # Obtenir le nombre de cœurs CPU
        cpu_cores = int(subprocess.check_output("nproc", shell=True, text=True).strip())
        
        # Obtenir la mémoire totale en GB
        mem_kb = int(subprocess.check_output("grep MemTotal /proc/meminfo | awk '{print $2}'", shell=True, text=True).strip())
        memory_gb = round(mem_kb / 1024 / 1024, 1)
        
        # Vérifier si NVIDIA-SMI est disponible
        nvidia_available = subprocess.run("command -v nvidia-smi", shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL).returncode == 0
        
        if nvidia_available:
            # Obtenir le nombre de GPUs
            gpu_count = int(subprocess.check_output("nvidia-smi --query-gpu=name --format=csv,noheader | wc -l", shell=True, text=True).strip())
            
            # Obtenir les détails des GPUs
            if gpu_count > 0:
                gpu_info = subprocess.check_output("nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader", shell=True, text=True).strip()
                for line in gpu_info.split('\n'):
                    if line.strip():
                        parts = line.split(', ')
                        if len(parts) >= 3:
                            gpu_memory = parts[2]
                            # Extraire la valeur numérique de la mémoire (par exemple "16376 MiB" -> 16376)
                            memory_value = re.search(r'(\d+)', gpu_memory)
                            if memory_value:
                                memory_mib = int(memory_value.group(1))
                                gpus_info.append({
                                    'id': parts[0],
                                    'name': parts[1],
                                    'memory': gpu_memory,
                                    'memory_mib': memory_mib
                                })
    except Exception as e:
        print(f"Erreur lors de la récupération des ressources système: {str(e)}")
    
    return {
        'cpu_cores': cpu_cores,
        'memory_gb': memory_gb,
        'gpu_count': gpu_count,
        'gpus': gpus_info
    }

# Nouvelles fonctions pour la gestion des mots de passe temporaires
def user_exists(username):
    """Vérifie si un utilisateur existe"""
    try:
        if os.path.exists(USER_FILE):
            with open(USER_FILE, 'r') as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        parts = line.strip().split(':')
                        if parts[0] == username:
                            return True
    except Exception as e:
        print(f"Erreur lors de la vérification de l'existence de l'utilisateur: {str(e)}")
    return False

def get_user_password(username):
    """Récupère le mot de passe haché d'un utilisateur"""
    try:
        if os.path.exists(USER_FILE):
            with open(USER_FILE, 'r') as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        parts = line.strip().split(':')
                        if parts[0] == username and len(parts) >= 2:
                            return parts[1]
    except Exception as e:
        print(f"Erreur lors de la récupération du mot de passe: {str(e)}")
    return None

def is_temp_password(username):
    """Vérifie si l'utilisateur doit changer son mot de passe"""
    try:
        result = subprocess.run(
            f"bash -c 'source ./password_utils.sh && is_temp_password \"{username}\" && echo true || echo false'",
            shell=True, 
            capture_output=True,
            text=True
        )
        return result.stdout.strip() == "true"
    except Exception as e:
        print(f"Erreur lors de la vérification du statut du mot de passe: {str(e)}")
        return False

def change_password(username, new_password):
    """Change le mot de passe d'un utilisateur"""
    try:
        # Appeler le script utilitaire pour changer le mot de passe
        result = subprocess.run(
            f"bash -c 'source ./password_utils.sh && change_password \"{username}\" \"{new_password}\"'",
            shell=True, 
            capture_output=True,
            text=True
        )
        
        # Vérifier si la commande a réussi
        if result.returncode == 0:
            print(f"Mot de passe changé avec succès pour {username}, output: {result.stdout}")
            return True
        else:
            print(f"Erreur lors du changement de mot de passe: {result.stderr}")
            return False
    except Exception as e:
        print(f"Exception lors du changement de mot de passe: {str(e)}")
        return False


# Template HTML
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bureaux Virtuels Linux</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root {
            --primary-color: #4361ee;
            --secondary-color: #3f37c9;
            --success-color: #4caf50;
            --warning-color: #f39c12;
            --danger-color: #e74c3c;
            --light-color: #f8f9fa;
            --dark-color: #343a40;
            --border-radius: 8px;
            --box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            --transition: all 0.3s ease;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f0f2f5;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
        }
        
        h1, h2, h3 {
            color: var(--dark-color);
            margin-bottom: 1rem;
        }
        
        h1 {
            font-size: 2.2rem;
            text-align: center;
            margin: 1.5rem 0;
            color: var(--primary-color);
            position: relative;
        }
        
        h1::after {
            content: '';
            display: block;
            width: 80px;
            height: 4px;
            background: var(--primary-color);
            margin: 10px auto;
            border-radius: 2px;
        }
        
        .container {
            background-color: white;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            padding: 25px;
            margin-bottom: 25px;
            transition: var(--transition);
        }
        
        .container:hover {
            box-shadow: 0 6px 10px rgba(0, 0, 0, 0.15);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--dark-color);
        }
        
        input, select {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: var(--border-radius);
            font-size: 16px;
            transition: var(--transition);
        }
        
        input:focus, select:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        button {
            background-color: var(--primary-color);
            color: white;
            padding: 12px 25px;
            border: none;
            border-radius: var(--border-radius);
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            transition: var(--transition);
            display: block;
            width: 100%;
            max-width: 300px;
            margin: 20px auto 0;
            text-transform: uppercase;
        }
        
        button:hover {
            background-color: var(--secondary-color);
            transform: translateY(-2px);
        }
        
        pre {
            background-color: #f8f9fa;
            border: 1px solid #ddd;
            padding: 15px;
            border-radius: var(--border-radius);
            white-space: pre-wrap;
            min-height: 200px;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.5;
        }
        
        .info-box {
            background-color: #e8f4fd;
            border-left: 6px solid var(--primary-color);
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 var(--border-radius) var(--border-radius) 0;
        }
        
        .checkbox-container {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .checkbox-container input {
            width: auto;
            margin-right: 10px;
            cursor: pointer;
        }
        
        .resource-box {
            background-color: #f0f8ff;
            padding: 20px;
            border-radius: var(--border-radius);
            margin-bottom: 25px;
            border: 1px solid #d0e1f9;
        }
        
        .resource-slider {
            width: 100%;
            height: 8px;
            -webkit-appearance: none;
            appearance: none;
            background: #d3d3d3;
            outline: none;
            border-radius: 10px;
            margin: 10px 0;
        }
        
        .resource-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--primary-color);
            cursor: pointer;
            transition: var(--transition);
        }
        
        .resource-slider::-webkit-slider-thumb:hover {
            background: var(--secondary-color);
            transform: scale(1.2);
        }
        
        .resource-slider::-moz-range-thumb {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: var(--primary-color);
            cursor: pointer;
            transition: var(--transition);
        }
        
        .resource-limits {
            margin-top: 15px;
            padding: 15px;
            background-color: #f9f9f9;
            border-radius: var(--border-radius);
            border: 1px solid #eee;
        }
        
        .resource-info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }
        
        .resource-info:last-child {
            border-bottom: none;
        }
        
        .resource-info span:first-child {
            font-weight: bold;
        }
        
        /* Style pour les options prédéfinies de GPU */
        .gpu-presets {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }
        
        .gpu-preset-btn {
            flex: 1;
            min-width: 100px;
            padding: 12px 8px;
            border: 1px solid #ddd;
            border-radius: var(--border-radius);
            background-color: white;
            cursor: pointer;
            text-align: center;
            transition: var(--transition);
            font-weight: 500;
        }
        
        .gpu-preset-btn:hover {
            background-color: #f8f8f8;
            border-color: #ccc;
            transform: translateY(-2px);
        }
        
        .gpu-preset-btn.active {
            background-color: var(--primary-color);
            color: white;
            border-color: var(--secondary-color);
        }
        
        .hidden {
            display: none !important;
        }
        
        .alert-info {
            background-color: #fff3cd;
            border-left: 6px solid var(--warning-color);
            padding: 15px;
            margin: 20px 0;
            font-size: 0.95em;
            border-radius: 0 var(--border-radius) var(--border-radius) 0;
        }
        
        .power-user-badge {
            display: inline-block;
            background-color: var(--warning-color);
            color: white;
            padding: 3px 8px;
            border-radius: 4px;
            font-weight: bold;
            margin-left: 10px;
            font-size: 0.8em;
            vertical-align: middle;
        }
        
        /* Section de résultat avec un style amélioré */
        .result-container {
            position: relative;
        }
        
        .result-container h2 {
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .result-container h2 i {
            margin-right: 10px;
            color: var(--primary-color);
        }
        
        /* Responsive design */
        @media (max-width: 768px) {
            body {
                padding: 10px;
            }
            
            .container {
                padding: 15px;
            }
            
            .gpu-presets {
                flex-direction: column;
                gap: 8px;
            }
            
            h1 {
                font-size: 1.8rem;
            }
        }
        
        /* Animation pour l'exécution en cours */
        @keyframes pulse {
            0% { opacity: 0.6; }
            50% { opacity: 1; }
            100% { opacity: 0.6; }
        }
        
        .executing {
            animation: pulse 1.5s infinite;
        }
        
        /* Style pour les détails des GPUs */
        details {
            margin-top: 10px;
        }
        
        summary {
            cursor: pointer;
            padding: 8px 0;
            font-weight: bold;
            color: var(--primary-color);
        }
        
        details ul {
            list-style-type: none;
            padding: 10px;
            margin-top: 8px;
            background: white;
            border-radius: var(--border-radius);
            border: 1px solid #e0e0e0;
        }
        
        details li {
            padding: 6px 0;
            border-bottom: 1px solid #eee;
        }
        
        details li:last-child {
            border-bottom: none;
        }
        
        /* Pointes informatives */
        .tip {
            position: relative;
            display: inline-block;
            margin-left: 5px;
            cursor: help;
        }
        
        .tip i {
            color: var(--primary-color);
            font-size: 14px;
        }
        
        .tip .tooltip {
            visibility: hidden;
            width: 200px;
            background-color: var(--dark-color);
            color: white;
            text-align: center;
            border-radius: 6px;
            padding: 5px;
            position: absolute;
            z-index: 1;
            bottom: 125%;
            left: 50%;
            margin-left: -100px;
            opacity: 0;
            transition: opacity 0.3s;
            font-size: 12px;
            font-weight: normal;
        }
        
        .tip:hover .tooltip {
            visibility: visible;
            opacity: 1;
        }
        
        /* Switch toggle pour le GPU */
        .switch {
            position: relative;
            display: inline-block;
            width: 54px;
            height: 28px;
            margin-right: 10px;
        }
        
        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 34px;
        }
        
        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        
        input:checked + .slider {
            background-color: var(--primary-color);
        }
        
        input:focus + .slider {
            box-shadow: 0 0 1px var(--primary-color);
        }
        
        input:checked + .slider:before {
            transform: translateX(26px);
        }
        
        /* Style pour l'affichage des valeurs */
        .value-display {
            display: block;
            font-size: 0.9em;
            color: #666;
            text-align: right;
            margin-top: 5px;
        }
        
        /* Modal pour le changement de mot de passe */
        .modal {
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .modal-content {
            background-color: white;
            padding: 30px;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            width: 90%;
            max-width: 500px;
        }
        
        .error-message {
            color: #e74c3c;
            margin-top: 15px;
            padding: 10px;
            background-color: #fde2e2;
            border-radius: 4px;
            text-align: center;
        }
    </style>
</head>
<body>
    <h1><i class="fas fa-desktop"></i> Gestion des bureaux virtuels</h1>
    
    
    
    <div class="resource-box">
        <h3><i class="fas fa-server"></i> Ressources disponibles sur le système</h3>
        <div class="resource-info">
            <span><i class="fas fa-microchip"></i> CPU:</span>
            <span>{{ resources.cpu_cores }} cœurs</span>
        </div>
        <div class="resource-info">
            <span><i class="fas fa-memory"></i> Mémoire:</span>
            <span>{{ resources.memory_gb }} GB</span>
        </div>
        <div class="resource-info">
            <span><i class="fas fa-tv"></i> GPU:</span>
            <span>{{ resources.gpu_count }} disponible(s)</span>
        </div>
        {% if resources.gpus %}
        <details>
            <summary><i class="fas fa-info-circle"></i> Détails des GPU</summary>
            <ul>
            {% for gpu in resources.gpus %}
                <li><i class="fas fa-microchip"></i> GPU {{ gpu.id }}: {{ gpu.name }} ({{ gpu.memory }})</li>
            {% endfor %}
            </ul>
        </details>
        {% endif %}
    </div>
    
    <div class="alert-info">
        <p><strong><i class="fas fa-info-circle"></i> Note :</strong> 
        {% if is_power_user %}
            <span class="power-user-badge"><i class="fas fa-bolt"></i> POWER USER</span> Vous avez accès à des ressources étendues : 
            CPU jusqu'à {{ power_limits.cpu }} cœurs, 
            {{ power_limits.memory }} de RAM et 
            {{ power_limits.gpu_memory }} MiB de mémoire GPU.
        {% else %}
            Pour assurer une répartition équitable des ressources, les limites maximales sont fixées à 4 cœurs CPU, 4 GB de RAM et 4 GB de mémoire GPU. Si vous désirez plus de ressources, contactez le techlab.
        {% endif %}
        </p>
    </div>


    <div class="container">
        <form id="scriptForm">
            <!-- MODIFICATION ICI: On supprime l'option de choix entre connexion et création de compte -->
            <input type="hidden" id="choice" name="choice" value="1">
            
            <div class="form-group">
                <label for="username"><i class="fas fa-user"></i> Nom d'utilisateur :</label>
                <input type="text" id="username" name="username" required placeholder="Entrez votre nom d'utilisateur">
            </div>
            
            <div class="form-group">
                <label for="password"><i class="fas fa-lock"></i> Mot de passe :</label>
                <input type="password" id="password" name="password" required placeholder="Entrez votre mot de passe">
            </div>
            
            <div class="form-group">
                <label for="image"><i class="fas fa-desktop"></i> Type de bureau virtuel :</label>
                <select id="image" name="image">
                    {% for image in images %}
                    <option value="{{ image.id }}">{{ image.name }}</option>
                    {% endfor %}
                </select>
            </div>
            
            <div class="resource-limits">
                <h3><i class="fas fa-sliders-h"></i> Limites de ressources</h3>
                
                <div class="form-group">
                    <label for="cpu_limit">
                        <i class="fas fa-microchip"></i> Nombre de cœurs CPU {% if is_power_user %}(max: {{ power_limits.cpu }}){% else %}(max: 4){% endif %}:
                        <div class="tip">
                            <i class="fas fa-question-circle"></i>
                            <span class="tooltip">Plus vous allouez de cœurs CPU, plus votre bureau virtuel sera réactif pour les tâches parallèles.</span>
                        </div>
                    </label>
                    <input type="range" id="cpu_limit" name="cpu_limit" min="0.1" {% if is_power_user %}max="{{ power_cpu_max }}"{% else %}max="4"{% endif %} step="0.1" value="1" class="resource-slider">
                    <span id="cpu_value" class="value-display">1 cœur(s)</span>
                </div>
                
                <div class="form-group">
                    <label for="memory_limit">
                        <i class="fas fa-memory"></i> Mémoire RAM {% if is_power_user %}(max: {{ power_limits.memory }}){% else %}(max: 4GB){% endif %}:
                        <div class="tip">
                            <i class="fas fa-question-circle"></i>
                            <span class="tooltip">Plus de RAM permet d'exécuter plus d'applications simultanément sans ralentissement.</span>
                        </div>
                    </label>
                    <input type="range" id="memory_limit" name="memory_limit" min="0.5" {% if is_power_user %}max="{{ power_memory_max }}"{% else %}max="4"{% endif %} step="0.5" value="2" class="resource-slider">
                    <span id="memory_value" class="value-display">2 GB</span>
                </div>
                
                <div class="checkbox-container">
                    <label class="switch">
                        <input type="checkbox" id="use_gpu" name="use_gpu" value="true" {% if resources.gpu_count == 0 %}disabled{% endif %}>
                        <span class="slider"></span>
                    </label>
                    <label for="use_gpu">
                        <i class="fas fa-tv"></i> Utiliser le GPU 
                        {% if resources.gpu_count == 0 %}(aucun GPU disponible){% endif %}
                        <div class="tip">
                            <i class="fas fa-question-circle"></i>
                            <span class="tooltip">Le GPU accélère le rendu graphique et certains calculs spécifiques.</span>
                        </div>
                    </label>
                </div>
                
                <div id="gpu-options" class="hidden">
                    {% if resources.gpus and resources.gpus|length > 0 %}
                    <div class="form-group">
                        <label for="gpu_memory_limit">
                            <i class="fas fa-microchip"></i> Mémoire GPU à utiliser :
                            <div class="tip">
                                <i class="fas fa-question-circle"></i>
                                <span class="tooltip">Plus de mémoire GPU permet de gérer des applications graphiques plus complexes.</span>
                            </div>
                        </label>
                        <input type="hidden" id="gpu_memory_limit" name="gpu_memory_limit" value="0">
                        
                        <div class="gpu-presets">
                            <div class="gpu-preset-btn active" data-value="0">
                                <i class="fas fa-rocket"></i> Maximum<br>{% if is_power_user %}({{ power_limits.gpu_memory }} MiB){% else %}(4GB max){% endif %}
                            </div>
                            <div class="gpu-preset-btn" data-value="1024">
                                <i class="fas fa-feather"></i> Faible<br>(1GB)
                            </div>
                            <div class="gpu-preset-btn" data-value="2048">
                                <i class="fas fa-balance-scale"></i> Moyen<br>(2GB)
                            </div>
                            <div class="gpu-preset-btn" data-value="3072">
                                <i class="fas fa-fire"></i> Élevé<br>(3GB)
                            </div>
                        </div>
                        <p class="value-display">
                            Mémoire GPU sélectionnée : <span id="gpu_memory_display">Pas de limite {% if is_power_user %}({{ power_limits.gpu_memory }} MiB max){% else %}(4GB max){% endif %}</span>
                        </p>
                    </div>
                    {% endif %}
                </div>
            </div>
            
            <button type="submit"><i class="fas fa-play"></i> Se Connecter</button>
        </form>
    </div>
    
    <div class="container result-container">
        <h2><i class="fas fa-terminal"></i> Résultat</h2>
        <pre id="output">Le résultat de l'exécution apparaîtra ici...</pre>
    </div>
    
    <div class="info-box">
        <h3><i class="fas fa-question-circle"></i> Comment se connecter</h3>
        <p>Après t'être connecté, un Docker sera mis à ta disposition.</p>
        <p>Pour t'y connecter :</p>
        
        <i class="fas fa-download"></i> Utilise un client RDP comme Remmina, Microsoft Remote Desktop ou FreeRDP
        <br>
        <i class="fas fa-plug"></i> Connecte-toi à l'adresse IP et au port indiqués dans les résultats
        <br>
        <i class="fas fa-key"></i> Utilise ton nom d'utilisateur et mot de passe que tu as définis ici
        
        <p><i class="fas fa-lightbulb"></i> Astuce : plus tu alloues de ressources, plus ton bureau virtuel sera rapide, mais ça consomme plus de ressources du serveur !</p>
    </div>
    
    <!-- Modal pour le changement de mot de passe (caché par défaut) -->
    <div id="password-change-modal" class="modal hidden">
        <div class="modal-content">
            <h3><i class="fas fa-key"></i> Changement de mot de passe requis</h3>
            <p>Tu utilises un mot de passe temporaire. Merci de le changer pour continuer.</p>
            <form id="password-change-form">
                <div class="form-group">
                    <label for="current-password">Mot de passe actuel :</label>
                    <input type="password" id="current-password" name="current_password" required>
                </div>
                <div class="form-group">
                    <label for="new-password">Nouveau mot de passe :</label>
                    <input type="password" id="new-password" name="new_password" required>
                </div>
                <div class="form-group">
                    <label for="confirm-password">Confirmer le nouveau mot de passe :</label>
                    <input type="password" id="confirm-password" name="confirm_password" required>
                </div>
                <button type="submit">Changer le mot de passe</button>
            </form>
            <div id="password-change-error" class="error-message hidden"></div>
        </div>
    </div>

    <script>

        document.addEventListener('DOMContentLoaded', function() {
            // S'assurer que la case use_gpu est décochée au chargement
            document.getElementById('use_gpu').checked = false;
            
            // S'assurer que les options GPU sont cachées au chargement
            document.getElementById('gpu-options').classList.add('hidden');
        });

        // Fonction pour vérifier le statut power user
        async function checkPowerUserStatus() {
            const username = document.getElementById('username').value;
            if (!username) return;
            
            try {
                const response = await fetch(`/check_power_user?username=${encodeURIComponent(username)}`);
                const data = await response.json();
                
                // Mettre à jour les sliders CPU et mémoire en fonction du statut power user
                const cpuSlider = document.getElementById('cpu_limit');
                const memSlider = document.getElementById('memory_limit');
                const gpuOptions = document.querySelector('.gpu-presets');
                
                if (data.is_power_user) {
                    // Mettre à jour les valeurs max pour power user
                    cpuSlider.max = data.limits.cpu > 0 ? data.limits.cpu : 8;
                    memSlider.max = data.limits.memory.replace('g', '');
                    
                    // Ajouter un badge power user
                    const alertBox = document.querySelector('.alert-info p');
                    if (!alertBox.querySelector('.power-user-badge')) {
                        const badge = document.createElement('span');
                        badge.className = 'power-user-badge';
                        badge.innerHTML = '<i class="fas fa-bolt"></i> POWER USER';
                        alertBox.innerHTML = '<strong><i class="fas fa-info-circle"></i> Note :</strong> ';
                        alertBox.appendChild(badge);
                        alertBox.innerHTML += ` Vous avez accès à des ressources étendues : CPU jusqu'à ${data.limits.cpu} cœurs, ${data.limits.memory} de RAM et ${data.limits.gpu_memory} MiB de mémoire GPU.`;
                    }
                    
                    // Mettre à jour le message du GPU
                    const gpuDisplay = document.getElementById('gpu_memory_display');
                    if (gpuDisplay.textContent.includes('Pas de limite')) {
                        gpuDisplay.textContent = `Pas de limite (${data.limits.gpu_memory} MiB max)`;
                    }
                    
                    // Mettre à jour les préréglages GPU s'ils existent
                    const presetButtons = document.querySelectorAll('.gpu-preset-btn');
                    if (presetButtons.length > 0) {
                        presetButtons[0].innerHTML = `<i class="fas fa-rocket"></i> Maximum<br>(${data.limits.gpu_memory} MiB)`;
                        
                        // Ajouter un bouton pour le max power user s'il n'existe pas déjà
                        if (parseInt(data.limits.gpu_memory) > 4096) {
                            let powerButton = null;
                            for (const btn of presetButtons) {
                                if (parseInt(btn.dataset.value) > 4096) {
                                    powerButton = btn;
                                    break;
                                }
                            }
                        }
                    }
                } else {
                    // Réinitialiser aux valeurs standard pour utilisateur normal
                    cpuSlider.max = 4;
                    memSlider.max = 4;
                    
                    // Mettre à jour le message d'alerte
                    const alertBox = document.querySelector('.alert-info p');
                    alertBox.innerHTML = '<strong><i class="fas fa-info-circle"></i> Note :</strong> Pour assurer une répartition équitable des ressources, les limites maximales sont fixées à 4 cœurs CPU, 4 GB de RAM et 4 GB de mémoire GPU. Si vous désirez plus de ressources, contactez le techlab.';
                    
                    // Mettre à jour le message du GPU
                    const gpuDisplay = document.getElementById('gpu_memory_display');
                    if (gpuDisplay.textContent.includes('Pas de limite')) {
                        gpuDisplay.textContent = 'Pas de limite (4GB max)';
                    }
                    
                    // Mettre à jour les préréglages GPU s'ils existent
                    const presetButtons = document.querySelectorAll('.gpu-preset-btn');
                    if (presetButtons.length > 0) {
                        presetButtons[0].innerHTML = '<i class="fas fa-rocket"></i> Maximum<br>(4GB max)';
                    }
                    
                }
            } catch (error) {
                console.error('Erreur lors de la vérification du statut power user:', error);
            }
        }
        
        // Fonction pour vérifier si le mot de passe est temporaire
        async function checkTempPassword(username) {
            try {
                const response = await fetch(`/check_temp_password?username=${encodeURIComponent(username)}`);
                const data = await response.json();
                
                if (data.is_temp_password) {
                    // Afficher la modal de changement de mot de passe
                    document.getElementById('password-change-modal').classList.remove('hidden');
                }
            } catch (error) {
                console.error('Erreur lors de la vérification du mot de passe temporaire:', error);
            }
        }
        
        // Vérifier le statut power user quand le nom d'utilisateur change
        document.getElementById('username').addEventListener('blur', checkPowerUserStatus);
        
        // Mise à jour des valeurs affichées pour les sliders
        document.getElementById('cpu_limit').addEventListener('input', function() {
            document.getElementById('cpu_value').textContent = this.value + ' cœur(s)';
        });
        
        document.getElementById('memory_limit').addEventListener('input', function() {
            document.getElementById('memory_value').textContent = this.value + ' GB';
        });
        
        // Afficher/masquer les options GPU
        document.getElementById('use_gpu').addEventListener('change', function() {
            document.getElementById('gpu-options').classList.toggle('hidden', !this.checked);
        });
        
        // Gestion des préréglages de mémoire GPU
        const gpuPresetButtons = document.querySelectorAll('.gpu-preset-btn');
        const gpuMemoryInput = document.getElementById('gpu_memory_limit');
        const gpuMemoryDisplay = document.getElementById('gpu_memory_display');
        
        gpuPresetButtons.forEach(button => {
            button.addEventListener('click', function() {
                // Désactiver tous les boutons
                gpuPresetButtons.forEach(btn => btn.classList.remove('active'));
                
                // Activer ce bouton
                this.classList.add('active');
                
                // Mettre à jour la valeur
                const memValue = this.getAttribute('data-value');
                gpuMemoryInput.value = memValue;
                
                // Mettre à jour l'affichage
                if (memValue == 0) {
                    const username = document.getElementById('username').value;
                    fetch(`/check_power_user?username=${encodeURIComponent(username)}`)
                        .then(response => response.json())
                        .then(data => {
                            if (data.is_power_user) {
                                gpuMemoryDisplay.textContent = `Pas de limite (${data.limits.gpu_memory} MiB max)`;
                            } else {
                                gpuMemoryDisplay.textContent = "Pas de limite (4GB max)";
                            }
                        })
                        .catch(() => {
                            gpuMemoryDisplay.textContent = "Pas de limite (4GB max)";
                        });
                } else {
                    gpuMemoryDisplay.textContent = memValue + " MiB";
                }
            });
        });
        
        // Lorsque le formulaire est soumis, stocker le nom d'utilisateur
        document.getElementById('scriptForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const outputElement = document.getElementById('output');
            const username = document.getElementById('username').value;
            
            // Stocker le nom d'utilisateur pour vérifier ensuite
            localStorage.setItem('last_username', username);
            
            outputElement.textContent = "Exécution en cours... ça peut prendre quelques secondes, patiente un peu...";
            outputElement.classList.add('executing');
            
            fetch('/execute', {
                method: 'POST',
                body: formData
            })
            .then(response => response.text())
            .then(data => {
                outputElement.classList.remove('executing');
                outputElement.textContent = data;
                
                // Scroll to result
                document.querySelector('.result-container').scrollIntoView({ behavior: 'smooth' });
                
                // Vérifier si on doit afficher la modal de changement de mot de passe
                if (data.includes('Connexion réussie') || data.includes('Connecte-toi avec RDP')) {
                    checkTempPassword(username);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                outputElement.classList.remove('executing');
                outputElement.textContent = 'Erreur: ' + error;
            });
        });
        
        // Gérer la soumission du formulaire de changement de mot de passe
        document.getElementById('password-change-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const username = localStorage.getItem('last_username');
            const currentPassword = document.getElementById('current-password').value;
            const newPassword = document.getElementById('new-password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            
            // Afficher un message pendant le traitement
            const errorElement = document.getElementById('password-change-error');
            errorElement.textContent = "Traitement en cours...";
            errorElement.style.backgroundColor = "#f0f8ff";  // Bleu clair
            errorElement.style.color = "#333";
            errorElement.classList.remove('hidden');
            
            // Validation simple côté client
            if (newPassword !== confirmPassword) {
                errorElement.textContent = 'Les mots de passe ne correspondent pas';
                errorElement.style.backgroundColor = "#fde2e2";
                errorElement.style.color = "#e74c3c";
                return;
            }
            
            if (newPassword.length < 8) {
                errorElement.textContent = 'Le mot de passe doit contenir au moins 8 caractères';
                errorElement.style.backgroundColor = "#fde2e2";
                errorElement.style.color = "#e74c3c";
                return;
            }
            
            // Envoyer la requête de changement de mot de passe
            try {
                const formData = new FormData();
                formData.append('username', username);
                formData.append('current_password', currentPassword);
                formData.append('new_password', newPassword);
                formData.append('confirm_password', confirmPassword);
                
                console.log("Envoi de la requête de changement de mot de passe...");
                
                const response = await fetch('/change_password', {
                    method: 'POST',
                    body: formData
                });
                
                console.log("Réponse reçue:", response.status);
                
                const responseText = await response.text();
                console.log("Contenu de la réponse:", responseText);
                
                if (response.ok) {
                    // Cacher la modal et afficher un message de succès
                    document.getElementById('password-change-modal').classList.add('hidden');
                    alert('Mot de passe changé avec succès! Tu peux maintenant te connecter avec ton nouveau mot de passe.');
                } else {
                    errorElement.textContent = responseText;
                    errorElement.style.backgroundColor = "#fde2e2";
                    errorElement.style.color = "#e74c3c";
                }
            } catch (error) {
                console.error('Erreur lors du changement de mot de passe:', error);
                errorElement.textContent = 'Erreur de communication avec le serveur';
                errorElement.style.backgroundColor = "#fde2e2";
                errorElement.style.color = "#e74c3c";
            }
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    images = get_available_images()
    resources = get_system_resources()
    return render_template_string(HTML_TEMPLATE, 
                                 images=images, 
                                 resources=resources,
                                 is_power_user=False,
                                 power_limits={'cpu': '12', 'memory': '32g', 'gpu_memory': '16376'},
                                 power_cpu_max=8,
                                 power_memory_max=16,
                                 power_gpu_max=8192)

@app.route('/check_power_user')
def check_power_user():
    """Vérifie si un utilisateur est un power user et retourne ses limites"""
    username = request.args.get('username', '')
    
    power_status = is_power_user(username)
    limits = get_power_user_limits(username) if power_status else {'cpu': '4', 'memory': '4g', 'gpu_memory': '4096'}
    
    if not limits:
        limits = {'cpu': '12', 'memory': '32g', 'gpu_memory': '16376'}
    
    # Convertir les valeurs en nombres pour le JavaScript
    cpu_max = limits['cpu']
    if cpu_max == 'unlimited':
        cpu_max = 16  # Valeur par défaut si illimité
    else:
        try:
            cpu_max = float(cpu_max)
        except:
            cpu_max = 8
    
    memory_max = limits['memory'].replace('g', '')
    if memory_max == 'unlimited':
        memory_max = 32  # Valeur par défaut si illimité
    else:
        try:
            memory_max = float(memory_max)
        except:
            memory_max = 8
    
    gpu_max = limits['gpu_memory']
    if gpu_max == 'unlimited':
        gpu_max = 16376  # Valeur par défaut si illimité
    else:
        try:
            gpu_max = int(gpu_max)
        except:
            gpu_max = 4096
    
    return {
        'is_power_user': power_status,
        'limits': limits,
        'cpu_max': cpu_max,
        'memory_max': memory_max,
        'gpu_max': gpu_max
    }

@app.route('/check_temp_password')
def check_temp_password():
    """Vérifie si un utilisateur doit changer son mot de passe"""
    username = request.args.get('username', '')
    return jsonify({'is_temp_password': is_temp_password(username)})

@app.route('/change_password', methods=['POST'])
def change_password_route():
    """Route pour changer le mot de passe"""
    username = request.form.get('username', '')
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    print(f"Tentative de changement de mot de passe pour: {username}")
    
    # Vérifier si l'utilisateur existe - utiliser subprocess.run avec des arguments séparés
    try:
        user_check = subprocess.run(
            ["bash", "-c", f"source ./password_utils.sh && user_exists {shlex.quote(username)} && echo true || echo false"],
            capture_output=True,
            text=True
        )
        user_exists = user_check.stdout.strip() == "true"
        if not user_exists:
            print(f"Utilisateur {username} inconnu")
            return "Utilisateur inconnu", 400
    except Exception as e:
        print(f"Erreur lors de la vérification de l'utilisateur: {str(e)}")
        return f"Erreur lors de la vérification de l'utilisateur: {str(e)}", 500
    
    # Vérifier le mot de passe actuel
    try:
        get_pwd_cmd = ["bash", "-c", f"source ./password_utils.sh && get_user_password {shlex.quote(username)}"]
        stored_hash = subprocess.check_output(get_pwd_cmd, text=True).strip()
        print(f"Hash récupéré pour {username}: {stored_hash}")
        
        # Utiliser directement bcrypt en Python
        is_valid = bcrypt.checkpw(current_password.encode(), stored_hash.encode())
        print(f"Résultat de la vérification: {is_valid}")
        
        if not is_valid:
            return "Mot de passe actuel incorrect", 400
    except Exception as e:
        print(f"Erreur lors de la vérification du mot de passe: {str(e)}")
        return f"Erreur lors de la vérification du mot de passe: {str(e)}", 500
    
    # Vérifier que les nouveaux mots de passe correspondent
    if new_password != confirm_password:
        return "Les nouveaux mots de passe ne correspondent pas", 400
    
    # Vérifier que le nouveau mot de passe est suffisamment fort
    if len(new_password) < 8:
        return "Le nouveau mot de passe doit contenir au moins 8 caractères", 400
    
    # Changer le mot de passe - utiliser subprocess.run avec des arguments séparés
    print(f"Tentative de changement du mot de passe pour {username}")
    try:
        result = subprocess.run(
            ["bash", "-c", f"source ./password_utils.sh && change_password {shlex.quote(username)} {shlex.quote(new_password)}"],
            capture_output=True,
            text=True
        )
        success = result.returncode == 0
    except Exception as e:
        print(f"Exception lors du changement de mot de passe: {str(e)}")
        success = False
    
    if success:
        print(f"Mot de passe changé avec succès pour {username}")
        return "Mot de passe changé avec succès", 200
    else:
        print(f"Erreur lors du changement de mot de passe pour {username}")
        return "Erreur lors du changement de mot de passe", 500

@app.route('/execute', methods=['POST'])
def execute_script():
    # Nous forçons maintenant le choix 1 (connexion uniquement)
    choice = "1"
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    image = request.form.get('image', 'xfce_gui_container')
    
    # Récupérer l'option GPU (cochée = "true", non-cochée = None)
    use_gpu = "o" if request.form.get('use_gpu') == "true" else "n"
    
    # Vérifier si c'est un power user
    power_user_status = is_power_user(username)
    power_limits = get_power_user_limits(username) if power_user_status else None

    # Si l'utilisateur est un power user mais qu'on n'a pas de limites, définir des valeurs par défaut
    if power_user_status and not power_limits:
        power_limits = {'cpu': 'unlimited', 'memory': 'unlimited', 'gpu_memory': 'unlimited'}
    
    # Récupérer les limites de ressources
    try:
        cpu_limit = float(request.form.get('cpu_limit', '1'))
        memory_limit = float(request.form.get('memory_limit', '2'))
    except ValueError:
        # Protection contre les valeurs non numériques
        return "Valeurs de ressources non valides", 400
    
    # Appliquer les limites en fonction du statut power user
    if power_user_status and power_limits:
        # Pour un power user, vérifier les limites spéciales
        cpu_max = power_limits['cpu']
        if cpu_max != 'unlimited':
            try:
                cpu_max = float(cpu_max)
                cpu_limit = min(cpu_limit, cpu_max)
            except:
                pass  # Garde la valeur entrée si la conversion échoue
        
        memory_max = power_limits['memory'].replace('g', '')
        if memory_max != 'unlimited':
            try:
                memory_max = float(memory_max)
                memory_limit = min(memory_limit, memory_max)
            except:
                pass  # Garde la valeur entrée si la conversion échoue
    else:
        # Pour un utilisateur normal, limiter à 4 cœurs CPU et 4 GB RAM
        cpu_limit = min(cpu_limit, 4.0)
        memory_limit = min(memory_limit, 4.0)
    
    # Formater la mémoire
    memory_limit = f"{memory_limit}g"  # Ajouter 'g' pour gigabytes
    
    # Gérer la mémoire GPU selon le statut power user
    gpu_memory_limit = request.form.get('gpu_memory_limit', '0') if use_gpu == "o" else "0"
    
    try:
        # Convertir en entier pour vérification
        gpu_memory_limit_int = int(gpu_memory_limit)
    except ValueError:
        # Protection contre les valeurs non numériques
        return "Valeur de mémoire GPU non valide", 400
    
    # Ici, la correction: si l'utilisateur a choisi "Maximum" (valeur 0) et n'est pas power user
    # on définit une limite de 4096 MiB (4 GB) au lieu de laisser illimité
    if use_gpu == "o":
        if gpu_memory_limit == "0":  # Si "Maximum" est sélectionné
            if power_user_status and power_limits:
                # Pour un power user, on utilise sa limite définie ou 8192 MiB par défaut
                gpu_max = power_limits['gpu_memory']
                if gpu_max == 'unlimited':
                    gpu_memory_limit = "8192"  # Valeur par défaut pour power users illimités
                else:
                    gpu_memory_limit = gpu_max
            else:
                # Pour un utilisateur normal, on limite à 4 GB même si "Maximum" est sélectionné
                gpu_memory_limit = "4096"
        else:
            # Si une autre option est sélectionnée (pas "Maximum")
            if power_user_status and power_limits:
                gpu_max = power_limits['gpu_memory']
                if gpu_max != 'unlimited':
                    try:
                        gpu_max = int(gpu_max)
                        gpu_memory_limit = str(min(int(gpu_memory_limit), gpu_max))
                    except:
                        pass  # Garde la valeur entrée si la conversion échoue
            else:
                # Limiter à 4 GB (4096 MiB) pour les utilisateurs normaux
                gpu_memory_limit = str(min(int(gpu_memory_limit), 4096))
    
    # Créer un fichier temporaire avec les entrées
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
        # Les variables cpu_limit et memory_limit contiennent déjà les bonnes valeurs
        # après les vérifications précédentes, donc tu peux les utiliser directement:
        temp.write(f"{choice}\n{username}\n{password}\n{image}\n")
        temp.write(f"{cpu_limit}\n{memory_limit}\n{use_gpu}\n")
        if use_gpu == "o":
            temp.write(f"{gpu_memory_limit}\n")
        temp_name = temp.name
    
    try:
        # Exécuter le script avec les entrées du fichier de manière sécurisée
        result = subprocess.run(
            ["bash", "-c", f"cat {shlex.quote(temp_name)} | bash ./script.sh"],
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Supprimer le fichier temporaire
        os.unlink(temp_name)
        
        # Construire la sortie
        output = result.stdout
        if result.stderr and not "standard in must be a tty" in result.stderr:
            output += "\nErreurs:\n" + result.stderr
            
        # S'assurer que la sortie n'est pas vide
        if not output or output.strip() == "":
            output = "⚠️ Avertissement: Le script n'a pas généré de sortie. Vérifie le script ou les logs."
            
        # Formater la sortie pour mettre en évidence les informations de connexion
        output = re.sub(r'(Connecte-toi avec RDP sur : .*)', r'✅ \1', output)
        output = re.sub(r'(USER : .*)', r'👤 \1', output)
        output = re.sub(r'(MOT DE PASSE : .*)', r'🔑 \1', output)
        
        return output
    except Exception as e:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        return f"Erreur d'exécution: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)