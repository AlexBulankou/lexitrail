/**
 * Regression test for the dead-CSS class mismatch on the policy pages.
 *
 * Bug: PrivacyPolicy and TermsOfService imported styles/Policy.css but rendered
 * the shared classes page-wrapper/page-container, while Policy.css only defines
 * .policy-wrapper/.policy-container (max-width: 800px; margin: 0 auto). None of
 * the imported CSS ever applied, so on desktop the pages rendered full-bleed
 * (~1400px measure on /privacy) or shrink-wrapped (/terms), instead of a
 * centered 800px reading column.
 *
 * jsdom cannot measure rendered boxes, so this pins the class contract from
 * both sides: the components must render the policy-* wrappers, and Policy.css
 * must actually declare them.
 */
import React from 'react';
import { render } from '@testing-library/react';
import fs from 'fs';
import path from 'path';
import PrivacyPolicy from './PrivacyPolicy';
import TermsOfService from './TermsOfService';

const pages = [
  ['PrivacyPolicy', PrivacyPolicy],
  ['TermsOfService', TermsOfService],
];

describe.each(pages)('%s reading column', (name, Component) => {
  test('renders the Policy.css wrapper classes, not the shared page-* classes', () => {
    const { container } = render(<Component />);

    const wrapper = container.querySelector('.policy-wrapper');
    expect(wrapper).not.toBeNull();
    const column = wrapper.querySelector('.policy-container');
    expect(column).not.toBeNull();

    // The old classes made Policy.css dead and handed layout to Home.css/App.css.
    expect(container.querySelector('.page-wrapper')).toBeNull();
    expect(container.querySelector('.page-container')).toBeNull();
  });
});

test('Policy.css declares the classes the policy pages render', () => {
  const css = fs.readFileSync(
    path.join(__dirname, '..', 'styles', 'Policy.css'),
    'utf8'
  );
  expect(css).toMatch(/\.policy-wrapper\s*\{/);
  expect(css).toMatch(/\.policy-container\s*\{/);
  // The reading column itself: capped and centered.
  const containerRule = css.match(/\.policy-container\s*\{[^}]*\}/)[0];
  expect(containerRule).toMatch(/max-width:\s*800px/);
  expect(containerRule).toMatch(/margin:\s*0 auto/);
});
