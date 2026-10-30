from review_system.env_config import load_env_file
from review_system.fastapi_app import run


if __name__ == "__main__":
    load_env_file(override=True)
    run()
