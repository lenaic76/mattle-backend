import uuid
import random
import string
from datetime import datetime
from typing import Dict, List

# ==================== CONSTANTES ====================

CLAN_RANKS = {
    "chef": {"label": "Mathématicien en chef", "level": 4},
    "expert": {"label": "Expert des équations", "level": 3},
    "analyste": {"label": "Analyste", "level": 2},
    "recrue": {"label": "Recrue", "level": 1},
}

LEAGUES = [
    {"name": "Bronze", "icon": "🥉", "min": 0, "max": 499},
    {"name": "Argent", "icon": "🥈", "min": 500, "max": 1499},
    {"name": "Or", "icon": "🥇", "min": 1500, "max": 2999},
    {"name": "Platine", "icon": "💎", "min": 3000, "max": 4999},
    {"name": "Diamant", "icon": "💠", "min": 5000, "max": 7999},
    {"name": "Maître", "icon": "👑", "min": 8000, "max": 999999},
]

WAR_FORMATS = [10, 15, 20]
WAR_DURATION_HOURS = 24
PLAYER_WAR_TIME_SECONDS = 120  # 2 minutes par joueur
PROBLEM_BUFFER_SIZE = 5  # buffer serveur uniquement, jamais envoyé au client
WAR_MATCHMAKING_TIMEOUT = 300  # 5 minutes max en file d'attente
WAR_QUEUE: Dict[str, dict] = {}  # file d'attente globale {clan_id: war_data}

# ==================== HELPERS ====================

def generate_clan_tag() -> str:
    """Génère un tag unique pour le clan ex: #MATH42"""
    chars = string.ascii_uppercase + string.digits
    tag = ''.join(random.choices(chars, k=6))
    return f"#{tag}"

def get_league(genius_index: int) -> dict:
    """Retourne la ligue en fonction de l'indice de génie"""
    for league in reversed(LEAGUES):
        if genius_index >= league["min"]:
            return league
    return LEAGUES[0]

def calculate_genius_gain(war_result: str, format_size: int) -> int:
    """Calcule l'indice de génie gagné/perdu après une guerre"""
    base = {10: 20, 15: 30, 20: 40}[format_size]
    if war_result == "victory":
        return base
    elif war_result == "defeat":
        return -base // 2
    else:  # draw
        return base // 4

def calculate_problem_difficulty(elo: int) -> int:
    """Calcule la difficulté des problèmes selon l'Elo"""
    if elo < 900:
        return 1
    elif elo < 1100:
        return 2
    elif elo < 1300:
        return 3
    elif elo < 1500:
        return 4
    else:
        return 5

def calculate_points(difficulty: int) -> int:
    """Points gagnés pour un problème résolu"""
    return difficulty  # 1pt pour diff 1, 2pts pour diff 2, etc.

def match_members(clan1_members: list, clan2_members: list) -> list:
    """
    Apparie les membres des deux clans par Elo le plus proche.
    Retourne une liste de paires [(member1, member2), ...]
    """
    clan1_sorted = sorted(clan1_members, key=lambda m: m["elo_online"])
    clan2_sorted = sorted(clan2_members, key=lambda m: m["elo_online"])

    pairs = []
    used2 = set()

    for m1 in clan1_sorted:
        best_match = None
        best_diff = float('inf')

        for i, m2 in enumerate(clan2_sorted):
            if i in used2:
                continue
            diff = abs(m1["elo_online"] - m2["elo_online"])
            if diff < best_diff:
                best_diff = diff
                best_match = (i, m2)

        if best_match:
            idx, m2 = best_match
            used2.add(idx)
            avg_elo = (m1["elo_online"] + m2["elo_online"]) // 2
            difficulty = calculate_problem_difficulty(avg_elo)
            # Grade minimum des deux adversaires pour que les questions soient équitables
            grade1 = m1.get("grade", 6)
            grade2 = m2.get("grade", 6)
            min_grade = min(grade1, grade2)

            pairs.append({
                "member1_id": m1["id"],
                "member1_username": m1["username"],
                "member1_elo": m1["elo_online"],
                "member1_grade": grade1,
                "member2_id": m2["id"],
                "member2_username": m2["username"],
                "member2_elo": m2["elo_online"],
                "member2_grade": grade2,
                "min_grade": min_grade,  # ← grade utilisé pour générer les problèmes
                "difficulty": difficulty,
                "shared_problem_ids": [],
            })

    return pairs