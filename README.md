# AI-Assisted Special Education Assessment Platform (POC) — Arabic / RTL

منصة مُساند الرقمية هي منصة تقييم وإعداد خطط علاجية فردية متعددة التخصصات (صعوبات تعلم، اضطراب طيف توحد، تأخر تخاطب ونطق، تكامل حسي، تنظيم سلوكي وانفعالي). تعتمد المنصة على محرك قواعد محدد سلفًا لحساب أولوية الحالات ومستويات الشدة وفجوات التقييم بين المدخلات، ومن ثم تغذية نموذج لغوي كبير عبر استرجاع بنية RAG من دليل إرشادي باللغة العربية الفصحى لصياغة خطة التدخل المقترحة تحت المسؤولية الإشرافية للأخصائي المعالج.

---

## 1. Architecture Overview (نظرة عامة على الهندسة البرمجية)

The platform is orchestratable via `docker-compose` and contains four primary layers:
1. **Frontend SPA (React + TS + TailwindCSS)**: Built RTL-first with standard Cairo typography and logical properties, ensuring a clean parent-facing register and a dense clinician-facing register.
2. **Backend Gateway (FastAPI)**: Implements Short-lived JWT security, Role-Based Access Control, and Fernet encryption to protect patient details (PHI) at rest.
3. **Database (PostgreSQL)**: Stores system logs, encrypted children records, MCQs responses, clinical observations, and audited events.
4. **Vector Store (Qdrant)**: Houses 24 Arabic clinical guidelines, smart goals, and specialty glossaries, queried via metadata-filtered embeddings.

```
Rule-Based Engine  →  Dynamic Questioning  →  RAG Retrieval  →  LLM (via OpenRouter)
   (deterministic)      (adaptive UI)          (grounding)        (draft generation, in Arabic)
```

---

## 2. Setup Instructions (خطوات التشغيل البرمجي)

### Prerequisites:
- Docker and Docker Compose installed.
- An [OpenRouter](https://openrouter.ai/keys) API key.

### Environment setup:
Copy the example env file and fill in your own secrets — never commit `.env`:
```bash
cp .env.example .env
# then edit .env and set OPENROUTER_API_KEY, JWT_SECRET, PHI_ENCRYPTION_KEY, POSTGRES_PASSWORD
```
Generate strong values for the secrets with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"                              # JWT_SECRET
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # PHI_ENCRYPTION_KEY
```

### Running the application:
1. **Spin up all containers**:
   ```bash
   docker-compose up --build
   ```
   This will boot:
   - PostgreSQL database on port `5432`
   - Qdrant vector database on port `6333`
   - FastAPI Backend API on `http://localhost:8000`
   - React Frontend SPA on `http://localhost:5173`

   For local (non-Docker) backend development, copy `backend/.env.example` to `backend/.env` instead — `config.py` loads it automatically.

2. **Database Auto-Seeding**:
   The backend automatically seeds basic demo credentials on startup if the database is blank. Additionally, you can run the dedicated seed script to populate synthetic clinical records and RAG guidelines:
   ```bash
   # Run seeding manually inside the backend container
   docker-compose exec backend python seed.py
   ```

### Quick Access Login Credentials (للتجربة السريعة):
Use the quick-select buttons on the portal login screen or enter manually:
- **Parent Profile**: User `parent` / Pass `parent123`
- **Clinician Profile**: User `specialist` / Pass `specialist123`
- **Administrator Profile**: User `admin` / Pass `admin123`

---

## 3. Disclaimers (إقرار وإخلاء مسؤولية)

> [!WARNING]
> **إقرار طبي**: هذه المنصة أداة دعم قرار إرشادي وليست أداة تشخيص طبي مستقلة. أي محتوى يتم توليده عبر الذكاء الاصطناعي هو مسودة تتطلب مراجعة واعتماد وتعديل أخصائي سريري مرخص.
>
> **إقرار تقني وخصوصية**: هذا الإصدار هو إثبات مفهوم (POC) فقط. البرنامج في حالته الحالية ليس معتمدًا لمعايير HIPAA أو GDPR أو تصنيفات الهيئات الصحية الوطنية. يحظر تمامًا استخدام بيانات حقيقية لمرضى حقيقيين في هذه النسخة، ويجب الاعتماد فقط على البيانات الاصطناعية (Synthetic Data).
