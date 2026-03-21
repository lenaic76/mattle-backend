import uuid
import random
import string
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import subprocess
import tempfile
import os
import json

# ==================== HELPERS ====================

def generate_class_code() -> str:
    """Génère un code de classe unique ex: MATH-X7K2"""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"MATH-{suffix}"

def get_today_date() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

# ==================== SANDBOX PYTHON ====================

def execute_teacher_code(code: str) -> dict:
    """
    Exécute le code Python du prof dans un sandbox sécurisé.
    Le code doit définir une fonction get_questions() qui retourne
    une liste de dicts avec 'question', 'answer', 'hint', 'explanation'.
    """
    # Template sécurisé — on injecte le code du prof
    safe_template = """
import json
import random
import math

# Code du professeur
{teacher_code}

# Exécution sécurisée
try:
    questions = get_questions()
    # Valide le format
    validated = []
    for q in questions:
        if isinstance(q, dict) and 'question' in q and 'answer' in q:
            validated.append({{
                'question': str(q.get('question', '')),
                'answer': float(q.get('answer', 0)),
                'hint': str(q.get('hint', '')),
                'explanation': str(q.get('explanation', 'Voir avec le professeur')),
            }})
    print(json.dumps({{'success': True, 'questions': validated}}))
except Exception as e:
    print(json.dumps({{'success': False, 'error': str(e)}}))
""".format(teacher_code=code)

    try:
        # Crée un fichier temporaire
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, dir='/tmp'
        ) as f:
            f.write(safe_template)
            tmp_path = f.name

        # Exécute avec timeout de 5 secondes
        result = subprocess.run(
            ['python3', tmp_path],
            capture_output=True,
            text=True,
            timeout=5,
        )

        # Nettoie le fichier temporaire
        os.unlink(tmp_path)

        if result.returncode == 0:
            output = json.loads(result.stdout.strip())
            return output
        else:
            return {'success': False, 'error': result.stderr[:200]}

    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Timeout: le code prend trop de temps'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ==================== TEMPLATE PYTHON POUR LE PROF ====================

TEACHER_CODE_TEMPLATE = '''# Exemple de questions personnalisées
# Votre fonction DOIT s'appeler get_questions()
# Elle DOIT retourner une liste de dictionnaires

def get_questions():
    questions = [
        {
            "question": "Combien font 2 + 2 ?",
            "answer": 4,
            "hint": "Compte sur tes doigts",
            "explanation": "2 + 2 = 4"
        },
        {
            "question": "Quelle est la valeur de pi arrondie à 0.01 ?",
            "answer": 3.14,
            "hint": "C'est le rapport circonférence/diamètre",
            "explanation": "Pi = 3.14159... arrondi à 0.01 = 3.14"
        },
    ]
    return questions
'''