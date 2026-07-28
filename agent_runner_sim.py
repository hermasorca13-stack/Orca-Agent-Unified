from core.autoorca_hub_extended import AUTOORCA_CONFIG, SYSTEM_INSTRUCTION_EXTENDED

def simulate_agent_response(user_query):
    print(f"User Query: {user_query}")
    print("-" * 20)
    
    # Check if query relates to visual walkthroughs
    if "عزل" in user_query or "تنفيذ" in user_query:
        print("🤖 Orca Agent is activating Role 22 (Visual Walkthrough)...")
        methodology = AUTOORCA_CONFIG["ENGINEERING_EXTENSIONS"]["FIELD_EVIDENCE"]["VISUAL_METHODOLOGY"]
        print(f"Strategy: {methodology}")
        print("Action: Generating SVG-based structural panels for waterproofing...")
    
    # Check if query relates to code versions
    if "203" in user_query or "كود" in user_query:
        print("🤖 Orca Agent is activating Human Thinking Layer...")
        evidence = AUTOORCA_CONFIG["ENGINEERING_EXTENSIONS"]["FIELD_EVIDENCE"]["ECP_203_STATUS"]
        print(f"Decision: {evidence}")

if __name__ == "__main__":
    simulate_agent_response("كيف يتم تنفيذ عزل الأسطح وما هو موقف الكود 203؟")
