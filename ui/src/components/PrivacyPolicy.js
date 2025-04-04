import React from 'react';
import '../styles/Policy.css';

const PrivacyPolicy = () => {
  return (
    <div className="page-wrapper">
      <div className="page-container">
        <div className="text-content">
          <h1>Privacy Policy</h1>
          <p className="last-updated">Last updated: January 19, 2025</p>

          <section>
            <h2>Information We Collect</h2>
            <p>Lexitrail collects and stores:</p>
            <ul>
              <li>Your email address (obtained through authentication)</li>
              <li>Game statistics and performance data, including:
                <ul>
                  <li>Words guessed correctly and incorrectly</li>
                  <li>Game history and statistics</li>
                </ul>
              </li>
            </ul>
          </section>

          <section>
            <h2>How We Use Your Information</h2>
            <p>We use your information to:</p>
            <ul>
              <li>Create and manage your account</li>
              <li>Track your game progress and statistics</li>
              <li>Improve our service</li>
              <li>Communicate with you about your account when necessary</li>
            </ul>
          </section>

          <section>
            <h2>Data Storage and Security</h2>
            <p>We implement appropriate technical and organizational measures to protect your personal information against unauthorized access, alteration, disclosure, or destruction. Your email address and game data are stored securely and are not shared with third parties.</p>
          </section>

          <section>
            <h2>Your Rights</h2>
            <p>You have the right to:</p>
            <ul>
              <li>Access your personal information</li>
              <li>Request correction of your personal information</li>
              <li>Request deletion of your account and associated data</li>
              <li>Withdraw your consent at any time</li>
            </ul>
          </section>

          <section>
            <h2>Changes to This Policy</h2>
            <p>We may update this Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page.</p>
          </section>

          <section>
            <h2>Contact</h2>
            <p>If you have any questions about this Privacy Policy, please contact us at: support@yojowa.com</p>
          </section>
        </div>
      </div>
    </div>
  );
};

export default PrivacyPolicy;