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
from google.adk.agents.run_config import RunConfig
from google.genai import types
from app.agents.stock_forecasting import stock_forecasting_agent


async def test():
    runner = InMemoryRunner(
        agent=stock_forecasting_agent,
        app_name="test"
    )

    message = """drug_names: Glucophage,Formet,Ciprobay,Amoxil,Flagyl,Azee,Panadol
countries: Bangladesh,Nepal,Pakistan,Nigeria,Ethiopia
disrupted_country: India"""

    print("Sending to stock_forecasting_agent...")
    print("=" * 50)

    session = await runner.session_service.create_session(
        app_name="test",
        user_id="test_user"
    )

    async for event in runner.run_async(
        user_id="test_user",
        session_id=session.id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=message)]
        ),
        run_config=RunConfig(max_llm_calls=500)
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:

                if getattr(part, "text", None):
                    print("\nTEXT:")
                    print(part.text)

                if getattr(part, "function_call", None):
                    print("\nFUNCTION CALL:")
                    print(part.function_call)

                if getattr(part, "function_response", None):
                    print("\nFUNCTION RESPONSE:")
                    print(part.function_response)


asyncio.run(test())