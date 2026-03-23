import asyncio
import uuid
import random
from datetime import datetime
from typing import Dict, Optional
from fastapi import WebSocket

# ==================== ÉTAT GLOBAL ====================

# File d'attente matchmaking: {user_id: {websocket, elo, username}}
waiting_queue: Dict[str, dict] = {}

# Matchs en cours: {match_id: MatchState}
active_matches: Dict[str, dict] = {}

# Connexions WebSocket: {user_id: websocket}
connections: Dict[str, WebSocket] = {}

# ==================== GÉNÉRATEUR DE PROBLÈMES ====================

def generate_duel_problem(grade: int = 6, elo: int = 1000) -> dict:
    """Génère un problème adapté au niveau et à l'Elo du joueur"""
    from problem_generators import get_problem_data
    import uuid

    # Difficulté selon l'Elo
    if elo < 900: difficulty = 1
    elif elo < 1100: difficulty = 2
    elif elo < 1300: difficulty = 3
    elif elo < 1500: difficulty = 4
    else: difficulty = 5

    categories = ["calcul", "algebre", "geometrie"]
    category = random.choice(categories)
    data = get_problem_data(category, difficulty, grade)

    return {
        "id": str(uuid.uuid4()),
        "question": data["question"],
        "answer": data["answer"],
        "type": category,
        "difficulty": difficulty,
    }

# ==================== BOT ====================

def create_bot(elo: int) -> dict:
    """Crée un bot avec le même Elo que le joueur"""
    bot_names = ["MathBot", "AlgoBot", "CalcBot", "NumBot", "PiBot"]
    return {
        "user_id": f"bot_{uuid.uuid4()}",
        "username": f"{random.choice(bot_names)}_{elo}",
        "elo_online": elo,
        "is_bot": True,
        "score": 0,
    }

async def bot_answer(match_id: str, bot_id: str, correct_answer: float):
    """Simule la réponse du bot après un délai aléatoire"""
    # Bot répond entre 2 et 6 secondes
    delay = random.uniform(2.0, 6.0)
    await asyncio.sleep(delay)
    
    if match_id in active_matches:
        match = active_matches[match_id]
        # Bot a 75% de chance de répondre correctement
        if random.random() < 0.75:
            await process_answer(match_id, bot_id, correct_answer, is_bot=True)
        else:
            wrong = correct_answer + random.randint(1, 5)
            await process_answer(match_id, bot_id, wrong, is_bot=True)

# ==================== LOGIQUE DU MATCH ====================

def calculate_elo_change(winner_elo: int, loser_elo: int) -> tuple:
    """Calcule le changement d'Elo après un match"""
    K = 32
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    winner_change = int(K * (1 - expected_winner))
    loser_change = -int(K * expected_winner)
    return winner_change, loser_change

async def send_to_player(user_id: str, message: dict):
    """Envoie un message à un joueur via WebSocket"""
    if user_id in connections:
        try:
            import json
            await connections[user_id].send_text(json.dumps(message))
        except Exception:
            pass

async def start_round(match_id: str):
    """Démarre un nouveau round"""
    if match_id not in active_matches:
        return
    
    match = active_matches[match_id]
    match["current_round"] += 1
    
    if match["current_round"] > match["total_rounds"]:
        await end_match(match_id)
        return
    
    grade1 = match["player1"].get("grade", 6)
    grade2 = match["player2"].get("grade", 6)
    # Même grade garanti par le matchmaking mais on prend le min par sécurité
    min_grade = min(grade1, grade2)
    avg_elo = (match["player1"]["elo_online"] + match["player2"]["elo_online"]) // 2
    problem = generate_duel_problem(grade=min_grade, elo=avg_elo)
    match["current_problem"] = problem
    match["round_answered"] = set()
    match["round_start_time"] = datetime.utcnow().timestamp()
    
    # Envoie le problème aux deux joueurs
    message = {
        "type": "new_round",
        "round": match["current_round"],
        "total_rounds": match["total_rounds"],
        "problem": {
            "id": problem["id"],
            "question": problem["question"],
        },
        "scores": {
            match["player1"]["username"]: match["player1"]["score"],
            match["player2"]["username"]: match["player2"]["score"],
        }
    }
    
    await send_to_player(match["player1"]["user_id"], message)
    await send_to_player(match["player2"]["user_id"], message)
    
    # Si joueur 2 est un bot, lance sa réponse automatique
    if match["player2"].get("is_bot"):
        asyncio.create_task(
            bot_answer(match_id, match["player2"]["user_id"], problem["answer"])
        )

async def process_answer(match_id: str, user_id: str, answer: float, is_bot: bool = False):
    """Traite la réponse d'un joueur"""
    if match_id not in active_matches:
        return
    
    match = active_matches[match_id]
    problem = match["current_problem"]
    
    if user_id in match["round_answered"]:
        return
    
    match["round_answered"].add(user_id)
    is_correct = abs(answer - problem["answer"]) < 0.1
    
    # Identifie le joueur
    if match["player1"]["user_id"] == user_id:
        current_player = match["player1"]
        opponent = match["player2"]
    else:
        current_player = match["player2"]
        opponent = match["player1"]
    
    if is_correct:
        current_player["score"] += 1
        result = "correct"
    else:
        result = "incorrect"
    
    # Notifie le joueur humain
    if not is_bot:
        await send_to_player(user_id, {
            "type": "answer_result",
            "correct": is_correct,
            "correct_answer": problem["answer"],
            "your_score": current_player["score"],
            "opponent_score": opponent["score"],
        })
    
    # Si les deux ont répondu ou si c'est correct → passe au round suivant
    if is_correct or len(match["round_answered"]) >= 2:
        await asyncio.sleep(2)
        await start_round(match_id)

async def end_match(match_id: str):
    """Termine le match et calcule l'Elo"""
    if match_id not in active_matches:
        return
    
    match = active_matches[match_id]
    p1 = match["player1"]
    p2 = match["player2"]
    
    # Détermine le gagnant
    if p1["score"] > p2["score"]:
        winner, loser = p1, p2
    elif p2["score"] > p1["score"]:
        winner, loser = p2, p1
    else:
        winner, loser = None, None  # Égalité
    
    # Calcule les changements d'Elo
    if winner and loser:
        winner_change, loser_change = calculate_elo_change(
            winner["elo_online"], loser["elo_online"]
        )
    else:
        winner_change = loser_change = 0
    
    # Envoie le résultat final
    for player in [p1, p2]:
        if player.get("is_bot"):
            continue
        
        if winner and player["user_id"] == winner["user_id"]:
            elo_change = winner_change
            result = "victory"
        elif loser and player["user_id"] == loser["user_id"]:
            elo_change = loser_change
            result = "defeat"
        else:
            elo_change = 0
            result = "draw"
        
        await send_to_player(player["user_id"], {
            "type": "match_end",
            "result": result,
            "your_score": player["score"],
            "opponent_score": p2["score"] if player == p1 else p1["score"],
            "opponent_username": p2["username"] if player == p1 else p1["username"],
            "elo_change": elo_change,
            "new_elo_online": player["elo_online"] + elo_change,
        })
        
        # Stocke le changement d'Elo à appliquer
        match[f"elo_change_{player['user_id']}"] = elo_change
    
    match["status"] = "finished"

# ==================== MATCHMAKING ====================

async def find_match(user_id: str, username: str, elo_online: int, websocket: WebSocket, db, grade: int = 6):
    """Cherche un adversaire ou crée un bot"""
    connections[user_id] = websocket
    
    # Cherche un adversaire dans la file d'attente avec Elo similaire
    opponent_id = None
    for waiting_id, waiting_data in waiting_queue.items():
        elo_diff = abs(waiting_data["elo_online"] - elo_online)
        same_grade = waiting_data.get("grade", 6) == grade
        if elo_diff <= 300 and same_grade:
            opponent_id = waiting_id
            break
    
    if opponent_id:
        # Adversaire trouvé !
        opponent_data = waiting_queue.pop(opponent_id)
        
        match_id = str(uuid.uuid4())
        active_matches[match_id] = {
            "match_id": match_id,
            "player1": {
                "user_id": opponent_id,
                "username": opponent_data["username"],
                "elo_online": opponent_data["elo_online"],
                "grade": opponent_data.get("grade", 6),
                "score": 0,
                "is_bot": False,
            },
            "player2": {
                "user_id": user_id,
                "username": username,
                "elo_online": elo_online,
                "grade": grade,
                "score": 0,
                "is_bot": False,
            },
            "current_round": 0,
            "total_rounds": 5,
            "current_problem": None,
            "round_answered": set(),
            "status": "playing",
            "round_start_time": None,
        }
        
        # Notifie les deux joueurs
        for player in [active_matches[match_id]["player1"], active_matches[match_id]["player2"]]:
            opponent = active_matches[match_id]["player2"] if player == active_matches[match_id]["player1"] else active_matches[match_id]["player1"]
            await send_to_player(player["user_id"], {
                "type": "match_found",
                "match_id": match_id,
                "opponent_username": opponent["username"],
                "opponent_elo": opponent["elo_online"],
            })
        
        # Lance le premier round après 3 secondes
        await asyncio.sleep(3)
        await start_round(match_id)
        
    else:
        # Pas d'adversaire → attend 10 secondes puis crée un bot
        waiting_queue[user_id] = {
            "username": username,
            "elo_online": elo_online,
            "grade": grade,
            "websocket": websocket,
        }
        
        await send_to_player(user_id, {
            "type": "searching",
            "message": "Recherche d'un adversaire...",
        })
        
        # Attend 10 secondes
        await asyncio.sleep(10)
        
        # Vérifie si le joueur est toujours en attente
        if user_id in waiting_queue:
            waiting_queue.pop(user_id)
            
            # Crée un bot
            bot = create_bot(elo_online)
            match_id = str(uuid.uuid4())
            
            active_matches[match_id] = {
                "match_id": match_id,
                "player1": {
                    "user_id": user_id,
                    "username": username,
                    "elo_online": elo_online,
                    "grade": grade,
                    "score": 0,
                    "is_bot": False,
                },
                "player2": bot,
                "current_round": 0,
                "total_rounds": 5,
                "current_problem": None,
                "round_answered": set(),
                "status": "playing",
                "round_start_time": None,
            }
            
            await send_to_player(user_id, {
                "type": "match_found",
                "match_id": match_id,
                "opponent_username": bot["username"],
                "opponent_elo": bot["elo_online"],
                "is_bot": True,
            })
            
            await asyncio.sleep(3)
            await start_round(match_id)
    
    return match_id if 'match_id' in locals() else None