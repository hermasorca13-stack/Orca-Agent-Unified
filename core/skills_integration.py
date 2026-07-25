import os

class SkillsInjector:
    def __init__(self):
        self.skills_path = "core/skills_data"
        self.skills = {}

    def load_skills(self):
        for file in os.listdir(self.skills_path):
            if file.endswith(".md"):
                skill_name = file.replace(".md", "")
                with open(os.path.join(self.skills_path, file), "r") as f:
                    self.skills[skill_name] = f.read()
        return self.skills

    def get_skill_prompt(self, skill_name):
        return self.skills.get(skill_name, "Skill not found.")

injector = SkillsInjector()
injector.load_skills()
