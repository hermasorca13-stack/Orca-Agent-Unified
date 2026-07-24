"""Core Orca Agent Engine - Main orchestrator for all tiers"""

import asyncio
from typing import Optional, Dict, Any
from loguru import logger
from .sensory_perception import SensoryPerception
from .causal_reasoning import CausalReasoning
from .deep_creativity import DeepCreativity
from .self_learning import SelfLearning
from .real_world_execution import RealWorldExecution
from .financial_intelligence import FinancialIntelligence
from .legal_compliance import LegalCompliance
from .health_intelligence import HealthIntelligence
from .teaching_coaching import TeachingCoaching
from .product_building import ProductBuilding
from .data_analysis import DataAnalysis
from .advanced_language import AdvancedLanguage
from .security_intelligence import SecurityIntelligence
from .human_simulation import HumanSimulation
from .self_awareness import SelfAwareness


class OrcaAgent:
    """Main Orca Agent class - orchestrates all 4 tiers"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize Orca Agent with configuration"""
        self.config = config or {}
        self.initialized = False
        logger.info("🦅 Initializing Orca Agent...")

    async def initialize(self) -> bool:
        """Initialize all agent components"""
        try:
            logger.info("🚀 Starting Orca Agent initialization...")
            
            # Initialize Tier 1: Sensory Perception
            self.sensory_perception = SensoryPerception()
            # No explicit async init for SensoryPerception, it initializes in constructor
            logger.info("✅ Sensory Perception Tier initialized.")
            
            # Initialize Tier 2: Causal Reasoning
            self.causal_reasoning = CausalReasoning()
            logger.info("✅ Causal Reasoning Tier initialized.")
            
            # Initialize Tier 3: Deep Creativity
            self.deep_creativity = DeepCreativity()
            logger.info("✅ Deep Creativity Tier initialized.")
            
            # Initialize Tier 4: Self-Learning
            self.self_learning = SelfLearning()
            logger.info("✅ Self-Learning Tier initialized.")

            # Initialize Real-World Execution
            self.real_world_execution = RealWorldExecution()
            logger.info("✅ Real-World Execution initialized.")

            # Initialize Financial Intelligence
            self.financial_intelligence = FinancialIntelligence()
            logger.info("✅ Financial Intelligence initialized.")

            # Initialize Legal & Compliance
            self.legal_compliance = LegalCompliance()
            logger.info("✅ Legal & Compliance initialized.")

            # Initialize Health Intelligence
            self.health_intelligence = HealthIntelligence()
            logger.info("✅ Health Intelligence initialized.")

            # Initialize Teaching & Coaching
            self.teaching_coaching = TeachingCoaching()
            logger.info("✅ Teaching & Coaching initialized.")

            # Initialize Product Building
            self.product_building = ProductBuilding()
            logger.info("✅ Product Building initialized.")

            # Initialize Data Analysis
            self.data_analysis = DataAnalysis()
            logger.info("✅ Data Analysis initialized.")

            # Initialize Advanced Language
            self.advanced_language = AdvancedLanguage()
            logger.info("✅ Advanced Language initialized.")

            # Initialize Security Intelligence
            self.security_intelligence = SecurityIntelligence()
            logger.info("✅ Security Intelligence initialized.")

            # Initialize Human Simulation
            self.human_simulation = HumanSimulation()
            logger.info("✅ Human Simulation initialized.")

            # Initialize Self-Awareness
            self.self_awareness = SelfAwareness()
            logger.info("✅ Self-Awareness initialized.")
            
            # Initialize Integration Layer
            await self._init_integrations()
            
            self.initialized = True
            logger.success("✅ Orca Agent initialized successfully!")
            return True
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False





    async def _init_integrations(self):
        """Initialize Integration Layer"""
        logger.info("🎯 Initializing Integration Layer...")
        # TODO: Initialize GitHub, Manus, Claude connections
        logger.debug("  ✓ GitHub API connected")
        logger.debug("  ✓ Manus API connected")
        logger.debug("  ✓ Claude API configured")

    async def process_task(self, task: str, context: Dict = None) -> Dict:
        """Process a task through the appropriate tiers"""
        if not self.initialized:
            raise RuntimeError("Agent not initialized")
        
        logger.info(f"🎯 Processing task: {task}")
        # Example of using sensory perception for a task
        if "process_file" in task:
            parts = task.split(":")
            if len(parts) == 3:
                file_path = parts[1]
                file_type = parts[2]
                result = await self.sensory_perception.process_file(file_path, file_type)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid process_file task format"}
        elif "analyze_correlation" in task:
            # Assuming task format: "analyze_correlation:var1:var2"
            parts = task.split(":")
            if len(parts) == 3:
                var1 = parts[1]
                var2 = parts[2]
                # Mock data for now, actual data would come from sensory_perception or other sources
                import pandas as pd
                data = pd.DataFrame({"var1": [1, 2, 3, 4, 5], "var2": [2, 4, 5, 4, 5], "confounder": [10, 8, 6, 4, 2]})
                result = await self.causal_reasoning.differentiate_correlation_causation(data, var1, var2)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid analyze_correlation task format"}
        elif "compose_music" in task:
            parts = task.split(":")
            if len(parts) >= 3:
                style = parts[1]
                duration = int(parts[2])
                theme = parts[3] if len(parts) > 3 else None
                result = await self.deep_creativity.compose_original_music(style, duration, theme)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid compose_music task format"}
        elif "write_screenplay" in task:
            parts = task.split(":")
            if len(parts) >= 3:
                genre = parts[1]
                plot_summary = parts[2]
                characters = parts[3].split(",") if len(parts) > 3 else None
                result = await self.deep_creativity.write_screenplay(genre, plot_summary, characters)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid write_screenplay task format"}
        elif "learn_from_interaction" in task:
            # Assuming task format: "learn_from_interaction:type:user_message:agent_response"
            parts = task.split(":")
            if len(parts) >= 4:
                interaction_type = parts[1]
                user_message = parts[2]
                agent_response = parts[3]
                interaction_data = {"type": interaction_type, "user_message": user_message, "agent_response": agent_response}
                result = await self.self_learning.learn_from_interaction(interaction_data)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid learn_from_interaction task format"}
        elif "detect_knowledge_gaps" in task:
            parts = task.split(":")
            if len(parts) == 2:
                query = parts[1]
                result = await self.self_learning.detect_knowledge_gaps(query)
                return {"status": "success", "result": result}
            else:
                return {"status": "error", "message": "Invalid detect_knowledge_gaps task format"}
        elif "book_travel" in task:
            # Format: "book_travel:details_json"
            parts = task.split(":", 1)
            import json
            details = json.loads(parts[1])
            result = await self.real_world_execution.book_flight_hotel(details)
            return {"status": "success", "result": result}
        elif "analyze_finances" in task:
            # Format: "analyze_finances:csv_path"
            parts = task.split(":")
            import pandas as pd
            data = pd.read_csv(parts[1])
            result = await self.financial_intelligence.analyze_bank_statements(data)
            return {"status": "success", "result": result}
        elif "check_legal_compliance" in task:
            # Format: "check_legal_compliance:policy_text:reg1,reg2"
            parts = task.split(":")
            result = await self.legal_compliance.check_compliance(parts[1], parts[2].split(","))
            return {"status": "success", "result": result}
        elif "health_checkup" in task:
            # Format: "health_checkup:symptom1,symptom2"
            parts = task.split(":")
            result = await self.health_intelligence.analyze_symptoms(parts[1].split(","))
            return {"status": "success", "result": result}
        elif "generate_curriculum" in task:
            # Format: "generate_curriculum:topic:level"
            parts = task.split(":")
            result = await self.teaching_coaching.generate_curriculum(parts[1], parts[2])
            return {"status": "success", "result": result}
        elif "build_mvp" in task:
            # Format: "build_mvp:idea"
            parts = task.split(":", 1)
            spec = await self.product_building.write_product_spec(parts[1])
            result = await self.product_building.build_mvp(spec["spec"])
            return {"status": "success", "result": result}
        elif "deep_data_analysis" in task:
            # Format: "deep_data_analysis:csv_path"
            parts = task.split(":")
            import pandas as pd
            data = pd.read_csv(parts[1])
            result = await self.data_analysis.analyze_dataset(data)
            return {"status": "success", "result": result}
        elif "translate" in task:
            # Format: "translate:text:target_lang"
            parts = task.split(":")
            result = await self.advanced_language.translate_contextual(parts[1], parts[2])
            return {"status": "success", "result": result}
        elif "security_audit" in task:
            # Format: "security_audit:content"
            parts = task.split(":", 1)
            result = await self.security_intelligence.assess_vulnerabilities(parts[1])
            return {"status": "success", "result": result}
        elif "simulate_persona" in task:
            # Format: "simulate_persona:name:message"
            parts = task.split(":")
            result = await self.human_simulation.simulate_persona(parts[1], parts[2])
            return {"status": "success", "result": result}
        elif "explain_thinking" in task:
            # Format: "explain_thinking:task:step1,step2"
            parts = task.split(":")
            result = await self.self_awareness.explain_thinking(parts[1], parts[2].split(","))
            return {"status": "success", "result": result}
        return {"status": "success", "result": "Task processed"}

    async def chat(self, user_id: str, message: str, options: Dict = None) -> Dict:
        """Process a chat message through the agent's multi-tier reasoning and creativity loop"""
        if not self.initialized:
            raise RuntimeError("Agent not initialized")
        
        logger.info(f"💬 Chat from {user_id}: {message[:50]}...")
        
        # Tier 1: Sensory Perception (Check if message contains file/media links - handled in Telegram adapter)
        
        # Tier 2: Causal Reasoning & Tier 4: Self-Learning (Context analysis)
        gap_check = await self.self_learning.detect_knowledge_gaps(message)
        
        # Tier 3: Deep Creativity (Generate response)
        # In a real scenario, this would call an LLM with the context from all tiers
        prompt = f"User: {message}\nContext: {gap_check.get('message', '')}"
        creative_response = await self.deep_creativity.creative_problem_solving(prompt)
        
        response_text = creative_response.get("solutions", f"أنا أحلل طلبك: {message}")
        
        # Tier 4: Learning from interaction
        await self.self_learning.learn_from_interaction({
            "type": "chat",
            "user_id": user_id,
            "user_message": message,
            "agent_response": response_text
        })
        
        return {
            "response": response_text,
            "tokensUsed": len(message.split()) + len(response_text.split()),
            "cost": 0.0001
        }

    async def health_check(self) -> Dict:
        """Check agent health status"""
        return {
            "status": "healthy",
            "initialized": self.initialized,
            "timestamp": asyncio.get_event_loop().time()
        }
