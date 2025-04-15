from flask import Flask, request, render_template_string
import subprocess
import tempfile
import os
import re

app = Flask(__name__)

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

# Template HTML avec instructions de connexion RDP et sélecteur d'images
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bureaux Virtuels Linux</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
        }
        input, select {
            width: 100%;
            padding: 8px;
            box-sizing: border-box;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        pre {
            background-color: #f4f4f4;
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 5px;
            white-space: pre-wrap;
            min-height: 200px;
            overflow-y: auto;
            max-height: 400px;
        }
        .info-box {
            background-color: #e7f3fe;
            border-left: 6px solid #2196F3;
            padding: 10px;
            margin: 15px 0;
        }
        .checkbox-container {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        .checkbox-container input {
            width: auto;
            margin-right: 10px;
        }
        .resource-box {
            background-color: #f0f8ff;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .resource-slider {
            width: 100%;
        }
        .resource-limits {
            margin-top: 10px;
            padding: 10px;
            background-color: #f9f9f9;
            border-radius: 5px;
        }
        .resource-info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
        }
        /* Style pour les options prédéfinies de GPU */
        .gpu-presets {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }
        .gpu-preset-btn {
            flex: 1;
            min-width: 100px;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            background-color: #f8f8f8;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s;
        }
        .gpu-preset-btn:hover {
            background-color: #e8e8e8;
        }
        .gpu-preset-btn.active {
            background-color: #4CAF50;
            color: white;
            border-color: #388E3C;
        }
        .hidden {
            display: none;
        }
        .alert-info {
            background-color: #fff3cd;
            border-left: 6px solid #ffc107;
            padding: 10px;
            margin: 15px 0;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <h1>Gestion des bureaux virtuels</h1>
    
    <div class="alert-info">
        <p><strong>Note :</strong> Pour assurer une répartition équitable des ressources, les limites maximales sont fixées à 4 cœurs CPU, 4 GB de RAM et 4 GB de mémoire GPU.</p>
    </div>
    
    <div class="resource-box">
        <h3>Ressources disponibles sur le système</h3>
        <div class="resource-info">
            <span>CPU:</span>
            <span>{{ resources.cpu_cores }} cœurs</span>
        </div>
        <div class="resource-info">
            <span>Mémoire:</span>
            <span>{{ resources.memory_gb }} GB</span>
        </div>
        <div class="resource-info">
            <span>GPU:</span>
            <span>{{ resources.gpu_count }} disponible(s)</span>
        </div>
        {% if resources.gpus %}
        <details>
            <summary>Détails des GPU</summary>
            <ul>
            {% for gpu in resources.gpus %}
                <li>GPU {{ gpu.id }}: {{ gpu.name }} ({{ gpu.memory }})</li>
            {% endfor %}
            </ul>
        </details>
        {% endif %}
    </div>
    
    <div class="container">
        <form id="scriptForm">
            <div class="form-group">
                <label for="choice">Action :</label>
                <select id="choice" name="choice">
                    <option value="1">1. Se connecter</option>
                    <option value="2">2. Créer un compte</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="username">Nom d'utilisateur :</label>
                <input type="text" id="username" name="username" required>
            </div>
            
            <div class="form-group">
                <label for="password">Mot de passe :</label>
                <input type="password" id="password" name="password" required>
            </div>
            
            <div class="form-group">
                <label for="image">Type de bureau virtuel :</label>
                <select id="image" name="image">
                    {% for image in images %}
                    <option value="{{ image.id }}">{{ image.name }}</option>
                    {% endfor %}
                </select>
            </div>
            
            <div class="resource-limits">
                <h3>Limites de ressources</h3>
                
                <div class="form-group">
                    <label for="cpu_limit">Nombre de cœurs CPU (max: 4):</label>
                    <input type="range" id="cpu_limit" name="cpu_limit" min="0.1" max="4" step="0.1" value="1" class="resource-slider">
                    <span id="cpu_value">1 cœur(s)</span>
                </div>
                
                <div class="form-group">
                    <label for="memory_limit">Mémoire RAM (max: 4GB):</label>
                    <input type="range" id="memory_limit" name="memory_limit" min="0.5" max="4" step="0.5" value="2" class="resource-slider">
                    <span id="memory_value">2 GB</span>
                </div>
                
                <div class="checkbox-container">
                    <input type="checkbox" id="use_gpu" name="use_gpu" value="true" {% if resources.gpu_count == 0 %}disabled{% endif %}>
                    <label for="use_gpu">Utiliser le GPU {% if resources.gpu_count == 0 %}(aucun GPU disponible){% endif %}</label>
                </div>
                
                <div id="gpu-options" class="hidden">
                    {% if resources.gpus and resources.gpus|length > 0 %}
                    <div class="form-group">
                        <label for="gpu_memory_limit">Mémoire GPU à utiliser :</label>
                        <input type="hidden" id="gpu_memory_limit" name="gpu_memory_limit" value="0">
                        
                        <div class="gpu-presets">
                            <div class="gpu-preset-btn active" data-value="0">
                                Maximum<br>(4GB max)
                            </div>
                            <div class="gpu-preset-btn" data-value="1024">
                                Faible<br>(1GB)
                            </div>
                            <div class="gpu-preset-btn" data-value="2048">
                                Moyen<br>(2GB)
                            </div>
                            <div class="gpu-preset-btn" data-value="3072">
                                Élevé<br>(3GB)
                            </div>
                        </div>
                        <p style="font-size: 0.8em; color: #666; margin-top: 10px;">
                            Mémoire GPU sélectionnée : <span id="gpu_memory_display">Pas de limite (4GB max)</span>
                        </p>
                    </div>
                    {% endif %}
                </div>
            </div>
            
            <button type="submit">Exécuter</button>
        </form>
    </div>
    
    <div class="container">
        <h2>Résultat</h2>
        <pre id="output">Le résultat de l'exécution apparaîtra ici...</pre>
    </div>
    
    <div class="info-box">
        <h3>Comment se connecter</h3>
        <p>Après avoir créé un compte ou t'être connecté, un bureau virtuel Linux sera mis à ta disposition.</p>
        <p>Pour t'y connecter :</p>
        <ol>
            <li>Utilise un client RDP comme Remmina, Microsoft Remote Desktop ou FreeRDP</li>
            <li>Connecte-toi à l'adresse IP et au port indiqués dans les résultats</li>
            <li>Utilise ton nom d'utilisateur et mot de passe que tu as définis ici</li>
        </ol>
        <p>Astuce : plus tu alloues de ressources, plus ton bureau virtuel sera rapide, mais ça consomme plus de ressources du serveur !</p>
    </div>

    <script>
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
                    gpuMemoryDisplay.textContent = "Pas de limite (4GB max)";
                } else {
                    gpuMemoryDisplay.textContent = memValue + " MiB";
                }
            });
        });
        
        document.getElementById('scriptForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            document.getElementById('output').textContent = "Exécution en cours... ça peut prendre quelques secondes, patiente un peu...";
            
            fetch('/execute', {
                method: 'POST',
                body: formData
            })
            .then(response => response.text())
            .then(data => {
                document.getElementById('output').textContent = data;
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('output').textContent = 'Erreur: ' + error;
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    images = get_available_images()
    resources = get_system_resources()
    return render_template_string(HTML_TEMPLATE, images=images, resources=resources)

@app.route('/execute', methods=['POST'])
def execute_script():
    choice = request.form.get('choice', '1')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    image = request.form.get('image', 'xfce_gui_container')
    
    # Validation de base des entrées
    if not username or not password:
        return "Erreur: Nom d'utilisateur et mot de passe requis."
    
    # Vérification que username ne contient pas de caractères dangereux
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return "Erreur: Le nom d'utilisateur ne doit contenir que des lettres, chiffres, tirets et underscores."
    
    # Récupérer l'option GPU (cochée = "true", non-cochée = None)
    use_gpu = "o" if request.form.get('use_gpu') == "true" else "n"
    
    # Récupérer les limites de ressources et s'assurer qu'elles respectent les maximums définis
    try:
        cpu_limit = float(request.form.get('cpu_limit', '1'))
        cpu_limit = min(max(0.1, cpu_limit), 4.0)  # Limiter entre 0.1 et 4 cœurs
        
        memory_limit = float(request.form.get('memory_limit', '2'))
        memory_limit = min(max(0.5, memory_limit), 4.0)  # Limiter entre 0.5 et 4 GB
        memory_limit = f"{memory_limit}g"  # Ajouter 'g' pour gigabytes
    except ValueError:
        return "Erreur: Valeurs de ressources invalides."
    
    gpu_memory_limit = "0"
    if use_gpu == "o":
        try:
            gpu_memory_limit = request.form.get('gpu_memory_limit', '0')
            if gpu_memory_limit != "0":
                # S'assurer que la mémoire GPU est limitée à 4 GB (4096 MiB)
                gpu_memory_limit = str(min(max(0, int(gpu_memory_limit)), 4096))
        except ValueError:
            return "Erreur: Valeur de mémoire GPU invalide."
    
    # Au lieu d'utiliser un fichier temporaire et shell=True, 
    # on passe directement les arguments au script
    script_path = os.path.abspath("./script.sh")
    if not os.path.exists(script_path):
        return "Erreur: Le script n'existe pas."
    
    # Préparer les entrées dans l'ordre attendu par le script
    process_inputs = f"{choice}\n{username}\n{password}\n{image}\n{cpu_limit}\n{memory_limit}\n{use_gpu}\n"
    if use_gpu == "o":
        process_inputs += f"{gpu_memory_limit}\n"
    
    try:
        # Exécuter le script sans shell=True
        process = subprocess.Popen(
            ["bash", script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Envoyer les entrées au script
        stdout, stderr = process.communicate(input=process_inputs)
        
        # Construire la sortie
        output = stdout
        if stderr and not "standard in must be a tty" in stderr:
            output += "\nErreurs:\n" + stderr
            
        # S'assurer que la sortie n'est pas vide
        if not output or output.strip() == "":
            output = "⚠️ Avertissement: Le script n'a pas généré de sortie. Vérifie le script ou les logs."
            
        # Formater la sortie pour mettre en évidence les informations de connexion
        output = re.sub(r'(Connecte-toi avec RDP sur : .*)', r'✅ \1', output)
        output = re.sub(r'(USER : .*)', r'👤 \1', output)
        output = re.sub(r'(MOT DE PASSE : .*)', r'🔑 \1', output)
        
        return output
    except Exception as e:
        return f"Erreur d'exécution: {str(e)}"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)