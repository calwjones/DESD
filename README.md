# DESD Project Documentation


## Running the Project

### Prerequisites

-   Docker Desktop
-   Git

------------------------------------------------------------------------

### Setup Instructions

1.  **Clone the repository**

    ``` bash
    git clone https://github.com/calwjones/DESD.git
    cd DESD-Project
    ```

2.  **Create environment configuration file**

    ``` bash
    cp .env.example .env
    ```

3.  **Build and start the containers**

    ``` bash
    docker compose up --build
    ```


4.  **Access the application**

        http://localhost:8089

------------------------------------------------------------------------

### Useful Commands

**Stop containers**

``` bash
docker compose down
```

**Rebuild containers**

``` bash
docker compose up --build
```

**Run Django management commands**

``` bash
docker compose exec web python manage.py <command>
```

------------------------------------------------------------------------

### Clean Startup Verification

To verify the project runs from a fresh state:

``` bash
docker compose down -v
docker compose up --build
```

This removes existing volumes and ensures the application starts
correctly from a clean environment.



## Group Members
- Arran Bailey
- Charlie Rodway
- Callum Jones
- Lei Ye (Tommy)

## Project Management

**Platform:** [Trello](https://trello.com/invite/desdprojectmanagement/ATTI69829abcc559b2d13bba32bf40251dd49C42A3A7)

## Key Dates

| Sprint | Dates | Focus |
|--------|-------|-------|
| Sprint 1 | 16.02 – 09.03 | Core architecture, basic Django models/database, and initial Docker setup |
| Sprint 2 | 16.03 – 06.04 | Expanded features, frontend/backend integration, and planning for external services |
| Sprint 3 | 13.04 – 07.05 | Complete implementation, passing provided test cases, and final demonstration |


## Sprint 1 Week 1: "Getting on the same page"
**W/C 16.02.26**

### Agenda

1. **Team member introductions** - getting to know each other
2. **Project specifications**
   - Task 2 assessment brief
   - Timeline
   - Task 2 case study
   - Task 2 architecture choice (brief demonstration and voting)

3. **Pre-requisites**
   - Django Download: pip install django
   - Docker Download: Docker Desktop (https://www.docker.com/products/docker-desktop/)
   - Docker VSCode extension download
   - GitHub repository set up - Callum

4. **Contributions matrix understanding**

5. **SMART Goals**
   - Tommy

6. **Weekly standup structure:**
   - Work completed - "what I did this week"
   - Planned work - "what I am going to do"
   - Impediments - "what slowed down my progress"
   - Timetabled times
