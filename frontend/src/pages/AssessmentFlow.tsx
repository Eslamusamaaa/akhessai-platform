import React, { useState, useEffect } from "react";
import apiFetch from "../apiFetch";
import { ArrowRight, ChevronLeft, CheckCircle2, BookOpen, Star } from "lucide-react";
import { QuestionRenderer } from "../components/QuestionRenderer";

interface Option {
  label_ar: string;
  points: number;
}

interface Question {
  id: string;
  type: "single_select" | "multi_select" | "likert_1_5" | "free_text" | "file_upload";
  label_ar: string;
  options?: Option[];
  is_core?: boolean;
  priority?: number;
  specialty_tags?: string[];
}

interface AssessmentFlowProps {
  sessionId: string;
  onBackToDashboard: () => void;
  token: string;
}

const SPECIALTY_NAMES: Record<string, string> = {
  autism: "طيف التوحد",
  adhd: "فرط الحركة وتشتت الانتباه",
  speech_language: "النطق واللغة",
  learning_disabilities: "صعوبات التعلم",
  sensory_processing: "التكامل الحسي",
  behavior_emotional: "السلوك والتنظيم الانفعالي",
};

const INFORMANT_CAPS: Record<string, number> = {
  parent: 35,
  teacher: 20,
  specialist: 15,
};

const ROLE_TO_INFORMANT: Record<string, string> = {
  parent: "parent",
  teacher: "teacher",
  specialist: "specialist",
  admin: "any",
};

const INFORMANT_LABEL: Record<string, string> = {
  parent: "ولي الأمر",
  teacher: "المعلم",
  specialist: "الأخصائي المعالج",
};

export const AssessmentFlow: React.FC<AssessmentFlowProps> = ({
  sessionId,
  onBackToDashboard,
  token,
}) => {
  const userRole = sessionStorage.getItem("role") || "";
  const [session, setSession] = useState<any>(null);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [selectedValue, setSelectedValue] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [finishedFlow, setFinishedFlow] = useState(false);
  const [answeredCount, setAnsweredCount] = useState(0);

  const fetchSessionAndQuestion = async () => {
    setLoading(true);
    try {
      const [sessRes, qRes] = await Promise.all([
        apiFetch(`/sessions/${sessionId}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        apiFetch(`/sessions/${sessionId}/next-question`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (sessRes.ok) {
        const sessData = await sessRes.json();
        setSession(sessData);
        const informant = sessData.current_informant || "parent";
        const perCount = sessData.informant_responses_count?.[informant] ?? sessData.responses_count ?? 0;
        setAnsweredCount(perCount);
      }

      if (qRes.ok) {
        const qData = await qRes.json();
        if (qData.finished) {
          setFinishedFlow(true);
          setCurrentQuestion(null);
        } else {
          setCurrentQuestion(qData.question);
          setSelectedValue([]);
        }
      }
    } catch (e) {
      console.error("Error loading questionnaire flow:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessionAndQuestion();
  }, [sessionId, token]);

  const handleSaveAndContinue = async () => {
    if (!currentQuestion) return;
    if (selectedValue.length === 0 && currentQuestion.type !== "free_text") {
      alert("الرجاء اختيار إجابة واحدة على الأقل للمتابعة.");
      return;
    }

    setSaving(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}/respond`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          question_id: currentQuestion.id,
          selected_options: selectedValue,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.finished) {
          setFinishedFlow(true);
          setCurrentQuestion(null);
        } else if (data.next_question) {
          setCurrentQuestion(data.next_question);
          setSelectedValue([]);
          setAnsweredCount(data.responses_count ?? (answeredCount + 1));
          if (data.current_informant && session) {
            setSession({ ...session, current_informant: data.current_informant, status: data.session_status });
          }
        } else {
          await fetchSessionAndQuestion();
        }
      } else {
        alert("حدث خطأ أثناء حفظ الإجابة.");
      }
    } catch (err) {
      console.error(err);
      alert("تعذر الاتصال بالخادم.");
    } finally {
      setSaving(false);
    }
  };

  const currentInformant = session?.current_informant || "parent";
  const cap = INFORMANT_CAPS[currentInformant] || 25;
  const progressPct = Math.min((answeredCount / cap) * 100, 100);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-16 text-center">
        <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-slate-500 font-bold">جاري تحميل الأسئلة الاستقصائية النشطة...</p>
      </div>
    );
  }

  // Role-gate: only the matching informant may answer
  const myInformant = ROLE_TO_INFORMANT[userRole];
  const sessionInformant = session?.current_informant || "parent";
  const isWrongRole = myInformant !== "any" && myInformant !== sessionInformant;

  if (isWrongRole) {
    const waitingFor = INFORMANT_LABEL[sessionInformant] || sessionInformant;
    const myLabel = INFORMANT_LABEL[myInformant] || myInformant;
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <button onClick={onBackToDashboard} className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold mb-6 transition">
          <ArrowRight className="w-5 h-5" />
          <span>الرجوع للوحة التحكم</span>
        </button>
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm p-10 text-center space-y-4">
          <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto" />
          <h2 className="text-xl font-extrabold text-slate-800">شكراً — انتهت مشاركتك كـ {myLabel}</h2>
          <p className="text-slate-500 font-medium">
            الجلسة تنتظر الآن مشاركة <span className="font-bold text-brand-600">{waitingFor}</span> لإكمال مراحل التقييم المتبقية.
          </p>
          <button onClick={onBackToDashboard} className="mt-4 bg-brand-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-brand-600 transition">
            العودة للداشبورد
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Back Button */}
      <button
        onClick={onBackToDashboard}
        className="inline-flex items-center gap-2 text-slate-500 hover:text-slate-800 font-bold mb-6 transition"
      >
        <ArrowRight className="w-5 h-5" />
        <span>الرجوع للوحة التحكم</span>
      </button>

      {/* Session Header */}
      {session && (
        <div className="mb-6 bg-white border border-slate-100 p-5 rounded-2xl shadow-sm space-y-4">
          <div className="flex items-center justify-between text-sm">
            <div>
              <span className="text-slate-400 font-medium">الطفل: </span>
              <span className="font-bold text-slate-800">{session.child_name}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium">المجيب الحالي:</span>
              <span className="font-bold text-brand-600 bg-brand-50 px-3 py-1 rounded-lg text-xs">
                {currentInformant === "parent" ? "ولي الأمر" :
                 currentInformant === "teacher" ? "المعلم" : "الأخصائي"}
              </span>
            </div>
          </div>

          {/* Progress bar */}
          <div>
            <div className="flex justify-between text-xs text-slate-400 font-bold mb-1.5">
              <span>تقدم الاستقصاء</span>
              <span>{answeredCount} / ~{cap} سؤال</span>
            </div>
            <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
              <div
                className="bg-brand-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Active specialties */}
          {session.active_specialties && session.active_specialties.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <span className="text-xs text-slate-400 font-bold mt-0.5">التخصصات النشطة:</span>
              {session.active_specialties.map((s: string) => (
                <span key={s} className="px-2 py-0.5 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-100">
                  {SPECIALTY_NAMES[s] || s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {finishedFlow ? (
        <div className="bg-white border border-slate-100 rounded-2xl p-8 shadow-sm text-center">
          <div className="w-16 h-16 bg-emerald-50 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="w-10 h-10" />
          </div>
          <h3 className="text-2xl font-bold text-slate-900 mb-4">تم إكمال هذه المرحلة بنجاح!</h3>
          <p className="text-slate-500 max-w-md mx-auto mb-8 leading-relaxed">
            {currentInformant === "parent"
              ? "تم الانتهاء من جميع أسئلة ولي الأمر. الخطوة التالية إكمال أسئلة المعلم والأخصائي."
              : currentInformant === "teacher"
              ? "تم الانتهاء من أسئلة المعلم. الخطوة التالية إكمال الملاحظة السريرية من الأخصائي."
              : "تم إكمال جميع مراحل الاستقصاء بنجاح. بانتظار مراجعة الأخصائي وتوليد التقرير."}
          </p>
          <button
            onClick={onBackToDashboard}
            className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl shadow hover:bg-brand-600 transition"
          >
            العودة للرئيسية
          </button>
        </div>
      ) : currentQuestion ? (
        <div className="space-y-4">
          {/* Question type badge */}
          <div className="flex items-center gap-2">
            {currentQuestion.is_core ? (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-brand-50 text-brand-700 border border-brand-200">
                <Star className="w-3.5 h-3.5" />
                سؤال أساسي (Core)
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                <BookOpen className="w-3.5 h-3.5" />
                استقصاء تخصصي
                {currentQuestion.specialty_tags && currentQuestion.specialty_tags.length > 0 && (
                  <span className="font-normal">— {currentQuestion.specialty_tags.map(t => SPECIALTY_NAMES[t] || t).join(", ")}</span>
                )}
              </span>
            )}
          </div>

          {/* Question Renderer Card */}
          <QuestionRenderer
            question={currentQuestion}
            value={selectedValue}
            onChange={setSelectedValue}
          />

          {/* Action Buttons */}
          <div className="flex justify-between items-center pt-2">
            <button
              onClick={onBackToDashboard}
              className="border border-slate-200 bg-white text-slate-600 font-bold px-6 py-3 rounded-xl hover:bg-slate-50 transition"
            >
              حفظ كمسودة وإغلاق
            </button>

            <button
              onClick={handleSaveAndContinue}
              disabled={saving}
              className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl shadow hover:bg-brand-600 disabled:opacity-50 transition flex items-center gap-2"
            >
              <span>{saving ? "جاري الحفظ..." : "حفظ ومتابعة التقييم"}</span>
              <ChevronLeft className="w-5 h-5" />
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-slate-100 rounded-2xl p-8 shadow-sm text-center text-slate-400">
          <span>لا توجد أسئلة متاحة حاليًا لهذا الدور أو المرحلة.</span>
        </div>
      )}
    </div>
  );
};
export default AssessmentFlow;
