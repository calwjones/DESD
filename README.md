# DESD Project Documentation

## System Overview

This project implements a marketplace platform for the Bristol Regional Food Network (BRFN). The system connects local producers with customers through an online marketplace where producers can list produce, customers can browse and place orders, and logistics staff can manage deliveries.

The system design is based on business process models developed during Term 1. These diagrams guided the architecture of the Django application and helped identify the key actors and interactions within the system.

## Business Process Models

### Strategic Process Diagram

![Strategic Diagram](docs/Strategic_Diagram.png)

### Operational Process Diagram

![Operational Diagram](docs/Operational_Diagram.png)

---

## System Architecture

The application follows a **modular Django architecture** (MTV pattern) where different responsibilities are separated into dedicated apps.

### Django Apps

**accounts**
Handles authentication and the custom user model. Users register as **Customer**, **Producer**, or **Logistics**, enabling role-based access throughout the system. Includes postcode geocoding for food miles calculation and favourite producer functionality.

**producers**
Manages producer profiles including business name, bio, location, and contact details. Exposes a producer dashboard displaying owned listings and order activity.

**products**
Full CRUD for product listings. Products include pricing, stock levels, stock threshold alerts, category, allergen info, availability dates, surplus deals, and AI quality grades. Customers can leave verified reviews.

**orders**
Shopping cart, multi-vendor checkout, and order lifecycle management (pending → confirmed → dispatched → delivered). Includes Stripe payment integration, payment splitting per producer, and weekly settlement calculations.

**delivery**
Logistics layer for order fulfilment. One `Delivery` record is created per producer per order on confirmation. Logistics staff progress deliveries through scheduled → collected → out for delivery → delivered, with order status rolled up automatically.

**ai_logs**
Logs all AI service interactions (quality grading and demand forecasting) including inputs, predictions, confidence scores, model versions, and any user overrides.

**marketplace**
Main customer-facing browse interface with search, category filtering, and allergen filtering.

---

## Infrastructure and Containerisation

The project uses **Docker Compose** to provide a reproducible development environment with five containers:

| Container | Role |
|---|---|
| `desd-web` | Django application — serves the website on port 8089 |
| `postgres:15` | PostgreSQL database |
| `desd-ai-quality` | AI microservice for product image quality grading |
| `desd-ai-demand` | AI microservice for demand forecasting |
| `desd-ai-dashboard` | Dashboard for monitoring AI service metrics |

Configuration values such as database credentials are stored in a **.env file**, ensuring sensitive information is not committed to the repository.

On startup, `entrypoint.sh` automatically runs migrations and loads fixtures so the system initialises correctly from a fresh clone.

---

## Database Design

The system uses Django's ORM to manage database operations against a PostgreSQL database. Key models and relationships:

- `CustomUser` — extends `AbstractUser` with role, postcode, coordinates, and allergen preferences
- `ProducerProfile` — one-to-one with a producer `CustomUser`
- `Product` — belongs to a producer; includes surplus deal fields and AI grading fields
- `Review` — one per customer per product, requires verified purchase
- `Order` / `OrderItem` — multi-vendor order with per-item producer tracking
- `Payment` / `PaymentSplit` — Stripe payment record split per producer
- `Settlement` — weekly producer payout records
- `Delivery` — one per producer per order, tracks logistics status independently
- `AIInteraction` — audit log for all AI service predictions

---

## Authentication and Authorisation

Authentication uses Django's built-in system with a **custom user model extending AbstractUser**.

| Role | Access |
|---|---|
| **Customer** | Browse marketplace, place orders, write reviews, manage allergen preferences |
| **Producer** | Manage own product listings, view orders, mark items ready for collection |
| **Logistics** | View all deliveries, progress delivery statuses |
| **Superuser** | Full Django admin access at `/admin/` |

Access is protected using `@login_required` and role checks in views. Producers can only modify their own listings.

---

## Signals

Four signal handlers run automatically in response to model events:

| Signal | Trigger | Effect |
|---|---|---|
| `producers/signals.py` | `CustomUser` saved | Auto-creates a `ProducerProfile` for new producers |
| `orders/signals.py` | `Order` saved | Deducts stock quantities when order status → confirmed |
| `products/signals.py` | `Product` saved | Emails favouriting customers when a surplus deal is activated |
| `delivery/signals.py` | `Order` saved | Creates one `Delivery` per producer when order is confirmed |

---

## Demo Data

Fixtures are loaded automatically by `entrypoint.sh` on container startup:

```bash
python manage.py loaddata accounts
python manage.py loaddata producers
python manage.py loaddata products
```

Historical order data can be seeded separately from a CSV file:

```bash
docker compose exec web python manage.py seed_orders --csv purchase_history.csv
```

### Demo Accounts

All seeded accounts use the password **`testpass123`**.

| Username | Role |
|---|---|
| `fredsfarm` | Producer |
| `greenvalley` | Producer |
| `sunshineorganics` | Producer |
| `riverside` | Producer |
| `hilltop` | Producer |
| `orchardlane` | Producer |
| `meadowfresh` | Producer |
| `thepreservery` | Producer |
| `wildroots` | Producer |
| `customer_<id>` | Customer (IDs from CSV) |

A superuser must be created manually:

```bash
docker exec -it <web_container_id> python manage.py createsuperuser
```

---

## Running the Project

### Prerequisites

- Docker Desktop
- Git

### Setup Instructions

1. **Clone the repository**

    ```bash
    git clone https://github.com/calwjones/DESD.git
    cd DESD
    ```

2. **Create environment configuration file**

    ```bash
    cp .env.example .env
    ```

3. **Build and start the containers**

    ```bash
    docker compose up --build
    ```

4. **Access the application**

    ```
    http://localhost:8089
    ```

5. **Access the Django admin**

    ```
    http://localhost:8089/admin/
    ```

---

### Useful Commands

**Stop containers**
```bash
docker compose down
```

**Rebuild containers**
```bash
docker compose up --build
```

**Run Django management commands**
```bash
docker compose exec web python manage.py <command>
```

**Create a superuser**
```bash
docker exec -it <web_container_id> python manage.py createsuperuser
```

**Full clean restart (removes volumes)**
```bash
docker compose down -v
docker compose up --build
```

---

## Project Management

The project is managed using **Jira** following an agile sprint methodology, organised into Epics, Tasks, and Sprints.

---

## Team Members

- Arran Bailey
- Charlie Rodway
- Callum Jones
- Lei Ye (Tommy)
