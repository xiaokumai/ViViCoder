from typing import List
from pydantic import BaseModel, Field

class FunctionalRequirement(BaseModel):
    id: str = Field(
        ...,
        description="Unique ID for the functional requirement (e.g., 'FR1', 'FR2')."
    )
    input: str = Field(
        ...,
        description="Describe the input data types, including size or range if applicable. If not stated, provide reasonable assumptions or 'None'."
    )
    processing: str = Field(
        ...,
        description="Briefly describe the core processing logic for the function."
    )
    output: str = Field(
        ...,
        description="Describe the output data types and ranges. If not stated, provide reasonable assumptions or 'None'."
    )

class RequirementsExtraction(BaseModel):
    functional_requirements: List[FunctionalRequirement] = Field(
        ...,
        description="List of extracted functional requirements, each describing a user-facing function."
                    
    )
    technical_requirements: List[str] = Field(
        ...,
        description="List of technical requirements explicitly mentioned by the user, such as languages, frameworks, or libraries."
                    
    )
    implicit_requirements: List[str] = Field(
        ...,
        description="List of inferred requirements, including test cases, boundary conditions, exceptions, and assumptions about user experience."
                    
    )
