# ⚡ PostMini

A lightweight, standalone, single-file local API client and Postman alternative. Built for developers who want a fast, zero-bloat tool to store API projects, organize requests, and execute HTTP requests without account walls, cloud sync requirements, or proprietary file formats.

## 🚀 Features

- **Single-File Architecture (`app.py`)**: The entire backend, SQLite database logic, execution engine, and responsive UI are contained in one file with **zero external CDN dependencies** (runs 100% offline).
- **Import Collections**:
  - **Direct Postman Export Support**: Upload or paste any standard Postman v2.0 or v2.1 export `.json` directly (folders are flattened automatically, URLs, headers, and bodies preserved).
  - **Clean PostMini Schema**: Simple, lightweight JSON format.
- **Built-in Docs & AI Prompt Page**:
  - Contains a ready-to-use LLM prompt to convert any Postman collection, cURL list, or OpenAPI/Swagger JSON to PostMini syntax.
  - Interactive sample collection ("DummyJSON Store API") with one-click direct import.
- **Project Management**: Organize requests into projects (e.g., *Auth Service*, *Payment API*).
- **Environment Base URL Variable**: Set a base URL per project and use `{{baseUrl}}/endpoint` or `/endpoint` in your requests.
- **Full Request Customization**:
  - Methods: `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, `HEAD`, `OPTIONS`.
  - Dynamic key-value tables with toggle checkboxes for **Query Parameters** and **Headers**.
  - Body support: **None**, **Raw JSON** (with auto-formatting / beautifier), and **Form Data**.
- **Execution Engine**:
  - Powered by Python's `requests` library.
  - Accurate elapsed time measurement in milliseconds (`ms`) and payload size.
  - Graceful timeout and connection failure handling.
- **Response Inspector**:
  - Status code badge with color coding (2xx green, 3xx blue, 4xx amber, 5xx red).
  - Pure vanilla offline syntax-highlighted JSON viewer.
  - Response headers table and one-click clipboard copy.
- **Keyboard Shortcuts**:
  - `Ctrl + Enter` (or `Cmd + Enter`): Run request.
  - `Ctrl + S` (or `Cmd + S`): Save request.

---

## 🛠️ Quick Start

### 1. Navigate to the Directory
```bash
cd "D:\python coding\postmini"
```

### 2. Run the Application Directly
```bash
python app.py
```

### 3. Open in Browser
Visit [http://127.0.0.1:5000](http://127.0.0.1:5000)

> **Note:** The SQLite database (`postmini.db`) will automatically initialize on your first launch.

---

## 📦 Pushing to GitHub

```bash
git init
git add .
git commit -m "Initial commit of PostMini"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```
