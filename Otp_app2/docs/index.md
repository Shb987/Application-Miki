# Miki Application Platform

Welcome to the comprehensive documentation for the **Miki Application Platform**. This application is a fully-featured, asynchronous backend service designed to power a robust educational and gamified ecosystem. Built primarily with **FastAPI** and **MongoDB**, it represents a modern architectural approach to handling diverse user interactions securely and efficiently.

## 🚀 Vision and Scope

The overarching goal of this platform is to provide an all-in-one educational environment. It scales from handling standard administrative duties (like user registration and role-based access control) to executing highly complex, interactive operations such as generating comprehensive exam PDFs, evaluating subjective answers using AI, and hosting competitive mini-games.

This system is inherently multi-tenant regarding user access, isolating state, and protecting data securely via stateless JWT deployments, while supporting thousands of asynchronous connections.

## 🌟 Key Application Features

### 1. Robust User & Identity Management
At the core of the service is a tightly integrated user management system. It provides discrete roles `Admin`, `Student/User`, and utilizes both secure JWT (JSON Web Tokens) for long-lived sessions and standard OTP (One-Time Password) pipelines for initial verifications, password resets, and critical account actions.

### 2. Comprehensive Educational Ecosystem
*   **The Exam Module**: A complete pipeline allowing administrators to construct questions, associate them with varying difficulty levels, and dynamically generate "Exam Papers". These papers are exported to PDF formats utilizing specialized layout services.
*   **Future Study Path Tracking**: The system autonomously tracks student analytics over time, synthesizing their quiz and exam metrics into actionable "Future Study Pathways".
*   **Intelligent Evaluation**: Beyond simple multiple-choice checking, the platform hosts logic (often augmented by AI) to evaluate subjective answers and provide granular feedback.

### 3. AI-Powered Interactivity
The platform ships with a suite of AI wrappers directly embedded into its routers:
*   **AI Tutor**: Routes that process student queries contextually based on their subject and grade.
*   **Voice Assistant Integration**: Endpoints built to ingest audio byte streams, process transcribed intent, and return synthesized TTS (Text-to-Speech) feedback.
*   **AI Student Companion**: A conversational agent specifically prompted to act as an encouraging, persistent educational buddy rather than a simple Q&A encyclopeida.

### 4. Embedded Gamification
Recognizing the need for engagement, the platform hosts server-side validated games. The business logic for **Chess**, **Wordle**, and spatial **Squares** games is executed and validated entirely via FastAPI services. High scores, move validation, and streak calculations are piped directly into the user's continuous metrics.

### 5. Server-Side Admin Dashboard
A completely self-contained **Admin Panel** exists within the FastAPI context. By harnessing `Jinja2` templates, administrators can manage the entire database without needing an external frontend application. Pages are dynamically rendered server-side and augmented with Bootstrap/Tailwind for styling.

---

## 🛠 Technology Stack Deep Dive

The technological choices reflect a priority on highly concurrent API throughput without sacrificing developer velocity:

*   **FastAPI Framework**: Chosen for its native asynchronous capabilities, automatic interactive documentation (Swagger), and tight integration with Pydantic for rigid runtime checking.
*   **Python 3.10+**: Leans heavily on modern Python type hinting to ensure code quality.
*   **MongoDB & Motor**: The primary operational database. Chosen for its schema flexibility (vital for rapidly changing educational question structures). `Motor` is used as the asynchronous driver to ensure database I/O does not block the FastAPI event loop.
*   **Pydantic (v2)**: Validates every single incoming and outgoing HTTP payload. Models govern the shape of Data inside MongoDB as well.
*   **Jinja2 Templates**: For Server-Side Rendering of the Admin dashboard.
*   **Firebase Admin SDK**: Employed heavily by the `scheduler_service` and `notification_service` to blast push notifications to connected mobile clients.
*   **Uvicorn**: An ASGI web server implementation used in production to route lightning-fast HTTP traffic to the FastAPI application.

## 🗂 Environment Configuration and Secrets

The application operates securely by relying entirely on `.env` files for runtime configuration. 
**Required Keys for Bootstrapping:**

```env
# Database Connections
MONGO_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/
DB_NAME=education_platform_db

# Security Cryptography
SECRET_KEY=a_very_long_cryptographic_hash_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_HOURS=24
OTP_EXPIRY_MINUTES=5

# External Integrations
FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json
YOUTUBE_API_KEY=AIzaSy... # For fetching educational video supplements
ONESIGNAL_APP_ID=onesignal_app_identifier
ONESIGNAL_API_KEY=onesignal_rest_api_key

# Cross Origin Requests
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://my-frontend.domain
```

## 🚀 Deployment Guide

### Local Development Quickstart

1.  **Repository Setup:** Clone the repository and navigate to `Otp_app2`.
2.  **Virtual Environment:** Execute `python -m venv venv` and activate it.
3.  **Dependency Strategy:** Execute `pip install -r requirements.txt`. (Note: Make sure your `pip` is updated to handle complex wheel builds for PyJWT and PyMongo if compiling on Windows).
4.  **Database Seeding (Critical):** Run `python seed_wordle.py`, `python seed_squares.py` and other seed files if this is a fresh database instance. Failing to do so will result in 404s when games attempt to pull required dictionary sets.
5.  **Execution:** Run `uvicorn main:app --reload --host 0.0.0.0 --port 8000`.

### Containerized Sandbox (Docker)

For environments identical to production, the project ships with a `Dockerfile` and `docker-compose.yml`.

```bash
# This will construct the image and orchestrate the Mongo Instance if configured.
docker-compose up --build -d
```
All environment variables must be supplied to the container at boot.
