We use Python 3.12.0

## Deploy locally
1. Clone the repo
2. Activate environment
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
3. Stay in root folder ./ and Install dependencies from requirements.txt
   ```bash
   pip install -r requirements.txt
   ```
4. Install package for enabling local docker file
    ```bash
    pip install python-dotenv
    ```
5. Run the application locally from venv
    ```bash
   cd app
   flask run
   ```
Note: the .env file is required and sets the category

6. Run the application via Dockerfile (not recommended)
   ```bash
   docker run --rm -p 8000:8000 -e APP_CATEGORY=land myflaskapp:latest
   ```
   
7. Run the application via docker compose (intended usecase)
```bash
   docker compose up --build
   ```