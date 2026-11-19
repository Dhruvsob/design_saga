import { Component } from "react";
import { isChunkError } from "../lib/chunks";

// Catches a page that fails to render or to load its code, so one broken screen
// shows a way out instead of blanking the whole app. Inside the layout the
// sidebar stays usable; resetKey (the path) clears the error on navigation.
export default class PageErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Page error", error, info?.componentStack);
  }

  componentDidUpdate(prev) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const stale = isChunkError(error);
    return (
      <div className="max-w-lg mx-auto text-center py-24 px-6" role="alert" data-testid="page-error">
        <div className="overline mb-3">{stale ? "NEW VERSION AVAILABLE" : "SOMETHING WENT WRONG"}</div>
        <h1 className="font-display font-bold tracking-tighter text-4xl mb-3">
          {stale ? "Reload to continue." : "This page couldn't open."}
        </h1>
        <p className="text-[var(--ink-2)] mb-6">
          {stale
            ? "The app was updated while this tab was open. Reloading fetches the new version; nothing you saved is lost."
            : "Reload the page to try again. If it keeps happening, tell your administrator which page and what you clicked."}
        </p>
        <div className="flex gap-3 justify-center">
          <button type="button" className="btn-primary" onClick={() => window.location.reload()} data-testid="page-error-reload">
            Reload
          </button>
          {!this.props.bare && (
            <a href="/dashboard" className="btn-ghost">Go to dashboard</a>
          )}
        </div>
      </div>
    );
  }
}
