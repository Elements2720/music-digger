import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  message: string | null;
}

/** Keeps one broken workspace from blanking the whole shell. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { message: null };

  static getDerivedStateFromError(error: unknown): State {
    return { message: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("Workspace crashed", error, info.componentStack);
  }

  render() {
    if (this.state.message) {
      return (
        <div className="panel p-5" role="alert">
          <p className="eyebrow text-danger">WORKSPACE ERROR</p>
          <p className="mt-2 font-mono text-sm text-heading">{this.state.message}</p>
          <button
            type="button"
            className="btn mt-4"
            onClick={() => this.setState({ message: null })}
          >
            TRY AGAIN
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
