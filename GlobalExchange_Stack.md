## Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.12 | Backend and server-rendered application |
| **Framework** | Django 6.x | Monolithic web application, ORM, admin, forms, templates, and sessions |
| **Database** | PostgreSQL 16 | Primary relational database |
| **Database driver** | `psycopg` 3 | PostgreSQL connectivity for Django |
| **Authentication** | Keycloak 26 + OpenID Connect | SSO, user identity, and role management |
| **OIDC integration** | `mozilla-django-oidc` | Connects Django to Keycloak |
| **Frontend** | Django Templates + Tailwind CSS 4.3 | Server-rendered HTML and utility-based styling |
| **CSS build** | Tailwind CLI / npm | Compiles CSS into `static/css/app.css` |
| **Production server** | Gunicorn | WSGI server for production |
| **Containers** | Docker + Docker Compose | Runs Django, PostgreSQL, Keycloak, and Mailpit |
| **Testing** | pytest, pytest-django, Coverage.py | Automated tests and coverage |
| **Documentation** | Sphinx | Project documentation |
| **Configuration** | `django-environ` | Environment-variable-based settings |
| **Development email** | Mailpit | Local SMTP server and email inbox at port `8025` |

### Architecture

```text
Browser
   │
   ▼
Django / Gunicorn
   ├── PostgreSQL
   └── Keycloak via OIDC
           └── PostgreSQL (Keycloak data)

Mailpit receives development email
```

### Notable details

- This is a **monolithic, server-rendered Django application**, not a React/Vue SPA.
- There is **no React, Vite, or CDN**; Tailwind is compiled locally with the Tailwind CLI.
- Development runs Django using `runserver`; production uses Gunicorn.
- Keycloak roles are synchronized into Django groups through a custom authentication backend.
- Separate Docker Compose configurations exist for development and production.
- No external REST framework, Celery, Redis, or message broker is currently present.

Key references: `requirements.txt`, `config/settings/base.py`, `package.json`, `docker-compose.yml`, and `docker-compose.prod.yml`.
