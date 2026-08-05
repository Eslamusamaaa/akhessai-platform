import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, UUID
from sqlalchemy.orm import relationship
from database import Base
from security import encrypt_phi, decrypt_phi

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # parent | teacher | specialist | admin
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    observations = relationship("ClinicalObservation", back_populates="specialist")
    approved_reports = relationship("DraftReport", back_populates="approved_by_user")

class Child(Base):
    __tablename__ = "children"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Encrypted PHI database columns
    _name = Column("name", String, nullable=False)
    _dob = Column("dob", String, nullable=False)  # ISO Date String YYYY-MM-DD
    _nationality = Column("nationality", String, nullable=True)
    _school = Column("school", String, nullable=True)
    _grade = Column("grade", String, nullable=True)
    _parent_contact = Column("parent_contact", String, nullable=True)
    
    gender = Column(String, nullable=False)  # male | female
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    sessions = relationship("AssessmentSession", back_populates="child", cascade="all, delete-orphan")

    @property
    def name(self) -> str:
        return decrypt_phi(self._name)

    @name.setter
    def name(self, value: str):
        self._name = encrypt_phi(value)

    @property
    def dob(self) -> str:
        return decrypt_phi(self._dob)

    @dob.setter
    def dob(self, value: str):
        self._dob = encrypt_phi(value)

    @property
    def nationality(self) -> str:
        return decrypt_phi(self._nationality)

    @nationality.setter
    def nationality(self, value: str):
        self._nationality = encrypt_phi(value)

    @property
    def school(self) -> str:
        return decrypt_phi(self._school)

    @school.setter
    def school(self, value: str):
        self._school = encrypt_phi(value)

    @property
    def grade(self) -> str:
        return decrypt_phi(self._grade)

    @grade.setter
    def grade(self, value: str):
        self._grade = encrypt_phi(value)

    @property
    def parent_contact(self) -> str:
        return decrypt_phi(self._parent_contact)

    @parent_contact.setter
    def parent_contact(self, value: str):
        self._parent_contact = encrypt_phi(value)

class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="onboarding")  # onboarding | core_screener | specialized_screening | clinical_observation | drafting | completed
    current_informant = Column(String, default="parent")  # parent | teacher | specialist
    age_band = Column(String, nullable=False)  # 0-6 | 6-18
    child_age_months = Column(Integer, nullable=True)  # Precise age at session creation for age-gated triggers
    onboarding_specialties = Column(JSON, default=list)  # List of selected specialties in onboarding
    active_specialties = Column(JSON, default=list)  # Specialties triggered + onboarding
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    child = relationship("Child", back_populates="sessions")
    responses = relationship("Response", back_populates="session", cascade="all, delete-orphan")
    clinical_observations = relationship("ClinicalObservation", back_populates="session", cascade="all, delete-orphan")
    draft_reports = relationship("DraftReport", back_populates="session", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = "responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String, nullable=False)
    informant = Column(String, nullable=False)  # parent | teacher | specialist
    selected_options = Column(JSON, nullable=False)  # Selected answer value(s)
    points = Column(Float, default=0.0)  # Normalized concern points
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AssessmentSession", back_populates="responses")

class ClinicalObservation(Base):
    __tablename__ = "clinical_observations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False)
    specialist_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Core observation dimensions (1 = Very Poor, 5 = Excellent)
    eye_contact = Column(Integer, nullable=False)
    response_to_name = Column(Integer, nullable=False)
    joint_attention = Column(Integer, nullable=False)
    social_reciprocity = Column(Integer, nullable=False)
    expressive_language = Column(Integer, nullable=False)
    receptive_language = Column(Integer, nullable=False)
    attention = Column(Integer, nullable=False)
    hyperactivity = Column(Integer, nullable=False)
    sensory_reactivity = Column(Integer, nullable=False)
    emotional_regulation = Column(Integer, nullable=False)
    
    _notes = Column("notes", Text, nullable=True)  # Encrypted qualitative clinical notes
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AssessmentSession", back_populates="clinical_observations")
    specialist = relationship("User", back_populates="observations")

    @property
    def notes(self) -> str:
        return decrypt_phi(self._notes)

    @notes.setter
    def notes(self, value: str):
        self._notes = encrypt_phi(value)

class DraftReport(Base):
    __tablename__ = "draft_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False)
    
    executive_summary = Column(Text, nullable=True)  # LLM-synthesized narrative
    domain_scores = Column(JSON, default=dict)  # Calculated scores, severity, and triggers
    suggested_goals = Column(JSON, default=list)  # Grounded goals from RAG
    suggested_referrals = Column(JSON, default=list)  # Recommended clinical referrals
    priority_tier = Column(String, nullable=False)  # Priority 1 | Priority 2 | Priority 3
    priority_rationale = Column(Text, nullable=False)

    # Extended LLM output fields (10-field schema from client.py)
    differential_considerations = Column(JSON, default=list)
    intervention_plan = Column(JSON, default=dict)  # {specialty: [steps]}
    school_accommodations = Column(JSON, default=list)
    home_program = Column(JSON, default=list)
    strengths_summary = Column(Text, nullable=True)
    followup_goals = Column(JSON, default=list)
    caveats = Column(JSON, default=list)

    # Rule-engine computed fields stored alongside report
    discrepancies = Column(JSON, default=list)
    strengths = Column(JSON, default=list)  # Domain names with low concern scores
    
    status = Column(String, default="draft")  # draft | reviewed | approved
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("AssessmentSession", back_populates="draft_reports")
    approved_by_user = relationship("User", back_populates="approved_reports")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # Actions might be system or unauthenticated
    action = Column(String, nullable=False)
    child_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSON, default=dict)  # Sanitized audit parameters (no PHI)
