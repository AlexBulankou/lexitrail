import React from 'react';

const About = () => {
  return (
    <div className="page-wrapper">
      <div className="page-container">
        <div className="text-content">
          <h1>About Lexitrail</h1>

          <div className="cta-button-container">
            <a
              href="https://github.com/AlexBulankou/lexitrail"
              target="_blank"
              rel="noopener noreferrer"
              className="cta-button"
            >
              🌟 Contribute on GitHub 🌟
            </a>
          </div>

          <section>
            <h2>Our Mission</h2>
            <p>
              At Lexitrail, we’re on a quest to revolutionize Chinese language learning through 
              state-of-the-art technology. By combining natural language processing, interactive 
              learning methodologies, and modern software design, we strive to make mastering 
              Chinese both accessible and stimulating for learners everywhere.
            </p>
            <p>
              Whether you’re deciphering your first characters or polishing advanced reading 
              comprehension, Lexitrail offers an adaptive platform that evolves with your progress.
            </p>
          </section>

          <section>
            <h2>Technology Stack</h2>
            <p>
              To bring you a seamless learning experience, we leverage cutting-edge tools and 
              best practices in software engineering:
            </p>
            <ul>
              <li>
                <strong>React Frontend:</strong> Our interactive, single-page application 
                is powered by React, ensuring a responsive interface that feels natural 
                and lightning-fast.
              </li>
              <li>
                <strong>AI-Driven Backend:</strong> Advanced NLP and machine learning models 
                deployed on Kubernetes handle real-time vocabulary analysis and personalized 
                practice recommendations.
              </li>
              <li>
                <strong>Cloud-Native Infrastructure:</strong> Hosted on Google Cloud 
                Platform (GCP) for scalable, secure, and globally distributed services.
              </li>
              <li>
                <strong>Continuous Integration & Deployment:</strong> Automated pipelines 
                ensure every update is tested, verified, and deployed with minimal downtime 
                or user interruption.
              </li>
            </ul>
          </section>

          <section>
            <h2>Open Source Collaboration</h2>
            <p>
              Lexitrail is proudly open source. We thrive on community feedback and contributions, 
              believing that collective innovation drives better technology. Our goal is to make 
              the codebase accessible and welcoming to developers of all backgrounds and skill levels.
            </p>
            <p>
              From refining user experience to enhancing AI models, your pull requests, bug reports, 
              and feature ideas help shape the future of Lexitrail.
            </p>
          </section>

          <div className="cta-button-container">
            <a
              href="https://github.com/AlexBulankou/lexitrail"
              target="_blank"
              rel="noopener noreferrer"
              className="cta-button"
            >
              🌟 Contribute on GitHub 🌟
            </a>
          </div>

        </div>
      </div>
    </div>
  );
};

export default About;
