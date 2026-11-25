from pydantic import BaseModel, Field
from typing import List
from LowLevel_Design.output import DetailedModul


class ModuleCode(BaseModel):
    id: str = Field(..., description="Module ID (e.g., Module1). Must match the module design.")
    code: str = Field(
        ...,
        description=(
            "Complete Python code for the module in a fenced code block (```python ...```), "
            "fully functional and self-contained. "
            "Include all required import statements for standard or third-party libraries. "
            "Follow the design exactly—inputs, outputs, and inter-module interactions."
        ),
    )
    
class CodeOutput(BaseModel):
    modules: List[ModuleCode]
    
class ModuleCodeImpl(DetailedModul):
    code: str = Field(..., description="The actual code implementation for the module. Package the code in triple backticks (```) with a language tag matching the tech_stack, e.g., ```python ...``` for Python code.")
    
class CodeDesign(BaseModel):
    modules: List[ModuleCodeImpl]
    collaboration: str
    

