import { AlertTriangle } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "./ui";

interface Props {
  children: ReactNode;
  resetKey?: string;
}
interface State {
  error: Error | null;
}

/** Keeps a rendering bug on one page from blanking the whole application. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-lg py-16 text-center">
        <AlertTriangle className="mx-auto h-8 w-8 text-amber-500" />
        <h1 className="mt-3 text-lg font-semibold">This page could not be displayed</h1>
        <p className="mt-1 text-sm text-muted">An unexpected error occurred. Your data has not been changed.</p>
        <Button className="mt-5" onClick={() => this.setState({ error: null })}>
          Try again
        </Button>
      </div>
    );
  }
}
