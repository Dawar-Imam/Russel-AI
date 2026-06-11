from app.schemas.schema import DemoMessage


def get_demo_message() -> DemoMessage:
    return DemoMessage(message="Hello from Russel.AI backend")
