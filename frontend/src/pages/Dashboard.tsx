import React, { useState, useEffect } from "react";
import { Plus, Baby as ChildIcon, ClipboardList, Award, Users, ArrowLeft, RefreshCw, Shield } from "lucide-react";
import apiFetch from "../apiFetch";

interface Child {
  id: string;
  name: string;
  dob: string;
  gender: string;
  nationality?: string;
  school?: string;
  grade?: string;
  parent_contact?: string;
}

interface Session {
  id: string;
  child_id: string;
  child_name: string;
  age_band: string;
  status: string;
  current_informant: string;
  onboarding_specialties: string[];
  active_specialties: string[];
  responses_count: number;
}

interface AuditLog {
  id: string;
  timestamp: string;
  user_id: string;
  action: string;
  child_id: string;
  details: any;
}


interface DashboardProps {
  role: string;
  onStartSession: (sessionId: string) => void;
  onOpenClinicianSession: (sessionId: string) => void;
  token: string;
}

export const Dashboard: React.FC<DashboardProps> = ({
  role,
  onStartSession,
  onOpenClinicianSession,
  token,
}) => {
  const [children, setChildren] = useState<Child[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegForm, setShowRegForm] = useState(false);

  // Form State
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState("male");
  const [nationality, setNationality] = useState("");
  const [school, setSchool] = useState("");
  const [grade, setGrade] = useState("");
  const [contact, setContact] = useState("");
  const [selectedSpecs, setSelectedSpecs] = useState<string[]>([]);
  const [formSubmitting, setFormSubmitting] = useState(false);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      // Fetch children
      const chRes = await apiFetch("/children", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (chRes.ok) setChildren(await chRes.json());

      const sessRes = await apiFetch("/sessions", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (sessRes.ok) setSessions(await sessRes.json());

      if (role === "admin") {
        const logsRes = await apiFetch("/audit-logs", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (logsRes.ok) setAuditLogs(await logsRes.json());
      }
    } catch (e) {
      console.error("Error loading dashboard data:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [role, token]);

  const handleSpecToggle = (spec: string) => {
    if (selectedSpecs.includes(spec)) {
      setSelectedSpecs(selectedSpecs.filter((s) => s !== spec));
    } else {
      setSelectedSpecs([...selectedSpecs, spec]);
    }
  };

  const handleRegisterChild = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !dob || selectedSpecs.length === 0) {
      alert("يرجى ملء الاسم الكامل وتاريخ الميلاد واختيار تخصص واحد على الأقل.");
      return;
    }
    setFormSubmitting(true);
    try {
      const res = await apiFetch("/children", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name,
          dob,
          gender,
          nationality,
          school,
          grade,
          parent_contact: contact,
        }),
      });

      if (res.ok) {
        const childData = await res.json();
        const childId = childData.id;

        // Now initiate assessment session for this child
        const sessRes = await apiFetch("/sessions", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            child_id: childId,
            onboarding_specialties: selectedSpecs,
          }),
        });

        if (sessRes.ok) {
          const sessData = await sessRes.ok ? await sessRes.json() : null;
          alert("تم تسجيل الطفل وبدء جلسة التقييم بنجاح!");
          setShowRegForm(false);
          // Clear inputs
          setName("");
          setDob("");
          setNationality("");
          setSchool("");
          setGrade("");
          setContact("");
          setSelectedSpecs([]);
          fetchDashboardData();
        }
      }
    } catch (err) {
      console.error(err);
      alert("حدث خطأ أثناء الاتصال بالخادم.");
    } finally {
      setFormSubmitting(false);
    }
  };

  // Helper to resolve status badges
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "onboarding":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-700">التهيئة المبدئية</span>;
      case "core_screener":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700">الفحص الأساسي الجاري</span>;
      case "specialized_screening":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-indigo-50 text-indigo-700">استقصاء تخصصي</span>;
      case "clinical_observation":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-amber-50 text-amber-700 border border-amber-200">بانتظار الملاحظة السريرية</span>;
      case "drafting":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-pink-50 text-pink-700 border border-pink-200">بانتظار مراجعة مسودة الذكاء الاصطناعي</span>;
      case "completed":
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800">مكتمل ومعتمد</span>;
      default:
        return <span className="px-3 py-1 text-xs font-semibold rounded-full bg-slate-100 text-slate-700">{status}</span>;
    }
  };

  const getStatusStepNum = (status: string) => {
    switch (status) {
      case "onboarding": return 1;
      case "core_screener": return 2;
      case "specialized_screening": return 3;
      case "clinical_observation": return 4;
      case "drafting": return 5;
      case "completed": return 6;
      default: return 1;
    }
  };

  // Use real sessions fetched from the backend API
  const activeSessions: Session[] = sessions;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      
      {/* Header Section */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight mb-2">
            {role === "parent" ? "لوحة متابعة ولي الأمر" : role === "teacher" ? "لوحة متابعة المعلم" : "منصة التقييم السريري ودعم القرار"}
          </h1>
          <p className="text-slate-500 font-medium">
            {role === "parent"
              ? "مرحبًا بك. يمكنك فحص طفلك ومتابعة الخطط العلاجية المقترحة بكل يسر وبساطة."
              : role === "teacher"
              ? "مرحبًا بك زميلنا المعلم. يمكنك تعبئة تقييمك للطالب والمساهمة في الفحص الشامل."
              : "مرحبًا بك زميلنا الأخصائي. المنصة تمكنك من جمع البيانات المتعددة والتحكم في تقارير الدعم."}
          </p>
        </div>
        
        {role === "parent" && (
          <button
            onClick={() => setShowRegForm(true)}
            className="inline-flex items-center gap-2 bg-brand-500 text-white font-bold px-5 py-3 rounded-xl shadow-md hover:bg-brand-600 transition-all duration-200"
          >
            <Plus className="w-5 h-5" />
            <span>تسجيل طفل جديد</span>
          </button>
        )}
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <div className="bg-white border border-slate-100 p-6 rounded-2xl shadow-sm flex items-center gap-4">
          <div className="p-3 bg-brand-50 rounded-xl text-brand-500">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <span className="text-sm font-medium text-slate-400 block mb-0.5">إجمالي الأطفال المسجلين</span>
            <span className="text-2xl font-bold text-slate-900">{children.length}</span>
          </div>
        </div>
        <div className="bg-white border border-slate-100 p-6 rounded-2xl shadow-sm flex items-center gap-4">
          <div className="p-3 bg-blue-50 rounded-xl text-blue-500">
            <ClipboardList className="w-6 h-6" />
          </div>
          <div>
            <span className="text-sm font-medium text-slate-400 block mb-0.5">التقييمات النشطة جاري العمل عليها</span>
            <span className="text-2xl font-bold text-slate-900">
              {activeSessions.filter(s => s.status !== "completed").length}
            </span>
          </div>
        </div>
        <div className="bg-white border border-slate-100 p-6 rounded-2xl shadow-sm flex items-center gap-4">
          <div className="p-3 bg-emerald-50 rounded-xl text-emerald-500">
            <Award className="w-6 h-6" />
          </div>
          <div>
            <span className="text-sm font-medium text-slate-400 block mb-0.5">التقارير المعتمدة نهائيًا</span>
            <span className="text-2xl font-bold text-slate-900">
              {activeSessions.filter(s => s.status === "completed").length}
            </span>
          </div>
        </div>
      </div>

      {/* Main Panel grid */}
      <div className="grid grid-cols-1 gap-8">
        
        {/* Child Onboarding Dialog / Form */}
        {showRegForm && (
          <div className="bg-white rounded-2xl border-2 border-brand-200 p-6 md:p-8 shadow-md mb-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                <ChildIcon className="w-6 h-6 text-brand-500" />
                <span>تسجيل طفل جديد وبدء الفحص المبدئي</span>
              </h3>
              <button
                onClick={() => setShowRegForm(false)}
                className="p-2 text-slate-400 hover:text-slate-600 rounded-lg"
              >
                إغلاق
              </button>
            </div>
            
            <form onSubmit={handleRegisterChild} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">اسم الطفل بالكامل</label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                    placeholder="مثال: ياسر محمد أحمد"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">تاريخ الميلاد</label>
                  <input
                    type="date"
                    required
                    value={dob}
                    onChange={(e) => setDob(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">الجنس</label>
                  <select
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                  >
                    <option value="male">ذكر</option>
                    <option value="female">أنثى</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">الجنسية</label>
                  <input
                    type="text"
                    value={nationality}
                    onChange={(e) => setNationality(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                    placeholder="مثال: سعودي"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">رقم جوال ولي الأمر</label>
                  <input
                    type="tel"
                    value={contact}
                    onChange={(e) => setContact(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                    placeholder="مثال: +966500000000"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">اسم الروضة / المدرسة</label>
                  <input
                    type="text"
                    value={school}
                    onChange={(e) => setSchool(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                    placeholder="اسم المدرسة الحالية"
                  />
                </div>
                <div>
                  <label className="block text-sm font-bold text-slate-700 mb-2">الصف الدراسي</label>
                  <input
                    type="text"
                    value={grade}
                    onChange={(e) => setGrade(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-slate-800 focus:border-brand-500 focus:outline-none"
                    placeholder="الصف الدراسي للطفل"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-700 mb-3">
                  تحديد التخصصات المطلوبة للفحص (متعدد الخيارات)
                </label>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                  {[
                    { id: "autism", name: "اضطراب طيف التوحد" },
                    { id: "adhd", name: "فرط الحركة وتشتت الانتباه" },
                    { id: "speech_language", name: "تأخر النطق واللغة" },
                    { id: "learning_disabilities", name: "صعوبات التعلم" },
                    { id: "sensory_processing", name: "التكامل الحسي" },
                    { id: "behavior_emotional", name: "تعديل السلوك" },
                  ].map((spec) => {
                    const isSelected = selectedSpecs.includes(spec.id);
                    return (
                      <button
                        key={spec.id}
                        type="button"
                        onClick={() => handleSpecToggle(spec.id)}
                        className={`px-4 py-3 rounded-xl border-2 text-start transition-all duration-200 ${
                          isSelected
                            ? "border-brand-500 bg-brand-50/50 text-brand-900 font-bold"
                            : "border-slate-100 bg-slate-50 text-slate-700 hover:border-slate-200"
                        }`}
                      >
                        {spec.name}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex gap-4">
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="bg-brand-500 text-white px-6 py-3 rounded-xl font-bold shadow hover:bg-brand-600 transition disabled:opacity-50"
                >
                  {formSubmitting ? "جاري الحفظ..." : "تسجيل الطفل والبدء"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowRegForm(false)}
                  className="border border-slate-200 text-slate-600 px-6 py-3 rounded-xl font-bold hover:bg-slate-50"
                >
                  إلغاء
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Dashboard Grid Content */}
        <div className="bg-white border border-slate-100 rounded-2xl shadow-sm overflow-hidden">
          <div className="p-6 border-b border-slate-100 flex items-center justify-between">
            <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <ClipboardList className="w-5 h-5 text-brand-500" />
              <span>{role === "parent" ? "حالة تقييم أطفالي" : "قائمة الحالات وسير العمل السريري"}</span>
            </h3>
            
            <button 
              onClick={fetchDashboardData}
              className="p-2 text-slate-400 hover:text-slate-600 rounded-lg"
              title="تحديث البيانات"
            >
              <RefreshCw className="w-5 h-5" />
            </button>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400">
              <div className="w-8 h-8 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
              <span>جاري تحميل بيانات لوحة التحكم...</span>
            </div>
          ) : activeSessions.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <span>لا توجد حالات مسجلة حاليًا في النظام. سجل طفلاً للبدء.</span>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {activeSessions.map((session) => (
                <div key={session.id} className="p-6 hover:bg-slate-50/50 transition duration-150">
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
                    
                    {/* Left: Child Details */}
                    <div>
                      <div className="flex items-center gap-3 mb-2">
                        <span className="w-10 h-10 rounded-full bg-brand-50 text-brand-600 font-bold flex items-center justify-center text-lg">
                          {session.child_name.charAt(0)}
                        </span>
                        <div>
                          <h4 className="text-lg font-bold text-slate-900">{session.child_name}</h4>
                          <span className="text-xs text-slate-400 font-medium">
                            الفئة العمرية: {session.age_band === "0-6" ? "الطفولة المبكرة (0-6 سنوات)" : "المدرسة والمراهقة (6-18 سنة)"}
                          </span>
                        </div>
                      </div>
                      
                      <div className="flex flex-wrap gap-2 mt-3">
                        {session.onboarding_specialties.map((spec) => (
                          <span key={spec} className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-100 text-slate-500">
                            {spec === "autism" && "توحد"}
                            {spec === "adhd" && "فرط حركة وتشتت انتباه"}
                            {spec === "speech_language" && "تخاطب ولغة"}
                            {spec === "learning_disabilities" && "صعوبات تعلم"}
                            {spec === "sensory_processing" && "تكامل حسي"}
                            {spec === "behavior_emotional" && "تعديل سلوك"}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Middle: Progress Steps Tracker */}
                    <div className="flex-1 max-w-md">
                      <div className="flex justify-between text-xs text-slate-400 mb-1.5 font-bold">
                        <span>مسار التقييم التفاعلي</span>
                        <span>الخطوة {getStatusStepNum(session.status)} من 6</span>
                      </div>
                      
                      <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden flex flex-row-reverse">
                        <div 
                          className="bg-brand-500 h-full rounded-full transition-all duration-300"
                          style={{ width: `${(getStatusStepNum(session.status) / 6) * 100}%` }}
                        />
                      </div>
                      
                      <div className="flex justify-between items-center mt-2">
                        {renderStatusBadge(session.status)}
                        <span className="text-xs text-slate-500">
                          المجيب النشط: {
                            session.current_informant === "parent" ? "ولي الأمر (الوالد)" :
                            session.current_informant === "teacher" ? "معلم الفصل" : "الأخصائي المعالج"
                          }
                        </span>
                      </div>
                    </div>

                    {/* Right: Actions */}
                    <div className="flex items-center gap-3">
                      {role === "parent" ? (
                        session.status === "completed" ? (
                          <button 
                            onClick={() => onOpenClinicianSession(session.id)}
                            className="bg-emerald-500 text-white font-bold px-4 py-2.5 rounded-xl shadow-sm hover:bg-emerald-600 transition text-sm"
                          >
                            عرض التقرير المعتمد
                          </button>
                        ) : session.current_informant === "parent" ? (
                          <button
                            onClick={() => onStartSession(session.id)}
                            className="bg-brand-500 text-white font-bold px-5 py-2.5 rounded-xl shadow-sm hover:bg-brand-600 transition text-sm"
                          >
                            استكمال إجابات ولي الأمر
                          </button>
                        ) : (
                          <span className="text-xs text-slate-400 font-bold bg-slate-50 px-3 py-2 rounded-lg border border-slate-100">
                            بانتظار إجابات المدرسة / الأخصائي المعالج
                          </span>
                        )
                      ) : (
                        // Specialist & Admin UI
                        session.status === "clinical_observation" ? (
                          <button
                            onClick={() => onOpenClinicianSession(session.id)}
                            className="bg-amber-500 text-white font-bold px-4 py-2.5 rounded-xl shadow-sm hover:bg-amber-600 transition text-sm"
                          >
                            تعبئة الملاحظة السريرية
                          </button>
                        ) : session.status === "drafting" ? (
                          <button
                            onClick={() => onOpenClinicianSession(session.id)}
                            className="bg-brand-500 text-white font-bold px-4 py-2.5 rounded-xl shadow-sm hover:bg-brand-600 transition text-sm"
                          >
                            مراجعة مسودة التقرير (AI)
                          </button>
                        ) : session.status === "completed" ? (
                          <button
                            onClick={() => onOpenClinicianSession(session.id)}
                            className="bg-emerald-500 text-white font-bold px-4 py-2.5 rounded-xl shadow-sm hover:bg-emerald-600 transition text-sm"
                          >
                            عرض التقرير المعتمد
                          </button>
                        ) : (
                          <button
                            onClick={() => onStartSession(session.id)}
                            className="border border-brand-500 text-brand-600 font-bold px-4 py-2.5 rounded-xl hover:bg-brand-50 transition text-sm"
                          >
                            استعراض كـ {session.current_informant === "parent" ? "ولي أمر" : "معلم"}
                          </button>
                        )
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Security Audit Trail Panel for Admin */}
        {role === "admin" && (
          <div className="bg-white border border-slate-100 rounded-2xl shadow-sm p-6 mt-6">
            <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2 mb-6">
              <Shield className="w-5 h-5 text-red-500" />
              <span>سجل التدقيق الأمني وحماية خصوصية بيانات المرضى (Audit Trail)</span>
            </h3>
            
            <div className="overflow-x-auto">
              <table className="w-full text-start text-sm text-slate-600">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-400 font-bold text-right">
                    <th className="pb-3 text-right">الوقت والتاريخ</th>
                    <th className="pb-3 text-right">العملية / الإجراء</th>
                    <th className="pb-3 text-right">معرف الطفل</th>
                    <th className="pb-3 text-right">تفاصيل تقنية (لا تحتوي على بيانات ملموسة PHI)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-6 text-center text-slate-400">
                        لا توجد سجلات أمنية حاليًا. قم بتسجيل طفل أو توليد تقرير لإصدار السجلات.
                      </td>
                    </tr>
                  ) : (
                    auditLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50/50">
                        <td className="py-3 font-medium text-slate-500">{new Date(log.timestamp).toLocaleString("ar")}</td>
                        <td className="py-3 font-bold text-slate-900">
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            log.action === "GENERATE_LLM_DRAFT" ? "bg-pink-100 text-pink-700" :
                            log.action === "APPROVE_REPORT" ? "bg-emerald-100 text-emerald-700" :
                            log.action === "CHILD_CREATE" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-700"
                          }`}>
                            {log.action}
                          </span>
                        </td>
                        <td className="py-3 font-mono text-xs">{log.child_id ? `CHILD_${log.child_id.substring(0, 8)}` : "N/A"}</td>
                        <td className="py-3 font-mono text-xs text-slate-400">{JSON.stringify(log.details)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
export default Dashboard;
