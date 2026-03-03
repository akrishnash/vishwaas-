import React from 'react';

/**
 * Simple error boundary for dashboard pages.
 */
export class ErrorBoundary extends React.Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{ margin: '1.5rem' }}>
          <h3 style={{ color: 'var(--danger)' }}>Something went wrong</h3>
          <pre style={{ fontSize: '0.8rem', color: 'var(--text-muted)', overflow: 'auto' }}>
            {this.state.error?.message}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
