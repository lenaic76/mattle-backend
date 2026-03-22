from fastapi import FastAPI, APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import random
import math
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt
import hashlib
from duel import find_match, process_answer, active_matches, connections, waiting_queue
from teacher import generate_class_code, execute_teacher_code, TEACHER_CODE_TEMPLATE
from clan import (
    generate_clan_tag, get_league, calculate_genius_gain,
    CLAN_RANKS, LEAGUES, WAR_FORMATS, WAR_QUEUE
)
from clan_war import (
    active_wars, war_connections, get_war_scores,
    try_matchmaking, start_player_battle,
    submit_war_answer, end_war, send_war, broadcast_war
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'mattle_db')]

SECRET_KEY = os.environ.get('SECRET_KEY', 'mattle-secret-key-2025')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30
ph = PasswordHasher()
security = HTTPBearer(auto_error=False)

app = FastAPI(title="Mattle API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== MODELS ====================

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    grade: int = 6
    role: str = "student"

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    elo: int
    elo_online: int
    grade: int
    role: str
    problems_solved: int
    correct_answers: int
    streak_days: int
    last_daily_date: Optional[str] = None
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class AnswerSubmit(BaseModel):
    problem_id: str
    answer: float
    is_daily: bool = False

class AnswerResponse(BaseModel):
    correct: bool
    correct_answer: float
    explanation: str
    elo_change: int
    new_elo: int

class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    elo: int
    elo_online: int
    problems_solved: int
    accuracy: float

class UserStats(BaseModel):
    total_problems: int
    correct_answers: int
    accuracy: float
    elo_history: List[dict]
    category_stats: dict
    streak_days: int
    best_streak: int

# ==================== HELPERS ====================

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token invalide")
        user = await db.users.find_one({"id": user_id})
        if user is None:
            raise HTTPException(status_code=401, detail="Utilisateur non trouvé")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide")

def calculate_elo_change(user_elo: int, problem_elo: int, correct: bool) -> int:
    K = 32
    expected = 1 / (1 + 10 ** ((problem_elo - user_elo) / 400))
    actual = 1 if correct else 0
    return int(K * (actual - expected))

def get_today_date() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def clean_doc(doc: dict) -> dict:
    """Supprime le _id MongoDB non sérialisable"""
    if doc:
        doc.pop("_id", None)
    return doc

# ==================== GENERATEURS ====================

def generate_calcul_problem(difficulty: int) -> dict:
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

def generate_algebre_problem(difficulty: int) -> dict:
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

def generate_geometrie_problem(difficulty: int) -> dict:
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

DAILY_RIDDLES = [
    {"question": "Je suis un nombre à deux chiffres. La somme de mes chiffres est 10. Si on inverse mes chiffres, on obtient un nombre plus grand de 36. Quel nombre suis-je?",
     "answer": 37.0, "explanation": "37: 3+7=10, et 73-37=36", "hint": "Appelle le nombre 'ab'"},
    {"question": "Un fermier a des poules et des lapins. Il compte 35 têtes et 94 pattes. Combien a-t-il de lapins?",
     "answer": 12.0, "explanation": "x+y=35 et 4x+2y=94, donc x=12 lapins", "hint": "Pose un système d'équations"},
    {"question": "Quel est le plus petit nombre entier positif divisible par 1, 2, 3, 4, 5 et 6?",
     "answer": 60.0, "explanation": "C'est le PPCM: 60", "hint": "Cherche le PPCM"},
    {"question": "Si je triple un nombre et j'ajoute 15, j'obtiens le même résultat que si je double ce nombre et j'ajoute 40. Quel est ce nombre?",
     "answer": 25.0, "explanation": "3x+15=2x+40, donc x=25", "hint": "Pose une équation"},
    {"question": "Dans une suite: 2, 6, 12, 20, 30, ?. Quel est le nombre suivant?",
     "answer": 42.0, "explanation": "Différences: +4,+6,+8,+10,+12. Donc 30+12=42", "hint": "Regarde les différences"},
    {"question": "Un escargot grimpe 10m. Le jour il monte 3m, la nuit il glisse 2m. En combien de jours atteint-il le sommet?",
     "answer": 8.0, "explanation": "Après 7 jours il est à 7m. Le 8ème jour il monte 3m et atteint 10m", "hint": "Attention au dernier jour!"},
    {"question": "Je pense à un nombre. Je le multiplie par 5 et je soustrais 7, j'obtiens 38. Quel est ce nombre?",
     "answer": 9.0, "explanation": "5x-7=38, donc 5x=45, x=9", "hint": "Fais les opérations inverses"},
    {"question": "La somme de trois nombres consécutifs est 75. Quel est le plus grand?",
     "answer": 26.0, "explanation": "n+(n+1)+(n+2)=75, n=24, le plus grand est 26", "hint": "Appelle le premier nombre n"},
]

def get_daily_riddle(date_str: str) -> dict:
    date_hash = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
    riddle = DAILY_RIDDLES[date_hash % len(DAILY_RIDDLES)].copy()
    riddle["id"] = f"riddle_{date_str}"
    riddle["elo_value"] = 1500
    return riddle

def generate_problem(category: str, difficulty: int) -> dict:
    if category == "calcul":
        data = generate_calcul_problem(difficulty)
    elif category == "algebre":
        data = generate_algebre_problem(difficulty)
    else:
        data = generate_geometrie_problem(difficulty)
    return {
        "id": str(uuid.uuid4()),
        "category": category,
        "difficulty": difficulty,
        "question": data["question"],
        "answer": data["answer"],
        "hint": data.get("hint"),
        "explanation": data["explanation"],
        "elo_value": 800 + (difficulty * 200),
    }

# ==================== AUTH ====================

@api_router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    if await db.users.find_one({"email": user_data.email}):
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    if await db.users.find_one({"username": user_data.username}):
        raise HTTPException(status_code=400, detail="Nom d'utilisateur déjà pris")
    user_id = str(uuid.uuid4())
    today = get_today_date()
    user = {
        "id": user_id,
        "username": user_data.username,
        "email": user_data.email,
        "password_hash": hash_password(user_data.password),
        "elo": 1000,
        "elo_online": 1000,
        "grade": user_data.grade,
        "role": user_data.role,
        "problems_solved": 0,
        "correct_answers": 0,
        "streak_days": 0,
        "best_streak": 0,
        "last_daily_date": None,
        "elo_history": [{"date": today, "elo": 1000}],
        "category_stats": {
            "calcul": {"solved": 0, "correct": 0},
            "algebre": {"solved": 0, "correct": 0},
            "geometrie": {"solved": 0, "correct": 0},
        },
        "created_at": datetime.utcnow(),
    }
    await db.users.insert_one(user)
    token = create_access_token({"sub": user_id})
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id, username=user_data.username, email=user_data.email,
            elo=1000, elo_online=1000, grade=user_data.grade,
            role=user_data.role, problems_solved=0,
            correct_answers=0, streak_days=0, last_daily_date=None,
            created_at=user["created_at"],
        )
    )

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_access_token({"sub": user["id"]})
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user["id"], username=user["username"], email=user["email"],
            elo=user["elo"], elo_online=user.get("elo_online", 1000),
            grade=user["grade"], role=user.get("role", "student"),
            problems_solved=user["problems_solved"],
            correct_answers=user["correct_answers"],
            streak_days=user["streak_days"],
            last_daily_date=user.get("last_daily_date"),
            created_at=user["created_at"],
        )
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"], username=current_user["username"],
        email=current_user["email"], elo=current_user["elo"],
        elo_online=current_user.get("elo_online", 1000),
        grade=current_user["grade"], role=current_user.get("role", "student"),
        problems_solved=current_user["problems_solved"],
        correct_answers=current_user["correct_answers"],
        streak_days=current_user["streak_days"],
        last_daily_date=current_user.get("last_daily_date"),
        created_at=current_user["created_at"],
    )

# ==================== PROBLEMS ====================

@api_router.get("/problems/generate")
async def generate_problems(
    category: str = "calcul",
    count: int = 5,
    current_user: dict = Depends(get_current_user)
):
    user_elo = current_user["elo"]
    if user_elo < 900:
        difficulties = [1, 1, 2, 2, 2]
    elif user_elo < 1100:
        difficulties = [1, 2, 2, 3, 3]
    elif user_elo < 1300:
        difficulties = [2, 2, 3, 3, 4]
    elif user_elo < 1500:
        difficulties = [2, 3, 3, 4, 4]
    else:
        difficulties = [3, 3, 4, 4, 5]
    problems = []
    for i in range(min(count, 10)):
        diff = difficulties[i % len(difficulties)]
        problems.append(generate_problem(category, diff))
    return {"problems": problems}

@api_router.post("/problems/cache")
async def cache_problem(problem: dict, current_user: dict = Depends(get_current_user)):
    problem["user_id"] = current_user["id"]
    problem["cached_at"] = datetime.utcnow()
    await db.problems_cache.update_one(
        {"id": problem["id"]}, {"$set": problem}, upsert=True
    )
    return {"status": "cached"}

@api_router.post("/problems/submit", response_model=AnswerResponse)
async def submit_answer(
    submission: AnswerSubmit,
    current_user: dict = Depends(get_current_user)
):
    problem = await db.problems_cache.find_one({"id": submission.problem_id})
    if not problem:
        raise HTTPException(status_code=404, detail="Problème non trouvé")
    is_correct = abs(submission.answer - problem["answer"]) < 0.1
    elo_change = calculate_elo_change(current_user["elo"], problem["elo_value"], is_correct)
    new_elo = max(100, current_user["elo"] + elo_change)
    category = problem.get("category", "calcul")
    cat_stats = current_user.get("category_stats", {})
    if category not in cat_stats:
        cat_stats[category] = {"solved": 0, "correct": 0}
    cat_stats[category]["solved"] += 1
    if is_correct:
        cat_stats[category]["correct"] += 1
    today = get_today_date()
    elo_history = current_user.get("elo_history", [])
    if not elo_history or elo_history[-1]["date"] != today:
        elo_history.append({"date": today, "elo": new_elo})
    else:
        elo_history[-1]["elo"] = new_elo
    update_data = {
        "elo": new_elo,
        "problems_solved": current_user["problems_solved"] + 1,
        "category_stats": cat_stats,
        "elo_history": elo_history[-30:],
    }
    if is_correct:
        update_data["correct_answers"] = current_user["correct_answers"] + 1
    await db.users.update_one({"id": current_user["id"]}, {"$set": update_data})
    return AnswerResponse(
        correct=is_correct, correct_answer=problem["answer"],
        explanation=problem.get("explanation", ""),
        elo_change=elo_change, new_elo=new_elo,
    )

# ==================== DAILY ====================

@api_router.get("/daily/challenge")
async def get_daily_challenge(current_user: dict = Depends(get_current_user)):
    today = get_today_date()
    user_daily = await db.daily_completions.find_one({
        "user_id": current_user["id"], "date": today
    })
    completed_problems = user_daily.get("completed_problems", []) if user_daily else []
    riddle_completed = user_daily.get("riddle_completed", False) if user_daily else False
    daily_cache = await db.daily_challenges.find_one({"date": today})
    if not daily_cache:
        problems = []
        for cat in ["calcul", "algebre", "geometrie"]:
            for diff in [2, 3, 4]:
                problems.append(generate_problem(cat, diff))
        riddle = get_daily_riddle(today)
        daily_cache = {"date": today, "problems": problems, "riddle": riddle}
        await db.daily_challenges.insert_one(daily_cache)
    return {
        "date": today,
        "problems": daily_cache["problems"],
        "riddle": daily_cache["riddle"],
        "completed_problems": completed_problems,
        "riddle_completed": riddle_completed,
        "streak": current_user.get("streak_days", 0),
    }

@api_router.post("/daily/submit")
async def submit_daily_answer(
    submission: AnswerSubmit,
    current_user: dict = Depends(get_current_user)
):
    today = get_today_date()
    daily = await db.daily_challenges.find_one({"date": today})
    if not daily:
        raise HTTPException(status_code=404, detail="Défi quotidien non trouvé")
    is_riddle = submission.problem_id.startswith("riddle_")
    problem = daily["riddle"] if is_riddle else next(
        (p for p in daily["problems"] if p["id"] == submission.problem_id), None
    )
    if not problem:
        raise HTTPException(status_code=404, detail="Problème non trouvé")
    is_correct = abs(submission.answer - problem["answer"]) < 0.1
    user_daily = await db.daily_completions.find_one({
        "user_id": current_user["id"], "date": today
    }) or {
        "user_id": current_user["id"], "date": today,
        "completed_problems": [], "riddle_completed": False,
    }
    if is_riddle:
        if user_daily.get("riddle_completed"):
            return {"correct": is_correct, "already_completed": True}
        user_daily["riddle_completed"] = is_correct
    else:
        if submission.problem_id in user_daily["completed_problems"]:
            return {"correct": is_correct, "already_completed": True}
        user_daily["completed_problems"].append(submission.problem_id)
    problem_elo = problem.get("elo_value", 1500)
    elo_change = calculate_elo_change(current_user["elo"], problem_elo, is_correct)
    if is_riddle and is_correct:
        elo_change = int(elo_change * 1.5)
    new_elo = max(100, current_user["elo"] + elo_change)
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    last_daily = current_user.get("last_daily_date")
    if last_daily == yesterday:
        new_streak = current_user.get("streak_days", 0) + 1
    elif last_daily == today:
        new_streak = current_user.get("streak_days", 0)
    else:
        new_streak = 1
    today_history = get_today_date()
    elo_history = current_user.get("elo_history", [])
    if not elo_history or elo_history[-1]["date"] != today_history:
        elo_history.append({"date": today_history, "elo": new_elo})
    else:
        elo_history[-1]["elo"] = new_elo
    update_data = {
        "elo": new_elo,
        "last_daily_date": today,
        "streak_days": new_streak,
        "best_streak": max(current_user.get("best_streak", 0), new_streak),
        "problems_solved": current_user["problems_solved"] + 1,
        "elo_history": elo_history[-30:],
    }
    if is_correct:
        update_data["correct_answers"] = current_user["correct_answers"] + 1
    await db.users.update_one({"id": current_user["id"]}, {"$set": update_data})
    await db.daily_completions.update_one(
        {"user_id": current_user["id"], "date": today},
        {"$set": user_daily}, upsert=True
    )
    return {
        "correct": is_correct,
        "correct_answer": problem["answer"],
        "explanation": problem.get("explanation", ""),
        "elo_change": elo_change,
        "new_elo": new_elo,
        "streak": new_streak,
    }

# ==================== LEADERBOARD & STATS ====================

@api_router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(limit: int = 50):
    users = await db.users.find({"role": "student"}).sort("elo_online", -1).limit(limit).to_list(limit)
    leaderboard = []
    for rank, user in enumerate(users, 1):
        accuracy = (user["correct_answers"] / user["problems_solved"] * 100) \
            if user["problems_solved"] > 0 else 0
        leaderboard.append(LeaderboardEntry(
            rank=rank, username=user["username"],
            elo=user["elo"],
            elo_online=user.get("elo_online", 1000),
            problems_solved=user["problems_solved"],
            accuracy=round(accuracy, 1),
        ))
    return leaderboard

@api_router.get("/stats/me", response_model=UserStats)
async def get_my_stats(current_user: dict = Depends(get_current_user)):
    return UserStats(
        total_problems=current_user["problems_solved"],
        correct_answers=current_user["correct_answers"],
        accuracy=round(
            (current_user["correct_answers"] / current_user["problems_solved"] * 100)
            if current_user["problems_solved"] > 0 else 0, 1
        ),
        elo_history=current_user.get("elo_history", []),
        category_stats=current_user.get("category_stats", {}),
        streak_days=current_user.get("streak_days", 0),
        best_streak=current_user.get("best_streak", 0),
    )

@api_router.get("/stats/rank")
async def get_my_rank(current_user: dict = Depends(get_current_user)):
    higher_count = await db.users.count_documents({
        "elo_online": {"$gt": current_user.get("elo_online", 1000)},
        "role": "student"
    })
    total_users = await db.users.count_documents({"role": "student"})
    return {
        "rank": higher_count + 1,
        "total_users": total_users,
        "percentile": round((1 - higher_count / total_users) * 100, 1) if total_users > 0 else 100,
    }

@api_router.get("/")
async def root():
    return {"message": "Mattle API v1.0", "status": "running"}

@api_router.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

# ==================== TEACHER ROUTES ====================

@api_router.post("/teacher/classes")
async def create_class(
    class_data: dict,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    class_id = str(uuid.uuid4())
    code = generate_class_code()
    new_class = {
        "id": class_id,
        "name": class_data.get("name", "Ma classe"),
        "subject": class_data.get("subject", "Maths"),
        "teacher_id": current_user["id"],
        "teacher_name": current_user["username"],
        "code": code,
        "students": [],
        "exercises": [],
        "created_at": datetime.utcnow(),
    }
    await db.classes.insert_one(new_class)
    clean_doc(new_class)
    return {"class": new_class}

@api_router.get("/teacher/classes")
async def get_teacher_classes(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    classes = await db.classes.find(
        {"teacher_id": current_user["id"]}
    ).to_list(100)
    for c in classes:
        clean_doc(c)
    return {"classes": classes}

@api_router.get("/teacher/classes/{class_id}")
async def get_class(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Classe non trouvée")
    if class_doc["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    clean_doc(class_doc)
    students_info = []
    for student_id in class_doc.get("students", []):
        student = await db.users.find_one({"id": student_id})
        if student:
            students_info.append({
                "id": student["id"],
                "username": student["username"],
                "grade": student["grade"],
            })
    return {
        "class": class_doc,
        "students": students_info,
    }

@api_router.delete("/teacher/classes/{class_id}")
async def delete_class(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Classe non trouvée")
    if class_doc["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    await db.classes.delete_one({"id": class_id})
    await db.exercises.delete_many({"class_id": class_id})
    await db.class_results.delete_many({"class_id": class_id})
    return {"message": "Classe supprimée"}

@api_router.post("/teacher/classes/{class_id}/exercises")
async def create_exercise(
    class_id: str,
    exercise_data: dict,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc or class_doc["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    exercise_type = exercise_data.get("type", "auto")
    questions = []
    if exercise_type == "auto":
        category = exercise_data.get("category", "calcul")
        difficulty = exercise_data.get("difficulty", 2)
        count = exercise_data.get("count", 10)
        for _ in range(count):
            prob = generate_problem(category, difficulty)
            questions.append({
                "id": prob["id"],
                "question": prob["question"],
                "answer": prob["answer"],
                "hint": prob.get("hint", ""),
                "explanation": prob["explanation"],
            })
    elif exercise_type == "python":
        code = exercise_data.get("code", "")
        result = execute_teacher_code(code)
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"Erreur dans votre code: {result.get('error')}"
            )
        for q in result.get("questions", []):
            q["id"] = str(uuid.uuid4())
            questions.append(q)
    elif exercise_type == "manual":
        for q in exercise_data.get("questions", []):
            q["id"] = str(uuid.uuid4())
            questions.append(q)
    exercise_id = str(uuid.uuid4())
    exercise = {
        "id": exercise_id,
        "class_id": class_id,
        "teacher_id": current_user["id"],
        "title": exercise_data.get("title", "Exercice sans titre"),
        "description": exercise_data.get("description", ""),
        "type": exercise_type,
        "questions": questions,
        "code": exercise_data.get("code", "") if exercise_type == "python" else "",
        "active": True,
        "created_at": datetime.utcnow(),
        "results": [],
    }
    await db.exercises.insert_one(exercise)
    clean_doc(exercise)
    await db.classes.update_one(
        {"id": class_id},
        {"$push": {"exercises": exercise_id}}
    )
    return {"exercise": exercise}

@api_router.get("/teacher/classes/{class_id}/exercises")
async def get_class_exercises(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Classe non trouvée")
    exercises = await db.exercises.find({"class_id": class_id}).to_list(100)
    for ex in exercises:
        clean_doc(ex)
    return {"exercises": exercises}

@api_router.delete("/teacher/exercises/{exercise_id}")
async def delete_exercise(
    exercise_id: str,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    exercise = await db.exercises.find_one({"id": exercise_id})
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercice non trouvé")
    if exercise["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    await db.exercises.delete_one({"id": exercise_id})
    await db.class_results.delete_many({"exercise_id": exercise_id})
    return {"message": "Exercice supprimé"}

@api_router.get("/teacher/code-template")
async def get_code_template(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    return {"template": TEACHER_CODE_TEMPLATE}

@api_router.post("/teacher/test-code")
async def test_teacher_code(
    code_data: dict,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    result = execute_teacher_code(code_data.get("code", ""))
    return result

@api_router.get("/teacher/classes/{class_id}/stats")
async def get_class_stats(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Accès réservé aux professeurs")
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc or class_doc["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")
    results = await db.class_results.find({"class_id": class_id}).to_list(10000)
    student_stats = {}
    for r in results:
        sid = r["student_id"]
        if sid not in student_stats:
            student_stats[sid] = {
                "student_id": sid,
                "username": r.get("username", "Inconnu"),
                "total": 0,
                "correct": 0,
                "exercises_done": set(),
                "total_time": 0,
                "history": [],
            }
        student_stats[sid]["total"] += 1
        if r.get("correct"):
            student_stats[sid]["correct"] += 1
        student_stats[sid]["exercises_done"].add(r.get("exercise_id"))
        student_stats[sid]["total_time"] += r.get("time_spent", 0)
        student_stats[sid]["history"].append({
            "date": r.get("date"),
            "correct": r.get("correct"),
            "exercise_id": r.get("exercise_id"),
        })
    students_list = []
    for sid, stats in student_stats.items():
        accuracy = round(
            (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1
        )
        students_list.append({
            "student_id": sid,
            "username": stats["username"],
            "total_answers": stats["total"],
            "correct_answers": stats["correct"],
            "accuracy": accuracy,
            "exercises_done": len(stats["exercises_done"]),
            "total_time_seconds": stats["total_time"],
            "avg_time_per_question": round(
                stats["total_time"] / stats["total"], 1
            ) if stats["total"] > 0 else 0,
            "history": sorted(stats["history"], key=lambda x: x.get("date", "")),
        })
    students_list.sort(key=lambda x: x["accuracy"], reverse=True)
    exercise_stats = {}
    for r in results:
        eid = r.get("exercise_id")
        if eid not in exercise_stats:
            exercise_stats[eid] = {
                "exercise_id": eid,
                "title": r.get("exercise_title", "Exercice"),
                "total": 0,
                "correct": 0,
                "total_time": 0,
                "students_attempted": set(),
            }
        exercise_stats[eid]["total"] += 1
        if r.get("correct"):
            exercise_stats[eid]["correct"] += 1
        exercise_stats[eid]["total_time"] += r.get("time_spent", 0)
        exercise_stats[eid]["students_attempted"].add(r.get("student_id"))
    exercises_list = []
    for eid, stats in exercise_stats.items():
        accuracy = round(
            (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0, 1
        )
        exercises_list.append({
            "exercise_id": eid,
            "title": stats["title"],
            "total_answers": stats["total"],
            "correct_answers": stats["correct"],
            "accuracy": accuracy,
            "students_attempted": len(stats["students_attempted"]),
            "avg_time_seconds": round(
                stats["total_time"] / stats["total"], 1
            ) if stats["total"] > 0 else 0,
        })
    return {
        "class_name": class_doc["name"],
        "total_students": len(class_doc.get("students", [])),
        "students_stats": students_list,
        "exercises_stats": exercises_list,
    }

# ==================== STUDENT ROUTES ====================

@api_router.post("/student/join-class")
async def join_class(
    join_data: dict,
    current_user: dict = Depends(get_current_user)
):
    code = join_data.get("code", "").upper().strip()
    class_doc = await db.classes.find_one({"code": code})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Code de classe invalide")
    student_id = current_user["id"]
    if student_id in class_doc.get("students", []):
        raise HTTPException(status_code=400, detail="Tu es déjà dans cette classe")
    await db.classes.update_one(
        {"id": class_doc["id"]},
        {"$push": {"students": student_id}}
    )
    return {
        "message": f"Tu as rejoint la classe {class_doc['name']}",
        "class": {
            "id": class_doc["id"],
            "name": class_doc["name"],
            "teacher_name": class_doc["teacher_name"],
        }
    }

@api_router.get("/student/classes")
async def get_student_classes(current_user: dict = Depends(get_current_user)):
    classes = await db.classes.find({"students": current_user["id"]}).to_list(100)
    result = []
    for c in classes:
        exercises = await db.exercises.find(
            {"class_id": c["id"], "active": True}
        ).to_list(100)
        result.append({
            "id": c["id"],
            "name": c["name"],
            "teacher_name": c["teacher_name"],
            "exercises_count": len(exercises),
        })
    return {"classes": result}

@api_router.get("/student/classes/{class_id}/exercises")
async def get_student_exercises(
    class_id: str,
    current_user: dict = Depends(get_current_user)
):
    class_doc = await db.classes.find_one({"id": class_id})
    if not class_doc:
        raise HTTPException(status_code=404, detail="Classe non trouvée")
    if current_user["id"] not in class_doc.get("students", []):
        raise HTTPException(status_code=403, detail="Tu n'es pas dans cette classe")
    exercises = await db.exercises.find(
        {"class_id": class_id, "active": True}
    ).to_list(100)
    result = []
    for ex in exercises:
        done = await db.class_results.find_one({
            "exercise_id": ex["id"],
            "student_id": current_user["id"],
        })
        result.append({
            "id": ex["id"],
            "title": ex["title"],
            "description": ex["description"],
            "questions_count": len(ex.get("questions", [])),
            "already_done": done is not None,
        })
    return {
        "class_name": class_doc["name"],
        "teacher_name": class_doc["teacher_name"],
        "exercises": result,
    }

@api_router.get("/student/exercises/{exercise_id}")
async def get_exercise(
    exercise_id: str,
    current_user: dict = Depends(get_current_user)
):
    exercise = await db.exercises.find_one({"id": exercise_id})
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercice non trouvé")
    clean_doc(exercise)
    return {"exercise": exercise}

@api_router.post("/student/exercises/{exercise_id}/submit")
async def submit_exercise_result(
    exercise_id: str,
    result_data: dict,
    current_user: dict = Depends(get_current_user)
):
    exercise = await db.exercises.find_one({"id": exercise_id})
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercice non trouvé")
    answers = result_data.get("answers", [])
    time_spent = result_data.get("time_spent", 0)
    questions = exercise.get("questions", [])
    results = []
    correct_count = 0
    nb_questions = len(questions)
    time_per_question = round(time_spent / nb_questions, 1) if nb_questions > 0 else 0
    for i, question in enumerate(questions):
        if i < len(answers):
            try:
                student_answer = float(answers[i]) if answers[i] != "" else None
            except (ValueError, TypeError):
                student_answer = None
            correct_answer = float(question["answer"])
            is_correct = student_answer is not None and abs(student_answer - correct_answer) < 0.1
            if is_correct:
                correct_count += 1
            results.append({
                "question": question["question"],
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "correct": is_correct,
                "explanation": question.get("explanation", ""),
            })
            await db.class_results.insert_one({
                "id": str(uuid.uuid4()),
                "class_id": exercise["class_id"],
                "exercise_id": exercise_id,
                "exercise_title": exercise["title"],
                "student_id": current_user["id"],
                "username": current_user["username"],
                "question_id": question.get("id", str(i)),
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "correct": is_correct,
                "time_spent": time_per_question,
                "date": get_today_date(),
                "created_at": datetime.utcnow(),
            })
    accuracy = round((correct_count / len(questions) * 100) if questions else 0, 1)
    return {
        "results": results,
        "correct_count": correct_count,
        "total": len(questions),
        "accuracy": accuracy,
        "time_spent": time_spent,
    }

# ==================== CLAN ROUTES ====================

@api_router.post("/clans")
async def create_clan(
    clan_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas créer de clan")

    # Vérifie que l'utilisateur n'est pas déjà dans un clan
    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    name = clan_data.get("name", "").strip()
    if not name or len(name) < 3 or len(name) > 20:
        raise HTTPException(status_code=400, detail="Le nom doit faire entre 3 et 20 caractères")

    # Vérifie que le nom n'existe pas déjà
    if await db.clans.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Ce nom de clan est déjà pris")

    clan_id = str(uuid.uuid4())
    tag = generate_clan_tag()
    genius_index = 0
    league = get_league(genius_index)

    clan = {
        "id": clan_id,
        "name": name,
        "tag": tag,
        "description": clan_data.get("description", ""),
        "genius_index": genius_index,
        "league": league["name"],
        "members": [{
            "id": current_user["id"],
            "username": current_user["username"],
            "elo_online": current_user.get("elo_online", 1000),
            "rank": "chef",
        }],
        "current_war_id": None,
        "war_history": [],
        "created_at": datetime.utcnow(),
    }

    await db.clans.insert_one(clan)
    clean_doc(clan)

    # Met à jour l'utilisateur
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "chef"}}
    )

    return {"clan": clan}

@api_router.get("/clans/my")
async def get_my_clan(current_user: dict = Depends(get_current_user)):
    """Récupère le clan de l'utilisateur"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        return {"clan": None}
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        return {"clan": None}
    clean_doc(clan)

    # Calcule l'Elo total du clan
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))

    return {"clan": clan}

@api_router.get("/clans/search")
async def search_clans(q: str = "", limit: int = 20):
    """Recherche des clans par nom"""
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    clans = await db.clans.find(query).limit(limit).to_list(limit)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "description": clan.get("description", ""),
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"clans": result}

@api_router.get("/clans/{clan_id}")
async def get_clan(clan_id: str):
    """Récupère le détail d'un clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")
    clean_doc(clan)
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))
    return {"clan": clan}

@api_router.post("/clans/{clan_id}/join")
async def join_clan(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejoindre un clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas rejoindre un clan")

    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if len(clan.get("members", [])) >= 40:
        raise HTTPException(status_code=400, detail="Le clan est complet (40/40)")

    new_member = {
        "id": current_user["id"],
        "username": current_user["username"],
        "elo_online": current_user.get("elo_online", 1000),
        "rank": "recrue",
    }

    await db.clans.update_one(
        {"id": clan_id},
        {"$push": {"members": new_member}}
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "recrue"}}
    )

    return {"message": f"Tu as rejoint le clan {clan['name']} !"}

@api_router.post("/clans/leave")
async def leave_clan(current_user: dict = Depends(get_current_user)):
    """Quitter son clan"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        raise HTTPException(status_code=400, detail="Tu n'es pas dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    clan_rank = current_user.get("clan_rank", "recrue")

    # Si chef et seul membre → supprime le clan
    if clan_rank == "chef" and len(clan.get("members", [])) == 1:
        await db.clans.delete_one({"id": clan_id})
    elif clan_rank == "chef":
        # Passe le grade de chef au prochain membre le plus gradé
        members = clan.get("members", [])
        members = [m for m in members if m["id"] != current_user["id"]]
        rank_order = ["expert", "analyste", "recrue"]
        new_chef = None
        for rank in rank_order:
            for m in members:
                if m.get("rank") == rank:
                    new_chef = m
                    break
            if new_chef:
                break
        if not new_chef and members:
            new_chef = members[0]
        if new_chef:
            await db.clans.update_one(
                {"id": clan_id, "members.id": new_chef["id"]},
                {"$set": {"members.$.rank": "chef"}}
            )
            await db.users.update_one(
                {"id": new_chef["id"]},
                {"$set": {"clan_rank": "chef"}}
            )
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )
    else:
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Tu as quitté le clan"}

@api_router.post("/clans/{clan_id}/promote")
async def promote_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Promouvoir un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank != "chef":
        raise HTTPException(status_code=403, detail="Seul le chef peut promouvoir")

    member_id = member_data.get("member_id")
    new_rank = member_data.get("rank")

    if new_rank not in CLAN_RANKS:
        raise HTTPException(status_code=400, detail="Rang invalide")
    if new_rank == "chef":
        raise HTTPException(status_code=400, detail="Utilise /transfer-leadership pour transférer le commandement")

    await db.clans.update_one(
        {"id": clan_id, "members.id": member_id},
        {"$set": {"members.$.rank": new_rank}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$set": {"clan_rank": new_rank}}
    )

    return {"message": "Membre promu"}

@api_router.post("/clans/{clan_id}/kick")
async def kick_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expulser un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    member_id = member_data.get("member_id")
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'expulser toi-même")

    await db.clans.update_one(
        {"id": clan_id},
        {"$pull": {"members": {"id": member_id}}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Membre expulsé"}

# ==================== CLAN WAR ROUTES ====================

@api_router.post("/clans/{clan_id}/war/start")
async def start_war(
    clan_id: str,
    war_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Lance la recherche d'une guerre de clan"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Seul le chef ou un expert peut lancer une guerre")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if clan.get("current_war_id"):
        raise HTTPException(status_code=400, detail="Ton clan est déjà en guerre")

    if clan_id in WAR_QUEUE:
        raise HTTPException(status_code=400, detail="Ton clan est déjà en file d'attente")

    war_format = war_data.get("format")
    if war_format not in WAR_FORMATS:
        raise HTTPException(status_code=400, detail="Format invalide (10, 15 ou 20)")

    selected_member_ids = war_data.get("member_ids", [])
    if len(selected_member_ids) != war_format:
        raise HTTPException(
            status_code=400,
            detail=f"Tu dois sélectionner exactement {war_format} membres"
        )

    # Récupère les infos des membres sélectionnés
    all_members = clan.get("members", [])
    selected_members = [m for m in all_members if m["id"] in selected_member_ids]

    if len(selected_members) != war_format:
        raise HTTPException(status_code=400, detail="Certains membres sont invalides")

    genius_index = clan.get("genius_index", 0)
    league = get_league(genius_index)

    # Ajoute à la file d'attente
    WAR_QUEUE[clan_id] = {
        "clan_name": clan["name"],
        "format": war_format,
        "league": league["name"],
        "genius_index": genius_index,
        "members": selected_members,
        "queued_at": datetime.utcnow().isoformat(),
    }

    # Essaie de trouver un adversaire immédiatement
    war_id = await try_matchmaking(clan_id, db)

    if war_id:
        return {
            "status": "war_started",
            "war_id": war_id,
            "message": "Adversaire trouvé ! La guerre commence !",
        }
    else:
        return {
            "status": "searching",
            "message": f"Recherche d'un adversaire en ligue {league['name']}...",
        }

@api_router.delete("/clans/{clan_id}/war/cancel")
async def cancel_war_search(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Annule la recherche de guerre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    if clan_id in WAR_QUEUE:
        WAR_QUEUE.pop(clan_id)
        return {"message": "Recherche annulée"}
    raise HTTPException(status_code=400, detail="Ton clan n'est pas en file d'attente")

@api_router.get("/clans/{clan_id}/war/current")
async def get_current_war(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère la guerre en cours du clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    war_id = clan.get("current_war_id")

    # Vérifie si en file d'attente
    if clan_id in WAR_QUEUE:
        return {
            "status": "searching",
            "queue_data": {
                "format": WAR_QUEUE[clan_id]["format"],
                "league": WAR_QUEUE[clan_id]["league"],
                "queued_at": WAR_QUEUE[clan_id]["queued_at"],
            }
        }

    if not war_id or war_id not in active_wars:
        # Vérifie en base
        war_db = await db.clan_wars.find_one({"id": war_id}) if war_id else None
        if war_db:
            clean_doc(war_db)
            return {"status": "finished", "war": war_db}
        return {"status": "no_war"}

    scores = get_war_scores(war_id)
    return {"status": "active", "war_id": war_id, "scores": scores}

@api_router.get("/wars/{war_id}/scores")
async def get_war_scores_route(
    war_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère les scores en temps réel d'une guerre"""
    scores = get_war_scores(war_id)
    if not scores:
        raise HTTPException(status_code=404, detail="Guerre non trouvée")
    return scores

# ==================== CLAN ROUTES ====================

@api_router.post("/clans")
async def create_clan(
    clan_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas créer de clan")

    # Vérifie que l'utilisateur n'est pas déjà dans un clan
    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    name = clan_data.get("name", "").strip()
    if not name or len(name) < 3 or len(name) > 20:
        raise HTTPException(status_code=400, detail="Le nom doit faire entre 3 et 20 caractères")

    # Vérifie que le nom n'existe pas déjà
    if await db.clans.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Ce nom de clan est déjà pris")

    clan_id = str(uuid.uuid4())
    tag = generate_clan_tag()
    genius_index = 0
    league = get_league(genius_index)

    clan = {
        "id": clan_id,
        "name": name,
        "tag": tag,
        "description": clan_data.get("description", ""),
        "genius_index": genius_index,
        "league": league["name"],
        "members": [{
            "id": current_user["id"],
            "username": current_user["username"],
            "elo_online": current_user.get("elo_online", 1000),
            "rank": "chef",
        }],
        "current_war_id": None,
        "war_history": [],
        "created_at": datetime.utcnow(),
    }

    await db.clans.insert_one(clan)
    clean_doc(clan)

    # Met à jour l'utilisateur
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "chef"}}
    )

    return {"clan": clan}

@api_router.get("/clans/my")
async def get_my_clan(current_user: dict = Depends(get_current_user)):
    """Récupère le clan de l'utilisateur"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        return {"clan": None}
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        return {"clan": None}
    clean_doc(clan)

    # Calcule l'Elo total du clan
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))

    return {"clan": clan}

@api_router.get("/clans/search")
async def search_clans(q: str = "", limit: int = 20):
    """Recherche des clans par nom"""
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    clans = await db.clans.find(query).limit(limit).to_list(limit)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "description": clan.get("description", ""),
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"clans": result}

@api_router.get("/clans/{clan_id}")
async def get_clan(clan_id: str):
    """Récupère le détail d'un clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")
    clean_doc(clan)
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))
    return {"clan": clan}

@api_router.post("/clans/{clan_id}/join")
async def join_clan(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejoindre un clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas rejoindre un clan")

    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if len(clan.get("members", [])) >= 40:
        raise HTTPException(status_code=400, detail="Le clan est complet (40/40)")

    new_member = {
        "id": current_user["id"],
        "username": current_user["username"],
        "elo_online": current_user.get("elo_online", 1000),
        "rank": "recrue",
    }

    await db.clans.update_one(
        {"id": clan_id},
        {"$push": {"members": new_member}}
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "recrue"}}
    )

    return {"message": f"Tu as rejoint le clan {clan['name']} !"}

@api_router.post("/clans/leave")
async def leave_clan(current_user: dict = Depends(get_current_user)):
    """Quitter son clan"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        raise HTTPException(status_code=400, detail="Tu n'es pas dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    clan_rank = current_user.get("clan_rank", "recrue")

    # Si chef et seul membre → supprime le clan
    if clan_rank == "chef" and len(clan.get("members", [])) == 1:
        await db.clans.delete_one({"id": clan_id})
    elif clan_rank == "chef":
        # Passe le grade de chef au prochain membre le plus gradé
        members = clan.get("members", [])
        members = [m for m in members if m["id"] != current_user["id"]]
        rank_order = ["expert", "analyste", "recrue"]
        new_chef = None
        for rank in rank_order:
            for m in members:
                if m.get("rank") == rank:
                    new_chef = m
                    break
            if new_chef:
                break
        if not new_chef and members:
            new_chef = members[0]
        if new_chef:
            await db.clans.update_one(
                {"id": clan_id, "members.id": new_chef["id"]},
                {"$set": {"members.$.rank": "chef"}}
            )
            await db.users.update_one(
                {"id": new_chef["id"]},
                {"$set": {"clan_rank": "chef"}}
            )
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )
    else:
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Tu as quitté le clan"}

@api_router.post("/clans/{clan_id}/promote")
async def promote_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Promouvoir un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank != "chef":
        raise HTTPException(status_code=403, detail="Seul le chef peut promouvoir")

    member_id = member_data.get("member_id")
    new_rank = member_data.get("rank")

    if new_rank not in CLAN_RANKS:
        raise HTTPException(status_code=400, detail="Rang invalide")
    if new_rank == "chef":
        raise HTTPException(status_code=400, detail="Utilise /transfer-leadership pour transférer le commandement")

    await db.clans.update_one(
        {"id": clan_id, "members.id": member_id},
        {"$set": {"members.$.rank": new_rank}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$set": {"clan_rank": new_rank}}
    )

    return {"message": "Membre promu"}

@api_router.post("/clans/{clan_id}/kick")
async def kick_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expulser un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    member_id = member_data.get("member_id")
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'expulser toi-même")

    await db.clans.update_one(
        {"id": clan_id},
        {"$pull": {"members": {"id": member_id}}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Membre expulsé"}

# ==================== CLAN WAR ROUTES ====================

@api_router.post("/clans/{clan_id}/war/start")
async def start_war(
    clan_id: str,
    war_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Lance la recherche d'une guerre de clan"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Seul le chef ou un expert peut lancer une guerre")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if clan.get("current_war_id"):
        raise HTTPException(status_code=400, detail="Ton clan est déjà en guerre")

    if clan_id in WAR_QUEUE:
        raise HTTPException(status_code=400, detail="Ton clan est déjà en file d'attente")

    war_format = war_data.get("format")
    if war_format not in WAR_FORMATS:
        raise HTTPException(status_code=400, detail="Format invalide (10, 15 ou 20)")

    selected_member_ids = war_data.get("member_ids", [])
    if len(selected_member_ids) != war_format:
        raise HTTPException(
            status_code=400,
            detail=f"Tu dois sélectionner exactement {war_format} membres"
        )

    # Récupère les infos des membres sélectionnés
    all_members = clan.get("members", [])
    selected_members = [m for m in all_members if m["id"] in selected_member_ids]

    if len(selected_members) != war_format:
        raise HTTPException(status_code=400, detail="Certains membres sont invalides")

    genius_index = clan.get("genius_index", 0)
    league = get_league(genius_index)

    # Ajoute à la file d'attente
    WAR_QUEUE[clan_id] = {
        "clan_name": clan["name"],
        "format": war_format,
        "league": league["name"],
        "genius_index": genius_index,
        "members": selected_members,
        "queued_at": datetime.utcnow().isoformat(),
    }

    # Essaie de trouver un adversaire immédiatement
    war_id = await try_matchmaking(clan_id, db)

    if war_id:
        return {
            "status": "war_started",
            "war_id": war_id,
            "message": "Adversaire trouvé ! La guerre commence !",
        }
    else:
        return {
            "status": "searching",
            "message": f"Recherche d'un adversaire en ligue {league['name']}...",
        }

@api_router.delete("/clans/{clan_id}/war/cancel")
async def cancel_war_search(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Annule la recherche de guerre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    if clan_id in WAR_QUEUE:
        WAR_QUEUE.pop(clan_id)
        return {"message": "Recherche annulée"}
    raise HTTPException(status_code=400, detail="Ton clan n'est pas en file d'attente")

@api_router.get("/clans/{clan_id}/war/current")
async def get_current_war(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère la guerre en cours du clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    war_id = clan.get("current_war_id")

    # Vérifie si en file d'attente
    if clan_id in WAR_QUEUE:
        return {
            "status": "searching",
            "queue_data": {
                "format": WAR_QUEUE[clan_id]["format"],
                "league": WAR_QUEUE[clan_id]["league"],
                "queued_at": WAR_QUEUE[clan_id]["queued_at"],
            }
        }

    if not war_id or war_id not in active_wars:
        # Vérifie en base
        war_db = await db.clan_wars.find_one({"id": war_id}) if war_id else None
        if war_db:
            clean_doc(war_db)
            return {"status": "finished", "war": war_db}
        return {"status": "no_war"}

    scores = get_war_scores(war_id)
    return {"status": "active", "war_id": war_id, "scores": scores}

@api_router.get("/wars/{war_id}/scores")
async def get_war_scores_route(
    war_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère les scores en temps réel d'une guerre"""
    scores = get_war_scores(war_id)
    if not scores:
        raise HTTPException(status_code=404, detail="Guerre non trouvée")
    return scores

# ==================== CLAN ROUTES ====================

@api_router.post("/clans")
async def create_clan(
    clan_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas créer de clan")

    # Vérifie que l'utilisateur n'est pas déjà dans un clan
    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    name = clan_data.get("name", "").strip()
    if not name or len(name) < 3 or len(name) > 20:
        raise HTTPException(status_code=400, detail="Le nom doit faire entre 3 et 20 caractères")

    # Vérifie que le nom n'existe pas déjà
    if await db.clans.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Ce nom de clan est déjà pris")

    clan_id = str(uuid.uuid4())
    tag = generate_clan_tag()
    genius_index = 0
    league = get_league(genius_index)

    clan = {
        "id": clan_id,
        "name": name,
        "tag": tag,
        "description": clan_data.get("description", ""),
        "genius_index": genius_index,
        "league": league["name"],
        "members": [{
            "id": current_user["id"],
            "username": current_user["username"],
            "elo_online": current_user.get("elo_online", 1000),
            "rank": "chef",
        }],
        "current_war_id": None,
        "war_history": [],
        "created_at": datetime.utcnow(),
    }

    await db.clans.insert_one(clan)
    clean_doc(clan)

    # Met à jour l'utilisateur
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "chef"}}
    )

    return {"clan": clan}

@api_router.get("/clans/my")
async def get_my_clan(current_user: dict = Depends(get_current_user)):
    """Récupère le clan de l'utilisateur"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        return {"clan": None}
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        return {"clan": None}
    clean_doc(clan)

    # Calcule l'Elo total du clan
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))

    return {"clan": clan}

@api_router.get("/clans/search")
async def search_clans(q: str = "", limit: int = 20):
    """Recherche des clans par nom"""
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    clans = await db.clans.find(query).limit(limit).to_list(limit)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "description": clan.get("description", ""),
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"clans": result}

@api_router.get("/clans/{clan_id}")
async def get_clan(clan_id: str):
    """Récupère le détail d'un clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")
    clean_doc(clan)
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))
    return {"clan": clan}

@api_router.post("/clans/{clan_id}/join")
async def join_clan(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejoindre un clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas rejoindre un clan")

    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if len(clan.get("members", [])) >= 40:
        raise HTTPException(status_code=400, detail="Le clan est complet (40/40)")

    new_member = {
        "id": current_user["id"],
        "username": current_user["username"],
        "elo_online": current_user.get("elo_online", 1000),
        "rank": "recrue",
    }

    await db.clans.update_one(
        {"id": clan_id},
        {"$push": {"members": new_member}}
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "recrue"}}
    )

    return {"message": f"Tu as rejoint le clan {clan['name']} !"}

@api_router.post("/clans/leave")
async def leave_clan(current_user: dict = Depends(get_current_user)):
    """Quitter son clan"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        raise HTTPException(status_code=400, detail="Tu n'es pas dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    clan_rank = current_user.get("clan_rank", "recrue")

    # Si chef et seul membre → supprime le clan
    if clan_rank == "chef" and len(clan.get("members", [])) == 1:
        await db.clans.delete_one({"id": clan_id})
    elif clan_rank == "chef":
        # Passe le grade de chef au prochain membre le plus gradé
        members = clan.get("members", [])
        members = [m for m in members if m["id"] != current_user["id"]]
        rank_order = ["expert", "analyste", "recrue"]
        new_chef = None
        for rank in rank_order:
            for m in members:
                if m.get("rank") == rank:
                    new_chef = m
                    break
            if new_chef:
                break
        if not new_chef and members:
            new_chef = members[0]
        if new_chef:
            await db.clans.update_one(
                {"id": clan_id, "members.id": new_chef["id"]},
                {"$set": {"members.$.rank": "chef"}}
            )
            await db.users.update_one(
                {"id": new_chef["id"]},
                {"$set": {"clan_rank": "chef"}}
            )
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )
    else:
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Tu as quitté le clan"}

@api_router.post("/clans/{clan_id}/promote")
async def promote_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Promouvoir un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank != "chef":
        raise HTTPException(status_code=403, detail="Seul le chef peut promouvoir")

    member_id = member_data.get("member_id")
    new_rank = member_data.get("rank")

    if new_rank not in CLAN_RANKS:
        raise HTTPException(status_code=400, detail="Rang invalide")
    if new_rank == "chef":
        raise HTTPException(status_code=400, detail="Utilise /transfer-leadership pour transférer le commandement")

    await db.clans.update_one(
        {"id": clan_id, "members.id": member_id},
        {"$set": {"members.$.rank": new_rank}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$set": {"clan_rank": new_rank}}
    )

    return {"message": "Membre promu"}

@api_router.post("/clans/{clan_id}/kick")
async def kick_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expulser un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    member_id = member_data.get("member_id")
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'expulser toi-même")

    await db.clans.update_one(
        {"id": clan_id},
        {"$pull": {"members": {"id": member_id}}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Membre expulsé"}

# ==================== CLAN WAR ROUTES ====================

@api_router.post("/clans/{clan_id}/war/start")
async def start_war(
    clan_id: str,
    war_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Lance la recherche d'une guerre de clan"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Seul le chef ou un expert peut lancer une guerre")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if clan.get("current_war_id"):
        raise HTTPException(status_code=400, detail="Ton clan est déjà en guerre")

    if clan_id in WAR_QUEUE:
        raise HTTPException(status_code=400, detail="Ton clan est déjà en file d'attente")

    war_format = war_data.get("format")
    if war_format not in WAR_FORMATS:
        raise HTTPException(status_code=400, detail="Format invalide (10, 15 ou 20)")

    selected_member_ids = war_data.get("member_ids", [])
    if len(selected_member_ids) != war_format:
        raise HTTPException(
            status_code=400,
            detail=f"Tu dois sélectionner exactement {war_format} membres"
        )

    # Récupère les infos des membres sélectionnés
    all_members = clan.get("members", [])
    selected_members = [m for m in all_members if m["id"] in selected_member_ids]

    if len(selected_members) != war_format:
        raise HTTPException(status_code=400, detail="Certains membres sont invalides")

    genius_index = clan.get("genius_index", 0)
    league = get_league(genius_index)

    # Ajoute à la file d'attente
    WAR_QUEUE[clan_id] = {
        "clan_name": clan["name"],
        "format": war_format,
        "league": league["name"],
        "genius_index": genius_index,
        "members": selected_members,
        "queued_at": datetime.utcnow().isoformat(),
    }

    # Essaie de trouver un adversaire immédiatement
    war_id = await try_matchmaking(clan_id, db)

    if war_id:
        return {
            "status": "war_started",
            "war_id": war_id,
            "message": "Adversaire trouvé ! La guerre commence !",
        }
    else:
        return {
            "status": "searching",
            "message": f"Recherche d'un adversaire en ligue {league['name']}...",
        }

@api_router.delete("/clans/{clan_id}/war/cancel")
async def cancel_war_search(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Annule la recherche de guerre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    if clan_id in WAR_QUEUE:
        WAR_QUEUE.pop(clan_id)
        return {"message": "Recherche annulée"}
    raise HTTPException(status_code=400, detail="Ton clan n'est pas en file d'attente")

@api_router.get("/clans/{clan_id}/war/current")
async def get_current_war(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère la guerre en cours du clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    war_id = clan.get("current_war_id")

    # Vérifie si en file d'attente
    if clan_id in WAR_QUEUE:
        return {
            "status": "searching",
            "queue_data": {
                "format": WAR_QUEUE[clan_id]["format"],
                "league": WAR_QUEUE[clan_id]["league"],
                "queued_at": WAR_QUEUE[clan_id]["queued_at"],
            }
        }

    if not war_id or war_id not in active_wars:
        # Vérifie en base
        war_db = await db.clan_wars.find_one({"id": war_id}) if war_id else None
        if war_db:
            clean_doc(war_db)
            return {"status": "finished", "war": war_db}
        return {"status": "no_war"}

    scores = get_war_scores(war_id)
    return {"status": "active", "war_id": war_id, "scores": scores}

@api_router.get("/wars/{war_id}/scores")
async def get_war_scores_route(
    war_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère les scores en temps réel d'une guerre"""
    scores = get_war_scores(war_id)
    if not scores:
        raise HTTPException(status_code=404, detail="Guerre non trouvée")
    return scores

# ==================== CLAN ROUTES ====================

@api_router.post("/clans")
async def create_clan(
    clan_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas créer de clan")

    # Vérifie que l'utilisateur n'est pas déjà dans un clan
    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    name = clan_data.get("name", "").strip()
    if not name or len(name) < 3 or len(name) > 20:
        raise HTTPException(status_code=400, detail="Le nom doit faire entre 3 et 20 caractères")

    # Vérifie que le nom n'existe pas déjà
    if await db.clans.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Ce nom de clan est déjà pris")

    clan_id = str(uuid.uuid4())
    tag = generate_clan_tag()
    genius_index = 0
    league = get_league(genius_index)

    clan = {
        "id": clan_id,
        "name": name,
        "tag": tag,
        "description": clan_data.get("description", ""),
        "genius_index": genius_index,
        "league": league["name"],
        "members": [{
            "id": current_user["id"],
            "username": current_user["username"],
            "elo_online": current_user.get("elo_online", 1000),
            "rank": "chef",
        }],
        "current_war_id": None,
        "war_history": [],
        "created_at": datetime.utcnow(),
    }

    await db.clans.insert_one(clan)
    clean_doc(clan)

    # Met à jour l'utilisateur
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "chef"}}
    )

    return {"clan": clan}

@api_router.get("/clans/my")
async def get_my_clan(current_user: dict = Depends(get_current_user)):
    """Récupère le clan de l'utilisateur"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        return {"clan": None}
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        return {"clan": None}
    clean_doc(clan)

    # Calcule l'Elo total du clan
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))

    return {"clan": clan}

@api_router.get("/clans/search")
async def search_clans(q: str = "", limit: int = 20):
    """Recherche des clans par nom"""
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    clans = await db.clans.find(query).limit(limit).to_list(limit)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "description": clan.get("description", ""),
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"clans": result}

@api_router.get("/clans/{clan_id}")
async def get_clan(clan_id: str):
    """Récupère le détail d'un clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")
    clean_doc(clan)
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))
    return {"clan": clan}

@api_router.post("/clans/{clan_id}/join")
async def join_clan(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejoindre un clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas rejoindre un clan")

    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if len(clan.get("members", [])) >= 40:
        raise HTTPException(status_code=400, detail="Le clan est complet (40/40)")

    new_member = {
        "id": current_user["id"],
        "username": current_user["username"],
        "elo_online": current_user.get("elo_online", 1000),
        "rank": "recrue",
    }

    await db.clans.update_one(
        {"id": clan_id},
        {"$push": {"members": new_member}}
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "recrue"}}
    )

    return {"message": f"Tu as rejoint le clan {clan['name']} !"}

@api_router.post("/clans/leave")
async def leave_clan(current_user: dict = Depends(get_current_user)):
    """Quitter son clan"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        raise HTTPException(status_code=400, detail="Tu n'es pas dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    clan_rank = current_user.get("clan_rank", "recrue")

    # Si chef et seul membre → supprime le clan
    if clan_rank == "chef" and len(clan.get("members", [])) == 1:
        await db.clans.delete_one({"id": clan_id})
    elif clan_rank == "chef":
        # Passe le grade de chef au prochain membre le plus gradé
        members = clan.get("members", [])
        members = [m for m in members if m["id"] != current_user["id"]]
        rank_order = ["expert", "analyste", "recrue"]
        new_chef = None
        for rank in rank_order:
            for m in members:
                if m.get("rank") == rank:
                    new_chef = m
                    break
            if new_chef:
                break
        if not new_chef and members:
            new_chef = members[0]
        if new_chef:
            await db.clans.update_one(
                {"id": clan_id, "members.id": new_chef["id"]},
                {"$set": {"members.$.rank": "chef"}}
            )
            await db.users.update_one(
                {"id": new_chef["id"]},
                {"$set": {"clan_rank": "chef"}}
            )
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )
    else:
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Tu as quitté le clan"}

@api_router.post("/clans/{clan_id}/promote")
async def promote_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Promouvoir un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank != "chef":
        raise HTTPException(status_code=403, detail="Seul le chef peut promouvoir")

    member_id = member_data.get("member_id")
    new_rank = member_data.get("rank")

    if new_rank not in CLAN_RANKS:
        raise HTTPException(status_code=400, detail="Rang invalide")
    if new_rank == "chef":
        raise HTTPException(status_code=400, detail="Utilise /transfer-leadership pour transférer le commandement")

    await db.clans.update_one(
        {"id": clan_id, "members.id": member_id},
        {"$set": {"members.$.rank": new_rank}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$set": {"clan_rank": new_rank}}
    )

    return {"message": "Membre promu"}

@api_router.post("/clans/{clan_id}/kick")
async def kick_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expulser un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    member_id = member_data.get("member_id")
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'expulser toi-même")

    await db.clans.update_one(
        {"id": clan_id},
        {"$pull": {"members": {"id": member_id}}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Membre expulsé"}

# ==================== CLAN WAR ROUTES ====================

@api_router.post("/clans/{clan_id}/war/start")
async def start_war(
    clan_id: str,
    war_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Lance la recherche d'une guerre de clan"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Seul le chef ou un expert peut lancer une guerre")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if clan.get("current_war_id"):
        raise HTTPException(status_code=400, detail="Ton clan est déjà en guerre")

    if clan_id in WAR_QUEUE:
        raise HTTPException(status_code=400, detail="Ton clan est déjà en file d'attente")

    war_format = war_data.get("format")
    if war_format not in WAR_FORMATS:
        raise HTTPException(status_code=400, detail="Format invalide (10, 15 ou 20)")

    selected_member_ids = war_data.get("member_ids", [])
    if len(selected_member_ids) != war_format:
        raise HTTPException(
            status_code=400,
            detail=f"Tu dois sélectionner exactement {war_format} membres"
        )

    # Récupère les infos des membres sélectionnés
    all_members = clan.get("members", [])
    selected_members = [m for m in all_members if m["id"] in selected_member_ids]

    if len(selected_members) != war_format:
        raise HTTPException(status_code=400, detail="Certains membres sont invalides")

    genius_index = clan.get("genius_index", 0)
    league = get_league(genius_index)

    # Ajoute à la file d'attente
    WAR_QUEUE[clan_id] = {
        "clan_name": clan["name"],
        "format": war_format,
        "league": league["name"],
        "genius_index": genius_index,
        "members": selected_members,
        "queued_at": datetime.utcnow().isoformat(),
    }

    # Essaie de trouver un adversaire immédiatement
    war_id = await try_matchmaking(clan_id, db)

    if war_id:
        return {
            "status": "war_started",
            "war_id": war_id,
            "message": "Adversaire trouvé ! La guerre commence !",
        }
    else:
        return {
            "status": "searching",
            "message": f"Recherche d'un adversaire en ligue {league['name']}...",
        }

@api_router.delete("/clans/{clan_id}/war/cancel")
async def cancel_war_search(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Annule la recherche de guerre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    if clan_id in WAR_QUEUE:
        WAR_QUEUE.pop(clan_id)
        return {"message": "Recherche annulée"}
    raise HTTPException(status_code=400, detail="Ton clan n'est pas en file d'attente")

@api_router.get("/clans/{clan_id}/war/current")
async def get_current_war(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère la guerre en cours du clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    war_id = clan.get("current_war_id")

    # Vérifie si en file d'attente
    if clan_id in WAR_QUEUE:
        return {
            "status": "searching",
            "queue_data": {
                "format": WAR_QUEUE[clan_id]["format"],
                "league": WAR_QUEUE[clan_id]["league"],
                "queued_at": WAR_QUEUE[clan_id]["queued_at"],
            }
        }

    if not war_id or war_id not in active_wars:
        # Vérifie en base
        war_db = await db.clan_wars.find_one({"id": war_id}) if war_id else None
        if war_db:
            clean_doc(war_db)
            return {"status": "finished", "war": war_db}
        return {"status": "no_war"}

    scores = get_war_scores(war_id)
    return {"status": "active", "war_id": war_id, "scores": scores}

@api_router.get("/wars/{war_id}/scores")
async def get_war_scores_route(
    war_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère les scores en temps réel d'une guerre"""
    scores = get_war_scores(war_id)
    if not scores:
        raise HTTPException(status_code=404, detail="Guerre non trouvée")
    return scores

# ==================== CLAN ROUTES ====================

@api_router.post("/clans")
async def create_clan(
    clan_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Créer un nouveau clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas créer de clan")

    # Vérifie que l'utilisateur n'est pas déjà dans un clan
    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    name = clan_data.get("name", "").strip()
    if not name or len(name) < 3 or len(name) > 20:
        raise HTTPException(status_code=400, detail="Le nom doit faire entre 3 et 20 caractères")

    # Vérifie que le nom n'existe pas déjà
    if await db.clans.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Ce nom de clan est déjà pris")

    clan_id = str(uuid.uuid4())
    tag = generate_clan_tag()
    genius_index = 0
    league = get_league(genius_index)

    clan = {
        "id": clan_id,
        "name": name,
        "tag": tag,
        "description": clan_data.get("description", ""),
        "genius_index": genius_index,
        "league": league["name"],
        "members": [{
            "id": current_user["id"],
            "username": current_user["username"],
            "elo_online": current_user.get("elo_online", 1000),
            "rank": "chef",
        }],
        "current_war_id": None,
        "war_history": [],
        "created_at": datetime.utcnow(),
    }

    await db.clans.insert_one(clan)
    clean_doc(clan)

    # Met à jour l'utilisateur
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "chef"}}
    )

    return {"clan": clan}

@api_router.get("/clans/my")
async def get_my_clan(current_user: dict = Depends(get_current_user)):
    """Récupère le clan de l'utilisateur"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        return {"clan": None}
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        return {"clan": None}
    clean_doc(clan)

    # Calcule l'Elo total du clan
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))

    return {"clan": clan}

@api_router.get("/clans/search")
async def search_clans(q: str = "", limit: int = 20):
    """Recherche des clans par nom"""
    query = {}
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    clans = await db.clans.find(query).limit(limit).to_list(limit)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "description": clan.get("description", ""),
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"clans": result}

@api_router.get("/clans/{clan_id}")
async def get_clan(clan_id: str):
    """Récupère le détail d'un clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")
    clean_doc(clan)
    total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
    clan["total_elo"] = total_elo
    clan["league"] = get_league(clan.get("genius_index", 0))
    return {"clan": clan}

@api_router.post("/clans/{clan_id}/join")
async def join_clan(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Rejoindre un clan"""
    if current_user.get("role") == "teacher":
        raise HTTPException(status_code=403, detail="Les professeurs ne peuvent pas rejoindre un clan")

    existing = await db.clans.find_one({"members.id": current_user["id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Tu es déjà dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if len(clan.get("members", [])) >= 40:
        raise HTTPException(status_code=400, detail="Le clan est complet (40/40)")

    new_member = {
        "id": current_user["id"],
        "username": current_user["username"],
        "elo_online": current_user.get("elo_online", 1000),
        "rank": "recrue",
    }

    await db.clans.update_one(
        {"id": clan_id},
        {"$push": {"members": new_member}}
    )
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"clan_id": clan_id, "clan_rank": "recrue"}}
    )

    return {"message": f"Tu as rejoint le clan {clan['name']} !"}

@api_router.post("/clans/leave")
async def leave_clan(current_user: dict = Depends(get_current_user)):
    """Quitter son clan"""
    clan_id = current_user.get("clan_id")
    if not clan_id:
        raise HTTPException(status_code=400, detail="Tu n'es pas dans un clan")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    clan_rank = current_user.get("clan_rank", "recrue")

    # Si chef et seul membre → supprime le clan
    if clan_rank == "chef" and len(clan.get("members", [])) == 1:
        await db.clans.delete_one({"id": clan_id})
    elif clan_rank == "chef":
        # Passe le grade de chef au prochain membre le plus gradé
        members = clan.get("members", [])
        members = [m for m in members if m["id"] != current_user["id"]]
        rank_order = ["expert", "analyste", "recrue"]
        new_chef = None
        for rank in rank_order:
            for m in members:
                if m.get("rank") == rank:
                    new_chef = m
                    break
            if new_chef:
                break
        if not new_chef and members:
            new_chef = members[0]
        if new_chef:
            await db.clans.update_one(
                {"id": clan_id, "members.id": new_chef["id"]},
                {"$set": {"members.$.rank": "chef"}}
            )
            await db.users.update_one(
                {"id": new_chef["id"]},
                {"$set": {"clan_rank": "chef"}}
            )
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )
    else:
        await db.clans.update_one(
            {"id": clan_id},
            {"$pull": {"members": {"id": current_user["id"]}}}
        )

    await db.users.update_one(
        {"id": current_user["id"]},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Tu as quitté le clan"}

@api_router.post("/clans/{clan_id}/promote")
async def promote_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Promouvoir un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank != "chef":
        raise HTTPException(status_code=403, detail="Seul le chef peut promouvoir")

    member_id = member_data.get("member_id")
    new_rank = member_data.get("rank")

    if new_rank not in CLAN_RANKS:
        raise HTTPException(status_code=400, detail="Rang invalide")
    if new_rank == "chef":
        raise HTTPException(status_code=400, detail="Utilise /transfer-leadership pour transférer le commandement")

    await db.clans.update_one(
        {"id": clan_id, "members.id": member_id},
        {"$set": {"members.$.rank": new_rank}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$set": {"clan_rank": new_rank}}
    )

    return {"message": "Membre promu"}

@api_router.post("/clans/{clan_id}/kick")
async def kick_member(
    clan_id: str,
    member_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expulser un membre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    member_id = member_data.get("member_id")
    if member_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'expulser toi-même")

    await db.clans.update_one(
        {"id": clan_id},
        {"$pull": {"members": {"id": member_id}}}
    )
    await db.users.update_one(
        {"id": member_id},
        {"$unset": {"clan_id": "", "clan_rank": ""}}
    )

    return {"message": "Membre expulsé"}

# ==================== CLAN WAR ROUTES ====================

@api_router.post("/clans/{clan_id}/war/start")
async def start_war(
    clan_id: str,
    war_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Lance la recherche d'une guerre de clan"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Seul le chef ou un expert peut lancer une guerre")

    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    if clan.get("current_war_id"):
        raise HTTPException(status_code=400, detail="Ton clan est déjà en guerre")

    if clan_id in WAR_QUEUE:
        raise HTTPException(status_code=400, detail="Ton clan est déjà en file d'attente")

    war_format = war_data.get("format")
    if war_format not in WAR_FORMATS:
        raise HTTPException(status_code=400, detail="Format invalide (10, 15 ou 20)")

    selected_member_ids = war_data.get("member_ids", [])
    if len(selected_member_ids) != war_format:
        raise HTTPException(
            status_code=400,
            detail=f"Tu dois sélectionner exactement {war_format} membres"
        )

    # Récupère les infos des membres sélectionnés
    all_members = clan.get("members", [])
    selected_members = [m for m in all_members if m["id"] in selected_member_ids]

    if len(selected_members) != war_format:
        raise HTTPException(status_code=400, detail="Certains membres sont invalides")

    genius_index = clan.get("genius_index", 0)
    league = get_league(genius_index)

    # Ajoute à la file d'attente
    WAR_QUEUE[clan_id] = {
        "clan_name": clan["name"],
        "format": war_format,
        "league": league["name"],
        "genius_index": genius_index,
        "members": selected_members,
        "queued_at": datetime.utcnow().isoformat(),
    }

    # Essaie de trouver un adversaire immédiatement
    war_id = await try_matchmaking(clan_id, db)

    if war_id:
        return {
            "status": "war_started",
            "war_id": war_id,
            "message": "Adversaire trouvé ! La guerre commence !",
        }
    else:
        return {
            "status": "searching",
            "message": f"Recherche d'un adversaire en ligue {league['name']}...",
        }

@api_router.delete("/clans/{clan_id}/war/cancel")
async def cancel_war_search(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Annule la recherche de guerre"""
    clan_rank = current_user.get("clan_rank", "recrue")
    if clan_rank not in ["chef", "expert"]:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    if clan_id in WAR_QUEUE:
        WAR_QUEUE.pop(clan_id)
        return {"message": "Recherche annulée"}
    raise HTTPException(status_code=400, detail="Ton clan n'est pas en file d'attente")

@api_router.get("/clans/{clan_id}/war/current")
async def get_current_war(
    clan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère la guerre en cours du clan"""
    clan = await db.clans.find_one({"id": clan_id})
    if not clan:
        raise HTTPException(status_code=404, detail="Clan non trouvé")

    war_id = clan.get("current_war_id")

    # Vérifie si en file d'attente
    if clan_id in WAR_QUEUE:
        return {
            "status": "searching",
            "queue_data": {
                "format": WAR_QUEUE[clan_id]["format"],
                "league": WAR_QUEUE[clan_id]["league"],
                "queued_at": WAR_QUEUE[clan_id]["queued_at"],
            }
        }

    if not war_id or war_id not in active_wars:
        # Vérifie en base
        war_db = await db.clan_wars.find_one({"id": war_id}) if war_id else None
        if war_db:
            clean_doc(war_db)
            return {"status": "finished", "war": war_db}
        return {"status": "no_war"}

    scores = get_war_scores(war_id)
    return {"status": "active", "war_id": war_id, "scores": scores}

@api_router.get("/wars/{war_id}/scores")
async def get_war_scores_route(
    war_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Récupère les scores en temps réel d'une guerre"""
    scores = get_war_scores(war_id)
    if not scores:
        raise HTTPException(status_code=404, detail="Guerre non trouvée")
    return scores

# ==================== CLASSEMENTS CLANS ====================

@api_router.get("/rankings/clans/genius")
async def ranking_clans_genius(limit: int = 50):
    """Classement des clans par indice de génie"""
    clans = await db.clans.find().sort("genius_index", -1).limit(limit).to_list(limit)
    result = []
    for rank, clan in enumerate(clans, 1):
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", []))
        result.append({
            "rank": rank,
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    return {"rankings": result}

@api_router.get("/rankings/clans/elo")
async def ranking_clans_elo(limit: int = 50):
    """Classement des clans par Elo total"""
    clans = await db.clans.find().to_list(500)
    result = []
    for clan in clans:
        clean_doc(clan)
        total_elo = sum(m.get("elo_online", 1000) for m in clan.get("members", [])) 
        result.append({
            "id": clan["id"],
            "name": clan["name"],
            "tag": clan["tag"],
            "genius_index": clan.get("genius_index", 0),
            "league": get_league(clan.get("genius_index", 0)),
            "members_count": len(clan.get("members", [])),
            "total_elo": total_elo,
        })
    result.sort(key=lambda x: x["total_elo"], reverse=True)
    for rank, item in enumerate(result[:limit], 1):
        item["rank"] = rank
    return {"rankings": result[:limit]}

# ==================== WEBSOCKET DUEL ====================

@app.websocket("/ws/duel/{user_id}")
async def duel_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connections[user_id] = websocket
    import json
    try:
        data = await websocket.receive_text()
        player_data = json.loads(data)
        username = player_data.get("username")
        elo_online = player_data.get("elo_online", 1000)
        asyncio.create_task(
            find_match(user_id, username, elo_online, websocket, db)
        )
        while True:
            message = await websocket.receive_text()
            msg_data = json.loads(message)
            if msg_data.get("type") == "answer":
                match_id = msg_data.get("match_id")
                answer = float(msg_data.get("answer", 0))
                if match_id in active_matches:
                    match = active_matches[match_id]
                    if match.get("status") == "finished":
                        elo_change_key = f"elo_change_{user_id}"
                        if elo_change_key in match:
                            elo_change = match[elo_change_key]
                            user = await db.users.find_one({"id": user_id})
                            if user:
                                new_elo_online = max(100, user.get("elo_online", 1000) + elo_change)
                                await db.users.update_one(
                                    {"id": user_id},
                                    {"$set": {"elo_online": new_elo_online}}
                                )
                    else:
                        await process_answer(match_id, user_id, answer)
            elif msg_data.get("type") == "cancel_search":
                if user_id in waiting_queue:
                    waiting_queue.pop(user_id)
                    await websocket.send_text(json.dumps({"type": "search_cancelled"}))
    except WebSocketDisconnect:
        if user_id in connections:
            connections.pop(user_id)
        if user_id in waiting_queue:
            waiting_queue.pop(user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user_id in connections:
            connections.pop(user_id)

app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/war/{user_id}")
async def war_websocket(websocket: WebSocket, user_id: str):
    """WebSocket pour la guerre de clan en temps réel"""
    await websocket.accept()
    war_connections[user_id] = websocket
    import json
    try:
        while True:
            message = await websocket.receive_text()
            msg_data = json.loads(message)

            if msg_data.get("type") == "start_battle":
                war_id = msg_data.get("war_id")
                result = await start_player_battle(war_id, user_id)
                if result:
                    await websocket.send_text(json.dumps({
                        "type": "battle_ready",
                        **result
                    }))

            elif msg_data.get("type") == "submit_answer":
                war_id = msg_data.get("war_id")
                problem_id = msg_data.get("problem_id")
                answer = float(msg_data.get("answer", 0))
                result = await submit_war_answer(war_id, user_id, problem_id, answer)
                if result:
                    await websocket.send_text(json.dumps({
                        "type": "answer_result",
                        **result
                    }))

            elif msg_data.get("type") == "get_scores":
                war_id = msg_data.get("war_id")
                scores = get_war_scores(war_id)
                await websocket.send_text(json.dumps({
                    "type": "scores_update",
                    "scores": scores,
                }))

    except WebSocketDisconnect:
        if user_id in war_connections:
            war_connections.pop(user_id)
    except Exception as e:
        logger.error(f"War WebSocket error: {e}")
        if user_id in war_connections:
            war_connections.pop(user_id)

@app.on_event("shutdown")
async def shutdown():
    client.close()