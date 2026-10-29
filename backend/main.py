import uuid
import time
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

# Local imports
from sqlalchemy import text
from database import engine, Base, get_db, SessionLocal
import models
import security
from config import settings, IS_DEV
from questions.resolver import QUESTION_BANK, get_next_question
from rules.evaluator import evaluate_rules
from rag.pipeline import rag_client
from llm.client import generate_report_draft

# Create DB tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI-Assisted Special Education Assessment Platform (POC)",
    description="Arabic/RTL Healthcare decision support system.",
    version="1.0.0",
    docs_url="/docs" if IS_DEV else None,
    redoc_url=None,
    openapi_url="/openapi.json" if IS_DEV else None,
)

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response

# CORS: only explicitly allowed origins (configured via ALLOWED_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

security_bearer = HTTPBearer()

# --- Pydantic Schemas ---

class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=10, max_length=128)
    role: str = "parent"  # self-registration allows parent | teacher only

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    username: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class ChildCreate(BaseModel):
    name: str
    dob: str  # YYYY-MM-DD
    gender: str  # male | female
    nationality: Optional[str] = None
    school: Optional[str] = None
    grade: Optional[str] = None
    parent_contact: Optional[str] = None

class SessionCreate(BaseModel):
    child_id: uuid.UUID
    onboarding_specialties: List[str]

class QuestionResponse(BaseModel):
    question_id: str
    selected_options: List[str]

class ClinicalObservationCreate(BaseModel):
    eye_contact: int = Field(..., ge=1, le=5)
    response_to_name: int = Field(..., ge=1, le=5)
    joint_attention: int = Field(..., ge=1, le=5)
    social_reciprocity: int = Field(..., ge=1, le=5)
    expressive_language: int = Field(..., ge=1, le=5)
    receptive_language: int = Field(..., ge=1, le=5)
    attention: int = Field(..., ge=1, le=5)
    hyperactivity: int = Field(..., ge=1, le=5)
    sensory_reactivity: int = Field(..., ge=1, le=5)
    emotional_regulation: int = Field(..., ge=1, le=5)
    notes: Optional[str] = ""

class ReportApproval(BaseModel):
    executive_summary: str
    suggested_goals: List[str]
    suggested_referrals: List[str]
    school_accommodations: Optional[List[str]] = []
    home_program: Optional[List[str]] = []
    followup_goals: Optional[List[str]] = []
    caveats: Optional[List[str]] = []

# --- Auth Dependencies ---

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="غير مصرح",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials or not credentials.credentials:
        raise unauthorized
    payload = security.decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise unauthorized
    try:
        user_uuid = uuid.UUID(str(payload.get("sub")))
    except ValueError:
        raise unauthorized
    user = db.query(models.User).filter(models.User.id == user_uuid).first()
    if not user:
        raise unauthorized
    return user  # role always comes from the database, never from the token

def verify_roles(allowed_roles: List[str]):
    def dependency(user: models.User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ليس لديك صلاحية لهذا الإجراء")
        return user
    return dependency

STAFF_ROLES = {"specialist", "admin", "teacher"}

def assert_child_access(user: models.User, child) -> None:
    """Staff may access every child; parents only the children they registered (404 hides existence)."""
    if user.role in STAFF_ROLES:
        return
    if child is None or child.created_by != user.id:
        raise HTTPException(status_code=404, detail="غير موجود")

# Helper to log audit events
def log_audit(
    db: Session,
    action: str,
    user_id: Optional[uuid.UUID],
    child_id: Optional[uuid.UUID],
    details: Dict[str, Any]
):
    audit_entry = models.AuditLog(
        user_id=user_id,
        action=action,
        child_id=child_id,
        details=details
    )
    db.add(audit_entry)
    db.commit()

# --- Startup Seed Event ---
@app.on_event("startup")
def startup_event():
    # Run lightweight schema migration for new columns (SQLite-safe ADD COLUMN)
    _migrations = {
        "users": [
            ("email", "TEXT"),
        ],
        "assessment_sessions": [
            ("child_age_months", "INTEGER"),
        ],
        "children": [
            ("created_by", "UUID"),
        ],
        "draft_reports": [
            ("differential_considerations", "JSON"),
            ("intervention_plan", "JSON"),
            ("school_accommodations", "JSON"),
            ("home_program", "JSON"),
            ("strengths_summary", "TEXT"),
            ("followup_goals", "JSON"),
            ("caveats", "JSON"),
            ("discrepancies", "JSON"),
            ("strengths", "JSON"),
        ],
    }
    with engine.connect() as conn:
        for table, cols in _migrations.items():
            for col_name, col_type in cols:
                try:
                    sql_type = "CHAR(32)" if col_type == "UUID" and engine.dialect.name == "sqlite" else col_type
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {sql_type}"))
                    conn.commit()
                except Exception:
                    pass  # Column already exists

    # Demo users are created only when explicitly enabled, with a password from the environment.
    if settings.SEED_DEMO_USERS:
        if len(settings.DEMO_PASSWORD) < 12:
            print("[Startup] SEED_DEMO_USERS is on but DEMO_PASSWORD is missing or shorter than 12 chars; skipping.")
            return
        db = SessionLocal()
        try:
            if db.query(models.User).count() == 0:
                pw_hash = security.hash_password(settings.DEMO_PASSWORD)
                db.add_all([
                    models.User(username=u, email=f"{u}@example.com", password_hash=pw_hash, role=u)
                    for u in ("admin", "specialist", "parent", "teacher")
                ])
                db.commit()
                print("[Startup] Seeded demo users: admin, specialist, parent, teacher")
        except Exception as e:
            print(f"[Startup] Error seeding: {e}")
        finally:
            db.close()

# --- Auth Endpoints ---

SELF_REGISTER_ROLES = {"parent", "teacher"}
_DUMMY_HASH = security.hash_password(secrets.token_urlsafe(16))  # equalises timing for unknown users

# Simple in-memory brute-force limiter (per instance): 5 failures / 15 minutes per username
_FAILED_LOGINS: Dict[str, List[float]] = defaultdict(list)
_MAX_FAILS, _WINDOW = 5, 15 * 60

def _is_locked(key: str) -> bool:
    now = time.time()
    _FAILED_LOGINS[key] = [ts for ts in _FAILED_LOGINS[key] if now - ts < _WINDOW]
    return len(_FAILED_LOGINS[key]) >= _MAX_FAILS

@app.post("/auth/register", response_model=Dict[str, Any])
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    if user_data.role not in SELF_REGISTER_ROLES:
        raise HTTPException(status_code=403, detail="لا يمكن التسجيل بهذا الدور")
    existing = db.query(models.User).filter(models.User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="اسم المستخدم مسجل مسبقًا")

    new_user = models.User(
        username=user_data.username,
        password_hash=security.hash_password(user_data.password),
        role=user_data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit(db, "USER_REGISTER", new_user.id, None, {"role": new_user.role})

    return {"status": "success", "message": "تم التسجيل بنجاح"}

class JSONLogin(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=128)

@app.post("/auth/login", response_model=TokenResponse)
def login_json(credentials: JSONLogin, db: Session = Depends(get_db)):
    key = credentials.username.lower()
    if _is_locked(key):
        raise HTTPException(status_code=429, detail="محاولات كثيرة، حاول لاحقًا")
    user = db.query(models.User).filter(models.User.username == credentials.username).first()
    ok = security.verify_password(credentials.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        _FAILED_LOGINS[key].append(time.time())
        raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
    _FAILED_LOGINS.pop(key, None)
    log_audit(db, "USER_LOGIN", user.id, None, {})
    return {
        "access_token": security.create_access_token(user.id, user.role),
        "refresh_token": security.create_refresh_token(user.id),
        "role": user.role,
        "username": user.username,
    }

@app.post("/auth/refresh", response_model=Dict[str, str])
def refresh_token(req: TokenRefreshRequest, db: Session = Depends(get_db)):
    payload = security.decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="توكن تحديث غير صالح")
        
    user_id = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id)
    except Exception:
        raise HTTPException(status_code=401, detail="معرف مستخدم غير صالح")
    user = db.query(models.User).filter(models.User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=401, detail="المستخدم غير موجود")
        
    new_access = security.create_access_token(user.id, user.role)
    return {"access_token": new_access}

# --- Children Endpoints ---

@app.post("/children", response_model=Dict[str, Any])
def create_child(
    child: ChildCreate, 
    db: Session = Depends(get_db), 
    user: models.User = Depends(get_current_user)
):
    new_child = models.Child(gender=child.gender)
    new_child.created_by = user.id
    new_child.name = child.name
    new_child.dob = child.dob
    new_child.nationality = child.nationality
    new_child.school = child.school
    new_child.grade = child.grade
    new_child.parent_contact = child.parent_contact
    
    db.add(new_child)
    db.commit()
    db.refresh(new_child)
    
    log_audit(db, "CHILD_CREATE", user.id, new_child.id, {})
    
    return {"id": new_child.id, "status": "success"}

@app.get("/children", response_model=List[Dict[str, Any]])
def list_children(
    db: Session = Depends(get_db), 
    user: models.User = Depends(get_current_user)
):
    # Staff (specialist/admin/teacher) see all children; parents only the ones they registered.
    query = db.query(models.Child)
    if user.role not in STAFF_ROLES:
        query = query.filter(models.Child.created_by == user.id)
    children_list = query.all()

    result = []
    for c in children_list:
        # Decrypt fields dynamically via properties
        result.append({
            "id": c.id,
            "name": c.name,
            "dob": c.dob,
            "gender": c.gender,
            "nationality": c.nationality,
            "school": c.school,
            "grade": c.grade,
            "parent_contact": c.parent_contact,
            "created_at": c.created_at
        })
    return result

@app.get("/sessions", response_model=List[Dict[str, Any]])
def list_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    """Return all assessment sessions with child info and response count."""
    sessions_query = db.query(models.AssessmentSession)
    if user.role not in STAFF_ROLES:
        own_child_ids = [c.id for c in db.query(models.Child).filter(models.Child.created_by == user.id).all()]
        sessions_query = sessions_query.filter(models.AssessmentSession.child_id.in_(own_child_ids))
    sessions = sessions_query.all()
    result = []
    for s in sessions:
        child = db.query(models.Child).filter(models.Child.id == s.child_id).first()
        resp_count = db.query(models.Response).filter(models.Response.session_id == s.id).count()
        try:
            child_name = child.name if child else "—"
        except Exception:
            child_name = "—"
        result.append({
            "id": str(s.id),
            "child_id": str(s.child_id),
            "child_name": child_name,
            "age_band": s.age_band,
            "status": s.status,
            "current_informant": s.current_informant,
            "onboarding_specialties": s.onboarding_specialties,
            "active_specialties": s.active_specialties,
            "responses_count": resp_count,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return result

# --- Assessment Sessions ---

@app.post("/sessions", response_model=Dict[str, Any])
def create_session(
    payload: SessionCreate, 
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    child = db.query(models.Child).filter(models.Child.id == payload.child_id).first()
    if not child:
        raise HTTPException(status_code=404, detail="الطفل غير موجود")
    assert_child_access(user, child)

    # Calculate age band based on DOB (0-6 or 6-18)
    try:
        birth_date = datetime.strptime(child.dob, "%Y-%m-%d")
        age_days = (datetime.now() - birth_date).days
        age_years = age_days / 365.25
        child_age_months = int(age_days / 30.4375)
    except Exception:
        age_years = 4.0
        child_age_months = 48  # conservative fallback

    age_band = "0-6" if age_years < 6.0 else "6-18"

    new_session = models.AssessmentSession(
        child_id=child.id,
        status="core_screener",  # specialties selected at registration → skip onboarding step
        current_informant="parent",
        age_band=age_band,
        child_age_months=child_age_months,
        onboarding_specialties=payload.onboarding_specialties,
        active_specialties=payload.onboarding_specialties
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    
    log_audit(db, "SESSION_START", user.id, child.id, {"session_id": str(new_session.id), "age_band": age_band})
    
    return {"session_id": str(new_session.id), "status": "success"}

@app.get("/sessions/{session_id}", response_model=Dict[str, Any])
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.AssessmentSession).filter(models.AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
    assert_child_access(user, session.child)
        
    child = session.child
    
    # Calculate current rule results
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).all()
    evaluation = evaluate_rules(session, responses)
    
    return {
        "id": session.id,
        "child_id": session.child_id,
        "child_name": child.name,
        "age_band": session.age_band,
        "status": session.status,
        "current_informant": session.current_informant,
        "onboarding_specialties": session.onboarding_specialties,
        "active_specialties": session.active_specialties,
        "evaluation": evaluation,
        "responses_count": len(responses),
        "informant_responses_count": {
            "parent": sum(1 for r in responses if r.informant == "parent"),
            "teacher": sum(1 for r in responses if r.informant == "teacher"),
            "specialist": sum(1 for r in responses if r.informant == "specialist"),
        }
    }

@app.get("/sessions/{session_id}/next-question", response_model=Dict[str, Any])
def get_session_next_question(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.AssessmentSession).filter(models.AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
    assert_child_access(user, session.child)
        
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).all()
    
    # Re-run rule engine to ensure active_specialties is dynamically updated before resolving next question
    evaluation = evaluate_rules(session, responses)
    if set(session.active_specialties) != set(evaluation["active_specialties"]):
        session.active_specialties = evaluation["active_specialties"]
        db.commit()
        
    next_q = get_next_question(session, responses)
    if not next_q:
        return {"finished": True}
        
    return {"finished": False, "question": next_q}

@app.post("/sessions/{session_id}/respond", response_model=Dict[str, Any])
def submit_response(
    session_id: uuid.UUID,
    resp_data: QuestionResponse,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    session = db.query(models.AssessmentSession).filter(models.AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
    assert_child_access(user, session.child)

    # Role-to-informant gate: only the matching role may submit answers
    ROLE_INFORMANT_MAP = {"parent": "parent", "teacher": "teacher", "specialist": "specialist"}
    expected_informant = ROLE_INFORMANT_MAP.get(user.role)
    if expected_informant and session.current_informant != expected_informant:
        raise HTTPException(
            status_code=403,
            detail=f"دورك في التقييم لا يتطابق مع المرحلة الحالية. المجيب المطلوب: {session.current_informant}"
        )
        
    # Find question points from bank
    question = next((q for q in QUESTION_BANK if q["id"] == resp_data.question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="السؤال غير موجود")
        
    # Calculate points based on selected option(s)
    points = 0.0
    if question["type"] == "multi_select":
        # Sum option points
        for opt_val in resp_data.selected_options:
            match_opt = next((o for o in question["options"] if o["label_ar"] == opt_val), None)
            if match_opt:
                points += match_opt["points"]
        # Cap at 100
        points = min(points, 100.0)
    else:
        # Single select or likert
        selected_val = resp_data.selected_options[0] if resp_data.selected_options else ""
        match_opt = next((o for o in question["options"] if o["label_ar"] == selected_val), None)
        if match_opt:
            points = match_opt["points"]
            
    # Check if response already exists, if so overwrite
    existing_resp = db.query(models.Response).filter(
        models.Response.session_id == session_id,
        models.Response.question_id == resp_data.question_id,
        models.Response.informant == session.current_informant
    ).first()
    
    if existing_resp:
        existing_resp.selected_options = resp_data.selected_options
        existing_resp.points = points
    else:
        new_resp = models.Response(
            session_id=session_id,
            question_id=resp_data.question_id,
            informant=session.current_informant,
            selected_options=resp_data.selected_options,
            points=points
        )
        db.add(new_resp)
        
    db.commit()
    
    # Check if we should advance informant status
    # If no more questions for current informant, trigger next state
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).all()
    # Evaluate rules to update specialties
    evaluation = evaluate_rules(session, responses)
    session.active_specialties = evaluation["active_specialties"]
    db.commit()
    
    next_q = get_next_question(session, responses)
    finished = False
    if not next_q:
        # Advance informant or assessment status
        if session.current_informant == "parent":
            session.current_informant = "teacher"
            session.status = "specialized_screening"
        elif session.current_informant == "teacher":
            session.current_informant = "specialist"
            session.status = "clinical_observation"
        else:
            finished = True
        db.commit()
        
    return {
        "status": "success",
        "current_informant": session.current_informant,
        "session_status": session.status,
        "finished": finished,
        "next_question": next_q,
        "responses_count": len(responses)
    }

# --- Clinical Observation ---

@app.post("/sessions/{session_id}/observation", response_model=Dict[str, Any])
def submit_observation(
    session_id: uuid.UUID,
    obs_data: ClinicalObservationCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["specialist", "admin"]))
):
    session = db.query(models.AssessmentSession).filter(models.AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
        
    # Check if observation exists
    obs = db.query(models.ClinicalObservation).filter(models.ClinicalObservation.session_id == session_id).first()
    if obs:
        obs.eye_contact = obs_data.eye_contact
        obs.response_to_name = obs_data.response_to_name
        obs.joint_attention = obs_data.joint_attention
        obs.social_reciprocity = obs_data.social_reciprocity
        obs.expressive_language = obs_data.expressive_language
        obs.receptive_language = obs_data.receptive_language
        obs.attention = obs_data.attention
        obs.hyperactivity = obs_data.hyperactivity
        obs.sensory_reactivity = obs_data.sensory_reactivity
        obs.emotional_regulation = obs_data.emotional_regulation
        obs.notes = obs_data.notes
        obs.specialist_id = user.id
    else:
        obs = models.ClinicalObservation(
            session_id=session_id,
            specialist_id=user.id,
            eye_contact=obs_data.eye_contact,
            response_to_name=obs_data.response_to_name,
            joint_attention=obs_data.joint_attention,
            social_reciprocity=obs_data.social_reciprocity,
            expressive_language=obs_data.expressive_language,
            receptive_language=obs_data.receptive_language,
            attention=obs_data.attention,
            hyperactivity=obs_data.hyperactivity,
            sensory_reactivity=obs_data.sensory_reactivity,
            emotional_regulation=obs_data.emotional_regulation
        )
        obs.notes = obs_data.notes
        db.add(obs)
        
    # Advance session status to drafting
    session.status = "drafting"
    db.commit()
    
    log_audit(db, "SUBMIT_CLINICAL_OBSERVATION", user.id, session.child_id, {"session_id": str(session.id)})
    
    return {"status": "success"}

@app.get("/sessions/{session_id}/observation", response_model=Dict[str, Any])
def get_observation(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["specialist", "admin"]))
):
    obs = db.query(models.ClinicalObservation).filter(models.ClinicalObservation.session_id == session_id).first()
    if not obs:
        raise HTTPException(status_code=404, detail="لم يتم ملء نموذج الملاحظة السريرية بعد")
        
    return {
        "eye_contact": obs.eye_contact,
        "response_to_name": obs.response_to_name,
        "joint_attention": obs.joint_attention,
        "social_reciprocity": obs.social_reciprocity,
        "expressive_language": obs.expressive_language,
        "receptive_language": obs.receptive_language,
        "attention": obs.attention,
        "hyperactivity": obs.hyperactivity,
        "sensory_reactivity": obs.sensory_reactivity,
        "emotional_regulation": obs.emotional_regulation,
        "notes": obs.notes
    }

# --- LLM Report & RAG Endpoints ---

@app.post("/sessions/{session_id}/generate-report", response_model=Dict[str, Any])
def trigger_report_draft(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["specialist", "admin"]))
):
    session = db.query(models.AssessmentSession).filter(models.AssessmentSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
        
    responses = db.query(models.Response).filter(models.Response.session_id == session_id).all()
    obs = db.query(models.ClinicalObservation).filter(models.ClinicalObservation.session_id == session_id).first()
    
    # 1. Evaluate scores
    eval_results = evaluate_rules(session, responses)
    
    # Find elevated domains to filter RAG (e.g. concern >= 40.0)
    elevated_domains = [domain for domain, data in eval_results["severity_levels"].items() if data["level"] >= 3]
    
    # 2. Query Qdrant RAG system
    # Combine active specialties and query words
    rag_docs = rag_client.search_guidelines(
        specialties=eval_results["active_specialties"],
        domains=elevated_domains,
        age_band=session.age_band,
        query=f"أهداف وتوصيات وخطط علاجية لـ {', '.join(eval_results['active_specialties'])}",
        limit=6
    )
    
    # Log retrieved RAG document IDs for transparency
    retrieved_ids = [doc["id"] for doc in rag_docs]
    print(f"[RAG] Retrieved document IDs {retrieved_ids} for session {session.id}")
    
    # 3. Call OpenRouter
    child = session.child
    specialist_notes = obs.notes if obs else ""
    
    draft = generate_report_draft(
        child_id=str(child.id),
        age_band=session.age_band,
        gender=child.gender,
        domain_scores=eval_results["severity_levels"],
        priority_tier=eval_results["priority_tier"],
        priority_rationale=eval_results["priority_rationale_ar"],
        specialist_notes=specialist_notes,
        rag_context=rag_docs,
        strengths=eval_results.get("strengths", []),
        active_specialties=eval_results.get("active_specialties", []),
    )
    
    # 4. Check if DraftReport already exists
    report = db.query(models.DraftReport).filter(models.DraftReport.session_id == session_id).first()
    _report_fields = dict(
        executive_summary=draft.get("summary", ""),
        domain_scores=eval_results["severity_levels"],
        suggested_goals=draft.get("suggested_goals", []),
        suggested_referrals=draft.get("suggested_referrals", []),
        priority_tier=eval_results["priority_tier"],
        priority_rationale=eval_results["priority_rationale_ar"],
        differential_considerations=draft.get("differential_considerations", []),
        intervention_plan=draft.get("intervention_plan", {}),
        school_accommodations=draft.get("school_accommodations", []),
        home_program=draft.get("home_program", []),
        strengths_summary=draft.get("strengths_summary", ""),
        followup_goals=draft.get("followup_goals", []),
        caveats=draft.get("caveats", []),
        discrepancies=eval_results.get("discrepancies", []),
        strengths=eval_results.get("strengths", []),
        status="draft",
    )
    if report:
        for k, v in _report_fields.items():
            setattr(report, k, v)
    else:
        report = models.DraftReport(session_id=session_id, **_report_fields)
        db.add(report)
        
    db.commit()
    db.refresh(report)
    
    log_audit(
        db, 
        "GENERATE_LLM_DRAFT", 
        user.id, 
        session.child_id, 
        {"session_id": str(session.id), "retrieved_doc_ids": retrieved_ids}
    )
    
    return {"status": "success", "report_id": report.id}

@app.get("/sessions/{session_id}/report", response_model=Dict[str, Any])
def get_report(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user)
):
    report = db.query(models.DraftReport).filter(models.DraftReport.session_id == session_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="لم يتم إنشاء مسودة التقرير بعد")

    session = report.session
    child = session.child
    if user.role not in {"specialist", "admin"}:
        # Unapproved AI drafts are for clinicians only; approved reports only for the owning parent.
        if report.status != "approved":
            raise HTTPException(status_code=403, detail="ليس لديك صلاحية لهذا الإجراء")
        assert_child_access(user, child)
    
    return {
        "id": report.id,
        "session_id": report.session_id,
        "child_name": child.name,
        "gender": child.gender,
        "age_band": session.age_band,
        "executive_summary": report.executive_summary,
        "domain_scores": report.domain_scores,
        "suggested_goals": report.suggested_goals,
        "suggested_referrals": report.suggested_referrals,
        "priority_tier": report.priority_tier,
        "priority_rationale": report.priority_rationale,
        # Extended LLM fields
        "differential_considerations": report.differential_considerations or [],
        "intervention_plan": report.intervention_plan or {},
        "school_accommodations": report.school_accommodations or [],
        "home_program": report.home_program or [],
        "strengths_summary": report.strengths_summary or "",
        "followup_goals": report.followup_goals or [],
        "caveats": report.caveats or [],
        # Rule-engine fields
        "discrepancies": report.discrepancies or [],
        "strengths": report.strengths or [],
        "status": report.status,
        "approved_at": report.approved_at,
    }

@app.post("/sessions/{session_id}/report/approve", response_model=Dict[str, Any])
def approve_report(
    session_id: uuid.UUID,
    payload: ReportApproval,
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["specialist", "admin"]))
):
    report = db.query(models.DraftReport).filter(models.DraftReport.session_id == session_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="التقرير غير موجود")
        
    # Apply specialist edits and approve
    report.executive_summary = payload.executive_summary
    report.suggested_goals = payload.suggested_goals
    report.suggested_referrals = payload.suggested_referrals
    report.school_accommodations = payload.school_accommodations
    report.home_program = payload.home_program
    report.followup_goals = payload.followup_goals
    report.caveats = payload.caveats
    report.status = "approved"
    report.approved_by = user.id
    report.approved_at = datetime.utcnow()
    
    # Set session status as completed
    report.session.status = "completed"
    
    db.commit()
    
    log_audit(db, "APPROVE_REPORT", user.id, report.session.child_id, {"session_id": str(session_id)})
    
    return {"status": "success", "message": "تم اعتماد التقرير بنجاح من قبل الأخصائي"}

# --- Audit Logs ---

@app.delete("/admin/reset-all-data", response_model=Dict[str, Any])
def reset_all_data(
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["admin"]))
):
    """Delete all children, sessions, responses, observations, reports and audit logs. Admin only."""
    db.query(models.AuditLog).delete()
    db.query(models.DraftReport).delete()
    db.query(models.ClinicalObservation).delete()
    db.query(models.AssessmentResponse).delete()
    db.query(models.AssessmentSession).delete()
    db.query(models.Child).delete()
    db.commit()
    log_audit(db, "ADMIN_RESET_ALL", user.id, None, {"action": "all data wiped"})
    return {"status": "success", "message": "تم مسح جميع البيانات بنجاح"}

@app.get("/audit-logs", response_model=List[Dict[str, Any]])
def list_audit_logs(
    db: Session = Depends(get_db),
    user: models.User = Depends(verify_roles(["admin"]))
):
    logs = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).all()
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "timestamp": log.timestamp,
            "user_id": log.user_id,
            "action": log.action,
            "child_id": log.child_id,
            "details": log.details
        })
    return result
