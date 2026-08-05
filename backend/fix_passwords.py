import os
import sqlalchemy
from sqlalchemy.orm import sessionmaker
import models
import security

POSTGRES_URL = "postgresql://neondb_owner:npg_8pGeM0uELSJQ@ep-snowy-recipe-ayh0jb0k-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require"

engine = sqlalchemy.create_engine(POSTGRES_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

pwd_map = {
    'parent': 'parent123',
    'teacher': 'teacher123',
    'specialist': 'specialist123',
    'admin': 'admin123'
}

users = db.query(models.User).all()
for u in users:
    if u.username in pwd_map:
        u.password_hash = security.hash_password(pwd_map[u.username])
        print(f"Set password for user '{u.username}' -> '{pwd_map[u.username]}'")

db.commit()
print("All passwords fixed in Neon Postgres database!")
db.close()
