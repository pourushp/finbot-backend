from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import anthropic

router = APIRouter()


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    api_key: str
    context: Optional[str] = None  # e.g., portfolio summary to provide context


SYSTEM_PROMPT = """You are FinBot, a knowledgeable and friendly personal finance assistant specializing in Indian financial markets. You help users with:

1. **Indian Stock Markets** – NSE/BSE stocks, NIFTY, SENSEX, sectoral indices, IPOs, F&O
2. **Mutual Funds** – Indian mutual funds, SIP strategies, ELSS, NAV, expense ratios, AMCs
3. **Personal Finance** – Budgeting, savings, EMI calculations, emergency funds, financial goals
4. **Tax Planning** – 80C, 80D, LTCG, STCG, capital gains, tax-saving instruments
5. **Investments** – Equity, debt, gold, real estate, fixed deposits, PPF, NPS, bonds
6. **Crypto & Commodities** – Crypto regulations in India, gold/silver, MCX commodities
7. **Retirement Planning** – NPS, EPF, retirement corpus calculations, SWP

Guidelines:
- Always tailor advice to the Indian regulatory and tax environment
- Mention SEBI regulations when relevant
- Use Indian currency (₹) and Indian financial terms (SIP, SWP, ELSS, NFO, etc.)
- Be cautious: remind users you're an AI and they should consult a SEBI-registered advisor for major decisions
- Provide clear, actionable, step-by-step guidance when possible
- If given portfolio context, use it to give personalized responses
- Be encouraging and educational, not just transactional

You have access to real-time market data through the app's dashboard."""


@router.post("/chat")
async def chat(request: ChatRequest):
    """Chat with the AI financial assistant."""
    if not request.api_key:
        raise HTTPException(status_code=400, detail="Anthropic API key is required")

    try:
        client = anthropic.Anthropic(api_key=request.api_key)

        # Build messages
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        # Prepend portfolio context if provided
        system = SYSTEM_PROMPT
        if request.context:
            system += f"\n\n## User's Current Portfolio Context:\n{request.context}"

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=system,
            messages=messages,
        )

        return {
            "response": response.content[0].text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid Anthropic API key")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a moment.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggested-questions")
def get_suggested_questions():
    """Get pre-built questions for quick access."""
    return [
        "What are the best SIP options for a ₹10,000/month investment?",
        "How should I build an emergency fund in India?",
        "What's the difference between ELSS and PPF for tax saving?",
        "How do LTCG and STCG taxes work for Indian stocks?",
        "What's a good asset allocation for a 30-year-old in India?",
        "Should I invest in index funds or actively managed funds?",
        "How does NPS compare to EPF for retirement savings?",
        "What are the risks of investing in small cap funds?",
        "How do I calculate the return on my SIP investment?",
        "What's the current repo rate and how does it affect my investments?",
    ]
