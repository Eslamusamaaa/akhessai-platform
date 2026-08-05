import React from "react";

interface Option {
  label_ar: string;
  points: number;
}

interface Question {
  id: string;
  type: "single_select" | "multi_select" | "likert_1_5" | "free_text" | "file_upload";
  label_ar: string;
  options?: Option[];
}

interface QuestionRendererProps {
  question: Question;
  value: string[];
  onChange: (value: string[]) => void;
}

export const QuestionRenderer: React.FC<QuestionRendererProps> = ({
  question,
  value = [],
  onChange,
}) => {
  const handleSingleSelect = (optionLabel: string) => {
    onChange([optionLabel]);
  };

  const handleMultiSelect = (optionLabel: string) => {
    if (value.includes(optionLabel)) {
      onChange(value.filter((val) => val !== optionLabel));
    } else {
      onChange([...value, optionLabel]);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 md:p-8 transition-all duration-300">
      <h3 className="text-xl font-bold text-slate-900 mb-6 leading-relaxed">
        {question.label_ar}
      </h3>

      {question.type === "single_select" && question.options && (
        <div className="space-y-3">
          {question.options.map((opt, i) => {
            const isSelected = value.includes(opt.label_ar);
            return (
              <button
                key={i}
                type="button"
                onClick={() => handleSingleSelect(opt.label_ar)}
                className={`w-full text-start px-5 py-4 rounded-xl border-2 transition-all duration-200 flex items-center justify-between ${
                  isSelected
                    ? "border-brand-500 bg-brand-50/50 text-brand-900 font-semibold"
                    : "border-slate-100 bg-slate-50/50 text-slate-700 hover:border-brand-200 hover:bg-brand-50/10"
                }`}
              >
                <span>{opt.label_ar}</span>
                <span
                  className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                    isSelected ? "border-brand-500 bg-brand-500" : "border-slate-300 bg-white"
                  }`}
                >
                  {isSelected && <span className="w-2 h-2 rounded-full bg-white" />}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {question.type === "likert_1_5" && question.options && (
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          {question.options.map((opt, i) => {
            const isSelected = value.includes(opt.label_ar);
            return (
              <button
                key={i}
                type="button"
                onClick={() => handleSingleSelect(opt.label_ar)}
                className={`px-4 py-5 rounded-xl border-2 text-center transition-all duration-200 flex flex-col items-center justify-between gap-3 h-full ${
                  isSelected
                    ? "border-brand-500 bg-brand-50/50 text-brand-900 font-semibold shadow-sm"
                    : "border-slate-100 bg-slate-50/50 text-slate-700 hover:border-brand-200 hover:bg-brand-50/10"
                }`}
              >
                <span className="w-8 h-8 rounded-full bg-slate-100 text-slate-700 font-bold flex items-center justify-center text-sm border border-slate-200">
                  {i + 1}
                </span>
                <span className="text-sm font-medium leading-tight">{opt.label_ar}</span>
              </button>
            );
          })}
        </div>
      )}

      {question.type === "multi_select" && question.options && (
        <div className="space-y-3">
          {question.options.map((opt, i) => {
            const isSelected = value.includes(opt.label_ar);
            return (
              <button
                key={i}
                type="button"
                onClick={() => handleMultiSelect(opt.label_ar)}
                className={`w-full text-start px-5 py-4 rounded-xl border-2 transition-all duration-200 flex items-center justify-between ${
                  isSelected
                    ? "border-brand-500 bg-brand-50/50 text-brand-900 font-semibold"
                    : "border-slate-100 bg-slate-50/50 text-slate-700 hover:border-brand-200 hover:bg-brand-50/10"
                }`}
              >
                <span>{opt.label_ar}</span>
                <span
                  className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                    isSelected ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300 bg-white"
                  }`}
                >
                  {isSelected && (
                    <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
                      <path d="M0 11l2-2 5 5L18 3l2 2L7 18z" />
                    </svg>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {question.type === "free_text" && (
        <textarea
          rows={4}
          value={value[0] || ""}
          onChange={(e) => onChange([e.target.value])}
          className="w-full rounded-xl border-2 border-slate-100 bg-slate-50/50 p-4 text-slate-800 focus:border-brand-500 focus:bg-white focus:outline-none transition-all duration-200"
          placeholder="اكتب ملاحظاتك أو التفاصيل الإضافية هنا..."
        />
      )}
    </div>
  );
};
export default QuestionRenderer;
