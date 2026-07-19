import os

from dotenv import find_dotenv, load_dotenv
from openai import AuthenticationError, OpenAI, OpenAIError


def clean_key(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def mask_key(value: str) -> str:
    if len(value) <= 12:
        return "<too short>"

    return f"{value[:7]}...{value[-4:]}"


dotenv_path = find_dotenv()
load_dotenv(dotenv_path=dotenv_path, override=True)

api_key = clean_key(os.getenv("OPENAI_API_KEY"))

print(f"Loaded .env from: {dotenv_path or '<not found>'}")
print(f"Using key: {mask_key(api_key)}")
print(f"Key length: {len(api_key)}")

if not api_key:
    raise SystemExit("OPENAI_API_KEY is empty or missing.")

client = OpenAI(api_key=api_key)

try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Say hello in one sentence."}
        ]
    )
except AuthenticationError as error:
    raise SystemExit(f"Authentication failed: {error}") from error
except OpenAIError as error:
    raise SystemExit(f"OpenAI request failed: {error}") from error

print(response.choices[0].message.content)
