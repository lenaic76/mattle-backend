import uuid
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Set
from clan import (
    match_members, calculate_points, calculate_problem_difficulty,
    calculate_genius_gain, WAR_DURATION_HOURS, PLAYER_WAR_TIME_SECONDS,
    PROBLEM_BUFFER_SIZE, WAR_QUEUE
)

# ==================== ÉTAT GLOBAL ====================

# Guerres actives {war_id: WarState}
active_wars: Dict[str, dict] = {}

# Connexions WebSocket des joueurs en guerre {user_id: websocket}
war_connections: Dict[str, object] = {}

# ==================== GÉNÉRATEUR DE PROBLÈMES ====================

def generate_war_problem(difficulty: int, category: str = None) -> dict:
    """Génère un problème pour la guerre selon la difficulté"""
    import random
    import math

    categories = ["calcul", "algebre", "geometrie"]
    if not category:
        category = random.choice(categories)

    if category == "calcul":
        return _gen_calcul(difficulty)
    elif category == "algebre":
        return _gen_algebre(difficulty)
    else:
        return _gen_geometrie(difficulty)

def _gen_calcul(difficulty: int) -> dict:
    import random
    if difficulty == 1:
        a, b = random.randint(1, 20), random.randint(1, 20)
        op = random.choice(['+', '-'])
        if op == '+':
            return {"id": str(uuid.uuid4()), "question": f"{a} + {b} = ?",
                    "answer": float(a + b), "difficulty": difficulty,
                    "explanation": f"{a} + {b} = {a+b}"}
        else:
            if a < b: a, b = b, a
            return {"id": str(uuid.uuid4()), "question": f"{a} - {b} = ?",
                    "answer": float(a - b), "difficulty": difficulty,
                    "explanation": f"{a} - {b} = {a-b}"}
    elif difficulty == 2:
        a, b = random.randint(2, 12), random.randint(2, 12)
        return {"id": str(uuid.uuid4()), "question": f"{a} × {b} = ?",
                "answer": float(a * b), "difficulty": difficulty,
                "explanation": f"{a} × {b} = {a*b}"}
    elif difficulty == 3:
        a = random.randint(2, 12)
        b = random.randint(2, 10)
        return {"id": str(uuid.uuid4()), "question": f"{a * b} ÷ {a} = ?",
                "answer": float(b), "difficulty": difficulty,
                "explanation": f"{a*b} ÷ {a} = {b}"}
    elif difficulty == 4:
        n1, d1 = random.randint(1, 5), random.randint(2, 6)
        n2, d2 = random.randint(1, 5), random.randint(2, 6)
        answer = round((n1/d1) + (n2/d2), 2)
        return {"id": str(uuid.uuid4()),
                "question": f"{n1}/{d1} + {n2}/{d2} = ? (arrondi 0.01)",
                "answer": answer, "difficulty": difficulty,
                "explanation": f"= {answer}"}
    else:
        base = random.randint(2, 10)
        exp = random.randint(2, 3)
        return {"id": str(uuid.uuid4()), "question": f"{base}^{exp} = ?",
                "answer": float(base ** exp), "difficulty": difficulty,
                "explanation": f"{base}^{exp} = {base**exp}"}

def _gen_algebre(difficulty: int) -> dict:
    import random
    if difficulty <= 2:
        a = random.randint(2, 5)
        x = random.randint(1, 10)
        b = random.randint(1, 20)
        c = a * x + b
        return {"id": str(uuid.uuid4()),
                "question": f"Résous: {a}x + {b} = {c}. x = ?",
                "answer": float(x), "difficulty": difficulty,
                "explanation": f"x = {x}"}
    elif difficulty <= 3:
        a = random.randint(3, 7)
        c = random.randint(1, a - 1)
        x = random.randint(1, 8)
        b = random.randint(1, 15)
        d = (a - c) * x + b
        return {"id": str(uuid.uuid4()),
                "question": f"Résous: {a}x + {b} = {c}x + {d}. x = ?",
                "answer": float(x), "difficulty": difficulty,
                "explanation": f"x = {x}"}
    else:
        x = random.randint(2, 6)
        return {"id": str(uuid.uuid4()),
                "question": f"Résous: x² = {x*x}. x = ? (positif)",
                "answer": float(x), "difficulty": difficulty,
                "explanation": f"x = {x}"}

def _gen_geometrie(difficulty: int) -> dict:
    import random, math
    if difficulty <= 2:
        l, w = random.randint(3, 12), random.randint(2, 8)
        if random.choice([True, False]):
            return {"id": str(uuid.uuid4()),
                    "question": f"Aire rectangle {l}×{w} cm² ?",
                    "answer": float(l * w), "difficulty": difficulty,
                    "explanation": f"{l}×{w} = {l*w}"}
        else:
            return {"id": str(uuid.uuid4()),
                    "question": f"Périmètre rectangle {l}×{w} cm ?",
                    "answer": float(2*(l+w)), "difficulty": difficulty,
                    "explanation": f"2×({l}+{w}) = {2*(l+w)}"}
    elif difficulty <= 3:
        r = random.randint(2, 10)
        answer = round(3.14 * r * r, 2)
        return {"id": str(uuid.uuid4()),
                "question": f"Aire cercle r={r}cm (π≈3.14) ?",
                "answer": answer, "difficulty": difficulty,
                "explanation": f"π×{r}² = {answer}"}
    elif difficulty <= 4:
        base = random.randint(4, 15)
        height = random.randint(3, 12)
        answer = (base * height) / 2
        return {"id": str(uuid.uuid4()),
                "question": f"Aire triangle base={base} hauteur={height} cm² ?",
                "answer": answer, "difficulty": difficulty,
                "explanation": f"({base}×{height})/2 = {answer}"}
    else:
        a, b = random.randint(3, 8), random.randint(4, 10)
        c = round(math.sqrt(a*a + b*b), 2)
        return {"id": str(uuid.uuid4()),
                "question": f"Hypoténuse triangle {a}cm et {b}cm ?",
                "answer": c, "difficulty": difficulty,
                "explanation": f"√({a}²+{b}²) = {c}"}

# ==================== ENVOI WEBSOCKET ====================

async def send_war(user_id: str, message: dict):
    """Envoie un message WebSocket à un joueur en guerre"""
    if user_id in war_connections:
        try:
            await war_connections[user_id].send_text(json.dumps(message))
        except Exception:
            pass

async def broadcast_war(war_id: str, message: dict):
    """Envoie un message à tous les joueurs d'une guerre"""
    if war_id not in active_wars:
        return
    war = active_wars[war_id]
    all_members = (
        war["clan1"]["war_members"] +
        war["clan2"]["war_members"]
    )
    for member_id in all_members:
        await send_war(member_id, message)

# ==================== SCORE EN TEMPS RÉEL ====================

def get_war_scores(war_id: str) -> dict:
    """Retourne les scores actuels de la guerre"""
    if war_id not in active_wars:
        return {}
    war = active_wars[war_id]

    clan1_score = sum(
        war["scores"].get(uid, {}).get("points", 0)
        for uid in war["clan1"]["war_members"]
    )
    clan2_score = sum(
        war["scores"].get(uid, {}).get("points", 0)
        for uid in war["clan2"]["war_members"]
    )

    clan1_time_left = sum(
        war["scores"].get(uid, {}).get("time_remaining", PLAYER_WAR_TIME_SECONDS)
        for uid in war["clan1"]["war_members"]
        if not war["scores"].get(uid, {}).get("played", False)
    )
    clan2_time_left = sum(
        war["scores"].get(uid, {}).get("time_remaining", PLAYER_WAR_TIME_SECONDS)
        for uid in war["clan2"]["war_members"]
        if not war["scores"].get(uid, {}).get("played", False)
    )

    members_detail = {}
    for uid in war["clan1"]["war_members"] + war["clan2"]["war_members"]:
        score_data = war["scores"].get(uid, {})
        members_detail[uid] = {
            "username": score_data.get("username", "?"),
            "points": score_data.get("points", 0),
            "problems_solved": score_data.get("problems_solved", 0),
            "played": score_data.get("played", False),
            "playing": score_data.get("playing", False),
            "time_remaining": score_data.get("time_remaining", PLAYER_WAR_TIME_SECONDS),
            "clan": 1 if uid in war["clan1"]["war_members"] else 2,
        }

    return {
        "clan1_score": clan1_score,
        "clan2_score": clan2_score,
        "clan1_name": war["clan1"]["name"],
        "clan2_name": war["clan2"]["name"],
        "clan1_time_left": clan1_time_left,
        "clan2_time_left": clan2_time_left,
        "members": members_detail,
        "war_end_time": war["end_time"].isoformat(),
        "status": war["status"],
    }

# ==================== MATCHMAKING ====================

async def try_matchmaking(clan_id: str, db) -> str | None:
    """
    Cherche un adversaire dans la file d'attente.
    Retourne le war_id si un match est trouvé.
    """
    if clan_id not in WAR_QUEUE:
        return None

    my_data = WAR_QUEUE[clan_id]
    my_format = my_data["format"]
    my_league = my_data["league"]

    for other_clan_id, other_data in list(WAR_QUEUE.items()):
        if other_clan_id == clan_id:
            continue
        if other_data["format"] != my_format:
            continue
        if other_data["league"] != my_league:
            continue

        # Match trouvé !
        WAR_QUEUE.pop(clan_id, None)
        WAR_QUEUE.pop(other_clan_id, None)

        war_id = await create_war(
            clan1_id=clan_id,
            clan1_data=my_data,
            clan2_id=other_clan_id,
            clan2_data=other_data,
            db=db
        )
        return war_id

    return None

async def create_war(clan1_id: str, clan1_data: dict,
                     clan2_id: str, clan2_data: dict, db) -> str:
    """Crée une guerre entre deux clans"""
    war_id = str(uuid.uuid4())
    now = datetime.utcnow()
    end_time = now + timedelta(hours=WAR_DURATION_HOURS)

    # Apparie les membres par Elo
    pairs = match_members(clan1_data["members"], clan2_data["members"])

    # Initialise les scores
    scores = {}
    all_members1 = [m["id"] for m in clan1_data["members"]]
    all_members2 = [m["id"] for m in clan2_data["members"]]

    for m in clan1_data["members"] + clan2_data["members"]:
        scores[m["id"]] = {
            "username": m["username"],
            "points": 0,
            "problems_solved": 0,
            "played": False,
            "playing": False,
            "time_remaining": PLAYER_WAR_TIME_SECONDS,
            "current_problem": None,
            "problem_buffer": [],
        }

    # Génère le buffer initial pour chaque paire
    # Utilise le grade minimum des deux adversaires pour équité
    for pair in pairs:
        diff = pair["difficulty"]
        min_grade = pair.get("min_grade", 6)
        buffer = [generate_war_problem(diff, grade=min_grade)
                for _ in range(PROBLEM_BUFFER_SIZE)]
        pair["shared_problem_ids"] = [p["id"] for p in buffer]
        pair["problem_buffer"] = buffer
        pair["buffer_index"] = 0

    war = {
        "id": war_id,
        "clan1": {
            "id": clan1_id,
            "name": clan1_data["clan_name"],
            "war_members": all_members1,
        },
        "clan2": {
            "id": clan2_id,
            "name": clan2_data["clan_name"],
            "war_members": all_members2,
        },
        "format": clan1_data["format"],
        "pairs": pairs,
        "scores": scores,
        "start_time": now,
        "end_time": end_time,
        "status": "active",
        "genius_gain": calculate_genius_gain("victory", clan1_data["format"]),
    }

    active_wars[war_id] = war

    # Sauvegarde en base
    await db.clan_wars.insert_one({
        "id": war_id,
        "clan1_id": clan1_id,
        "clan1_name": clan1_data["clan_name"],
        "clan2_id": clan2_id,
        "clan2_name": clan2_data["clan_name"],
        "format": clan1_data["format"],
        "start_time": now,
        "end_time": end_time,
        "status": "active",
        "pairs": [{
            "member1_id": p["member1_id"],
            "member1_username": p["member1_username"],
            "member2_id": p["member2_id"],
            "member2_username": p["member2_username"],
            "difficulty": p["difficulty"],
        } for p in pairs],
    })

    # Met à jour les clans
    for clan_id_up in [clan1_id, clan2_id]:
        await db.clans.update_one(
            {"id": clan_id_up},
            {"$set": {"current_war_id": war_id}}
        )

    # Notifie tous les membres
    for member_id in all_members1 + all_members2:
        clan_num = 1 if member_id in all_members1 else 2
        opponent_name = clan2_data["clan_name"] if clan_num == 1 else clan1_data["clan_name"]
        await send_war(member_id, {
            "type": "war_started",
            "war_id": war_id,
            "opponent_clan": opponent_name,
            "end_time": end_time.isoformat(),
            "format": clan1_data["format"],
        })

    # Lance le timer de fin de guerre
    asyncio.create_task(war_end_timer(war_id, db))

    return war_id

# ==================== TIMER DE FIN ====================

async def war_end_timer(war_id: str, db):
    """Timer qui termine la guerre après 24h"""
    await asyncio.sleep(WAR_DURATION_HOURS * 3600)
    await end_war(war_id, db)

# Calcul des pièces selon l'écart de score
async def calculate_war_coins(clan_score: int, opponent_score: int, result: str) -> int:
    if result != "victory":
        return 0
    total = clan_score + opponent_score
    if total == 0:
        return 50
    win_ratio = clan_score / total
    if win_ratio > 0.75:  # Victoire écrasante (>75% des points)
        return 100
    elif win_ratio > 0.6:  # Victoire normale (60-75%)
        return 75
    else:  # Victoire serrée (<60%)
        return 50

async def end_war(war_id: str, db):
    """Termine la guerre et calcule les résultats"""
    if war_id not in active_wars:
        return

    war = active_wars[war_id]
    if war["status"] != "active":
        return

    war["status"] = "finished"

    # Calcule les scores finaux
    scores = get_war_scores(war_id)
    clan1_score = scores["clan1_score"]
    clan2_score = scores["clan2_score"]

    if clan1_score > clan2_score:
        winner_id = war["clan1"]["id"]
        loser_id = war["clan2"]["id"]
        result_clan1 = "victory"
        result_clan2 = "defeat"
    elif clan2_score > clan1_score:
        winner_id = war["clan2"]["id"]
        loser_id = war["clan1"]["id"]
        result_clan1 = "defeat"
        result_clan2 = "victory"
    else:
        winner_id = None
        result_clan1 = result_clan2 = "draw"

    format_size = war["format"]
    genius_gain1 = calculate_genius_gain(result_clan1, format_size)
    genius_gain2 = calculate_genius_gain(result_clan2, format_size)

    # Met à jour les clans en base
    clan1 = await db.clans.find_one({"id": war["clan1"]["id"]})
    clan2 = await db.clans.find_one({"id": war["clan2"]["id"]})

    if clan1:
        new_genius1 = max(0, clan1.get("genius_index", 0) + genius_gain1)
        await db.clans.update_one(
            {"id": war["clan1"]["id"]},
            {"$set": {
                "genius_index": new_genius1,
                "current_war_id": None,
            }, "$push": {
                "war_history": {
                    "war_id": war_id,
                    "result": result_clan1,
                    "score": clan1_score,
                    "opponent_score": clan2_score,
                    "opponent_name": war["clan2"]["name"],
                    "genius_change": genius_gain1,
                    "date": datetime.utcnow().isoformat(),
                }
            }}
        )

    if clan2:
        new_genius2 = max(0, clan2.get("genius_index", 0) + genius_gain2)
        await db.clans.update_one(
            {"id": war["clan2"]["id"]},
            {"$set": {
                "genius_index": new_genius2,
                "current_war_id": None,
            }, "$push": {
                "war_history": {
                    "war_id": war_id,
                    "result": result_clan2,
                    "score": clan2_score,
                    "opponent_score": clan1_score,
                    "opponent_name": war["clan1"]["name"],
                    "genius_change": genius_gain2,
                    "date": datetime.utcnow().isoformat(),
                }
            }}
        )
    # Distribue les pièces aux membres du clan gagnant
    coins_per_member1 = await calculate_war_coins(clan1_score, clan2_score, result_clan1)
    coins_per_member2 = await calculate_war_coins(clan2_score, clan1_score, result_clan2)

    # Clan 1
    if coins_per_member1 > 0:
        for member_id in war["clan1"]["war_members"]:
            await db.users.update_one(
                {"id": member_id},
                {"$inc": {"coins": coins_per_member1}}
            )

    # Clan 2
    if coins_per_member2 > 0:
        for member_id in war["clan2"]["war_members"]:
            await db.users.update_one(
                {"id": member_id},
                {"$inc": {"coins": coins_per_member2}}
            )

    # Met à jour la guerre en base
    await db.clan_wars.update_one(
        {"id": war_id},
        {"$set": {
            "status": "finished",
            "clan1_score": clan1_score,
            "clan2_score": clan2_score,
            "winner_id": winner_id,
            "finished_at": datetime.utcnow(),
        }}
    )

    # Notifie tous les membres
    for member_id in war["clan1"]["war_members"]:
        await send_war(member_id, {
            "type": "war_ended",
            "result": result_clan1,
            "your_score": clan1_score,
            "opponent_score": clan2_score,
            "genius_change": genius_gain1,
            "coins_earned": coins_per_member1,
        })
    for member_id in war["clan2"]["war_members"]:
        await send_war(member_id, {
            "type": "war_ended",
            "result": result_clan2,
            "your_score": clan2_score,
            "opponent_score": clan1_score,
            "genius_change": genius_gain2,
            "coins_earned": coins_per_member2,
        })

    active_wars.pop(war_id, None)

# ==================== LOGIQUE DE JEU ====================

def get_pair_for_player(war_id: str, user_id: str) -> dict | None:
    """Trouve la paire d'un joueur dans la guerre"""
    if war_id not in active_wars:
        return None
    war = active_wars[war_id]
    for pair in war["pairs"]:
        if pair["member1_id"] == user_id or pair["member2_id"] == user_id:
            return pair
    return None

async def start_player_battle(war_id: str, user_id: str) -> dict | None:
    """
    Lance la session de combat d'un joueur (2 minutes).
    Retourne le premier problème.
    """
    if war_id not in active_wars:
        return None

    war = active_wars[war_id]
    scores = war["scores"]

    if user_id not in scores:
        return None
    if scores[user_id].get("played"):
        return {"error": "Tu as déjà utilisé ton temps de combat"}
    if scores[user_id].get("playing"):
        return {"error": "Tu es déjà en combat"}

    scores[user_id]["playing"] = True
    scores[user_id]["battle_start"] = datetime.utcnow().isoformat()

    # Trouve la paire et récupère le premier problème
    pair = get_pair_for_player(war_id, user_id)
    if not pair:
        return None

    # Donne le premier problème du buffer partagé
    buffer = pair.get("problem_buffer", [])
    idx = pair.get("buffer_index", 0)

    if idx >= len(buffer):
        min_grade = pair.get("min_grade", 6)
        new_problems = [generate_war_problem(pair["difficulty"], grade=min_grade)
                    for _ in range(PROBLEM_BUFFER_SIZE)]
        pair["problem_buffer"].extend(new_problems)
        buffer = pair["problem_buffer"]

    problem = buffer[idx]
    pair["buffer_index"] = idx + 1
    scores[user_id]["current_problem"] = problem

    # Lance le timer du joueur
    asyncio.create_task(player_timer(war_id, user_id))

    # Broadcast le nouveau score
    await broadcast_war(war_id, {
        "type": "scores_update",
        "scores": get_war_scores(war_id),
    })

    return {
        "problem": {
            "id": problem["id"],
            "question": problem["question"],
            "difficulty": problem["difficulty"],
        },
        "time_seconds": PLAYER_WAR_TIME_SECONDS,
    }

async def player_timer(war_id: str, user_id: str):
    """Timer de 2 minutes pour un joueur"""
    start = datetime.utcnow()

    while True:
        await asyncio.sleep(1)

        if war_id not in active_wars:
            return

        war = active_wars[war_id]
        scores = war["scores"]

        if user_id not in scores:
            return

        elapsed = (datetime.utcnow() - start).seconds
        remaining = max(0, PLAYER_WAR_TIME_SECONDS - elapsed)
        scores[user_id]["time_remaining"] = remaining

        # Envoie le timer toutes les 5 secondes
        if elapsed % 5 == 0:
            await send_war(user_id, {
                "type": "timer_update",
                "time_remaining": remaining,
            })

        if remaining <= 0:
            # Temps écoulé
            scores[user_id]["playing"] = False
            scores[user_id]["played"] = True
            scores[user_id]["time_remaining"] = 0

            await send_war(user_id, {
                "type": "battle_ended",
                "reason": "timeout",
                "points": scores[user_id]["points"],
                "problems_solved": scores[user_id]["problems_solved"],
            })

            await broadcast_war(war_id, {
                "type": "scores_update",
                "scores": get_war_scores(war_id),
            })
            return

async def submit_war_answer(
    war_id: str, user_id: str, problem_id: str, answer: float
) -> dict | None:
    """Traite la réponse d'un joueur pendant la guerre"""
    if war_id not in active_wars:
        return None

    war = active_wars[war_id]
    scores = war["scores"]

    if user_id not in scores:
        return None
    if not scores[user_id].get("playing"):
        return {"error": "Tu n'es pas en combat"}
    if scores[user_id].get("time_remaining", 0) <= 0:
        return {"error": "Temps écoulé"}

    current_problem = scores[user_id].get("current_problem")
    if not current_problem or current_problem["id"] != problem_id:
        return {"error": "Problème invalide"}

    # Vérifie la réponse
    is_correct = abs(answer - current_problem["answer"]) < 0.1

    if is_correct:
        points = current_problem["difficulty"]
        scores[user_id]["points"] += points
        scores[user_id]["problems_solved"] += 1

    # Génère le problème suivant
    pair = get_pair_for_player(war_id, user_id)
    if not pair:
        return None

    buffer = pair.get("problem_buffer", [])
    idx = pair.get("buffer_index", 0)

    # Régénère le buffer si nécessaire
    if idx >= len(buffer) - 2:
        min_grade = pair.get("min_grade", 6)
        new_problems = [generate_war_problem(pair["difficulty"], grade=min_grade)
                    for _ in range(PROBLEM_BUFFER_SIZE)]
        pair["problem_buffer"].extend(new_problems)
        buffer = pair["problem_buffer"]
    next_problem = buffer[idx]
    pair["buffer_index"] = idx + 1
    scores[user_id]["current_problem"] = next_problem

    # Broadcast le score mis à jour
    await broadcast_war(war_id, {
        "type": "scores_update",
        "scores": get_war_scores(war_id),
    })

    return {
        "correct": is_correct,
        "correct_answer": current_problem["answer"] if not is_correct else None,
        "points_gained": current_problem["difficulty"] if is_correct else 0,
        "total_points": scores[user_id]["points"],
        "next_problem": {
            "id": next_problem["id"],
            "question": next_problem["question"],
            "difficulty": next_problem["difficulty"],
        },
    }