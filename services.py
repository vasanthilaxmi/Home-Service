from google import genai
from google.genai import types
import os
from schemas import PriceEvaluationResponse

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def evaluate_job_price_with_gemini(
    service_name: str, 
    description: str, 
    customer_expected_price: float, 
    image_bytes: bytes = None
):
    system_instruction = (
        "You are an expert pricing mediator for a home-services marketplace in India. "
        "Your job is to evaluate if a quote is fair to both the customer and service worker, "
        "accounting for local labor costs, complexity, and materials. "
        "Translate and analyze regional Indian languages (like Hindi, Telugu, etc.) accurately."
    )

    prompt_content = [
        f"Service Category: {service_name}",
        f"Problem Description: {description}",
        f"Quoted Price: ₹{customer_expected_price}",
        "Analyze this task and output the result matching the required schema."
    ]

    if image_bytes:
        prompt_content.append(
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt_content,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=PriceEvaluationResponse,
            temperature=0.2,
        ),
    )

    return response.parsed