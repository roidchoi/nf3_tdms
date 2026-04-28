#!/bin/bash

# 1. Create Conda Environment
echo "Creating Conda environment 'usdms_env'..."
conda create -n usdms_env python=3.12 -y

# 2. Activate Environment (Note: This might not work in subshell, user needs to activate manually)
# We will use 'conda run' or assume user activates it.
# For script purpose, we just print instructions.

# 3. Install Dependencies using uv
echo "Installing dependencies..."
# Ensure uv is installed (if not, pip install uv)
# Assuming uv is available in the base or user path.
# We use the full path to python in the new env to ensure correct install if not activated.
# But standard way is to ask user to activate. 
# Here we will output the commands for the user to run.

# 4. Create .env file
echo "Creating .env file..."
cat <<EOF > .env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=usdms_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5435
BACKEND_PORT=8005

# SEC User Agent (Format: "Company Name AdminContact@domain.com")
# MUST BE CHANGED to valid value
SEC_USER_AGENT="MyCompany Admin@mycompany.com"
EOF

echo "Setup script finished. Please run the following manually if not done:"
echo "1. conda activate usdms_env"
echo "2. uv pip install fastapi uvicorn[standard] asyncpg psycopg2-binary pandas numpy python-dotenv apscheduler requests aiohttp beautifulsoup4 lxml timescale-db-utils"
