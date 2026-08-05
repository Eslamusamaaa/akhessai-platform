import React, { useState, useEffect } from "react";
import apiFetch from "../apiFetch";
import {
  ArrowRight, Sparkles, Check, Trash2, Plus, AlertCircle, Award,
  FileText, GitFork, Target, School, Home, Heart, Calendar, Info,
  TrendingUp, AlertTriangle,
} from "lucide-react";

interface ClinicianPortalProps {
  sessionId: string;
  onBackToDashboard: () => void;
  token: string;
}

// 17-domain translation map matching evaluator.py DOMAIN_TRANSLATIONS_AR
const DOMAIN_LABELS: Record<string, string> = {
  social_communication:   "التواصل الاجتماعي",
  restricted_repetitive:  "السلوكيات النمطية التكرارية",
  attention:              "الانتباه والتركيز",
  hyperactivity:          "فرط الحركة",
  impulsivity:            "الاندفاعية",
  executive_function:     "الوظائف التنفيذية",
  expressive_language:    "اللغة التعبيرية",
  receptive_language:     "اللغة الاستقبالية",
  articulation:           "النطق ومخارج الحروف",
  pragmatic_language:     "اللغة البراغماتية الاجتماعية",
  sensory_reactivity:     "الاستجابة الحسية",
  vestibular:             "الجهاز الدهليزي (التوازن والحركة)",
  proprioceptive:         "الإحساس العميق بالجسم",
  emotional_regulation:   "التنظيم الانفعالي",
  externalizing:          "السلوكيات الخارجية (العدوان والتمرد)",
  internalizing:          "السلوكيات الداخلية (القلق والانسحاب)",
  academic_skills:        "المهارات الأكاديمية",
};

const SEVERITY_COLORS: Record<number, string> = {
  5: "bg-red-50 text-red-700 border border-red-200",
  4: "bg-orange-50 text-orange-700 border border-orange-200",
  3: "bg-amber-50 text-amber-700 border border-amber-200",
  2: "bg-blue-50 text-blue-700 border border-blue-100",
  1: "bg-slate-50 text-slate-600 border border-slate-100",
};

const ListEditor: React.FC<{
  label: string;
  icon: React.ReactNode;
  items: string[];
  isCompleted: boolean;
  placeholder: string;
  onChange: (items: string[]) => void;
}> = ({ label, icon, items, isCompleted, placeholder, onChange }) => {
  const [draft, setDraft] = useState("");
  return (
    <div>
      <label className="flex items-center gap-2 text-sm font-bold text-slate-700 mb-3">
        {icon}
        {label}
      </label>
      <div className="space-y-2 mb-3">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-start justify-between p-3 bg-slate-50 border border-slate-100 rounded-xl text-sm gap-3">
            <span className="text-slate-700 font-medium leading-relaxed flex-1">{item}</span>
            {!isCompleted && (
              <button
                type="button"
                onClick={() => onChange(items.filter((_, i) => i !== idx))}
                className="text-red-400 hover:text-red-600 p-0.5 flex-shrink-0"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-slate-400 italic px-1">لا توجد عناصر بعد.</p>
        )}
      </div>
      {!isCompleted && (
        <div className="flex gap-2">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                onChange([...items, draft.trim()]);
                setDraft("");
              }
            }}
            className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
            placeholder={placeholder}
          />
          <button
            type="button"
            onClick={() => { if (draft.trim()) { onChange([...items, draft.trim()]); setDraft(""); } }}
            className="bg-brand-50 text-brand-600 font-bold px-4 py-2.5 rounded-xl hover:bg-brand-100 transition text-sm flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            إضافة
          </button>
        </div>
      )}
    </div>
  );
};

export const ClinicianPortal: React.FC<ClinicianPortalProps> = ({
  sessionId,
  onBackToDashboard,
  token,
}) => {
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [submittingObs, setSubmittingObs] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [approvingReport, setApprovingReport] = useState(false);

  // Observation form state
  const [eyeContact, setEyeContact] = useState(3);
  const [responseToName, setResponseToName] = useState(3);
  const [jointAttention, setJointAttention] = useState(3);
  const [socialReciprocity, setSocialReciprocity] = useState(3);
  const [expressiveLanguage, setExpressiveLanguage] = useState(3);
  const [receptiveLanguage, setReceptiveLanguage] = useState(3);
  const [attention, setAttention] = useState(3);
  const [hyperactivity, setHyperactivity] = useState(3);
  const [sensoryReactivity, setSensoryReactivity] = useState(3);
  const [emotionalRegulation, setEmotionalRegulation] = useState(3);
  const [notes, setNotes] = useState("");

  // Report state
  const [report, setReport] = useState<any>(null);

  // Editable report fields
  const [editedSummary, setEditedSummary] = useState("");
  const [editedGoals, setEditedGoals] = useState<string[]>([]);
  const [editedReferrals, setEditedReferrals] = useState<string[]>([]);
  const [editedSchoolAccommodations, setEditedSchoolAccommodations] = useState<string[]>([]);
  const [editedHomeProgram, setEditedHomeProgram] = useState<string[]>([]);
  const [editedFollowupGoals, setEditedFollowupGoals] = useState<string[]>([]);
  const [editedCaveats, setEditedCaveats] = useState<string[]>([]);

  const loadClinicianData = async () => {
    setLoading(true);
    try {
      const sessRes = await apiFetch(`/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (sessRes.ok) {
        const sessData = await sessRes.json();
        setSession(sessData);

        if (sessData.status === "drafting" || sessData.status === "completed") {
          // Fetch observation
          const obsRes = await apiFetch(`/sessions/${sessionId}/observation`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (obsRes.ok) {
            const obsData = await obsRes.json();
            setEyeContact(obsData.eye_contact);
            setResponseToName(obsData.response_to_name);
            setJointAttention(obsData.joint_attention);
            setSocialReciprocity(obsData.social_reciprocity);
            setExpressiveLanguage(obsData.expressive_language);
            setReceptiveLanguage(obsData.receptive_language);
            setAttention(obsData.attention);
            setHyperactivity(obsData.hyperactivity);
            setSensoryReactivity(obsData.sensory_reactivity);
            setEmotionalRegulation(obsData.emotional_regulation);
            setNotes(obsData.notes || "");
          }

          // Fetch report
          const repRes = await apiFetch(`/sessions/${sessionId}/report`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (repRes.ok) {
            const repData = await repRes.json();
            setReport(repData);
            setEditedSummary(repData.executive_summary || "");
            setEditedGoals(repData.suggested_goals || []);
            setEditedReferrals(repData.suggested_referrals || []);
            setEditedSchoolAccommodations(repData.school_accommodations || []);
            setEditedHomeProgram(repData.home_program || []);
            setEditedFollowupGoals(repData.followup_goals || []);
            setEditedCaveats(repData.caveats || []);
          }
        }
      }
    } catch (e) {
      console.error("Error loading clinician portal data:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadClinicianData();
  }, [sessionId, token]);

  const handleSubmitObservation = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmittingObs(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}/observation`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          eye_contact: eyeContact, response_to_name: responseToName,
          joint_attention: jointAttention, social_reciprocity: socialReciprocity,
          expressive_language: expressiveLanguage, receptive_language: receptiveLanguage,
          attention: attention, hyperactivity: hyperactivity,
          sensory_reactivity: sensoryReactivity, emotional_regulation: emotionalRegulation,
          notes: notes,
        }),
      });
      if (res.ok) {
        alert("تم حفظ الملاحظة السريرية. يمكنك الآن توليد التقرير الذكي.");
        await loadClinicianData();
      } else {
        alert("فشل حفظ الملاحظة السريرية.");
      }
    } catch (err) {
      alert("خطأ في الاتصال بالخادم.");
    } finally {
      setSubmittingObs(false);
    }
  };

  const handleGenerateReport = async () => {
    setGeneratingReport(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}/generate-report`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        alert("تم توليد مسودة التقرير بنجاح!");
        await loadClinicianData();
      } else {
        alert("فشل توليد التقرير.");
      }
    } catch (err) {
      alert("خطأ في الشبكة.");
    } finally {
      setGeneratingReport(false);
    }
  };

  const handleApproveReport = async () => {
    setApprovingReport(true);
    try {
      const res = await apiFetch(`/sessions/${sessionId}/report/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          executive_summary: editedSummary,
          suggested_goals: editedGoals,
          suggested_referrals: editedReferrals,
          school_accommodations: editedSchoolAccommodations,
          home_program: editedHomeProgram,
          followup_goals: editedFollowupGoals,
          caveats: editedCaveats,
        }),
      });
      if (res.ok) {
        alert("تم اعتماد التقرير ووضعه في الملف الرسمي للطفل بنجاح!");
        await loadClinicianData();
      } else {
        alert("فشل اعتماد التقرير.");
      }
    } catch (err) {
      alert("خطأ في الخادم.");
    } finally {
      setApprovingReport(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-slate-500 font-bold">جاري تحميل بيانات الأخصائي والتقارير...</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center space-y-4">
        <p className="text-slate-500 font-bold">تعذر تحميل بيانات الجلسة. تحقق من الاتصال وأعد المحاولة.</p>
        <button onClick={onBackToDashboard} className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-brand-600 transition">
          الرجوع للوحة التحكم
        </button>
      </div>
    );
  }

  const isCompleted = session?.status === "completed";

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
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
        <div className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm mb-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div>
            <span className="text-xs font-bold text-brand-600 bg-brand-50 px-3 py-1 rounded-full block w-fit mb-2">
              ملف تقييم سريري نشط
            </span>
            <h2 className="text-2xl font-extrabold text-slate-900">{session.child_name}</h2>
            <p className="text-sm text-slate-400 mt-1 font-medium">
              الفئة العمرية: {session.age_band === "0-6" ? "الطفولة المبكرة" : "المدرسة والمراهقة"} • رقم التقييم: {session.id?.toString().substring(0, 8)}
            </p>
          </div>
          <div className="flex bg-slate-50 border border-slate-200/50 p-4 rounded-xl gap-6 text-sm">
            <div>
              <span className="text-slate-400 font-semibold block mb-0.5">عدد الإجابات</span>
              <span className="text-base font-bold text-slate-900">{session.responses_count} إجابة</span>
            </div>
            <div className="border-l border-slate-200"></div>
            <div>
              <span className="text-slate-400 font-semibold block mb-0.5">الحالة</span>
              <span className="text-base font-bold text-brand-600">
                {session.status === "clinical_observation" ? "الملاحظة السريرية" :
                 session.status === "drafting" ? "مراجعة المسودة" : "مكتمل ومعتمد"}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Observation Form */}
      {session && (session.status === "clinical_observation" || session.status === "drafting" || isCompleted) && (
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden mb-8">
          <div className="p-6 border-b border-slate-100 bg-slate-50/50">
            <h3 className="text-lg font-bold text-slate-900">
              {isCompleted ? "الملاحظات السريرية المرصودة" : "١. رصد الملاحظة السريرية والتقييم السلوكي"}
            </h3>
            <p className="text-xs text-slate-400 font-medium mt-1">
              مقياس من 1 (ضعيف جداً) إلى 5 (ممتاز)
            </p>
          </div>
          <form onSubmit={handleSubmitObservation} className="p-6 md:p-8 space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {[
                { label: "التواصل البصري واستمراريته", value: eyeContact, setter: setEyeContact },
                { label: "الاستجابة عند سماع الاسم", value: responseToName, setter: setResponseToName },
                { label: "الانتباه المشترك ومشاركة التركيز", value: jointAttention, setter: setJointAttention },
                { label: "التفاعل الاجتماعي المتبادل", value: socialReciprocity, setter: setSocialReciprocity },
                { label: "القدرة التعبيرية واللغوية النطقية", value: expressiveLanguage, setter: setExpressiveLanguage },
                { label: "القدرة الاستقبالية وفهم التوجيهات", value: receptiveLanguage, setter: setReceptiveLanguage },
                { label: "التركيز والاستمرار في المهام", value: attention, setter: setAttention },
                { label: "تنظيم الحركة والتململ الحركي", value: hyperactivity, setter: setHyperactivity },
                { label: "التحمل للمثيرات الحسية", value: sensoryReactivity, setter: setSensoryReactivity },
                { label: "التحكم الانفعالي وتنظيم الغضب", value: emotionalRegulation, setter: setEmotionalRegulation },
              ].map((dim, i) => (
                <div key={i} className="flex flex-col justify-between p-4 bg-slate-50/50 border border-slate-100 rounded-xl">
                  <span className="text-sm font-bold text-slate-700 mb-3">{dim.label}</span>
                  <div className="flex gap-2">
                    {[1, 2, 3, 4, 5].map((val) => (
                      <button
                        key={val}
                        type="button"
                        disabled={isCompleted || session.status === "drafting"}
                        onClick={() => dim.setter(val)}
                        className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all duration-150 ${
                          dim.value === val
                            ? "bg-brand-500 text-white shadow-sm"
                            : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        {val}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div>
              <label className="block text-sm font-bold text-slate-700 mb-2">الملاحظات الكيفية العامة</label>
              <textarea
                rows={4}
                required
                disabled={isCompleted || session.status === "drafting"}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full rounded-xl border border-slate-200 p-4 text-slate-800 focus:border-brand-500 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400"
                placeholder="اكتب تفاصيل الملاحظة (مثال: يظهر رفرفة يدين، لا يستجيب للاسم...)"
              />
            </div>
            {!isCompleted && session.status !== "drafting" && (
              <button
                type="submit"
                disabled={submittingObs}
                className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-brand-600 disabled:opacity-50 transition shadow-md"
              >
                {submittingObs ? "جاري حفظ التقييم السلوكي..." : "حفظ التقييم السلوكي وحساب النتائج"}
              </button>
            )}
          </form>
        </div>
      )}

      {/* Generate Report CTA */}
      {session && session.status === "drafting" && !report && (
        <div className="bg-brand-50 border border-brand-200 rounded-2xl p-6 md:p-8 shadow-sm flex flex-col md:flex-row items-center justify-between gap-6 mb-8">
          <div>
            <h3 className="text-lg font-bold text-brand-900 flex items-center gap-2 mb-1">
              <Sparkles className="w-5 h-5 text-brand-500" />
              جاهز لتوليد التقرير الذكي
            </h3>
            <p className="text-sm text-brand-700">
              سيقوم النظام بتوليد تقرير سريري شامل مكوّن من 10 أقسام بناءً على بيانات التقييم المُجمَّعة.
            </p>
          </div>
          <button
            onClick={handleGenerateReport}
            disabled={generatingReport}
            className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-brand-600 disabled:opacity-50 transition flex items-center gap-2 shadow-md w-full md:w-auto justify-center"
          >
            <span>{generatingReport ? "جاري توليد التقرير..." : "إنشاء التقرير بالذكاء الاصطناعي"}</span>
          </button>
        </div>
      )}

      {/* Full Report Panel */}
      {report && (
        <div className="space-y-8">

          {/* AI Warning Banner */}
          {report.status !== "approved" && (
            <div className="bg-pink-50 border border-pink-200 rounded-2xl px-6 py-4 flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-pink-600 flex-shrink-0" />
              <span className="text-sm font-bold text-pink-800">
                تحذير: مسودة منشأة بالذكاء الاصطناعي — يجب مراجعتها وتعديلها واعتمادها قبل النقل للملف الرسمي.
              </span>
            </div>
          )}

          {/* ── Section A: Rule-Engine Results (deterministic) ── */}
          <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100 bg-slate-50/50">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-brand-500" />
                أ. نتائج التقييم الموضوعية
              </h3>
            </div>
            <div className="p-6 space-y-6">

              {/* Domain Scores Grid */}
              <div>
                <h4 className="text-sm font-bold text-slate-600 mb-3">درجات شدة المجالات التنموية</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(report.domain_scores || {}).map(([domain, detail]: any) => (
                    <div key={domain} className="bg-white p-4 rounded-xl border border-slate-100 flex justify-between items-center shadow-sm">
                      <div>
                        <span className="font-bold text-slate-700 text-sm">
                          {DOMAIN_LABELS[domain] || domain}
                        </span>
                        <span className="text-xs text-slate-400 block mt-0.5">
                          معدل القلق: {detail.score?.toFixed(1)}/100
                        </span>
                      </div>
                      <span className={`px-3 py-1 rounded-lg text-xs font-bold ${SEVERITY_COLORS[detail.level] || SEVERITY_COLORS[1]}`}>
                        {detail.name_ar} (L{detail.level})
                      </span>
                    </div>
                  ))}
                  {Object.keys(report.domain_scores || {}).length === 0 && (
                    <p className="text-xs text-slate-400 italic col-span-2 px-1">لا توجد درجات محسوبة بعد.</p>
                  )}
                </div>
              </div>

              {/* Priority Tier */}
              <div className="border-t border-slate-100 pt-4 flex flex-wrap items-center gap-4">
                <span className="text-sm font-bold text-slate-500">تصنيف الأولوية الكلي:</span>
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                  report.priority_tier === "Priority 1" ? "bg-red-100 text-red-800" :
                  report.priority_tier === "Priority 2" ? "bg-amber-100 text-amber-800" : "bg-blue-100 text-blue-800"
                }`}>
                  {report.priority_tier === "Priority 1" && "تدخل عاجل — أولوية 1"}
                  {report.priority_tier === "Priority 2" && "تقييم أخصائي موصى به — أولوية 2"}
                  {report.priority_tier === "Priority 3" && "مراقبة ومتابعة — أولوية 3"}
                </span>
                <p className="text-sm text-slate-500 w-full mt-1">{report.priority_rationale}</p>
              </div>

              {/* Cross-informant discrepancies */}
              {report.discrepancies && report.discrepancies.length > 0 && (
                <div className="border-t border-slate-100 pt-4">
                  <h4 className="text-sm font-bold text-amber-700 flex items-center gap-2 mb-3">
                    <AlertTriangle className="w-4 h-4" />
                    فجوات تقييمية مرصودة بين المُخبرين
                  </h4>
                  <div className="space-y-2">
                    {report.discrepancies.map((d: any, idx: number) => (
                      <div key={idx} className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-100 rounded-xl text-sm">
                        <span className="font-bold text-amber-800">{DOMAIN_LABELS[d.domain] || d.domain}:</span>
                        <span className="text-amber-700">{d.rationale_ar || `فجوة ${d.delta} نقطة`}</span>
                        <span className="text-xs text-amber-600 mr-auto">Δ {d.delta}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Strengths */}
              {report.strengths && report.strengths.length > 0 && (
                <div className="border-t border-slate-100 pt-4">
                  <h4 className="text-sm font-bold text-emerald-700 flex items-center gap-2 mb-3">
                    <TrendingUp className="w-4 h-4" />
                    نقاط القوة المرصودة (مجالات النطاق البسيط)
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {report.strengths.map((s: any) => {
                      const domainKey = typeof s === "string" ? s : s.domain;
                      const label = DOMAIN_LABELS[domainKey] || (typeof s === "string" ? s : s.domain_ar || domainKey);
                      return (
                        <span key={domainKey} className="px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-100 text-xs font-bold">
                          {label}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── Section B: LLM-Generated Content ── */}
          <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
            <div className="p-6 border-b border-slate-100 bg-slate-50/50">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-brand-500" />
                ب. المسودة السريرية (قابلة للتعديل)
              </h3>
            </div>
            <div className="p-6 md:p-8 space-y-10">

              {/* 1. Executive Summary */}
              <div>
                <label className="flex items-center gap-2 text-sm font-bold text-slate-700 mb-2">
                  <FileText className="w-4 h-4 text-brand-500" />
                  الملخص السريري السردي للحالة
                </label>
                <textarea
                  rows={5}
                  disabled={isCompleted}
                  value={editedSummary}
                  onChange={(e) => setEditedSummary(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 p-4 text-slate-800 focus:border-brand-500 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500 leading-relaxed"
                  placeholder="الملخص الإكلينيكي للحالة..."
                />
              </div>

              {/* 2. Differential Considerations (read-only, AI insight) */}
              {report.differential_considerations && report.differential_considerations.length > 0 && (
                <div>
                  <h4 className="flex items-center gap-2 text-sm font-bold text-slate-700 mb-3">
                    <GitFork className="w-4 h-4 text-indigo-500" />
                    اعتبارات التشخيص التفريقي
                  </h4>
                  <div className="space-y-2">
                    {report.differential_considerations.map((item: string, idx: number) => (
                      <div key={idx} className="flex items-start gap-3 p-3 bg-indigo-50 border border-indigo-100 rounded-xl text-sm">
                        <Info className="w-4 h-4 text-indigo-500 flex-shrink-0 mt-0.5" />
                        <span className="text-indigo-800 leading-relaxed">{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 3. Suggested Goals */}
              <ListEditor
                label="أهداف الخطة الفردية المقترحة (SMART Goals)"
                icon={<Target className="w-4 h-4 text-brand-500" />}
                items={editedGoals}
                isCompleted={isCompleted}
                placeholder="أدخل هدفًا تدخليًا (Enter للإضافة)..."
                onChange={setEditedGoals}
              />

              {/* 4. Intervention Plan */}
              {report.intervention_plan && Object.keys(report.intervention_plan).length > 0 && (
                <div>
                  <h4 className="flex items-center gap-2 text-sm font-bold text-slate-700 mb-3">
                    <Target className="w-4 h-4 text-brand-500" />
                    خطة التدخل التفصيلية حسب التخصص
                  </h4>
                  <div className="space-y-4">
                    {Object.entries(report.intervention_plan).map(([specialty, steps]: any) => (
                      <div key={specialty} className="border border-slate-100 rounded-xl overflow-hidden">
                        <div className="bg-slate-50 px-4 py-2 border-b border-slate-100">
                          <span className="text-xs font-bold text-slate-600 uppercase tracking-wide">{specialty}</span>
                        </div>
                        <ul className="p-4 space-y-2">
                          {(steps as string[]).map((step: string, i: number) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                              <span className="w-5 h-5 rounded-full bg-brand-50 text-brand-600 font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">{i + 1}</span>
                              {step}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 5. School Accommodations */}
              <ListEditor
                label="التعديلات والتسهيلات المدرسية المقترحة"
                icon={<School className="w-4 h-4 text-blue-500" />}
                items={editedSchoolAccommodations}
                isCompleted={isCompleted}
                placeholder="أدخل تعديلًا مدرسيًا مقترحًا..."
                onChange={setEditedSchoolAccommodations}
              />

              {/* 6. Home Program */}
              <ListEditor
                label="البرنامج المنزلي للأسرة"
                icon={<Home className="w-4 h-4 text-emerald-500" />}
                items={editedHomeProgram}
                isCompleted={isCompleted}
                placeholder="أدخل نشاطًا أو توصية منزلية..."
                onChange={setEditedHomeProgram}
              />

              {/* 7. Strengths Summary */}
              {report.strengths_summary && (
                <div>
                  <label className="flex items-center gap-2 text-sm font-bold text-slate-700 mb-2">
                    <Heart className="w-4 h-4 text-emerald-500" />
                    ملخص نقاط القوة والإمكانات
                  </label>
                  <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4 text-sm text-emerald-800 leading-relaxed">
                    {report.strengths_summary}
                  </div>
                </div>
              )}

              {/* 8. Referrals */}
              <ListEditor
                label="قائمة الإحالات التخصصية المقترحة"
                icon={<FileText className="w-4 h-4 text-slate-500" />}
                items={editedReferrals}
                isCompleted={isCompleted}
                placeholder="أدخل إحالة تخصصية (مثل: أخصائي تخاطب)..."
                onChange={setEditedReferrals}
              />

              {/* 9. Followup Goals */}
              <ListEditor
                label="أهداف المتابعة (3–6 أشهر)"
                icon={<Calendar className="w-4 h-4 text-slate-500" />}
                items={editedFollowupGoals}
                isCompleted={isCompleted}
                placeholder="أدخل هدف متابعة..."
                onChange={setEditedFollowupGoals}
              />

              {/* 10. Caveats */}
              <ListEditor
                label="تحفظات وملاحظات تقنية / سريرية"
                icon={<Info className="w-4 h-4 text-amber-500" />}
                items={editedCaveats}
                isCompleted={isCompleted}
                placeholder="أدخل تحفظًا سريريًا أو محدودية في التقييم..."
                onChange={setEditedCaveats}
              />

            </div>
          </div>

          {/* Legal Disclaimer */}
          <div className="bg-amber-50 border border-amber-200/50 p-5 rounded-2xl">
            <h4 className="text-sm font-bold text-amber-800 mb-2">إقرار منصة أخصائي</h4>
            <p className="text-xs text-amber-700 leading-relaxed">
              هذه المنصة أداة دعم قرار إرشادية للأخصائيين ولا تُستخدم كأداة تشخيص طبي مستقلة.
              أي محتوى مُصاغ بالذكاء الاصطناعي يعتبر مسودة خاضعة للمسؤولية القانونية والمهنية للأخصائي المعتمد.
              تعتمد المنصة مؤشرات أولية فقط — وليس تشخيصات طبية نهائية.
            </p>
          </div>

          {/* Final Action */}
          {report.status !== "approved" ? (
            <div className="flex flex-wrap gap-4">
              <button
                type="button"
                onClick={handleApproveReport}
                disabled={approvingReport}
                className="bg-emerald-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-emerald-600 disabled:opacity-50 transition shadow-md flex items-center gap-2"
              >
                <Check className="w-5 h-5" />
                <span>{approvingReport ? "جاري الاعتماد..." : "اعتماد وحفظ التقرير النهائي"}</span>
              </button>
              <button
                type="button"
                onClick={handleGenerateReport}
                disabled={generatingReport}
                className="border border-brand-500 text-brand-600 font-bold bg-white px-5 py-3 rounded-xl hover:bg-brand-50 transition"
              >
                {generatingReport ? "جاري التوليد..." : "إعادة توليد المسودة (AI)"}
              </button>
            </div>
          ) : (
            <div className="bg-emerald-50 border border-emerald-200 p-5 rounded-2xl flex items-center gap-3 text-emerald-800">
              <Award className="w-6 h-6 flex-shrink-0" />
              <div>
                <h4 className="font-bold">تم اعتماد التقرير بنجاح!</h4>
                <p className="text-xs mt-1 text-emerald-700 font-medium">
                  تم إدراج هذا التقرير كملف رسمي ومعتمد في قاعدة البيانات.
                </p>
              </div>
            </div>
          )}

        </div>
      )}
    </div>
  );
};
export default ClinicianPortal;
