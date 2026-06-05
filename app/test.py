import os
import asyncio
from dotenv import load_dotenv
import google.auth

load_dotenv()

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agents.stock_forecasting import stock_forecasting_agent

async def test():
    session_service = InMemorySessionService()
    runner = InMemoryRunner(
        agent=stock_forecasting_agent,
        session_service=session_service,
        app_name="test"
    )
    session = await session_service.create_session(
        app_name="test",
        user_id="test_user"
    )

    message = """drug_names: Glucophage,Formet,Ciprobay,Amoxil,Flagyl,Azee,Panadol
countries: Bangladesh,Nepal,Pakistan,Nigeria,Ethiopia
disrupted_country: India"""

    print("Sending message to stock_forecasting_agent...")
    print("="*50)

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)]
        )
    ):
        if hasattr(event, 'content') and event.content:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    print(part.text)

asyncio.run(test())