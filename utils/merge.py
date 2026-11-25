from HighLevel_Design.output import ModuleExtended, ModuleNonFunc, InterfacesOutput, NonFunctionOutput, ModuleInterface
from LowLevel_Design.output import DetailedModul,DetailedDesign
from Coding.output import ModuleCode, ModuleCodeImpl
from typing import List, Dict

def add_nonfunctional(modules: InterfacesOutput, nonfunctional: NonFunctionOutput) -> List[ModuleExtended]:

    # 1) Build the stage 4 lookup table.
    ext_by_id: Dict[str, ModuleNonFunc] = {}
    for ext in nonfunctional.interfaces:
        ext_by_id[ext.id] = ext
        
    # 2) Merge records into new objects.
    added_modules: List[ModuleExtended] = []
    for mod in modules.modules:
        ext = ext_by_id.get(mod.id)
        nonfunc = ext.nonfunctional_notes if ext else ""
        
        base_dict = mod.model_dump() 

        merged = ModuleExtended(
            **base_dict,
            nonfunctional_notes=nonfunc or "",
        )
        added_modules.append(merged)
        
    return added_modules


def merge_designs(modules: List[ModuleInterface], detailed_design: List[DetailedDesign]) -> List[DetailedModul]:

    
    # 1) Build the stage 5 lookup table.
    detail_by_id: Dict[str, DetailedDesign] = {}
    for detail in detailed_design:
        detail_by_id[detail.id] = detail
        
    # 2) Merge records into new objects.
    final_modules: List[DetailedModul] = []
    for mod in modules:
        detail = detail_by_id.get(mod.id)
        design = detail.pseudo_code if detail else ""
        
        base_dict = mod.model_dump() 

        merged = DetailedModul(
            **base_dict,
            pseudo_code=design or "",
        )
        final_modules.append(merged)
        
    return final_modules


def merge_code(modules: List[DetailedModul], code_impl: List[ModuleCode]) -> List[ModuleCodeImpl]:

    
    # 1) Build the stage 6 lookup table.
    code_by_id: Dict[str, ModuleCode] = {}
    for code in code_impl:
        code_by_id[code.id] = code
        
    # 2) Merge records into new objects.
    final_modules: List[ModuleCodeImpl] = []
    for mod in modules:
        code = code_by_id.get(mod.id)
        code = code.code if code else ""
        
        base_dict = mod.model_dump() 

        merged = ModuleCodeImpl(
            **base_dict,
            code=code or ""
        )
        final_modules.append(merged)
        
    return final_modules
    
