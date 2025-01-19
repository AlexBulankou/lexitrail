import React from 'react';
import '../styles/Policy.css';

const TermsOfService = () => {
    return (
        <div className="page-wrapper">
            <div className="page-container">
                <div className="text-content">
                    <h1>Terms of Service</h1>
                    <p className="last-updated">Last updated: January 19, 2025</p>

                    <section>
                        <h2>1. Acceptance of Terms</h2>
                        <p>By accessing and using Lexitrail, you accept and agree to be bound by these Terms of Service.</p>
                    </section>

                    <section>
                        <h2>2. Service Description</h2>
                        <p>Lexitrail is a word game application that requires authentication to track user progress and game statistics.</p>
                    </section>

                    <section>
                        <h2>3. User Accounts</h2>
                        <p>To use Lexitrail, you must create an account using authentication services we provide. You are responsible for:</p>
                        <ul>
                            <li>Maintaining the confidentiality of your account</li>
                            <li>All activities that occur under your account</li>
                            <li>Notifying us immediately of any unauthorized use of your account</li>
                        </ul>
                    </section>

                    <section>
                        <h2>4. Data Collection and Privacy</h2>
                        <p>Our collection and use of personal information is governed by our Privacy Policy, which is incorporated into these Terms of Service.</p>
                    </section>

                    <section>
                        <h2>5. Acceptable Use</h2>
                        <p>You agree not to:</p>
                        <ul>
                            <li>Use the service for any unlawful purpose</li>
                            <li>Attempt to gain unauthorized access to any portion of the service</li>
                            <li>Interfere with or disrupt the service</li>
                            <li>Create multiple accounts for malicious purposes</li>
                            <li>Share your account credentials with others</li>
                        </ul>
                    </section>

                    <section>
                        <h2>6. Modifications to Service</h2>
                        <p>We reserve the right to:</p>
                        <ul>
                            <li>Modify or discontinue the service at any time</li>
                            <li>Change these terms of service at any time</li>
                            <li>Refuse service to anyone for any reason</li>
                        </ul>
                    </section>

                    <section>
                        <h2>7. Termination</h2>
                        <p>We may terminate or suspend your account and access to the service immediately, without prior notice, for any reason, including breach of these Terms of Service.</p>
                    </section>

                    <section>
                        <h2>8. Limitation of Liability</h2>
                        <p>The service is provided "as is" without warranties of any kind. We are not liable for any damages arising from your use of the service.</p>
                    </section>

                    <section>
                        <h2>Contact</h2>
                        <p>If you have any questions about these Terms of Service, please contact us at: support@yojowa.com</p>
                    </section>
                </div>
            </div>
        </div>
    );
};

export default TermsOfService;