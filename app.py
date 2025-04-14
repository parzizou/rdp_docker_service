from flask import Flask, request, render_template_string
import subprocess
import tempfile
import os

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
    </style>
</head>
<body>
    <h1>Gestion des bureaux virtuels</h1>
    
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
            
            <div class="checkbox-container">
                <input type="checkbox" id="use_gpu" name="use_gpu" value="true">
                <label for="use_gpu">Utiliser le GPU (recommandé pour les applications graphiques intensives)</label>
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
        <p>Après avoir créé un compte ou vous être connecté, un bureau virtuel Linux sera mis à votre disposition.</p>
        <p>Pour vous y connecter :</p>
        <ol>
            <li>Utilisez un client RDP comme Remmina, Microsoft Remote Desktop ou FreeRDP</li>
            <li>Connectez-vous à l'adresse IP et au port indiqués</li>
            <li>Utilisez votre nom d'utilisateur et mot de passe que vous avez définis ici</li>
        </ol>
    </div>

    <script>
        document.getElementById('scriptForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            document.getElementById('output').textContent = "Exécution en cours...";
            
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
    return render_template_string(HTML_TEMPLATE, images=images)

@app.route('/execute', methods=['POST'])
def execute_script():
    choice = request.form.get('choice', '1')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    image = request.form.get('image', 'xfce_gui_container')
    
    # Récupérer l'option GPU (cochée = "true", non-cochée = None)
    use_gpu = "o" if request.form.get('use_gpu') == "true" else "n"
    
    # Créer un fichier temporaire avec les entrées
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
        temp.write(f"{choice}\n{username}\n{password}\n{image}\n{use_gpu}\n")
        temp_name = temp.name
    
    try:
        # Exécuter le script avec les entrées du fichier et s'assurer que stdin est correctement géré
        result = subprocess.run(
            f"cat {temp_name} | bash ./script.sh", 
            shell=True, 
            capture_output=True, 
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Supprimer le fichier temporaire
        os.unlink(temp_name)
        
        # Construire la sortie
        output = result.stdout
        if result.stderr:
            output += "\nErreurs:\n" + result.stderr
            
        # S'assurer que la sortie n'est pas vide
        if not output or output.strip() == "":
            output = "⚠️ Avertissement: Le script n'a pas généré de sortie. Vérifiez le script ou les logs."
            
        return output
    except Exception as e:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        return f"Erreur d'exécution: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)