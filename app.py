from flask import Flask, request, render_template_string
import subprocess
import tempfile
import os

app = Flask(__name__)

# Template HTML avec instructions de connexion RDP mises à jour
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
    return render_template_string(HTML_TEMPLATE)

@app.route('/execute', methods=['POST'])
def execute_script():
    choice = request.form.get('choice', '1')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    
    # Créer un fichier temporaire avec les entrées
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp:
        temp.write(f"{choice}\n{username}\n{password}\n")
        temp_name = temp.name
    
    try:
        # Exécuter le script avec les entrées du fichier
        result = subprocess.run(
            f"cat {temp_name} | bash ./script.sh", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        
        # Supprimer le fichier temporaire
        os.unlink(temp_name)
        
        # Construire la sortie
        output = result.stdout
        if result.stderr:
            output += "\nErreurs:\n" + result.stderr
            
        return output
    except Exception as e:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        return f"Erreur d'exécution: {str(e)}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
