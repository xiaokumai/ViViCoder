from HighLevel_Design.output import NonFunctionOutput, OverallDesign
from LowLevel_Design.output import DetailedOutput
from Coding.output import CodeOutput
from requimentAnal.output import RequirementsExtraction


def requirements_to_text(requirements: RequirementsExtraction) -> str:
    lines = ["Functional Requirements:"]
    for fr in requirements.functional_requirements:
        lines.append(f"ID: {fr.id}")
        lines.append(f"- Input: {fr.input}")
        lines.append(f"- Processing: {fr.processing}")
        lines.append(f"- Output: {fr.output}")
        lines.append("\n")
    
    lines.append("Technical/Environmental Requirements:")
    if requirements.technical_requirements:
        for tr in requirements.technical_requirements:
            lines.append(f"- {tr}")
    else:
        lines.append("（None）")
    
    lines.append("\nImplicit Requirements:")
    if requirements.implicit_requirements:
        for ir in requirements.implicit_requirements:
            lines.append(f"- {ir}")
    else:
        lines.append("（None）")
    
    return "\n".join(lines)


def modules_to_text(design: OverallDesign) -> str:
    lines = ["Modules List:"]
    modules = design.modules
    

    for module in modules:
        lines.append(f"Module ID: {module.id}")
        
        
        lines.append(f"- function_signature: {module.function_signature}")
        lines.append(f"- requirement_refs: {', '.join(module.requirement_refs) if module.requirement_refs else '（None）'}")
        
        # inputs
        
        if module.inputs:
            lines.append(f"- inputs:")
            for i in module.inputs:
                lines.append(f"  - Name: {i.name}, Type: {i.data_type}, Note: {i.note or 'None'}")
        else:
            lines.append(f"- inputs: （None）")
        

        # outputs
        if module.outputs:
            lines.append(f"- outputs:")
            for o in module.outputs:
                lines.append(f"  - Name: {o.name}, Type: {o.data_type}, Note: {o.note or 'None'}")
        else:
            lines.append(f"- outputs: （None）")            
            

        lines.append("Module Summary:")
        for summary in module.summary:
            lines.append(f"  - {summary}")
        lines.append(f"tech_stack: {module.tech_stack}")
        lines.append(f"Function Signature: {module.function_signature}")
        
        lines.append(f"Non-functional Notes:{module.nonfunctional_notes}")
        lines.append(f"Dependencies:{module.dependencies}")
        
        lines.append("\n")


    lines.append(f"Collaboration Process:{design.collaboration}")
    return "\n".join(lines)

def nonfunctional_to_text(nonfunctional: NonFunctionOutput) -> str:
    lines = ["Non-Functional Requirements:"]
    for item in nonfunctional.interfaces:
        lines.append(f"Module ID: {item.id}")
        lines.append(f"- Non-Functional Notes: {item.nonfunctional_notes or 'None'}")
        lines.append("\n")
    return "\n".join(lines)

def detail_to_text(detailed: DetailedOutput) -> str:
    lines = ["Detailed Design:"]
    for item in detailed.detailed_modules:
        lines.append(f"Module ID: {item.id}")
        lines.append("Detailed Design Pseudo-Code:")
        lines.append(f"\n{item.pseudo_code}\n")
        lines.append("\n")
    return "\n".join(lines)

def code_to_text(code: CodeOutput) -> str:
    lines = ["Code Implementations:"]
    for item in code.modules:
        lines.append(f"Module ID: {item.id}")
        lines.append("Code Implementation:")
        lines.append(f"\n{item.code}\n")
        lines.append("\n")
    return "\n".join(lines)



def filter_assert_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("assert")]
