import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def check_postgresql():
    print_header("Checking PostgreSQL Installation")
    
    try:
        result = subprocess.run(
            ["psql", "--version"],
            capture_output=True,
            text=True
        )
        print(f"PostgreSQL found: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("PostgreSQL not found. Please install PostgreSQL.")
        print("\nInstallation instructions:")
        print("  - macOS: brew install postgresql")
        print("  - Linux: sudo apt-get install postgresql postgresql-contrib")
        print("  - Windows: Download from https://www.postgresql.org/download/windows/")
        return False

def check_python_deps():
    print_header("Checking Python Dependencies")
    
    required = ["psycopg2"]
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"{package}")
        except ImportError:
            print(f"{package} - NOT INSTALLED")
            missing.append(package)
    
    if missing:
        print(f"\nInstall missing packages:")
        print(f"  pip install {' '.join(missing)}")
        return False
    
    return True

def create_database():
    print_header("Creating PostgreSQL Database")
    
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    
    psql_cmd = ["psql", "-h", db_host, "-p", db_port, "-U", db_user]
    
    try:
        print(f"\nCreating database '{db_name}'...")
        subprocess.run(
            psql_cmd + ["-c", f"CREATE DATABASE {db_name};"],
            check=False,
            capture_output=True
        )
        print(f"Database created: {db_name}")
        return {
            "host": db_host,
            "port": db_port,
            "name": db_name,
            "user": db_user,
            "password": db_password
        }
    
    except Exception as e:
        print(f"Failed to create database: {e}")
        return None

def create_env_file(db_config):
    print_header("Creating .env Configuration File")
    
    env_content = f"""# PostgreSQL Configuration
DB_HOST={db_config['host']}
DB_PORT={db_config['port']}
DB_NAME={db_config['name']}
DB_USER={db_config['user']}
DB_PASSWORD={db_config['password']}
DB_POOL_MIN=2
DB_POOL_MAX=10
GROQ_API_KEY=your_groq_api_key_here
"""
    
    env_file = Path(".env")
    
    if env_file.exists():
        overwrite = input(".env already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite != 'y':
            print("Keeping existing .env file")
            return True
    
    try:
        env_file.write_text(env_content)
        print("Created .env file")
        print(f"\nContent:")
        print(env_content)
        return True
    except Exception as e:
        print(f" Failed to create .env: {e}")
        return False

def install_dependencies():
    print_header("Installing Python Dependencies")
    
    try:
        print("Installing psycopg2-binary...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "psycopg2-binary", "-q"],
            check=True
        )
        print("psycopg2-binary installed")
        return True
    except Exception as e:
        print(f"Failed to install dependencies: {e}")
        return False

def initialize_schema():
    print_header("Initializing Database Schema")
    
    try:
        from app.database_pg import init_db
        
        print("Initializing database schema...")
        init_db()
        print("Database schema initialized")
        return True
    except Exception as e:
        print(f" Failed to initialize schema: {e}")
        print(f"\nError details: {e}")
        return False

def test_connection():
    """Test database connection."""
    print_header("Testing Database Connection")
    
    try:
        from app.database_pg import health_check
        
        print("Testing connection...")
        if health_check():
            print("Database connection successful")
            return True
        else:
            print(" Database connection failed")
            return False
    except Exception as e:
        print(f" Connection test failed: {e}")
        return False

def main():
    print("\n")
    print("" + "="*68 + "")
    print("" + " "*68 + "")
    print("" + "  Audit Doc Tape - PostgreSQL Setup".center(68) + "")
    print("" + " "*68 + "")
    print("" + "="*68 + "")
    if not check_postgresql():
        print("\n Please install PostgreSQL first")
        return False
    
    input("\nPress Enter to continue...")
    if not check_python_deps():
        print("\n Installing missing Python dependencies...")
        if not install_dependencies():
            return False
    
    input("\nPress Enter to continue...")
    print_header("Database Configuration")
    print("You can use existing database or create a new one.")
    choice = input("Create new database? [Y/n]: ").strip().lower()
    
    db_config = None
    if choice != 'n':
        db_config = create_database()
        if not db_config:
            return False
    else:
        print("Using existing database configuration...")
        db_config = {
            "host": input("Host [localhost]: ").strip() or "localhost",
            "port": input("Port [5432]: ").strip() or "5432",
            "name": input("Database name [auditdoctape]: ").strip() or "auditdoctape",
            "user": input("User [postgres]: ").strip() or "postgres",
            "password": input("Password (leave blank): ").strip()
        }
    
    input("\nPress Enter to continue...")
    if not create_env_file(db_config):
        return False
    
    input("\nPress Enter to continue...")
    if not initialize_schema():
        print("\n Schema initialization failed")
        print("You can run: python -c 'from app.database_pg_pg import init_db; init_db()'")
        return False
    
    input("\nPress Enter to continue...")
    if not test_connection():
        print("\n Connection test failed")
        return False
    
    print_header("Setup Complete!")
    print("""
You're ready to use PostgreSQL with Audit Doc Tape!

Next steps:
1. Update imports in your code:
   from app.database_pg_pg import ...

2. Start your application:
   uvicorn app.main:app --reload

3. Test the API:
   curl http://localhost:8000/health
""")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

