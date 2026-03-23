import uuid
import asyncio
import json
import random
from datetime import datetime
from typing import Dict
from problem_generators import get_problem_data

# ==================== ÉTAT GLOBAL ====================

active_friend_duels: Dict[str, dict] = {}
friend_duel_connections: Dict[str, object] = {}

ROUNDS = 5
ROUND_TIME = 30  # secondes par round

# ==================== HELPERS ====================

def generate_friend_problem(difficulty: int, grade: int) -> dict:
    categories = ["calcul", "algebre", "geometrie"]
    category = random.choice(categories)
    data = get_problem_data(category, difficulty, grade)
    return {
        "id": str(uuid.uuid4()),
        "question": data["question"],
        "answer": data["answer"],
        "difficulty": difficulty,
        "category": category,
        "explanation": data.get("explanation", ""),
        "hint": data.get("hint", ""),
        "elo_value": 800 + (difficulty * 200),
    }

def calculate_difficulty_from_elo(elo: int) -> int:
    if elo < 900: return 1
    elif elo < 1100: return 2
    elif elo < 1300: return 3
    elif elo < 1500: return 4
    else: return 5

async def send_friend_duel(user_id: str, message: dict):
    if user_id in friend_duel_connections:
        try:
            await friend_duel_connections[user_id].send_text(json.dumps(message))
        except Exception:
            pass

# ==================== CRÉATION DU DUEL ====================

async def create_friend_duel(
    challenger_id: str,
    challenger_username: str,
    challenger_elo: int,
    challenger_grade: int,
    challenged_id: str,
    challenged_username: str,
    challenged_elo: int,
    challenged_grade: int,
    mode: str,
    db
) -> str:
    duel_id = str(uuid.uuid4())

    # Grade minimum pour équité
    min_grade = min(challenger_grade, challenged_grade)

    # Difficulté basée sur la moyenne des Elos
    avg_elo = (challenger_elo + challenged_elo) // 2
    difficulty = calculate_difficulty_from_elo(avg_elo)

    # Génère tous les problèmes à l'avance (mêmes pour les deux)
    problems = [generate_friend_problem(difficulty, min_grade) for _ in range(ROUNDS)]

    duel = {
        "id": duel_id,
        "challenger_id": challenger_id,
        "challenger_username": challenger_username,
        "challenged_id": challenged_id,
        "challenged_username": challenged_username,
        "mode": mode,
        "min_grade": min_grade,
        "difficulty": difficulty,
        "problems": problems,
        "current_round": 0,
        "status": "active",
        "scores": {
            challenger_id: {"points": 0, "answers": [], "username": challenger_username},
            challenged_id: {"points": 0, "answers": [], "username": challenged_username},
        },
        "round_answers": {},
        "created_at": datetime.utcnow().isoformat(),
    }

    active_friend_duels[duel_id] = duel

    # Sauvegarde en base
    await db.friend_duels.insert_one({
        "id": duel_id,
        "challenger_id": challenger_id,
        "challenged_id": challenged_id,
        "mode": mode,
        "status": "active",
        "created_at": datetime.utcnow(),
    })

    # Notifie les deux joueurs
    first_problem = {
        "id": problems[0]["id"],
        "question": problems[0]["question"],
        "difficulty": problems[0]["difficulty"],
        "hint": problems[0]["hint"],
    }

    for uid, uname in [(challenger_id, challenger_username), (challenged_id, challenged_username)]:
        opponent = challenged_username if uid == challenger_id else challenger_username
        await send_friend_duel(uid, {
            "type": "duel_started",
            "duel_id": duel_id,
            "opponent": opponent,
            "mode": mode,
            "rounds": ROUNDS,
            "current_round": 1,
            "problem": first_problem,
            "time_seconds": ROUND_TIME,
        })

    # Lance le timer du premier round
    asyncio.create_task(round_timer(duel_id, 0, db))

    return duel_id

# ==================== TIMER DE ROUND ====================

async def round_timer(duel_id: str, round_idx: int, db):
    await asyncio.sleep(ROUND_TIME)

    if duel_id not in active_friend_duels:
        return

    duel = active_friend_duels[duel_id]
    if duel["status"] != "active":
        return
    if duel["current_round"] != round_idx:
        return

    # Force la fin du round (les non-répondants ont 0 point pour ce round)
    await finish_round(duel_id, round_idx, db)

async def finish_round(duel_id: str, round_idx: int, db):
    if duel_id not in active_friend_duels:
        return

    duel = active_friend_duels[duel_id]
    if duel["status"] != "active":
        return

    problem = duel["problems"][round_idx]
    round_answers = duel["round_answers"].get(round_idx, {})

    challenger_id = duel["challenger_id"]
    challenged_id = duel["challenged_id"]

    # Calcule résultats du round
    round_result = {}
    for uid in [challenger_id, challenged_id]:
        answer_data = round_answers.get(uid)
        if answer_data:
            correct = abs(answer_data["answer"] - problem["answer"]) < 0.1
            points = problem["difficulty"] if correct else 0
        else:
            correct = False
            points = 0

        duel["scores"][uid]["points"] += points
        duel["scores"][uid]["answers"].append({
            "round": round_idx + 1,
            "correct": correct,
            "points": points,
        })
        round_result[uid] = {"correct": correct, "points": points}

    # Envoie résultats du round aux deux joueurs
    for uid in [challenger_id, challenged_id]:
        opponent_id = challenged_id if uid == challenger_id else challenger_id
        await send_friend_duel(uid, {
            "type": "round_result",
            "round": round_idx + 1,
            "correct_answer": problem["answer"],
            "explanation": problem["explanation"],
            "your_result": round_result[uid],
            "opponent_result": round_result[opponent_id],
            "scores": {
                "you": duel["scores"][uid]["points"],
                "opponent": duel["scores"][opponent_id]["points"],
            },
        })

    next_round = round_idx + 1

    # Dernier round → fin du duel
    if next_round >= ROUNDS:
        await asyncio.sleep(2)
        await finish_duel(duel_id, db)
        return

    # Passe au round suivant
    await asyncio.sleep(3)
    duel["current_round"] = next_round
    next_problem = duel["problems"][next_round]

    for uid in [challenger_id, challenged_id]:
        await send_friend_duel(uid, {
            "type": "next_round",
            "current_round": next_round + 1,
            "total_rounds": ROUNDS,
            "problem": {
                "id": next_problem["id"],
                "question": next_problem["question"],
                "difficulty": next_problem["difficulty"],
                "hint": next_problem["hint"],
            },
            "time_seconds": ROUND_TIME,
        })

    asyncio.create_task(round_timer(duel_id, next_round, db))

# ==================== SOUMISSION RÉPONSE ====================

async def submit_friend_answer(
    duel_id: str, user_id: str, problem_id: str, answer: float, db
) -> dict:
    if duel_id not in active_friend_duels:
        return {"error": "Duel non trouvé"}

    duel = active_friend_duels[duel_id]
    if duel["status"] != "active":
        return {"error": "Duel terminé"}

    round_idx = duel["current_round"]
    problem = duel["problems"][round_idx]

    if problem["id"] != problem_id:
        return {"error": "Mauvais problème"}

    # Enregistre la réponse
    if round_idx not in duel["round_answers"]:
        duel["round_answers"][round_idx] = {}

    if user_id in duel["round_answers"][round_idx]:
        return {"error": "Déjà répondu"}

    duel["round_answers"][round_idx][user_id] = {
        "answer": answer,
        "time": datetime.utcnow().isoformat(),
    }

    is_correct = abs(answer - problem["answer"]) < 0.1

    # Envoie confirmation immédiate au joueur
    await send_friend_duel(user_id, {
        "type": "answer_received",
        "correct": is_correct,
        "waiting_opponent": True,
    })

    # Si les deux ont répondu → termine le round immédiatement
    challenger_id = duel["challenger_id"]
    challenged_id = duel["challenged_id"]
    both_answered = (
        challenger_id in duel["round_answers"][round_idx] and
        challenged_id in duel["round_answers"][round_idx]
    )

    if both_answered:
        await finish_round(duel_id, round_idx, db)

    return {"status": "ok", "correct": is_correct}

# ==================== FIN DU DUEL ====================

async def finish_duel(duel_id: str, db):
    if duel_id not in active_friend_duels:
        return

    duel = active_friend_duels[duel_id]
    duel["status"] = "finished"

    challenger_id = duel["challenger_id"]
    challenged_id = duel["challenged_id"]

    c1_score = duel["scores"][challenger_id]["points"]
    c2_score = duel["scores"][challenged_id]["points"]

    if c1_score > c2_score:
        winner_id = challenger_id
        loser_id = challenged_id
    elif c2_score > c1_score:
        winner_id = challenged_id
        loser_id = challenger_id
    else:
        winner_id = None
        loser_id = None

    # Calcule changement d'Elo si mode classé
    elo_changes = {challenger_id: 0, challenged_id: 0}
    if duel["mode"] == "ranked":
        K = 32
        c1_elo = (await db.users.find_one({"id": challenger_id}) or {}).get("elo_online", 1000)
        c2_elo = (await db.users.find_one({"id": challenged_id}) or {}).get("elo_online", 1000)

        expected_c1 = 1 / (1 + 10 ** ((c2_elo - c1_elo) / 400))
        expected_c2 = 1 - expected_c1

        if winner_id == challenger_id:
            actual_c1, actual_c2 = 1, 0
        elif winner_id == challenged_id:
            actual_c1, actual_c2 = 0, 1
        else:
            actual_c1, actual_c2 = 0.5, 0.5

        elo_changes[challenger_id] = int(K * (actual_c1 - expected_c1))
        elo_changes[challenged_id] = int(K * (actual_c2 - expected_c2))

        # Met à jour les Elos en base
        for uid, change in elo_changes.items():
            user = await db.users.find_one({"id": uid})
            if user:
                new_elo = max(100, user.get("elo_online", 1000) + change)
                await db.users.update_one({"id": uid}, {"$set": {"elo_online": new_elo}})

    # Met à jour en base
    await db.friend_duels.update_one(
        {"id": duel_id},
        {"$set": {
            "status": "finished",
            "winner_id": winner_id,
            "challenger_score": c1_score,
            "challenged_score": c2_score,
            "finished_at": datetime.utcnow(),
        }}
    )

    # Notifie les deux joueurs
    for uid in [challenger_id, challenged_id]:
        opponent_id = challenged_id if uid == challenger_id else challenger_id
        my_score = duel["scores"][uid]["points"]
        opp_score = duel["scores"][opponent_id]["points"]

        if winner_id == uid:
            result = "victory"
        elif winner_id is None:
            result = "draw"
        else:
            result = "defeat"

        await send_friend_duel(uid, {
            "type": "duel_finished",
            "result": result,
            "your_score": my_score,
            "opponent_score": opp_score,
            "elo_change": elo_changes[uid],
            "mode": duel["mode"],
            "answers": duel["scores"][uid]["answers"],
        })

    active_friend_duels.pop(duel_id, None)