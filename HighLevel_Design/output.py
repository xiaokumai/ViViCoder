from typing import List, Optional
from pydantic import BaseModel, Field

# —— Field specifications —— #
class FieldSpec(BaseModel):
    name: str = Field(
        ..., 
        description="Field name"
        )
    data_type: str = Field(
        ..., 
        description=(
            "List all valid types for this field, separated by '|' (e.g., int | float | str). "
            "Include size/range/format/units if known. Mark disallowed types as 'disallowed'."
        )
        )
    note: Optional[str] = Field(None, description="Optional usage or destination explanation")
    


# —— Single-module interface definition —— #
class ModuleInterface(BaseModel):
    id: str = Field(..., description="Module ID (e.g., Module1), matches the partition result")
    # requirement_refs: List[str] = Field(..., description="List of referenced functional/behavioral requirements (e.g., FR1, FR3)")

    # Interface elements
    inputs: List[FieldSpec] = Field(default_factory=list, description="Input parameter definitions")
    outputs: List[FieldSpec] = Field(default_factory=list, description="Output result definitions")
    summary: List[str] = Field(default_factory=list, description="Short module description (functions/responsibilities/boundaries)")

    tech_stack: str = Field(..., description="Technologies used in the module (e.g., Python, NumPy, sort function)")
    function_signature: str = Field(
        ...,
        description=(
            "Function signature in the target language (declaration only, no body)"
        )
    )
    nonfunctional_notes: str = Field(
        default="",
        description="Non-functional requirements (performance, security, etc.), leave empty if not applicable"
    )
    
    dependencies: List[str] = Field(
        default_factory=list,
        description="Dependencies from other modules (e.g., ['Module 2: needs …']). Leave empty if no dependencies."
    )
    


class OverallDesign(BaseModel):
    modules: List[ModuleInterface] = Field(..., description="List of all modules with design and interface details")
    collaboration: str = Field(..., description="Step-by-step description of module collaboration, from user input to process completion.")




class InterfacesOutput(BaseModel):
    modules: List[ModuleInterface]
    
class ModuleNonFunc(BaseModel):
    id: str = Field(..., description="Module ID (e.g., Module1)")
    nonfunctional_notes: str = Field(
        default="",
        description="Non-functional design aspects for this module (performance, reliability, security, observability, operations, etc.); leave as an empty string if not applicable"
    )
    
class NonFunctionOutput(BaseModel):
    interfaces: List[ModuleNonFunc]
    

# ========== New merged types ==========
class ModuleExtended(ModuleInterface):
    nonfunctional_notes: str = Field(default="", description="Non-functional aspects; empty string if none")
    
