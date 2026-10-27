Inkloom AI 🌿

AI-Powered Brand Governance and Content Compliance Platform

Inkloom AI is a web-based content review platform that helps teams check whether their written content follows approved brand guidelines. It identifies potentially restricted terms, missing required phrases, exaggerated claims, inconsistent brand naming, and other content issues before publication.


«Note: The website link will work once the application has been successfully deployed on Render.»

🎯 Problem Statement

Organizations need to maintain a consistent brand voice and follow content guidelines across marketing messages, advertisements, and other written communications. Manually checking every piece of content can be time-consuming and may lead to missed issues.

Inkloom AI provides a simple interface to review content against configurable brand rules and help reviewers make informed decisions.

✨ Key Features

- Content Analysis: Enter or paste text for review.
- Brand Guidelines Management: Configure the brand name, tone, approved terms, forbidden terms, required phrases, and brand facts.
- Issue Detection: Identify restricted words, missing phrases, exaggerated claims, suspicious links, excessive punctuation, and other potential issues.
- Compliance Score: Display a rule-based score to indicate how closely content follows the configured guidelines.
- Suggestions and Findings: Show detected issues to help improve the content.
- Human Review Workflow: Approve content, reject it, or request changes, with an optional reviewer note.
- Review History: View previously analyzed content and its review decisions.
- Responsive Interface: Designed for use on desktop and mobile screens.

🛠️ Technology Stack

- Frontend: HTML5, CSS3, JavaScript
- Backend: Python and Flask
- Database: SQLite
- Deployment: Render
- Source Code Management: GitHub

⚙️ How It Works

1. The user enters or uploads content for review.
2. The application checks the content against the configured brand guidelines.
3. The system identifies possible issues and calculates a rule-based compliance score.
4. The user reviews the findings and suggestions.
5. A reviewer approves the content, rejects it, or requests changes.
6. The review is saved for future reference.

📁 Project Structure

InkloomAI/
├── app.py
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js
└── README.md

💻 Run the Project Locally

Prerequisites

- Python 3.10 or later
- pip package manager

Installation

1. Clone the repository:

git clone https://github.com/mondepurva17-prog/InkloomAI.git

2. Open the project folder:

cd InkloomAI

3. Install the required packages:

pip install -r requirements.txt

4. Start the Flask application:

python app.py

5. Open the following address in your browser:

http://127.0.0.1:5000

For deployment with Gunicorn, make sure "gunicorn" is included in "requirements.txt" and use the start command configured in Render.

🧪 Testing

The application can be tested using:

- Normal content that follows the configured guidelines.
- Content containing forbidden terms.
- Content missing required phrases.
- Content containing exaggerated claims or suspicious links.
- Different reviewer decisions.
- Saving and retrieving brand guidelines and review history.

Expected findings depend on the rules configured by the user. The compliance score is a rule-based indicator, not a probability that content is fraudulent or unsafe.

🔮 Future Improvements

1. Integrate a trained AI or language model to provide more context-aware content analysis.
2. Add user authentication, team roles, and collaborative review workflows.
3. Support more document formats and provide detailed compliance reports.
4. Add multilingual content checking.
5. Improve accessibility and mobile usability.

👥 Team

Team Name: Apex Triad

Team Members:

- Purva
- Kasturi
- Janavi

Institution: NMIET, Talegaon

📌 Project Purpose

Inkloom AI aims to make brand-content review more consistent, understandable, and efficient by combining configurable rules, clear findings, and human decision-making.

---

Developed as part of CodeStar 3.0.