import React from 'react';

type Props = {
  children: React.ReactNode;
  title?: string;
};

type State = {
  hasError: boolean;
  message: string;
};

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : 'Unknown render error',
    };
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo): void {
    // Keep error visible in console for debugging.
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card" style={{ margin: '16px', borderColor: 'var(--red-dim)' }}>
          <div className="card-header">
            <span className="card-title">{this.props.title || 'This page failed to render'}</span>
          </div>
          <div style={{ color: 'var(--red)', marginBottom: 12 }}>
            {this.state.message || 'Unexpected runtime error'}
          </div>
          <button className="btn btn-topnav btn-sm" onClick={() => window.location.reload()}>
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

