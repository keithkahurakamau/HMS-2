# Enterprise Hospital Management System (HMS)

A modern, comprehensive Hospital Management System designed to streamline healthcare operations, patient management, and facility administration. Built with a modular monolith architecture.

## 🚀 Features

- **User Authentication & Authorization**: Secure JWT-based login with role-based access control (Admin, Doctor, Nurse, Pharmacist, etc.).
- **Patient Management**: Complete patient records, history, and demographics.
- **Appointments & Queue**: Manage patient appointments and live department queues.
- **Clinical & Wards**: Track clinical notes, diagnoses, and ward/bed allocations.
- **Laboratory & Pharmacy**: Manage lab tests, results, pharmacy prescriptions, and drug dispensations.
- **Inventory Management**: Track hospital supplies, equipment, and stock levels.
- **Billing & Finance**: Comprehensive invoicing, payments, and financial analytics.
- **Real-Time Updates**: WebSocket integration for live queues and notifications.

## 🛠️ Technology Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python)
- **Database**: PostgreSQL with [SQLAlchemy](https://www.sqlalchemy.org/) ORM
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Security**: Passlib (Bcrypt), Python-JOSE (JWT), SlowAPI (Rate Limiting)

### Frontend
- **Framework**: [React 19](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/)
- **Routing**: React Router DOM
- **Icons & UI**: Lucide React, React Hot Toast
- **HTTP Client**: Axios

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.9+
- Node.js 18+
- PostgreSQL server running locally or remotely

### 1. Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```
2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On macOS/Linux:
   source venv/bin/activate  
   # On Windows:
   venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Environment Variables:**
   Ensure you have a `.env` file in the `backend/` directory and configure your database and secrets.
5. **Run Migrations & Seed Data:**
   ```bash
   alembic upgrade head
   python seed.py
   ```

### 2. Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```
2. **Install dependencies:**
   ```bash
   npm install
   ```

## 🏃‍♂️ Running the Application

You will need to run both the backend and frontend servers simultaneously in separate terminal windows.

**Start the Backend Server:**
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn app.main:app --reload
```
The API will be available at `http://localhost:8000`. You can access the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

**Start the Frontend Development Server:**
```bash
cd frontend
npm run dev
```
The application will be available at `http://localhost:5173`.
