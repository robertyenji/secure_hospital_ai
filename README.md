# 🏥 SecureHospital AI

<div align="center">

![SecureHospital AI](https://img.shields.io/badge/SecureHospital-AI-blue?style=for-the-badge&logo=hospital)
![Python](https://img.shields.io/badge/Python-3.11+-green?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-4.2-darkgreen?style=for-the-badge&logo=django)
![HIPAA](https://img.shields.io/badge/HIPAA-Compliant-red?style=for-the-badge)

**Enterprise-grade HIPAA-compliant AI integration for healthcare systems**

[Live Demo](https://secure-hospital-ai.vercel.app) • [Documentation](https://secure-hospital-ai.vercel.app/docs/) • [API Reference](https://secure-hospital-ai.vercel.app/api-reference/)

</div>

---

## 🎯 Overview

SecureHospital AI demonstrates how to safely integrate Large Language Models (LLMs) with sensitive healthcare data while maintaining strict HIPAA compliance. This project showcases a **three-layer security architecture** that can be adapted for any enterprise AI deployment.

### The Problem

Healthcare organizations want to leverage AI assistants but face critical challenges:
- How do you let AI access patient data without violating HIPAA?
- How do you enforce role-based access when AI can theoretically access anything?
- How do you maintain audit trails for AI-assisted data access?

### The Solution

SecureHospital AI implements a **defense-in-depth** approach with three security layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Django Frontend                                        │
│  • Session authentication                                        │
│  • Role verification                                             │
│  • Pre-flight permission check                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: LLM Handler                                            │
│  • Role-aware system prompts                                     │
│  • Tool filtering by permission                                  │
│  • Response sanitization                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: MCP Server                                             │
│  • JWT token validation                                          │
│  • Final RBAC enforcement                                        │
│  • PHI-level redaction                                           │
│  • Complete audit logging                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATABASE (PHI)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🔐 Security & Compliance
- **Three-layer RBAC enforcement** - No single point of failure
- **PHI data redaction** - Automatic masking based on user role
- **Complete audit logging** - Every data access is logged
- **JWT authentication** - Secure token-based API access

### 🤖 AI Integration
- **OpenAI GPT-4o integration** - Natural language medical queries
- **Model Context Protocol (MCP)** - Standardized tool interface
- **Streaming responses** - Real-time SSE chat interface
- **Role-aware prompting** - AI knows user's access level

### 👥 Role-Based Access Control

| Role | Patient Data | Medical Records | PHI Access | Scheduling |
|------|--------------|-----------------|------------|------------|
| **Admin** | ✅ Full | ✅ Full | ✅ Full | ✅ All Staff |
| **Doctor** | ✅ Full | ✅ Full | ✅ Full | Own Only |
| **Nurse** | ✅ Full | ✅ Full | ⚠️ Redacted | Own Only |
| **Auditor** | ✅ Read | ✅ Read | ✅ Read | ✅ All (Read) |
| **Reception** | Basic Only | ❌ No | ❌ No | Own Only |
| **Billing** | Demographics | ❌ No | 💳 Insurance Only | Own Only |

---

## 🛠️ Tech Stack

- **Backend**: Django 4.2, Django REST Framework
- **Database**: PostgreSQL (Supabase)
- **AI**: OpenAI GPT-4o, Model Context Protocol
- **Frontend**: Bootstrap 5, Server-Sent Events
- **Deployment**: Vercel (Serverless)
- **Authentication**: JWT (SimpleJWT)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL (or Supabase account)
- OpenAI API key

### Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/secure-hospital-ai.git
cd secure-hospital-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Run migrations
python manage.py migrate

# Start the server
python manage.py runserver

# In a separate terminal, start MCP server
cd mcp_server
uvicorn main:app --port 9000 --reload
```

### Import Demo Data

Visit `http://localhost:8000/seed-data/` and click "Import Demo Data"

### Demo Credentials

| Username | Role | Password |
|----------|------|----------|
| demo_admin | Admin | DemoPass123! |
| demo_doctor | Doctor | DemoPass123! |
| demo_nurse | Nurse | DemoPass123! |
| demo_billing | Billing | DemoPass123! |
| demo_reception | Reception | DemoPass123! |
| demo_auditor | Auditor | DemoPass123! |

---

## 📸 Screenshots

<details>
<summary>Click to view screenshots</summary>

### Landing Page
![Landing Page](docs/screenshots/landing.png)

### AI Chat Interface
![Chat Interface](docs/screenshots/chat.png)

### RBAC Demonstration
![RBAC Demo](docs/screenshots/rbac.png)

</details>

---

## 📁 Project Structure

```
secure_hospital_ai/
├── audit/                 # User model & audit logging
├── ehr/                   # EHR models (Patient, Staff, PHI)
├── frontend/              # Django views & templates
│   ├── templates/         # HTML templates
│   ├── llm_handler.py     # OpenAI integration
│   ├── rbac.py            # RBAC configuration
│   └── views.py           # API endpoints
├── mcp_server/            # Model Context Protocol server
│   ├── main.py            # FastAPI MCP implementation
│   └── tools/             # MCP tool definitions
├── seed_demo_data.py      # Demo data generator
└── manage.py
```

---

## 🔒 Security Considerations

This is a **demonstration project** for portfolio purposes. For production healthcare deployments, additional considerations include:

- [ ] HIPAA Business Associate Agreement (BAA) with cloud providers
- [ ] End-to-end encryption for PHI
- [ ] Regular security audits and penetration testing
- [ ] Incident response procedures
- [ ] Employee training on HIPAA compliance
- [ ] Data backup and disaster recovery

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 👤 Author

**Robert Agyemang**

- 🌐 Portfolio: [yourportfolio.com](https://yourportfolio.com)
- 💼 LinkedIn: [linkedin.com/in/yourprofile](https://linkedin.com/in/yourprofile)
- 🐦 Twitter: [@yourhandle](https://twitter.com/yourhandle)
- 📧 Email: your.email@example.com

---

## 🙏 Acknowledgments

- OpenAI for GPT-4o API
- Anthropic for Model Context Protocol specification
- Supabase for managed PostgreSQL
- Vercel for serverless hosting

---

<div align="center">

**⭐ Star this repo if you found it helpful!**

</div>
