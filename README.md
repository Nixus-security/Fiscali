# 🧾 Fiscali — Calculateur fiscal crypto pour la France

Fiscali simplifie la déclaration fiscale des cryptomonnaies pour les particuliers français. Importez vos transactions, obtenez votre formulaire 2086 pré-rempli.

## Features (MVP)

- **Import CSV** — Binance, Coinbase, Kraken, Bybit, OKX
- **Calcul PAMP** — Méthode du Prix d'Acquisition Moyen Pondéré (art. 150 VH bis CGI)
- **Formulaire 2086** — PDF pré-rempli, prêt à déclarer
- **Formulaire 3916-BIS** — Liste des comptes crypto étrangers
- **Flat tax 31.4%** — Calcul automatique PFU vs barème progressif

## Stack technique

| Layer     | Tech                          |
|-----------|-------------------------------|
| Backend   | Python 3.12 + FastAPI         |
| Frontend  | React + Vite + Tailwind CSS   |
| Database  | PostgreSQL                    |
| PDF       | ReportLab / fpdf2             |
| Payments  | Stripe                        |
| Deploy    | Railway / Fly.io              |

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Architecture

```
fiscali/
├── backend/          # API FastAPI + moteur fiscal
│   ├── app/
│   │   ├── api/          # Routes REST
│   │   ├── core/         # Config, DB, auth
│   │   ├── models/       # Modèles SQLAlchemy
│   │   ├── parsers/      # Parsers CSV par exchange
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Logique métier (PAMP, PDF)
│   │   └── utils/        # Helpers (prix, formatage)
│   └── tests/
├── frontend/         # UI React
│   └── src/
│       ├── components/   # Composants réutilisables
│       ├── pages/        # Pages principales
│       ├── hooks/        # Custom hooks
│       └── services/     # Appels API
└── docs/             # Documentation technique
```

## Roadmap

- [x] Architecture projet
- [ ] Moteur de calcul PAMP
- [ ] Parsers CSV (Binance, Coinbase, Kraken)
- [ ] Génération PDF formulaire 2086
- [ ] Frontend — Import & Dashboard
- [ ] Auth + Stripe
- [ ] API sync exchanges
- [ ] Staking / DeFi (BNC)

## Licence

Propriétaire — Tous droits réservés.
