from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "DeepSlide API"
    API_V1_STR: str = "/api/v1"
    
    class Config:
        env_file = "../.env"
        extra = "ignore" # Allow extra fields in .env

settings = Settings()
