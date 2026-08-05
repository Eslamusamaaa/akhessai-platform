import React from "react";

interface State { hasError: boolean; message: string }

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error?.message || String(error) };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-8 bg-slate-50">
          <div className="bg-white rounded-2xl border border-red-200 shadow-sm p-8 max-w-lg w-full text-center space-y-4">
            <h2 className="text-xl font-bold text-red-700">حدث خطأ في التطبيق</h2>
            <p className="text-sm text-slate-500 font-mono break-words text-start bg-slate-100 p-3 rounded-xl">
              {this.state.message}
            </p>
            <button
              onClick={() => { this.setState({ hasError: false, message: "" }); window.location.reload(); }}
              className="bg-brand-500 text-white font-bold px-6 py-3 rounded-xl hover:bg-brand-600 transition"
            >
              إعادة تحميل الصفحة
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
