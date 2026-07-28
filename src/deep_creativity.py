"""Deep Creativity Module for Orca Agent"""

import asyncio
import os
from typing import Dict, Any, List
from loguru import logger
import anthropic

# Initialize Claude client
_client = None

def get_claude_client():
    global _client
    if _client is None:
        api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            _client = anthropic.Anthropic(api_key=api_key)
        else:
            _client = None
    return _client

async def call_llm(prompt: str, model: str = None, max_tokens: int = 1000) -> str:
    """Call Claude API for real content generation"""
    if model is None:
        model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240229")
    
    client = get_claude_client()
    if client is None:
        logger.warning("⚠️ No Claude API key available, using fallback response")
        await asyncio.sleep(0.5)
        return f"[Fallback] I understand your request but need a Claude API key configured. Your prompt: {prompt[:80]}..."
    
    try:
        logger.info(f"🧠 Calling Claude API ({model}) with prompt: {prompt[:100]}...")
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system="You are Orca Agent's creative engine. Respond naturally and helpfully in the same language as the user.",
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        logger.error(f"❌ Claude API call failed: {e}")
        return f"[Error] Could not generate content: {str(e)[:200]}"

# Backward compatibility alias
call_llm_mock = call_llm


class DeepCreativity:
    """Handles deep creative generation tasks for the Orca Agent"""

    def __init__(self):
        logger.info("🎨 Initializing Deep Creativity module...")
        logger.info("✅ Deep Creativity module initialized.")

    async def compose_original_music(self, style: str, duration_seconds: int, theme: str = None) -> Dict:
        """Generate original music based on style, duration, and optional theme"""
        logger.info(f"Composing original music (Style: {style}, Duration: {duration_seconds}s, Theme: {theme})")
        
        # This would typically involve a dedicated music generation AI (e.g., Google Magenta, OpenAI Jukebox)
        # For now, we'll return a placeholder and suggest using Manus's generate tool.
        
        prompt = f"Compose an original piece of music in the {style} style, lasting {duration_seconds} seconds. "
        if theme:
            prompt += f"The theme should be: {theme}."
        
        generated_description = await call_llm_mock(prompt)
        
        return {
            "status": "pending_generation",
            "message": "Music composition requires specialized AI models. Please use Manus generate tool for actual music generation.",
            "generated_description": generated_description,
            "suggested_tool": "manus_generate_music",
            "parameters": {"style": style, "duration": duration_seconds, "theme": theme}
        }

    async def write_screenplay(self, genre: str, plot_summary: str, characters: List[str] = None) -> Dict:
        """Write a full screenplay with 3 acts based on genre, plot, and characters"""
        logger.info(f"Writing screenplay (Genre: {genre}, Plot: {plot_summary[:50]}...)")
        
        prompt = f"Write a three-act screenplay in the {genre} genre. Plot summary: {plot_summary}."
        if characters:
            prompt += f" Main characters: {', '.join(characters)}."
        
        screenplay_content = await call_llm_mock(prompt, max_tokens=2000) # Longer generation
        
        return {
            "status": "success",
            "genre": genre,
            "plot_summary": plot_summary,
            "screenplay": screenplay_content,
            "message": "Screenplay generated successfully."
        }

    async def invent_brand_identity(self, product_service: str, target_audience: str) -> Dict:
        """Invent brand names, slogans, and design concepts (logos, UI mockups)"""
        logger.info(f"Inventing brand identity for {product_service} (Audience: {target_audience})")
        
        prompt = f"Invent brand names, slogans, and describe visual concepts for a logo and UI mockup for a {product_service} targeting {target_audience}."
        
        brand_identity_text = await call_llm_mock(prompt, max_tokens=1500)
        
        return {
            "status": "success",
            "product_service": product_service,
            "target_audience": target_audience,
            "brand_identity": brand_identity_text,
            "message": "Brand identity concepts generated. Use image generation tools for visual mockups."
        }

    async def generate_poetry(self, theme: str, language: str = "arabic", style: str = "free verse") -> Dict:
        """Generate poetry in Arabic or English based on theme and style"""
        logger.info(f"Generating {language} poetry (Theme: {theme}, Style: {style})")
        
        prompt = f"Write a {style} poem in {language} about the theme of {theme}."
        
        poetry_content = await call_llm_mock(prompt, max_tokens=500)
        
        return {
            "status": "success",
            "theme": theme,
            "language": language,
            "style": style,
            "poetry": poetry_content,
            "message": "Poetry generated successfully."
        }

    async def invent_game(self, genre: str, core_mechanic: str, target_platform: str = "mobile") -> Dict:
        """Invent new game mechanics and balancing for a game"""
        logger.info(f"Inventing {genre} game for {target_platform} with core mechanic: {core_mechanic}")
        
        prompt = f"Invent a new {genre} game for {target_platform} with the core mechanic of {core_mechanic}. Describe the game mechanics, core loop, and basic balancing considerations."
        
        game_design = await call_llm_mock(prompt, max_tokens=1000)
        
        return {
            "status": "success",
            "genre": genre,
            "core_mechanic": core_mechanic,
            "target_platform": target_platform,
            "game_design": game_design,
            "message": "Game design concepts generated."
        }

    async def invent_recipes(self, available_ingredients: List[str], cuisine_style: str = "any") -> Dict:
        """Invent cooking recipes from available ingredients"""
        logger.info(f"Inventing recipes with ingredients: {', '.join(available_ingredients)} (Cuisine: {cuisine_style})")
        
        prompt = f"Invent a cooking recipe using the following ingredients: {', '.join(available_ingredients)}. The cuisine style should be {cuisine_style}. Provide ingredients list, steps, and serving suggestions."
        
        recipe = await call_llm_mock(prompt, max_tokens=700)
        
        return {
            "status": "success",
            "ingredients": available_ingredients,
            "cuisine_style": cuisine_style,
            "recipe": recipe,
            "message": "Recipe generated successfully."
        }

    async def design_marketing_campaign(self, product: str, target_audience: str, goals: List[str]) -> Dict:
        """Design a complete marketing campaign"""
        logger.info(f"Designing marketing campaign for {product} (Audience: {target_audience}, Goals: {', '.join(goals)})")
        
        prompt = f"Design a complete marketing campaign for {product} targeting {target_audience} with the following goals: {', '.join(goals)}. Include strategy, channels, messaging, and key performance indicators."
        
        campaign_plan = await call_llm_mock(prompt, max_tokens=2000)
        
        return {
            "status": "success",
            "product": product,
            "target_audience": target_audience,
            "goals": goals,
            "campaign_plan": campaign_plan,
            "message": "Marketing campaign plan generated."
        }

    async def creative_problem_solving(self, problem_description: str, constraints: List[str] = None) -> Dict:
        """Innovate solutions for complex problems"""
        logger.info(f"Innovating solutions for problem: {problem_description[:50]}...")
        
        prompt = f"Propose innovative solutions for the following complex problem: {problem_description}."
        if constraints:
            prompt += f" Consider these constraints: {', '.join(constraints)}."
        
        solutions = await call_llm_mock(prompt, max_tokens=1000)
        
        return {
            "status": "success",
            "problem": problem_description,
            "constraints": constraints,
            "solutions": solutions,
            "message": "Innovative solutions generated."
        }

    async def write_novel(self, genre: str, premise: str, main_characters: List[str]) -> Dict:
        """Write a full novel with evolving characters (placeholder for long-form generation)"""
        logger.warning(f"Novel writing is a long-form task and requires iterative generation. Generating a brief outline.")
        
        prompt = f"Generate a detailed outline for a {genre} novel based on the premise: {premise}. Include character arcs for {', '.join(main_characters)} and key plot points."
        
        novel_outline = await call_llm_mock(prompt, max_tokens=2000)
        
        return {
            "status": "pending_long_form",
            "message": "Full novel generation requires iterative process. Here is a detailed outline.",
            "outline": novel_outline,
            "suggested_next_step": "Use the outline to generate chapters iteratively."
        }


# Example usage (for testing purposes)
async def main():
    creativity_engine = DeepCreativity()

    print("\n--- Composing Original Music (Mock) ---")
    music_result = await creativity_engine.compose_original_music("classical", 180, "melancholy")
    print(music_result)

    print("\n--- Writing Screenplay ---")
    screenplay_result = await creativity_engine.write_screenplay(
        "sci-fi",
        "A lone astronaut discovers an ancient alien artifact that can manipulate time.",
        ["Commander Eva Rostova", "AI Companion KAI"]
    )
    print(screenplay_result)

    print("\n--- Inventing Brand Identity ---")
    brand_result = await creativity_engine.invent_brand_identity("AI-powered coffee machine", "tech-savvy millennials")
    print(brand_result)

    print("\n--- Generating Poetry (Arabic) ---")
    poetry_result = await creativity_engine.generate_poetry("الحب", "arabic", "free verse")
    print(poetry_result)

    print("\n--- Inventing Game ---")
    game_result = await creativity_engine.invent_game("puzzle", "gravity manipulation", "PC")
    print(game_result)

    print("\n--- Inventing Recipes ---")
    recipe_result = await creativity_engine.invent_recipes(["chicken breast", "broccoli", "rice", "soy sauce"], "Asian")
    print(recipe_result)

    print("\n--- Designing Marketing Campaign ---")
    campaign_result = await creativity_engine.design_marketing_campaign(
        "Eco-Friendly Smart Home Device",
        "environmentally conscious homeowners",
        ["increase brand awareness", "drive sales", "educate consumers"]
    )
    print(campaign_result)

    print("\n--- Creative Problem Solving ---")
    problem_result = await creativity_engine.creative_problem_solving(
        "How to reduce plastic waste in urban areas",
        ["cost-effective", "scalable", "community-driven"]
    )
    print(problem_result)

    print("\n--- Writing Novel (Outline) ---")
    novel_result = await creativity_engine.write_novel(
        "fantasy",
        "A young orphan discovers they are the last of a magical bloodline destined to save a dying world.",
        ["Elara", "Kael", "Shadow King"]
    )
    print(novel_result)

if __name__ == "__main__":
    asyncio.run(main())
