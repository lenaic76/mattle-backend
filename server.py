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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'mattle_db')]

# Sécurité
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
            elo=1000, elo_online=1000, grade=user_data.grade, problems_solved=0,
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
            grade=user["grade"], problems_solved=user["problems_solved"],
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
        grade=current_user["grade"], problems_solved=current_user["problems_solved"],
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
    users = await db.users.find().sort("elo_online", -1).limit(limit).to_list(limit)
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
    higher_count = await db.users.count_documents({"elo_online": {"$gt": current_user.get("elo_online", 1000)}})
    total_users = await db.users.count_documents({})
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

@app.on_event("shutdown")
async def shutdown():
    client.close()