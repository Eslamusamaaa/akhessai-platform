import React, { useState } from "react";
import { LogOut, User as UserIcon, BrainCircuit, Users, GraduationCap, Stethoscope, ShieldCheck } from "lucide-react";
import { Dashboard } from "./pages/Dashboard";
import { AssessmentFlow } from "./pages/AssessmentFlow";
import { ClinicianPortal } from "./pages/ClinicianPortal";
import { ErrorBoundary } from "./components/ErrorBoundary";
import apiFetch from "./apiFetch";

const ROLES = [
  {
    username: "parent",
    password: "parent123",
    label: "ولي الأمر",
    subtitle: "تسجيل الأطفال ومتابعة التقييم",
    icon: Users,
    color: "brand",
    bg: "bg-brand-50",
    border: "border-brand-200",
    iconBg: "bg-brand-500",
    hover: "hover:border-brand-400 hover:bg-brand-50/80",
  },
  {
    username: "teacher",
    password: "teacher123",
    label: "المعلم",
    subtitle: "تعبئة تقييم الطالب في البيئة المدرسية",
    icon: GraduationCap,
    color: "blue",
    bg: "bg-blue-50",
    border: "border-blue-200",
    iconBg: "bg-blue-500",
    hover: "hover:border-blue-400 hover:bg-blue-50/80",
  },
  {
    username: "specialist",
    password: "specialist123",
    label: "الأخصائي",
    subtitle: "الملاحظة السريرية ومراجعة التقارير",
    icon: Stethoscope,
    color: "amber",
    bg: "bg-amber-50",
    border: "border-amber-200",
    iconBg: "bg-amber-500",
    hover: "hover:border-amber-400 hover:bg-amber-50/80",
  },
  {
    username: "admin",
    password: "admin123",
    label: "مدير النظام",
    subtitle: "الإشراف الكامل وسجل التدقيق الأمني",
    icon: ShieldCheck,
    color: "emerald",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    iconBg: "bg-emerald-500",
    hover: "hover:border-emerald-400 hover:bg-emerald-50/80",
  },
];

export const App: React.FC = () => {
  const [token, setToken] = useState<string | null>(sessionStorage.getItem("token"));
  const [role, setRole] = useState<string>(sessionStorage.getItem("role") || "");
  const [userEmail, setUserEmail] = useState<string>(sessionStorage.getItem("userEmail") || "");
  const [loadingRole, setLoadingRole] = useState<string | null>(null);

  const [page, setPage] = useState<"dashboard" | "assessment_flow" | "clinician_portal">("dashboard");
  const [activeSessionId, setActiveSessionId] = useState<string>("");

  const handleRoleSelect = async (username: string, password: string) => {
    setLoadingRole(username);
    try {
      const res = await apiFetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: username, password }),
      });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        setRole(data.role);
        setUserEmail(data.username);
        sessionStorage.setItem("token", data.access_token);
        sessionStorage.setItem("role", data.role);
        sessionStorage.setItem("userEmail", data.username);
        setPage("dashboard");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingRole(null);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setRole("");
    setUserEmail("");
    sessionStorage.clear();
  };

  const startSessionFlow = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setPage("assessment_flow");
  };

  const openClinicianPortal = (sessionId: string) => {
    setActiveSessionId(sessionId);
    setPage("clinician_portal");
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-100 via-brand-50/20 to-slate-200 flex flex-col items-center justify-center p-6">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-brand-500 rounded-2xl shadow-lg mb-4">
            <BrainCircuit className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 mb-1">منصة أخصائي</h1>
          <p className="text-slate-500 font-medium">منصة التقييم التخصصي والتدخل المبكر</p>
        </div>

        {/* Role Cards */}
        <div className="w-full max-w-3xl">
          <p className="text-center text-slate-500 font-semibold mb-6 text-sm">اختر دورك للدخول مباشرةً</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {ROLES.map((r) => {
              const Icon = r.icon;
              const isLoading = loadingRole === r.username;
              return (
                <button
                  key={r.username}
                  onClick={() => handleRoleSelect(r.username, r.password)}
                  disabled={loadingRole !== null}
                  className={`
                    relative flex items-center gap-4 p-5 rounded-2xl border-2 bg-white text-right
                    transition-all duration-200 shadow-sm
                    ${r.hover} ${r.border}
                    disabled:opacity-60 disabled:cursor-not-allowed
                    ${isLoading ? "scale-95" : "hover:shadow-md hover:-translate-y-0.5"}
                  `}
                >
                  <div className={`shrink-0 w-12 h-12 ${r.iconBg} rounded-xl flex items-center justify-center shadow`}>
                    {isLoading ? (
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Icon className="w-6 h-6 text-white" />
                    )}
                  </div>
                  <div className="flex-1 text-right">
                    <p className="text-base font-extrabold text-slate-900">{r.label}</p>
                    <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{r.subtitle}</p>
                  </div>
                  {!isLoading && (
                    <div className="text-slate-300 text-lg">›</div>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <p className="mt-10 text-xs text-slate-400">© {new Date().getFullYear()} منصة أخصائي للتقييم والتأهيل الفردي</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50/50 flex flex-col">
      <nav className="bg-white border-b border-slate-200 shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-3">
              <span className="bg-brand-500 text-white p-2 rounded-xl">
                <BrainCircuit className="w-6 h-6" />
              </span>
              <span className="text-xl font-extrabold text-slate-900 tracking-tight">منصة أخصائي</span>
            </div>

            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 bg-slate-50 border border-slate-200/60 px-3 py-1.5 rounded-xl">
                <UserIcon className="w-4 h-4 text-brand-600" />
                <span className="text-sm font-bold text-slate-700">{userEmail}</span>
                <span className="text-xs bg-brand-100 text-brand-800 font-semibold px-2 py-0.5 rounded">
                  {role === "parent" ? "ولي أمر" :
                   role === "specialist" ? "أخصائي" :
                   role === "teacher" ? "معلم" :
                   role === "admin" ? "مدير النظام" : role}
                </span>
              </div>

              <button
                onClick={handleLogout}
                className="p-2 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition"
                title="العودة لاختيار الدور"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="flex-1">
        <ErrorBoundary>
          {page === "dashboard" && (
            <Dashboard
              role={role}
              onStartSession={startSessionFlow}
              onOpenClinicianSession={openClinicianPortal}
              token={token}
            />
          )}
          {page === "assessment_flow" && (
            <AssessmentFlow
              sessionId={activeSessionId}
              onBackToDashboard={() => setPage("dashboard")}
              token={token}
            />
          )}
          {page === "clinician_portal" && (
            <ClinicianPortal
              sessionId={activeSessionId}
              onBackToDashboard={() => setPage("dashboard")}
              token={token}
            />
          )}
        </ErrorBoundary>
      </main>

      <footer className="bg-white border-t border-slate-200 py-6 text-center text-xs text-slate-400 font-medium">
        <span>© {new Date().getFullYear()} منصة أخصائي للتقييم والتأهيل الفردي.</span>
      </footer>
    </div>
  );
};
export default App;
