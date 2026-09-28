"""
CV profile for semantic matching.

Only put your skills and experience here -- no name, email, or personal info.
The embed_text property is what gets compared against job descriptions.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class CVProfile:
    skills: List[str]
    years_experience: int
    role_types: List[str]
    preferred_stack: List[str]

    @property
    def embed_text(self) -> str:
        """Text representation for the embedding model."""
        return (
            f"Software engineer with {self.years_experience} years of experience. "
            f"Primary roles: {', '.join(self.role_types)}. "
            f"Core skills: {', '.join(self.skills)}. "
            f"Preferred stack: {', '.join(self.preferred_stack)}."
        )


# -- edit this to match your actual skills --
MY_CV = CVProfile(
    skills=[
        # AI / ML
        "Multi-Agent Orchestration",
        "Model Context Protocol",
        "Ollama",
        "Local LLMs",
        "Text-to-SQL",
        "Intent Recognition",
        "RAG pipelines",
        "LangGraph",
        "LangChain",
        "PyTorch",
        "TensorFlow",
        "Scikit-learn",
        "Capsule Networks",
        "Bi-LSTM",
        "sentence-transformers",
        "Hugging Face",
        "Vector Databases",
        # Frontend
        "React.js",
        "Redux Toolkit",
        "Redux Thunk",
        "TypeScript",
        "JavaScript",
        "Next.js",
        "Micro-frontends",
        "Webpack",
        "Atomic Design",
        "React Virtualization",
        "Jest",
        "React Testing Library",
        # Backend
        "Python",
        "FastAPI",
        "Node.js",
        "Express",
        "REST APIs",
        "CLI Tools",
        "JSON Schema",
        "System Architecture",
        # Databases & Infra
        "SQL Server",
        "PostgreSQL",
        "MongoDB",
        "Docker",
        "Git",
        "Jenkins CI/CD",
        "Azure",
    ],
    years_experience=6,
    role_types=["fullstack", "backend", "ml", "frontend"],
    preferred_stack=[
        "Python",
        "FastAPI",
        "Multi-Agent Orchestration",
        "LangGraph",
        "Ollama",
        "React.js",
        "TypeScript",
        "PostgreSQL",
        "Docker",
        "Text-to-SQL",
    ],
)
