import random
import math

# ================================================================
# CALCUL
# ================================================================

def generate_calcul_6eme(difficulty: int) -> dict:
    """Calcul niveau 6ème — À personnaliser"""
    if difficulty == 1:
        a, b = random.randint(1, 20), random.randint(1, 20)
        op = random.choice(['+', '-'])
        if op == '+':
            return {"question": f"{a} + {b} = ?", "answer": float(a + b),
                    "explanation": f"La réponse est {a + b}", "hint": "Calcule étape par étape"}
        else:
            if a < b: a, b = b, a
            return {"question": f"{a} - {b} = ?", "answer": float(a - b),
                    "explanation": f"La réponse est {a - b}", "hint": "Calcule étape par étape"}
    elif difficulty == 2:
        a, b = random.randint(2, 12), random.randint(2, 12)
        return {"question": f"{a} × {b} = ?", "answer": float(a * b),
                "explanation": f"La réponse est {a * b}", "hint": "Table de multiplication"}
    elif difficulty == 3:
        a = random.randint(2, 12)
        b = random.randint(2, 10)
        return {"question": f"{a * b} ÷ {a} = ?", "answer": float(b),
                "explanation": f"La réponse est {b}", "hint": "Division"}
    elif difficulty == 4:
        n1, d1 = random.randint(1, 5), random.randint(2, 6)
        n2, d2 = random.randint(1, 5), random.randint(2, 6)
        answer = round((n1/d1) + (n2/d2), 2)
        return {"question": f"{n1}/{d1} + {n2}/{d2} = ? (arrondi à 0.01)",
                "answer": answer, "explanation": f"La réponse est {answer}",
                "hint": "Trouve le dénominateur commun"}
    else:
        base = random.randint(2, 10)
        exp = random.randint(2, 3)
        return {"question": f"{base}^{exp} = ?", "answer": float(base ** exp),
                "explanation": f"{base}^{exp} = {base ** exp}", "hint": "Multiplication répétée"}

def generate_calcul_5eme(difficulty: int) -> dict:
    """Calcul niveau 5ème — À personnaliser"""
    return generate_calcul_6eme(difficulty)

def generate_calcul_4eme(difficulty: int) -> dict:
    """Calcul niveau 4ème — À personnaliser"""
    return generate_calcul_6eme(difficulty)

def generate_calcul_3eme(difficulty: int) -> dict:
    """Calcul niveau 3ème — À personnaliser"""
    return generate_calcul_6eme(difficulty)


# ================================================================
# ALGÈBRE
# ================================================================

def generate_algebre_6eme(difficulty: int) -> dict:
    """Algèbre niveau 6ème — À personnaliser"""
    if difficulty <= 2:
        a = random.randint(2, 5)
        x = random.randint(1, 10)
        b = random.randint(1, 20)
        c = a * x + b
        return {"question": f"Résous: {a}x + {b} = {c}. x = ?",
                "answer": float(x),
                "explanation": f"{a}x = {c - b}, donc x = {x}",
                "hint": "Isole x d'un côté"}
    elif difficulty <= 3:
        a = random.randint(3, 7)
        c = random.randint(1, a - 1)
        x = random.randint(1, 8)
        b = random.randint(1, 15)
        d = (a - c) * x + b
        return {"question": f"Résous: {a}x + {b} = {c}x + {d}. x = ?",
                "answer": float(x),
                "explanation": f"{a - c}x = {d - b}, donc x = {x}",
                "hint": "Regroupe les x d'un côté"}
    else:
        x = random.randint(2, 6)
        return {"question": f"Résous: x² = {x * x}. x = ? (valeur positive)",
                "answer": float(x),
                "explanation": f"x = √{x * x} = {x}",
                "hint": "Racine carrée"}

def generate_algebre_5eme(difficulty: int) -> dict:
    """Algèbre niveau 5ème — À personnaliser"""
    return generate_algebre_6eme(difficulty)

def generate_algebre_4eme(difficulty: int) -> dict:
    """Algèbre niveau 4ème — À personnaliser"""
    return generate_algebre_6eme(difficulty)

def generate_algebre_3eme(difficulty: int) -> dict:
    """Algèbre niveau 3ème — À personnaliser"""
    return generate_algebre_6eme(difficulty)


# ================================================================
# GÉOMÉTRIE
# ================================================================

def generate_geometrie_6eme(difficulty: int) -> dict:
    """Géométrie niveau 6ème — À personnaliser"""
    if difficulty <= 2:
        l, w = random.randint(3, 12), random.randint(2, 8)
        if random.choice([True, False]):
            return {"question": f"Aire d'un rectangle {l}cm × {w}cm (en cm²)?",
                    "answer": float(l * w),
                    "explanation": f"Aire = {l} × {w} = {l * w} cm²",
                    "hint": "Aire = longueur × largeur"}
        else:
            return {"question": f"Périmètre d'un rectangle {l}cm × {w}cm (en cm)?",
                    "answer": float(2 * (l + w)),
                    "explanation": f"Périmètre = 2×({l}+{w}) = {2*(l+w)} cm",
                    "hint": "Périmètre = 2×(L+l)"}
    elif difficulty <= 3:
        r = random.randint(2, 10)
        if random.choice([True, False]):
            answer = round(3.14 * r * r, 2)
            return {"question": f"Aire d'un cercle de rayon {r}cm (π≈3.14, arrondi 0.01)?",
                    "answer": answer,
                    "explanation": f"Aire = π×r² = 3.14×{r}² = {answer} cm²",
                    "hint": "Aire = π × r²"}
        else:
            answer = round(2 * 3.14 * r, 2)
            return {"question": f"Périmètre d'un cercle de rayon {r}cm (π≈3.14, arrondi 0.01)?",
                    "answer": answer,
                    "explanation": f"Périmètre = 2×π×r = {answer} cm",
                    "hint": "Périmètre = 2 × π × r"}
    elif difficulty <= 4:
        base = random.randint(4, 15)
        height = random.randint(3, 12)
        answer = (base * height) / 2
        return {"question": f"Aire d'un triangle base={base}cm hauteur={height}cm (en cm²)?",
                "answer": answer,
                "explanation": f"Aire = ({base}×{height})/2 = {answer} cm²",
                "hint": "Aire = (base × hauteur) / 2"}
    else:
        a, b = random.randint(3, 8), random.randint(4, 10)
        c = round(math.sqrt(a * a + b * b), 2)
        return {"question": f"Triangle rectangle avec côtés {a}cm et {b}cm. Hypoténuse? (arrondi 0.01)",
                "answer": c,
                "explanation": f"c = √({a}²+{b}²) = √{a*a+b*b} ≈ {c} cm",
                "hint": "Théorème de Pythagore: c² = a² + b²"}

def generate_geometrie_5eme(difficulty: int) -> dict:
    """Géométrie niveau 5ème — À personnaliser"""
    return generate_geometrie_6eme(difficulty)

def generate_geometrie_4eme(difficulty: int) -> dict:
    """Géométrie niveau 4ème — À personnaliser"""
    return generate_geometrie_6eme(difficulty)

def generate_geometrie_3eme(difficulty: int) -> dict:
    """Géométrie niveau 3ème — À personnaliser"""
    return generate_geometrie_6eme(difficulty)


# ================================================================
# ROUTEUR PRINCIPAL
# ================================================================

# Table de correspondance grade → fonctions
GENERATORS = {
    6: {
        "calcul": generate_calcul_6eme,
        "algebre": generate_algebre_6eme,
        "geometrie": generate_geometrie_6eme,
    },
    7: {
        "calcul": generate_calcul_5eme,
        "algebre": generate_algebre_5eme,
        "geometrie": generate_geometrie_5eme,
    },
    8: {
        "calcul": generate_calcul_4eme,
        "algebre": generate_algebre_4eme,
        "geometrie": generate_geometrie_4eme,
    },
    9: {
        "calcul": generate_calcul_3eme,
        "algebre": generate_algebre_3eme,
        "geometrie": generate_geometrie_3eme,
    },
}

def get_problem_data(category: str, difficulty: int, grade: int) -> dict:
    """
    Routeur principal : appelle la bonne fonction
    selon la catégorie et le niveau de l'élève.
    grade: 6=6ème, 7=5ème, 8=4ème, 9=3ème
    """
    # Fallback sur 6ème si le grade est inconnu
    grade_generators = GENERATORS.get(grade, GENERATORS[6])
    # Fallback sur calcul si la catégorie est inconnue
    generator_fn = grade_generators.get(category, grade_generators["calcul"])
    return generator_fn(difficulty)