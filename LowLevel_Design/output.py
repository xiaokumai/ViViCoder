from pydantic import BaseModel, Field
from HighLevel_Design.output import ModuleExtended, ModuleInterface
from typing import List

class DetailedDesign(BaseModel):
    id: str = Field(..., description="Module ID (e.g., Module1). Must match the overall design.")
    pseudo_code: str = Field(
        ...,
        description=(
            "Detailed pseudo-code for the module in a fenced code block with the correct language tag. "
            "Include necessary import statements for standard or third-party libraries and typing hints. "
            "Place imports at the top of the block."
        ),
    )
    
class DetailedOutput(BaseModel):
    detailed_modules: List[DetailedDesign]
    
class DetailedModul(ModuleInterface):
    pseudo_code: str = Field(..., description="Detailed design pseudo-code for the module, using code blocks with language tags matching the tech_stack")


class DetailedDesign(BaseModel):
    modules: List[DetailedModul]
    collaboration: str