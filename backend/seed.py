import os
import sys
from datetime import datetime, timedelta
from database import Base, engine, SessionLocal
import models
from security import hash_password
from rag.pipeline import rag_client

def seed_db():
    demo_pw = os.getenv("DEMO_PASSWORD", "")
    if len(demo_pw) < 12:
        sys.exit("[Seed] Set DEMO_PASSWORD (12+ chars) in the environment first.")
    if not str(engine.url).startswith("sqlite") and os.getenv("CONFIRM_DROP") != "yes":
        sys.exit("[Seed] Refusing to DROP tables on a non-SQLite database. Set CONFIRM_DROP=yes to override.")
    print("[Seed] Dropping and recreating SQL tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        print("[Seed] Seeding users...")
        
        # Hash passwords
        admin_pw = specialist_pw = parent_pw = teacher_pw = hash_password(demo_pw)
        
        users = [
            models.User(username="admin", password_hash=admin_pw, role="admin"),
            models.User(username="specialist", password_hash=specialist_pw, role="specialist"),
            models.User(username="parent", password_hash=parent_pw, role="parent"),
            models.User(username="teacher", password_hash=teacher_pw, role="teacher"),
        ]
        db.add_all(users)
        db.commit()
        
        # Retrieve specialist user id
        specialist = db.query(models.User).filter_by(username="specialist").first()
        
        print("[Seed] Seeding synthetic child records...")
        
        # Child 1: Yasser (High concern in Autism & Speech, Age 4)
        child1 = models.Child(
            gender="male"
        )
        child1.name = "ياسر محمد"
        child1.dob = (datetime.now() - timedelta(days=4*365)).strftime("%Y-%m-%d")
        child1.nationality = "سعودي"
        child1.school = "روضة الأمل"
        child1.grade = "تمهيدي"
        child1.parent_contact = "+966500000001"
        db.add(child1)
        
        # Child 2: سارة (6-18 age band, ADHD concern, Discrepancy between parent and teacher)
        child2 = models.Child(
            gender="female"
        )
        child2.name = "سارة أحمد"
        child2.dob = (datetime.now() - timedelta(days=8*365)).strftime("%Y-%m-%d")
        child2.nationality = "مصرية"
        child2.school = "مدرسة النهضة الابتدائية"
        child2.grade = "الصف الثالث"
        child2.parent_contact = "+966500000002"
        db.add(child2)
        
        # Child 3: عمر (0-6 age band, Typical Development)
        child3 = models.Child(
            gender="male"
        )
        child3.name = "عمر خالد"
        child3.dob = (datetime.now() - timedelta(days=3*365)).strftime("%Y-%m-%d")
        child3.nationality = "أردني"
        child3.school = "حضانات براعم المستقبل"
        child3.grade = "حضانة"
        child3.parent_contact = "+966500000003"
        db.add(child3)
        
        db.commit()
        
        print("[Seed] Seeding assessment sessions...")
        
        # Session 1: Yasser's assessment
        session1 = models.AssessmentSession(
            child_id=child1.id,
            status="clinical_observation",
            current_informant="specialist",
            age_band="0-6",
            onboarding_specialties=["autism", "speech_language"],
            active_specialties=["autism", "speech_language"]
        )
        db.add(session1)
        
        # Session 2: Sarah's assessment
        session2 = models.AssessmentSession(
            child_id=child2.id,
            status="core_screener",
            current_informant="parent",
            age_band="6-18",
            onboarding_specialties=["adhd", "learning_disabilities"],
            active_specialties=["adhd", "learning_disabilities"]
        )
        db.add(session2)
        
        # Session 3: Omar's assessment
        session3 = models.AssessmentSession(
            child_id=child3.id,
            status="completed",
            current_informant="parent",
            age_band="0-6",
            onboarding_specialties=["speech_language"],
            active_specialties=["speech_language"]
        )
        db.add(session3)
        db.commit()
        
        print("[Seed] Seeding test responses for Yasser (High concern)...")
        # Yasser responses (severe autism + speech)
        resp1 = [
            # social_communication: parent: Rare (66.6), Autism trigger (60+)
            models.Response(session_id=session1.id, question_id="q_core_01", informant="parent", selected_options=["نادرًا"], points=66.6),
            # attention: parent: Neutral (50.0)
            models.Response(session_id=session1.id, question_id="q_core_02", informant="parent", selected_options=["محايد"], points=50.0),
            # expressive language: parent: No (100.0)
            models.Response(session_id=session1.id, question_id="q_core_03", informant="parent", selected_options=["لا، لا يستطيع إطلاقًا"], points=100.0),
            # receptive language: parent: Rare (100.0)
            models.Response(session_id=session1.id, question_id="q_core_04", informant="parent", selected_options=["نادرًا أو أبدًا"], points=100.0),
            # sensory: parent: multiple (66.6)
            models.Response(session_id=session1.id, question_id="q_core_05", informant="parent", selected_options=["انزعاج شديد من الأصوات المعتادة كالخلاط أو المكنسة", "رفض ارتداء ملابس معينة بسبب ملمسها أو التكت الخاص بها"], points=66.6),
            # emotional: parent: meltdown (100.0)
            models.Response(session_id=session1.id, question_id="q_core_06", informant="parent", selected_options=["يدخل في نوبة غضب شديدة تستمر طويلاً ويصعب تهدئته"], points=100.0),
            # verbal status: parent: No (100.0)
            models.Response(session_id=session1.id, question_id="q_verbal_status", informant="parent", selected_options=["لا، لا ينطق بأي كلمة على الإطلاق"], points=100.0),
            # preverbal communication: parent: crying (100.0)
            models.Response(session_id=session1.id, question_id="q_preverbal_comm", informant="parent", selected_options=["يبكي أو يصرخ دون محاولة توجيه الآخرين لما يريد"], points=100.0),
            # autism t重複 behavioral: parent: always (100.0)
            models.Response(session_id=session1.id, question_id="q_autism_01", informant="parent", selected_options=["دائمًا"], points=100.0),
            # autism social: parent: ignores (100.0)
            models.Response(session_id=session1.id, question_id="q_autism_02", informant="parent", selected_options=["يتجاهل تمامًا ولا ينظر للاتجاه الذي تشير إليه"], points=100.0),
        ]
        db.add_all(resp1)
        
        # Clinical observation for Yasser (Completed by specialist)
        obs1 = models.ClinicalObservation(
            session_id=session1.id,
            specialist_id=specialist.id,
            eye_contact=1,         # 1 = Very Poor
            response_to_name=1,
            joint_attention=1,
            social_reciprocity=2,  # 2 = Poor
            expressive_language=1,
            receptive_language=1,
            attention=3,           # 3 = Fair
            hyperactivity=3,
            sensory_reactivity=2,
            emotional_regulation=2
        )
        obs1.notes = "ياسر طفل يظهر سلوكيات انعزالية تامة مع غياب كامل للتواصل البصري أو الاستجابة عند مناداته باسمه أحمد. يُصدر أصوات رفرفة بالأيدي عند التململ ويدخل في نوبات صراخ عند سحب الأشياء منه."
        db.add(obs1)
        
        print("[Seed] Seeding test responses for Sarah (Discrepancy: Parent vs Teacher on ADHD)...")
        # Sarah responses
        # Parent evaluation on attention (80 concern)
        # Teacher evaluation on attention (20 concern)
        # Difference = 60 (triggers cross-informant discrepancy flag)
        resp2 = [
            models.Response(session_id=session2.id, question_id="q_core_02", informant="parent", selected_options=["موافق"], points=80.0), # Parent ADHD concern
            models.Response(session_id=session2.id, question_id="q_core_08", informant="teacher", selected_options=["نادرًا ما ينطبق"], points=20.0), # Teacher ADHD concern
            models.Response(session_id=session2.id, question_id="q_core_07", informant="parent", selected_options=["يواجه بعض الصعوبات الطفيفة"], points=50.0), # Math concern
            models.Response(session_id=session2.id, question_id="q_core_10", informant="teacher", selected_options=["أقل بكثير ويحتاج إلى دعم مكثف"], points=100.0), # Reading concern
        ]
        db.add_all(resp2)
        
        print("[Seed] Seeding test responses for Omar (Typical development)...")
        resp3 = [
            models.Response(session_id=session3.id, question_id="q_core_01", informant="parent", selected_options=["دائمًا"], points=0.0),
            models.Response(session_id=session3.id, question_id="q_core_02", informant="parent", selected_options=["معارض تمامًا"], points=0.0),
            models.Response(session_id=session3.id, question_id="q_core_03", informant="parent", selected_options=["نعم، بسهولة"], points=0.0),
            models.Response(session_id=session3.id, question_id="q_core_04", informant="parent", selected_options=["نعم، دائمًا"], points=0.0),
            models.Response(session_id=session3.id, question_id="q_core_06", informant="parent", selected_options=["يهدأ بسرعة ويبحث عن بديل"], points=0.0),
        ]
        db.add_all(resp3)
        db.commit()
        
        print("[Seed] Seed data committed to SQL successfully.")
        
    except Exception as e:
        print(f"[Seed] Error seeding SQL database: {e}")
        db.rollback()
    finally:
        db.close()

    # Seed Qdrant
    print("[Seed] Seeding vector store...")
    rag_client.initialize_collection()

if __name__ == "__main__":
    seed_db()
