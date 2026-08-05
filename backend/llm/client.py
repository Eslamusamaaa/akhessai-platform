import re
import json
import requests
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from config import settings

# ── Output Schema ──────────────────────────────────────────────────────────────

class ReportDraftSchema(BaseModel):
    summary: str = Field(
        description="ملخص سريري سردي من 4-6 جمل يصف نتائج التقييم ومستوى الشدة الكلي مع الإشارة لنقاط القوة."
    )
    differential_considerations: List[str] = Field(
        description="قائمة من 1-3 اعتبارات تفريقية يجب أخذها بالحسبان (ASD مقابل ADHD مقابل تأخر لغة خالص، إلخ)."
    )
    suggested_goals: List[str] = Field(
        description="قائمة من 3-5 أهداف تدخل SMART مرتبة بالأولوية مستمدة من الإرشادات المرجعية."
    )
    intervention_plan: Dict[str, List[str]] = Field(
        description="خطة تدخل مُقسّمة حسب التخصص. المفاتيح هي اسم التخصص بالعربية والقيمة قائمة توصيات."
    )
    school_accommodations: List[str] = Field(
        description="قائمة من 2-4 تعديلات بيئية أو منهجية موصى بها في البيئة المدرسية."
    )
    home_program: List[str] = Field(
        description="قائمة من 2-3 أنشطة أو توجيهات منزلية عملية للوالدين."
    )
    suggested_referrals: List[str] = Field(
        description="قائمة الإحالات التخصصية الموصى بها مع سبب كل إحالة."
    )
    strengths_summary: str = Field(
        description="جملة واحدة أو جملتان تُبرزان نقاط القوة الملاحظة في ملف الطفل."
    )
    followup_goals: List[str] = Field(
        description="قائمة من 2-3 أهداف للمتابعة في 3-6 أشهر لقياس التقدم."
    )
    caveats: List[str] = Field(
        description="تحذيرات سريرية أو قيود على التفسير يجب على الأخصائي مراعاتها."
    )


# ── PHI Redaction ──────────────────────────────────────────────────────────────

COMMON_ARABIC_NAMES = [
    "أحمد", "محمد", "علي", "عمر", "حسن", "حسين", "خالد", "عبدالله", "يوسف", "إبراهيم",
    "سارة", "فاطمة", "مريم", "زينب", "نورة", "عائشة", "ليلى", "منى", "ريناد", "جود",
    "سلمان", "فهد", "عبدالرحمن", "سلطان", "فيصل", "ياسر", "ماجد", "خليل", "طارق", "رائد",
    "عبدالعزيز", "نايف", "بدر", "تركي", "وليد", "ريم", "هند", "لمى", "دانة", "غدير",
]


def redact_phi(text: str) -> str:
    """
    Strips telephone numbers, emails, dates, and common Arabic names
    before passing clinical notes to the external LLM.
    """
    if not text:
        return ""

    redacted = text

    # Phone numbers (Arabic and Western numerals)
    redacted = re.sub(r'\+?\b[0-9]{9,15}\b|[٠-٩]{9,15}', "[رقم]", redacted)

    # Email addresses
    redacted = re.sub(
        r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', "[بريد إلكتروني]", redacted
    )

    # Calendar dates (YYYY/MM/DD, DD-MM-YYYY, etc.)
    redacted = re.sub(r'\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b', "[تاريخ]", redacted)

    # Common Arabic names
    for name in COMMON_ARABIC_NAMES:
        redacted = re.sub(
            r'(?:^|(?<=\s))' + re.escape(name) + r'(?=\s|$|[،,.])',
            "[الحالة]",
            redacted,
        )

    return re.sub(r'\s+', ' ', redacted).strip()


# ── Prompt Builder ──────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
أنت مساعد سريري ذكي متخصص في التربية الخاصة والتقييم النمائي للأطفال، تعمل لصالح أخصائيين مرخصين.

## دورك
صياغة مسودة تقرير تقييمي سريري احترافي باللغة العربية الفصحى الميسّرة، مبنية على البيانات الكمية والملاحظات المحددة المقدمة إليك.

## قواعد غير قابلة للتجاوز
1. **لا تُصدر تشخيصًا طبيًا مستقلًا.** صاغ النتائج كـ "مؤشرات تستوجب مراجعة الأخصائي" لا كتشخيصات.
2. **لا تخترع أرقامًا أو نتائج** غير موجودة في البيانات المقدمة إليك.
3. **إذا كانت المعلومات غير كافية** لصياغة بند، اكتب "يحتاج إلى معلومات إضافية" ولا تملأ الفراغ بتخمينات.
4. **تحليل تفريقي مطلوب:** عند وجود نتائج عالية في أكثر من تخصص، ناقش الاحتمالات التفريقية بموضوعية.
5. **أخذ نقاط القوة بعين الاعتبار** جنبًا إلى جنب مع التحديات.

## المنهج المطلوب (فكر خطوة بخطوة قبل الكتابة)
أ. راجع الدرجات حسب الشدة وحدد المجالات الأكثر تأثيرًا.
ب. تحقق من وجود فجوات تقييمية بين المخبرين (والدين/معلم).
ج. تحقق من الفئة العمرية قبل اقتراح أهداف أو إحالات عمرية.
د. استخدم الإرشادات المرجعية المرفقة لبناء الأهداف والتوصيات.
هـ. أصدر النتيجة بـ JSON فقط وفق المخطط الدقيق التالي.

## مخطط JSON المطلوب (الالتزام الدقيق بهذه المفاتيح إلزامي)
{
  "summary": "...",
  "differential_considerations": ["...", "..."],
  "suggested_goals": ["...", "..."],
  "intervention_plan": {"التخاطب": ["..."], "العلاج الوظيفي": ["..."]},
  "school_accommodations": ["...", "..."],
  "home_program": ["...", "..."],
  "suggested_referrals": ["...", "..."],
  "strengths_summary": "...",
  "followup_goals": ["...", "..."],
  "caveats": ["..."]
}
"""

_SEVERITY_GUIDANCE = {
    1: "الشدة بسيطة جداً — التدخل وقائي وداعم",
    2: "الشدة خفيفة — تدخل داعم مبكر موصى به",
    3: "الشدة متوسطة — تدخل منظم ومتخصص ضروري",
    4: "الشدة شديدة — تدخل مكثف ومتعدد التخصصات عاجل",
    5: "الشدة شديدة جداً — إحالة وتدخل متكامل فوري مطلوب",
}

_DIFFERENTIAL_HINTS = {
    ("autism", "adhd"): (
        "التمييز بين ASD وADHD مطلوب: كلاهما يُظهر تشتتًا وصعوبة اجتماعية. "
        "ASD يتميز بضعف الانتباه المشترك والاهتمامات المحدودة والسلوكيات النمطية. "
        "ADHD يتميز بالاندفاعية وفرط الحركة المرتبطين بمتطلبات الانتباه لا بالسياق الاجتماعي. "
        "التشخيص المزدوج ممكن وشائع (50-70%)."
    ),
    ("autism", "speech_language"): (
        "التمييز بين تأخر اللغة الناتج عن التوحد وتأخر اللغة الخالص: "
        "في التوحد: ضعف التواصل غير اللفظي، غياب اللعب التخيلي، سلوكيات نمطية. "
        "في تأخر اللغة الخالص: التواصل الاجتماعي سليم نسبيًا، الطفل يُحاول التواصل بأساليب غير لفظية."
    ),
    ("adhd", "learning_disabilities"): (
        "التمييز بين صعوبات التعلم الناتجة عن ADHD وصعوبات التعلم النوعية: "
        "في ADHD: الأداء الأكاديمي يتحسن في بيئة خالية من التشتت. "
        "في صعوبات التعلم النوعية: الصعوبة في المهارة الأكاديمية المحددة تستمر حتى في بيئة مثالية."
    ),
}


def _get_differential_hint(specialties: List[str]) -> str:
    specialty_set = set(specialties)
    hints = []
    for key, hint in _DIFFERENTIAL_HINTS.items():
        if set(key).issubset(specialty_set):
            hints.append(hint)
    return "\n".join(hints) if hints else ""


def build_prompt(
    child_id_redacted: str,
    age_band: str,
    gender: str,
    domain_scores: Dict[str, Any],
    priority_tier: str,
    priority_rationale: str,
    specialist_notes_redacted: str,
    rag_context: List[Dict[str, Any]],
    strengths: List[Dict[str, Any]] = None,
    active_specialties: List[str] = None,
) -> Tuple[str, str]:
    """Assemble system + user prompts with differential hints and strengths profile."""

    # Determine max severity level for severity-aware guidance
    max_level = 1
    for detail in domain_scores.values():
        if isinstance(detail, dict) and detail.get("level", 1) > max_level:
            max_level = detail.get("level", 1)

    severity_context = _SEVERITY_GUIDANCE.get(max_level, "")
    differential_hint = _get_differential_hint(active_specialties or [])

    # Format domain scores
    score_lines = []
    for domain, detail in domain_scores.items():
        if isinstance(detail, dict):
            domain_ar = detail.get("domain_ar", domain)
            score_lines.append(
                f"• {domain_ar}: {detail['score']}/100 "
                f"— {detail['name_ar']} (Level {detail['level']})"
            )
        else:
            score_lines.append(f"• {domain}: {detail}/100")

    # Format strengths
    strengths_text = "لم تُرصد نقاط قوة واضحة في هذا التقييم."
    if strengths:
        s_items = [
            f"• {s.get('domain_ar', s['domain'])}: {s['score']}/100"
            for s in strengths
        ]
        strengths_text = "\n".join(s_items)

    # Format RAG context
    rag_sections = []
    for idx, doc in enumerate(rag_context):
        rag_sections.append(
            f"[وثيقة {idx+1}] {doc['title']} ({doc['category']})\n{doc['content']}"
        )

    user_data = (
        "═══════════════════════════════════════════════════\n"
        "بيانات الحالة (مجهولة الهوية)\n"
        "═══════════════════════════════════════════════════\n"
        f"المعرف المرجعي: {child_id_redacted}\n"
        f"الفئة العمرية: {age_band} سنوات\n"
        f"الجنس: {'ذكر' if gender == 'male' else 'أنثى' if gender == 'female' else gender}\n"
        f"التخصصات النشطة: {', '.join(active_specialties or [])}\n"
        f"مستوى الأولوية: {priority_tier}\n"
        f"مبرر الأولوية: {priority_rationale}\n\n"
        "═══════════════════════════════════════════════════\n"
        "نتائج تقييم المجالات (درجات الاهتمام السريري)\n"
        "═══════════════════════════════════════════════════\n"
        + "\n".join(score_lines) +
        f"\n\nمستوى التدخل المقترح: {severity_context}\n\n"
        "═══════════════════════════════════════════════════\n"
        "نقاط القوة (مجالات الأداء المقبول)\n"
        "═══════════════════════════════════════════════════\n"
        + strengths_text +
        (
            f"\n\n═══════════════════════════════════════════════════\n"
            f"اعتبارات التشخيص التفريقي\n"
            f"═══════════════════════════════════════════════════\n"
            f"{differential_hint}\n"
            if differential_hint else ""
        ) +
        "\n\n═══════════════════════════════════════════════════\n"
        "ملاحظات الأخصائي السريرية (منقحة)\n"
        "═══════════════════════════════════════════════════\n"
        f"{specialist_notes_redacted or 'لا توجد ملاحظات إضافية.'}\n\n"
        "═══════════════════════════════════════════════════\n"
        "الإرشادات المرجعية (RAG) — استخدمها لبناء الأهداف والتوصيات\n"
        "═══════════════════════════════════════════════════\n"
        + "\n\n".join(rag_sections) +
        "\n\n═══════════════════════════════════════════════════\n"
        "الرجاء الآن معالجة هذه البيانات وإصدار مسودة التقرير بصيغة JSON فقط.\n"
    )

    return _SYSTEM_TEMPLATE, user_data


# ── Main Generation Function ────────────────────────────────────────────────────

def generate_report_draft(
    child_id: str,
    age_band: str,
    gender: str,
    domain_scores: Dict[str, Any],
    priority_tier: str,
    priority_rationale: str,
    specialist_notes: str,
    rag_context: List[Dict[str, Any]],
    strengths: List[Dict[str, Any]] = None,
    active_specialties: List[str] = None,
) -> Dict[str, Any]:
    """
    Calls OpenRouter API with full clinical context and returns validated report draft.
    Returns a structured fallback on any error.
    """
    redacted_notes = redact_phi(specialist_notes)
    child_ref = f"CASE_{child_id[:8].upper()}"

    sys_prompt, user_prompt = build_prompt(
        child_id_redacted=child_ref,
        age_band=age_band,
        gender=gender,
        domain_scores=domain_scores,
        priority_tier=priority_tier,
        priority_rationale=priority_rationale,
        specialist_notes_redacted=redacted_notes,
        rag_context=rag_context,
        strengths=strengths or [],
        active_specialties=active_specialties or [],
    )

    fallback = {
        "summary": (
            "تعذّر توليد المسودة السردية بسبب خطأ تقني مؤقت في نظام الذكاء الاصطناعي. "
            "يُرجى مراجعة الدرجات والتقارير المرفقة وصياغة الملخص يدويًا."
        ),
        "differential_considerations": [
            "لم يتمكن النظام من توليد الاعتبارات التفريقية — يُرجى المراجعة اليدوية."
        ],
        "suggested_goals": [
            "مراجعة الأهداف الموجودة في الإرشادات المرجعية وتطبيق المناسب منها.",
            "وضع خطة تدخل فردية بالتعاون مع فريق التخصصات المتعددة.",
        ],
        "intervention_plan": {
            "ملاحظة": ["يتعذر التوليد التلقائي — يُرجى صياغة الخطة يدويًا."]
        },
        "school_accommodations": [
            "يُرجى مراجعة قائمة التعديلات المدرسية الموصى بها مع فريق المدرسة."
        ],
        "home_program": [
            "يُرجى التواصل مع الأخصائي للحصول على إرشادات البرنامج المنزلي."
        ],
        "suggested_referrals": [
            "راجع قائمة الإحالات الموصى بها بناءً على التخصصات المُفعّلة."
        ],
        "strengths_summary": "لم يُتمكن من استخلاص نقاط القوة تلقائيًا في هذه المرة.",
        "followup_goals": [
            "إعادة التقييم بعد 3-6 أشهر من التدخل لقياس التقدم."
        ],
        "caveats": [
            "حدث خطأ أثناء الاتصال بنظام الذكاء الاصطناعي (OpenRouter) أو أثناء التحقق من سلامة المخرجات.",
            "هذا التقرير مسودة مساعدة للأخصائي المرخص وليس تشخيصًا طبيًا مستقلًا.",
        ],
    }

    if not settings.OPENROUTER_API_KEY:
        print("[LLM] API key missing — returning fallback draft.")
        return fallback

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Special Education Assessment Platform",
    }

    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.15,   # Low temperature for clinical precision
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        validated = ReportDraftSchema(**parsed)
        return validated.model_dump()

    except Exception as e:
        print(f"[LLM] Error communicating with OpenRouter or validating schema: {e}")
        return fallback
