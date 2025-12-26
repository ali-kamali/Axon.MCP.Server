"""Helper script to generate secure secrets."""
import secrets


def generate_api_secret() -> str:
    """Generate secure API secret key."""
    return secrets.token_urlsafe(32)


def generate_jwt_secret() -> str:
    """Generate secure JWT secret key."""
    return secrets.token_urlsafe(64)


if __name__ == "__main__":
    print("Copy these values to your .env file:")
    print(f"API_SECRET_KEY={generate_api_secret()}")
    print(f"JWT_SECRET_KEY={generate_jwt_secret()}")


