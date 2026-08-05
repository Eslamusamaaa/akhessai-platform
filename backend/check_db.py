from database import SessionLocal
import models

def check_database():
    db = SessionLocal()
    try:
        print("=== Users ===")
        for u in db.query(models.User).all():
            print(f"- User: {u.username}, Role: {u.role}")

        print("\n=== Children ===")
        for c in db.query(models.Child).all():
            print(f"- Child ID: {c.id}, Name: {c.name}, Contact: {c.parent_contact}")

        print("\n=== Assessment Sessions ===")
        for s in db.query(models.AssessmentSession).all():
            print(f"- Session ID: {s.id}, Child: {s.child.name}, Status: {s.status}, Informant: {s.current_informant}")
            
        print("\n=== Draft Reports ===")
        for r in db.query(models.DraftReport).all():
            print(f"- Report ID: {r.id}, Session: {r.session_id}, Status: {r.status}, Summary: {r.executive_summary[:60] if r.executive_summary else 'None'}")
            
        print("\n=== Audit Logs ===")
        for l in db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(5).all():
            print(f"- Audit: {l.timestamp}, Action: {l.action}, Details: {l.details}")
    finally:
        db.close()

if __name__ == "__main__":
    check_database()
