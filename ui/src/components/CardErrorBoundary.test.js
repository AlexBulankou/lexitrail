/**
 * @jest-environment jsdom
 */
// issue-293: #291/#292's failure mode was total and silent — a dangling
// reference in ONE card blanked the WHOLE app, with no visible surface. The
// AC explicitly asks for a test that MOUNTS a component that throws and
// asserts the fallback renders, not just that CardErrorBoundary exists —
// so this uses @testing-library/react's real DOM render, per-file opted
// into jsdom (the repo's default jest environment is node; WordCard.js
// itself can't render standalone because it pulls in contexts/services, but
// a throwing child needs nothing beyond React itself).
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import CardErrorBoundary from './CardErrorBoundary';

function Bomb({ shouldThrow }) {
  if (shouldThrow) {
    throw new Error('dangling reference, e.g. #291/#292');
  }
  return <div>card content</div>;
}

// React logs the caught error to the console (jsdom's own "not implemented"
// noise aside); silence it here so a passing test doesn't print a scary
// stack trace, without hiding an assertion failure.
let consoleErrorSpy;
beforeEach(() => {
  consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => {
  consoleErrorSpy.mockRestore();
});

describe('CardErrorBoundary', () => {
  test('renders children normally when nothing throws', () => {
    render(
      <CardErrorBoundary>
        <Bomb shouldThrow={false} />
      </CardErrorBoundary>
    );
    expect(screen.getByText('card content')).toBeInTheDocument();
    expect(screen.queryByTestId('card-error-fallback')).not.toBeInTheDocument();
  });

  test('catches a render-time throw and shows a visible fallback, not blank', () => {
    render(
      <CardErrorBoundary>
        <Bomb shouldThrow={true} />
      </CardErrorBoundary>
    );
    expect(screen.getByTestId('card-error-fallback')).toBeInTheDocument();
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    expect(screen.queryByText('card content')).not.toBeInTheDocument();
  });

  test('the fallback offers a way to continue (retry), not a dead end', () => {
    let shouldThrow = true;
    function Flaky() {
      return <Bomb shouldThrow={shouldThrow} />;
    }
    render(
      <CardErrorBoundary>
        <Flaky />
      </CardErrorBoundary>
    );
    expect(screen.getByTestId('card-error-fallback')).toBeInTheDocument();

    // Fix the underlying condition, then use the boundary's own retry
    // affordance — this is the "way to continue/skip" the AC asks for.
    shouldThrow = false;
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));

    expect(screen.getByText('card content')).toBeInTheDocument();
    expect(screen.queryByTestId('card-error-fallback')).not.toBeInTheDocument();
  });

  test('a throw in ONE boundary does not affect a sibling boundary', () => {
    // The whole point of #293: scope the boundary per-card, not per-grid, so
    // one dangling reference degrades one card instead of the session.
    render(
      <div>
        <CardErrorBoundary>
          <Bomb shouldThrow={true} />
        </CardErrorBoundary>
        <CardErrorBoundary>
          <Bomb shouldThrow={false} />
        </CardErrorBoundary>
      </div>
    );
    expect(screen.getByTestId('card-error-fallback')).toBeInTheDocument();
    expect(screen.getByText('card content')).toBeInTheDocument();
  });
});
