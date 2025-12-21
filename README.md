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

## Deploy via Docker
1. Build the docker image
   ```bash
   sudo docker build -t piaas-df-test .
   ```
2A.Run the application via Dockerfile (not recommended)
   ```bash
   sudo docker run --rm -p 8000:8000 piaas-df-test
   ```
2B.Run the application via docker compose (intended usecase)
   ```bash
   sudo docker compose up
   ```