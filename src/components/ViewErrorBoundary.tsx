// Named import: this project's tsconfig has no esModuleInterop, so the default
// `React` import resolves to `any` and a class extending it loses `this.props`.
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { AlertOctagon, RotateCcw } from "lucide-react";

interface Props {
  /** Changing this resets the boundary — pass the active tab so navigating away
   *  from a broken view clears the error instead of trapping the user on it. */
  resetKey?: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Contains a render failure to the current view.
 *
 * Without this, one bad field shape from the API unmounts the entire React tree
 * and the operator sees a blank page with no way back — which is exactly what a
 * mistyped `work_order_summary` did during development.
 */
export class ViewErrorBoundary extends Component<Props, State> {
  // This project ships no @types/react, so `Component` resolves to `any` and the
  // inherited members are invisible to tsc. Declaring the two we use keeps the
  // file type-checked without adding a types package that would surface errors
  // across every existing component at once.
  declare props: Props;
  declare setState: (state: State) => void;

  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ViewErrorBoundary] View crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="bg-white rounded-2xl border border-rose-200 p-8 shadow-xs max-w-2xl">
        <div className="flex items-start space-x-4">
          <div className="w-11 h-11 rounded-2xl bg-rose-50 border border-rose-100 text-rose-600 flex items-center justify-center shrink-0">
            <AlertOctagon className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-slate-900">This view failed to render</h2>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              The rest of the dashboard is still running — switch to another tab, or retry once the
              detection backend returns valid data.
            </p>
            <pre className="mt-4 text-[11px] text-rose-700 bg-rose-50 border border-rose-100 rounded-xl px-3.5 py-2.5 whitespace-pre-wrap break-words font-mono">
              {this.state.error.message}
            </pre>
            <button
              onClick={() => this.setState({ error: null })}
              className="mt-4 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Retry</span>
            </button>
          </div>
        </div>
      </div>
    );
  }
}
