import React from 'react';
import '../styles/CardErrorBoundary.css';

// issue-293: #291/#292 was a dangling-reference typo in WordCard that took
// the ENTIRE render tree to a blank white screen — no console-visible surface
// for a user, total and silent. This boundary is scoped per-card (wraps ONE
// WordCard/MiniWordCard, not the whole grid) so the next orphaned-reference-
// shaped bug degrades one card instead of the session.
class CardErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('CardErrorBoundary caught a card render error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card-error-fallback" data-testid="card-error-fallback">
          <p>This card failed to load.</p>
          <button
            className="card-error-retry"
            onClick={() => this.setState({ hasError: false })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default CardErrorBoundary;
