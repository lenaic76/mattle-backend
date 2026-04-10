import random
import math
# =========================================================
# UTILITAIRES 4ÈME
# =========================================================

def choix_signe(n):
    return n if random.choice([True, False]) else -n

def pgcd(a, b):
    while b:
        a, b = b, a % b
    return a

def simplifier(num, den):
    g = pgcd(abs(num), abs(den))
    return num // g, den // g
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
        exo_type = random.choice(["division", "decomposition"])

        if exo_type == "division":
            a = random.randint(2, 12)
            b = random.randint(2, 10)

            return {"question": f"{a * b} ÷ {a} = ?", "answer": float(b),
                    "explanation": f"{a*b} ÷ {a} = {b}", "hint": "Division"}

        elif exo_type == "decomposition":
            n = random.randint(10000, 999999)
            digits = list(str(n))
            powers = [10 ** i for i in range(len(digits)-1, -1, -1)]

            decomposition = " + ".join([f"({d} × {p})" for d, p in zip(digits, powers) if d != '0'])

            return {"question": (
                    "Voici un exemple de décomposition :\n"
                    "23 256 = (2 × 10 000) + (3 × 1 000) + (2 × 100) + (5 × 10) + (6 × 1)\n\n"
                    f"Décompose le nombre suivant de la même façon :\n{n}"),
                    "answer": decomposition,
                    "explanation": f"{n} = {decomposition}",
                    "hint": "Chaque chiffre est une puissances de 10"}
    elif difficulty == 4:
        exo_type = random.choice(["denominateur", "pourcentage", "conversion horaire"])

        if exo_type == "denominateur":
            n1, d1 = random.randint(1, 5), random.randint(2, 6)
            n2, d2 = random.randint(1, 5), random.randint(2, 6)
            answer = round((n1/d1) + (n2/d2), 2)
            return {"question": f"{n1}/{d1} + {n2}/{d2} = ? (arrondi à 0.01)",
                    "answer": answer, "explanation": f"La réponse est {answer}",
                    "hint": "Trouve le dénominateur commun"}
        elif exo_type == "pourcentage":
            total = random.randint(20, 200)
            percent = random.choice([10, 25, 50])
            result = total * percent / 100

            return {"question": f"Calcule {percent}% de {total}",
                    "answer": float(result),
                    "explanation": f"{percent}% de {total} = {result}",
                    "hint": "Multiplie puis divise par 100"}
        elif exo_type == "conversion horaire" :
            minutes = random.randint(60, 500)
            h = minutes // 60
            m = minutes % 60

            return {"question": f"Convertis {minutes} minutes en heures et minutes",
                    "answer": (h, m),
                    "explanation": f"{minutes} min = {h}h {m}min",
                    "hint": "1h = 60 min"} 
    else:
        base = random.randint(2, 10)
        exp = random.randint(2, 3)
        return {"question": f"{base}^{exp} = ?", "answer": float(base ** exp),
                "explanation": f"{base}^{exp} = {base ** exp}", "hint": "Multiplication répétée"}

def generate_calcul_5eme(difficulty: int) -> dict:
    """Calcul niveau 5ème — À personnaliser"""
    return generate_calcul_6eme(difficulty)

# =========================================================
# CALCUL 4ÈME
# Chapitres : nombres relatifs, fractions, puissances,
#             pourcentages, racines carrées, priorités
# =========================================================



def generate_calcul_4eme(difficulty: int) -> dict:

    if difficulty == 1:
        # Nombres relatifs — addition/soustraction avec 2 opérations
        a = choix_signe(random.randint(10, 49))
        b = choix_signe(random.randint(-15, 15))
        c = choix_signe(random.randint(-25, 25))

        op1, op2 = random.choice([('+', '+'), ('+', '-'), ('-', '+'), ('-', '-')])

        # Construction de l'expression et du résultat
        if op1 == '+':
            temp = a + b
        else:
            temp = a - b

        if op2 == '+':
            result = temp + c
        else:
            result = temp - c

        question = f"Calculer : ({a}) {op1} ({b}) {op2} ({c})"

        return {
            "question": question,
            "answer": float(result),
            "hint": "Attention aux signes et calcule étape par étape !",
            "explanation": f"({a}) {op1} ({b}) = {temp}, puis {temp} {op2} ({c}) = {result}"
        }

    elif difficulty == 2:
        # Fractions — addition/soustraction même dénominateur ou simple
        choix = random.choice(['fraction_add', 'relatifs_mult', 'pourcentage_simple'])

        if choix == 'fraction_add':
            den = random.randint(2, 12)
            a = random.randint(1, den - 1)
            b = random.randint(1, den - 1)
            op = random.choice(['+', '-'])
            num_res = a + b if op == '+' else a - b
            n, d = simplifier(num_res, den)
            return {
                "question": f"Calculer : {a}/{den} {op} {b}/{den} (donner le résultat simplifié sous forme a/b ou entier)",
                "answer": round(num_res / den, 4),
                "hint": "Même dénominateur → on additionne les numérateurs",
                "explanation": f"{a}/{den} {op} {b}/{den} = {num_res}/{den} = {n}/{d}"
            }
        elif choix == 'relatifs_mult':
            a = _choix_signe(random.randint(2, 12))
            b = _choix_signe(random.randint(2, 12))
            c = _choix_signe(random.randint(2, 12))
            if a*b<40:
                return {
                "question": f"Calculer : ({a}) × ({b}) × ({c})",
                "answer": float(a * b * c),
                "hint": "Deux signes identiques → résultat positif",
                "explanation": f"({a}) × ({b}) × ({c}) = {a * b * c}"
            }
            else:
                return {
                    "question": f"Calculer : ({a}) × ({b})",
                    "answer": float(a * b),
                    "hint": "Deux signes identiques → résultat positif",
                    "explanation": f"({a}) × ({b}) = {a * b}"
                }
        else:
            prix = random.randint(20, 200)
            taux = random.choice([10, 20, 25, 50, 75])
            val = prix * taux // 100
            return {
                "question": f"Calculer {taux}% de {prix}",
                "answer": float(val),
                "hint": f"Multiplier par {taux}/100",
                "explanation": f"{taux}% de {prix} = {prix} × {taux}/100 = {val}"
            }

    elif difficulty == 3:
        # Fractions dénominateurs différents, puissances, pourcentages
        choix = random.choice(['fraction_diff', 'puissance', 'pourcentage_reduction'])

        if choix == 'fraction_diff':
            a = random.randint(1, 8)
            b = random.randint(2, 9)
            c = random.randint(1, 8)
            d = random.randint(2, 9)
            while b == d:
                d = random.randint(2, 9)
            op = random.choice(['+', '-'])
            num = a * d + c * b if op == '+' else a * d - c * b
            den = b * d
            n, denom = _simplifier(num, den)
            return {
                "question": f"Calculer : {a}/{b} {op} {c}/{d} (arrondi 0.01)",
                "answer": round(num / den, 2),
                "hint": "Trouver le dénominateur commun",
                "explanation": f"{a}/{b} {op} {c}/{d} = {num}/{den} ≈ {round(num/den, 2)}"
            }
        elif choix == 'puissance':
            a = random.randint(2, 7)
            n = random.randint(2, 4)
            m = random.randint(2, 4)
            type_p = random.choice(['produit', 'quotient'])
            if type_p == 'produit':
                return {
                    "question": f"Simplifier : {a}^{n} × {a}^{m} = {a}^?",
                    "answer": float(n + m),
                    "hint": f"a^n × a^m = a^(n+m)",
                    "explanation": f"{a}^{n} × {a}^{m} = {a}^{n+m}"
                }
            else:
                big = max(n, m)
                small = min(n, m)
                return {
                    "question": f"Simplifier : {a}^{big} ÷ {a}^{small} = {a}^?",
                    "answer": float(big - small),
                    "hint": "a^n ÷ a^m = a^(n-m)",
                    "explanation": f"{a}^{big} ÷ {a}^{small} = {a}^{big - small}"
                }
        else:
            prix = random.randint(50, 300)
            taux = random.choice([5, 15, 20, 30])
            reduction = round(prix * taux / 100, 2)
            nouveau = round(prix - reduction, 2)
            return {
                "question": f"Un article coûte {prix}€. Après une réduction de {taux}%, quel est son nouveau prix ?",
                "answer": nouveau,
                "hint": f"Nouveau prix = {prix} × (1 - {taux}/100)",
                "explanation": f"Réduction = {prix} × {taux}/100 = {reduction}€ → Nouveau prix = {prix} - {reduction} = {nouveau}€"
            }

    elif difficulty == 4:
        # Racines carrées, priorités, fractions × ÷, puissances négatives
        choix = random.choice(['racine', 'fraction_mult', 'priorites', 'puissance_neg'])

        if choix == 'racine':
            carres = [4, 9, 16, 25, 36, 49, 64, 81, 100, 121, 144, 169]
            c = random.choice(carres)
            mult = random.randint(2, 5)
            val = c * mult * mult
            return {
                "question": f"Calculer : √{val}",
                "answer": float(math.sqrt(val)),
                "hint": f"√{val} = √({c} × {mult}²) = √{c} × {mult}",
                "explanation": f"√{val} = {int(_math.sqrt(val))}"
            }
        elif choix == 'fraction_mult':
            a = random.randint(1, 8)
            b = random.randint(2, 9)
            c = random.randint(1, 8)
            d = random.randint(2, 9)
            op = random.choice(['×', '÷'])
            if op == '×':
                num, den = a * c, b * d
                n, denom = _simplifier(num, den)
                return {
                    "question": f"Calculer : ({a}/{b}) × ({c}/{d}) (arrondi 0.01)",
                    "answer": round((a * c) / (b * d), 2),
                    "hint": "Multiplier numérateurs entre eux et dénominateurs entre eux",
                    "explanation": f"({a}/{b}) × ({c}/{d}) = {a*c}/{b*d} = {n}/{denom} ≈ {round(n/denom, 2)}"
                }
            else:
                num, den = a * d, b * c
                n, denom = _simplifier(num, den)
                return {
                    "question": f"Calculer : ({a}/{b}) ÷ ({c}/{d}) (arrondi 0.01)",
                    "answer": round((a * d) / (b * c), 2),
                    "hint": "Diviser par une fraction = multiplier par son inverse",
                    "explanation": f"({a}/{b}) ÷ ({c}/{d}) = ({a}/{b}) × ({d}/{c}) = {a*d}/{b*c} ≈ {round(a*d/(b*c), 2)}"
                }
        elif choix == 'priorites':
            a = random.randint(2, 8)
            b = random.randint(2, 8)
            c = random.randint(2, 8)
            d = random.randint(1, 6)
            res = a + b * c - d
            return {
                "question": f"Calculer en respectant les priorités : {a} + {b} × {c} - {d}",
                "answer": float(res),
                "hint": "La multiplication s'effectue avant l'addition",
                "explanation": f"{a} + {b} × {c} - {d} = {a} + {b*c} - {d} = {res}"
            }
        else:
            a = random.randint(2, 5)
            n = random.randint(1, 3)
            return {
                "question": f"Calculer : {a}^(-{n}) (arrondi 0.01)",
                "answer": round(1 / (a ** n), 4),
                "hint": f"a^(-n) = 1/a^n",
                "explanation": f"{a}^(-{n}) = 1/{a}^{n} = 1/{a**n} ≈ {round(1/(a**n), 4)}"
            }

    else:  # difficulty == 5
        # Calculs complexes combinés
        choix = random.choice(['expression_complete', 'fraction_complexe', 'puissance_fraction'])

        if choix == 'expression_complete':
            a = _choix_signe(random.randint(2, 8))
            b = _choix_signe(random.randint(2, 8))
            c = random.randint(2, 6)
            d = random.randint(1, 5)
            res = round(a * b + c ** 2 - d, 2)
            return {
                "question": f"Calculer : ({a}) × ({b}) + {c}² - {d}",
                "answer": float(res),
                "hint": "Calcule d'abord la puissance et la multiplication",
                "explanation": f"({a}) × ({b}) + {c}² - {d} = {a*b} + {c**2} - {d} = {res}"
            }
        elif choix == 'fraction_complexe':
            a = random.randint(1, 6)
            b = random.randint(2, 8)
            c = random.randint(1, 6)
            d = random.randint(2, 8)
            e = random.randint(1, 6)
            f = random.randint(2, 8)
            res = round(a/b + c/d - e/f, 4)
            return {
                "question": f"Calculer : {a}/{b} + {c}/{d} - {e}/{f} (arrondi 0.01)",
                "answer": round(res, 2),
                "hint": "Trouve le dénominateur commun aux 3 fractions",
                "explanation": f"{a}/{b} + {c}/{d} - {e}/{f} ≈ {round(res, 2)}"
            }
        else:
            a = random.randint(2, 5)
            b = random.randint(2, 4)
            c = random.randint(2, 4)
            num = a ** b
            den = a ** c
            exp = b - c
            return {
                "question": f"Simplifier : {a}^{b} / {a}^{c} et donner le résultat décimal (arrondi 0.01)",
                "answer": round(num / den, 2),
                "hint": "a^n / a^m = a^(n-m)",
                "explanation": f"{a}^{b} / {a}^{c} = {a}^{b-c} = {a}^{exp} = {round(num/den, 2)}"
            }

def generate_calcul_3eme(difficulty: int) -> dict:
    """Calcul niveau 3ème — À personnaliser"""
    return generate_calcul_6eme(difficulty)


# ================================================================
# ALGÈBRE
# ================================================================

def generate_algebre_6eme(difficulty: int) -> dict:
    """Algèbre niveau 6ème — À personnaliser"""
    
    if difficulty == 1:
        values = [random.uniform(-1, 2) for _ in range(4)]
        valid = [v for v in values if 0 <= v <= 1]

        return {"question": f"Parmi ces nombres {values}, lesquels peuvent être une probabilité ?",
                "answer": valid,
                "explanation": "Une probabilité est entre 0 et 1",
                "hint": "Intervalle [0 ; 1]"}
    elif difficulty == 2:
        total = random.randint(5, 20)
        success = random.randint(1, total)

        return {"question": f"Il y a {success} boules rouges sur {total}. Probabilité de tirer rouge ?",
                "answer": float(success / total),
                "explanation": f"{success}/{total}",
                "hint": "Cas favorables / cas possibles"}
    elif difficulty == 3:
        a = random.randint(2, 5)
        x = random.randint(1, 10)
        b = random.randint(1, 20)
        c = a * x + b
        return {"question": f"Résous: {a}x + {b} = {c}. x = ?",
                "answer": float(x),
                "explanation": f"{a}x = {c - b}, donc x = {x}",
                "hint": "Isole x d'un côté"}
    elif difficulty == 4:
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

# =========================================================
# ALGÈBRE 4ÈME
# Chapitres : développement, factorisation, équations,
#             identités remarquables, systèmes
# =========================================================

def generate_algebre_4eme(difficulty: int) -> dict:

    if difficulty == 1:
        # Calcul littéral — réduction d'expressions simples
        a = random.randint(2, 9)
        b = random.randint(1, 10)
        c = random.randint(2, 9)
        d = random.randint(1, 10)
        coeff = a + c
        cst = b - d
        return {
            "question": f"Réduire : {a}x + {b} + {c}x - {d}",
            "answer": float(coeff),
            "hint": "Regroupe les termes en x ensemble et les constantes ensemble",
            "explanation": f"{a}x + {c}x + {b} - {d} = {coeff}x + {cst} → le coefficient de x est {coeff}"
        }

    elif difficulty == 2:
        # Développement simple k(ax + b)
        k = random.randint(2, 8)
        a = random.randint(1, 9)
        b = choix_signe(random.randint(1, 9))
        ka = k * a
        kb = k * b
        return {
            "question": f"Développer : {k}({a}x + ({b}))",
            "answer": float(ka),
            "hint": "Multiplier chaque terme de la parenthèse par le facteur extérieur",
            "explanation": f"{k}({a}x + ({b})) = {ka}x + {kb} → le coefficient de x est {ka}"
        }

    elif difficulty == 3:
        # Équations du premier degré
        x_val = random.randint(-8, 8)
        a = random.randint(2, 8)
        b = choix_signe(random.randint(1, 15))
        c = a * x_val + b
        return {
            "question": f"Résoudre : {a}x + ({b}) = {c}  → x = ?",
            "answer": float(x_val),
            "hint": "Isole x en soustrayant la constante puis en divisant par le coefficient",
            "explanation": f"{a}x = {c} - ({b}) = {c - b} → x = {c - b}/{a} = {x_val}"
        }

    elif difficulty == 4:
        # Identités remarquables ou factorisation
        choix = random.choice(['identite_carree', 'factorisation', 'equation_2membres'])

        if choix == 'identite_carree':
            a = random.randint(2, 8)
            b = random.randint(1, 8)
            # (ax + b)² = a²x² + 2abx + b²
            a2 = a ** 2
            deux_ab = 2 * a * b
            b2 = b ** 2
            return {
                "question": f"Développer : ({a}x + {b})²  → coefficient de x = ?",
                "answer": float(deux_ab),
                "hint": "(a+b)² = a² + 2ab + b²",
                "explanation": f"({a}x + {b})² = {a2}x² + {deux_ab}x + {b2} → coefficient de x = {deux_ab}"
            }
        elif choix == 'factorisation':
            a = random.randint(2, 6)
            b = random.randint(2, 6)
            # a²-b² = (a-b)(a+b)
            diff = a ** 2 - b ** 2
            return {
                "question": f"Factoriser : {a**2}x² - {b**2}  (identité remarquable a²-b²) → donner (ax-b), le coefficient de x dans le premier facteur = ?",
                "answer": float(a),
                "hint": "a² - b² = (a-b)(a+b)",
                "explanation": f"{a**2}x² - {b**2} = ({a}x - {b})({a}x + {b}) → coefficient de x = {a}"
            }
        else:
            # Équation à 2 membres avec x des 2 côtés
            x_val = random.randint(-5, 5)
            a = random.randint(3, 8)
            b = random.randint(1, 6)
            c = random.randint(1, a - 1)
            d = (a - c) * x_val + b
            return {
                "question": f"Résoudre : {a}x + {b} = {c}x + {d}  → x = ?",
                "answer": float(x_val),
                "hint": "Regroupe les x d'un côté et les constantes de l'autre",
                "explanation": f"{a-c}x = {d-b} → x = {x_val}"
            }

    else:  # difficulty == 5
        # Systèmes d'équations ou expressions complexes
        choix = random.choice(['systeme', 'expression_algebrique'])

        if choix == 'systeme':
            x = random.randint(-4, 4)
            y = random.randint(-4, 4)
            a1 = random.randint(1, 4)
            b1 = random.randint(1, 4)
            c1 = a1 * x + b1 * y
            a2 = random.randint(1, 4)
            b2 = random.randint(1, 4)
            while a1 * b2 == a2 * b1:
                b2 = random.randint(1, 4)
            c2 = a2 * x + b2 * y
            return {
                "question": (
                    f"Système : {a1}x + {b1}y = {c1} et {a2}x + {b2}y = {c2}\n"
                    f"Trouver x (entier)"
                ),
                "answer": float(x),
                "hint": "Utilise la méthode par substitution ou par combinaison",
                "explanation": f"La solution est x = {x}, y = {y}"
            }
        else:
            a = random.randint(2, 6)
            b = random.randint(1, 5)
            # Développer (ax+b)(ax-b) = a²x²-b²
            res = a ** 2 - b ** 2
            return {
                "question": f"Développer et simplifier : ({a}x + {b})({a}x - {b}) pour x=1 → résultat = ?",
                "answer": float(res),
                "hint": "(a+b)(a-b) = a² - b²",
                "explanation": f"({a}x+{b})({a}x-{b}) = {a**2}x²-{b**2} → pour x=1 : {a**2}-{b**2} = {res}"
            }

def generate_algebre_3eme(difficulty: int) -> dict:
    """Algèbre niveau 3ème"""
    # équation simple ax + b = c
    if difficulty == 1:
        a = random.randint(2, 8)
        x = random.randint(1, 10)
        b = random.randint(1, 20)
        c = a * x + b

        return {
            "question": f"Résous: {a}x + {b} = {c}. x = ?",
            "answer": float(x),
            "explanation": f"{a}x = {c - b} donc x = {x}",
            "hint": "Isole x"
        }
    
    # équation ax + b = cx + d
    elif difficulty == 2:
        a = random.randint(3, 9)
        c = random.randint(1, a - 1)
        x = random.randint(1, 10)
        b = random.randint(1, 15)
        d = (a - c) * x + b

        return {
            "question": f"Résous: {a}x + {b} = {c}x + {d}. x = ?",
            "answer": float(x),
            "explanation": f"{a - c}x = {d - b} donc x = {x}",
            "hint": "Regroupe les x d'un côté" 
        }
    
    # équation avec fractions
    elif difficulty == 3:
        x = random.randint(1, 10)
        d = random.randint(2, 5)
        b = random.randint(1, 10)

        c = (x / d) + b
        c = round(c, 2)

        return {
            "question": f"Résous: x/{d} + {b} = {c}. x = ? (arrondi 0.01)",
            "answer": float(x),
            "explanation": f"x/{d} = {c - b} donc x = {x}",
            "hint": "Multiplie par le dénominateur"
        }
    
    # produit nul
    elif difficulty == 4:
        exo_type = random.choice(['produit', 'inequation'])

        if exo_type == 'produit':
        
            x1 = random.randint(1, 10)
            x2 = random.randint(1, 10)

            return {
                "question": f"Résous: (x - {x1})(x - {x2}) = 0. Donne UNE solution.",
                "answer": float(x1),
                "explanation": f"Produit nul ⇒ x = {x1} ou x = {x2}",
                "hint": "Un produit est nul si un facteur est nul"
            }
            
        else:
            a = random.randint(2, 6)
            x = random.randint(1, 10)
            b = random.randint(1, 10)
            c = a * x + b

            return {
                "question": f"Résous: {a}x + {b} > {c}. x > ?",
                "answer": float(x),
                "explanation": f"x > {x}",
                "hint": "Comme une équation"
            }
    
    # Niveau 5
    else:
        exo_type = random.choice(['developpement', 'identite', 'factorisation'])

        # Développement simple
        if exo_type == 'developpement':
            a = random.randint(2, 5)
            b = random.randint(1, 10)

            correct = f"{a}x + {a*b}"
            wrong1 = f"{a}x + {b}"
            wrong2 = f"{a*b}x"
            
            choices = [correct, wrong1, wrong2]
            random.shuffle(choices)

            return {
                "question": f"Développe: {a}(x + {b})",
                "choices": choices,
                "answer": correct,
                "explanation": correct,
                "hint": "Distribue le {a}"
            }
        
        # Identité remarquable
        elif exo_type == 'identite':
            a = random.randint(1, 9)

            correct = f"x² + {2*a}x + {a*a}"
            wrong1 = f"x² + {a}x + {a*a}"
            wrong2 = f"x² + {2*a}x"
            
            choices = [correct, wrong1, wrong2]
            random.shuffle(choices)

            return {
                "question": f"Développe: (x + {a})²",
                "choices": choices,
                "answer": correct,
                "explanation": correct,
                "hint": "(a+b)² = a² + 2ab + b²"
            }
        
        # Factorisation
        else:
            a = random.randint(2, 6)
            b = random.randint(1, 10)

            correct = f"{a}(x + {b})"
            wrong1 = f"{a}x + {b}"
            wrong2 = f"{a}(x + {a*b})"
            
            choices = [correct, wrong1, wrong2]
            random.shuffle(choices)

            return {
                "question": f"Factorise: {a}x + {a*b}",
                "choices": choices,
                "answer": correct,
                "explanation": correct,
                "hint": "Cherche le facteur commun"
            }


# ================================================================
# GÉOMÉTRIE
# ================================================================

def generate_geometrie_6eme(difficulty: int) -> dict:
    """Géométrie niveau 6ème — À personnaliser"""
    if difficulty == 1:
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
    elif difficulty == 2:
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
    elif difficulty == 3:
        base = random.randint(4, 15)
        height = random.randint(3, 12)
        answer = (base * height) / 2
        return {"question": f"Aire d'un triangle base={base}cm hauteur={height}cm (en cm²)?",
                "answer": answer,
                "explanation": f"Aire = ({base}×{height})/2 = {answer} cm²",
                "hint": "Aire = (base × hauteur) / 2"}
    elif difficulty == 4:
        a = random.randint(20, 100)
        b = random.randint(20, 100)
        c = 180 - a - b

        return {"question": f"Triangle : angles {a}° et {b}°. Quel est le troisième angle ?",
                "answer": float(c),
                "explanation": f"180 - {a} - {b} = {c}",
                "hint": "Somme = 180°"}
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

# =========================================================
# GÉOMÉTRIE 4ÈME
# Chapitres : Pythagore, Thalès, trigonométrie intro,
#             cercles, transformations, volumes
# =========================================================

def generate_geometrie_4eme(difficulty: int) -> dict:

    if difficulty == 1:
        # Aires et périmètres simples
        choix = random.choice(['rectangle', 'triangle', 'cercle_perim'])

        if choix == 'rectangle':
            L = random.randint(3, 15)
            l = random.randint(2, 10)
            choix2 = random.choice(['perimetre', 'aire'])
            if choix2 == 'perimetre':
                return {
                    "question": f"Rectangle {L}cm × {l}cm. Périmètre (en cm) ?",
                    "answer": float(2 * (L + l)),
                    "hint": "P = 2×(L+l)",
                    "explanation": f"P = 2×({L}+{l}) = {2*(L+l)} cm"
                }
            else:
                return {
                    "question": f"Rectangle {L}cm × {l}cm. Aire (en cm²) ?",
                    "answer": float(L * l),
                    "hint": "A = L×l",
                    "explanation": f"A = {L}×{l} = {L*l} cm²"
                }
        elif choix == 'triangle':
            b = random.randint(4, 14)
            h = random.randint(3, 12)
            return {
                "question": f"Triangle base={b}cm hauteur={h}cm. Aire (en cm²) ?",
                "answer": float((b * h) / 2),
                "hint": "A = (base × hauteur) / 2",
                "explanation": f"A = ({b}×{h})/2 = {(b*h)/2} cm²"
            }
        else:
            r = random.randint(2, 10)
            return {
                "question": f"Cercle rayon={r}cm. Périmètre (π≈3.14, arrondi 0.01) ?",
                "answer": round(2 * 3.14 * r, 2),
                "hint": "P = 2×π×r",
                "explanation": f"P = 2×3.14×{r} = {round(2*3.14*r, 2)} cm"
            }

    elif difficulty == 2:
        # Pythagore — trouver l'hypoténuse ou un côté
        triplets = [(3, 4, 5), (5, 12, 13), (6, 8, 10), (8, 15, 17), (7, 24, 25)]
        a, b, c = random.choice(triplets)
        choix = random.choice(['hypotenuse', 'cote'])

        if choix == 'hypotenuse':
            return {
                "question": f"Triangle rectangle, côtés {a}cm et {b}cm. Hypoténuse (en cm) ?",
                "answer": float(c),
                "hint": "c² = a² + b²",
                "explanation": f"c = √({a}²+{b}²) = √{a**2+b**2} = {c} cm"
            }
        else:
            return {
                "question": f"Triangle rectangle, hypoténuse {c}cm, un côté {a}cm. Autre côté (en cm) ?",
                "answer": float(b),
                "hint": "b² = c² - a²",
                "explanation": f"b = √({c}²-{a}²) = √{c**2-a**2} = {b} cm"
            }

    elif difficulty == 3:
        # Thalès ou volumes
        choix = random.choice(['thales', 'volume_pave', 'volume_cylindre'])

        if choix == 'thales':
            AB = random.randint(4, 12)
            AC = random.randint(4, 12)
            k = random.choice([2, 3, 4])
            AM = AB * k
            AN = AC * k
            return {
                "question": (
                    f"Droites parallèles. AB={AB}cm, AC={AC}cm, AM={AM}cm. "
                    f"Calculer AN par le théorème de Thalès (en cm) ?"
                ),
                "answer": float(AN),
                "hint": "AB/AM = AC/AN",
                "explanation": f"AN = (AM × AC) / AB = ({AM}×{AC})/{AB} = {AN} cm"
            }
        elif choix == 'volume_pave':
            L = random.randint(3, 12)
            l = random.randint(2, 8)
            h = random.randint(2, 8)
            return {
                "question": f"Pavé droit {L}cm × {l}cm × {h}cm. Volume (en cm³) ?",
                "answer": float(L * l * h),
                "hint": "V = L × l × h",
                "explanation": f"V = {L}×{l}×{h} = {L*l*h} cm³"
            }
        else:
            r = random.randint(2, 7)
            h = random.randint(3, 12)
            vol = round(3.14 * r ** 2 * h, 2)
            return {
                "question": f"Cylindre rayon={r}cm hauteur={h}cm. Volume (π≈3.14, arrondi 0.01) ?",
                "answer": vol,
                "hint": "V = π × r² × h",
                "explanation": f"V = 3.14 × {r}² × {h} = {vol} cm³"
            }

    elif difficulty == 4:
        # Trigonométrie intro (sin, cos, tan dans triangle rectangle)
        angles = [30, 45, 60]
        angle = random.choice(angles)
        hyp = random.randint(5, 15)

        sin_vals = {30: 0.5, 45: round(math.sqrt(2)/2, 4), 60: round(math.sqrt(3)/2, 4)}
        cos_vals = {30: round(math.sqrt(3)/2, 4), 45: round(math.sqrt(2)/2, 4), 60: 0.5}

        choix = random.choice(['sin', 'cos'])

        if choix == 'sin':
            cote_opp = round(hyp * sin_vals[angle], 2)
            return {
                "question": (
                    f"Triangle rectangle. Angle={angle}°, hypoténuse={hyp}cm. "
                    f"Côté opposé à l'angle (arrondi 0.01) ?"
                ),
                "answer": cote_opp,
                "hint": f"sin({angle}°) = côté opposé / hypoténuse",
                "explanation": f"côté opposé = {hyp} × sin({angle}°) = {hyp} × {sin_vals[angle]} = {cote_opp} cm"
            }
        else:
            cote_adj = round(hyp * cos_vals[angle], 2)
            return {
                "question": (
                    f"Triangle rectangle. Angle={angle}°, hypoténuse={hyp}cm. "
                    f"Côté adjacent à l'angle (arrondi 0.01) ?"
                ),
                "answer": cote_adj,
                "hint": f"cos({angle}°) = côté adjacent / hypoténuse",
                "explanation": f"côté adjacent = {hyp} × cos({angle}°) = {hyp} × {cos_vals[angle]} = {cote_adj} cm"
            }

    else:  # difficulty == 5
        # Problèmes combinés Pythagore + trigonométrie ou Thalès + aires
        choix = random.choice(['pytha_trigo', 'thales_aire'])

        if choix == 'pytha_trigo':
            a = random.randint(3, 9)
            b = random.randint(3, 9)
            c = round(math.sqrt(a**2 + b**2), 2)
            return {
                "question": (
                    f"Triangle rectangle côtés {a}cm et {b}cm. "
                    f"Calculer l'hypoténuse (arrondi 0.01) ?"
                ),
                "answer": c,
                "hint": "c = √(a²+b²)",
                "explanation": f"c = √({a}²+{b}²) = √{a**2+b**2} ≈ {c} cm"
            }
        else:
            r = random.randint(3, 9)
            h = random.randint(4, 12)
            # Volume cône = (1/3)πr²h
            vol = round((1/3) * 3.14 * r**2 * h, 2)
            return {
                "question": (
                    f"Cône rayon={r}cm hauteur={h}cm. "
                    f"Volume (π≈3.14, arrondi 0.01) ?"
                ),
                "answer": vol,
                "hint": "V = (1/3) × π × r² × h",
                "explanation": f"V = (1/3) × 3.14 × {r}² × {h} = {vol} cm³"
            }

def generate_geometrie_3eme(difficulty: int) -> dict:
    """Géométrie niveau 3ème"""
    # Pythagore (classique)
    if difficulty == 1:
        a = random.randint(3, 10)
        b = random.randint(4, 12)
        c = round(math.sqrt(a**2 + b**2), 2)

        return {
            "question": f"Triangle rectangle avec côtés {a} cm et {b} cm. Calcule l'hypoténuse (arrondi 0.01).",
            "answer": c,
            "explanation": f"c = √({a}² + {b}²) = √{a*a + b*b} ≈ {c}",
            "hint": "Théorème de Pythagore: c² = a² + b²"
        }
    
    # Réciproque de Pythagore
    elif difficulty == 2:
        a = random.randint(3, 10)
        b = random.randint(4, 12)
        c = int(math.sqrt(a**2 + b**2))

        return {
            "question": f"Un triangle a pour côtés {a}, {b} et {c}. Est-il rectangle ? (réponds par 1 pour oui, 0 pour non)",
            "answer": 1.0,
            "explanation": f"{a}² + {b}² = {a*a + b*b} et {c}² = {c*c} donc égalité → triangle rectangle",
            "hint": "Vérifie si a² + b² = c²"
        }
    
    # Trigonométrie
    elif difficulty == 3:
        adjacent = random.randint(3, 10)
        hypotenuse = random.randint(adjacent + 1, 15)

        cos_value = round(adjacent / hypotenuse, 2)

        return {
            "question": f"Dans un triangle rectangle, côté adjacent = {adjacent} cm et hypoténuse = {hypotenuse} cm. Calcule cos(angle) (arrondi 0.01).",
            "answer": cos_value,
            "explanation": f"cos = adjacent / hypoténuse = {adjacent}/{hypotenuse} ≈ {cos_value}",
            "hint": "cos = adjacent / hypoténuse"
        }
    
    # Thalès
    elif difficulty == 4:
        AB = random.randint(4, 10)
        AC = random.randint(6, 15)
        AD = random.randint(2, AB - 1)

        AE = round((AD * AC) / AB, 2)

        return {
            "question": f"Dans une configuration de Thalès: AB={AB}, AC={AC}, AD={AD}. Calcule AE (arrondi 0.01).",
            "answer": AE,
            "explanation": f"AE = (AD × AC) / AB = ({AD} × {AC}) / {AB} ≈ {AE}",
            "hint": "Utilise le théorème de Thalès"
        }
    
    # Distance dans un repère
    else:
        x1, y1 = random.randint(-5, 5), random.randint(-5, 5)
        x2, y2 = random.randint(-5, 5), random.randint(-5, 5)

        distance = round(math.sqrt((x2 - x1)**2 + (y2 - y1)**2), 2)

        return {
            "question": f"Calcule la distance entre A({x1},{y1}) et B({x2},{y2}) (arrondi 0.01).",
            "answer": distance,
            "explanation": f"d = √(({x2}-{x1})² + ({y2}-{y1})²) ≈ {distance}",
            "hint": "Utilise la formule de distance"
        }


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