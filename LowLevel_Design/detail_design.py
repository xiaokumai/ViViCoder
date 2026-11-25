from LowLevel_Design.agents import DetailedDesignAgent
from utils.config_log import tracer
from utils.merge import merge_designs
from LowLevel_Design.output import DetailedDesign


@tracer
def detailed_design(modules_design: dict) -> dict:
    """
    Generates detailed design pseudo-code for each module based on the overall design.
    """
    
    res = DetailedDesignAgent.generate_detailed_design(modules_design)

    
    return res


# @tracer
# def detailed_document(requirements: dict, modules_design: dict) -> str:
#     """
#     Generates a structured documentation string including detailed design.
#     """
#     design_res = detailed_design(requirements, modules_design)
    
# #     document = f"""
# # # Detailed Design Documentation
# # ## 1. Introduction
# # This document provides a detailed design of each module based on the overall design and requirements analysis. It includes pseudo-code representations for each module.

# # ## 2. Detailed Module Designs
# # {detail_to_text(design_res["detailed_design"])}

# #     """
    
# #     design_res["doc"] = document
    
# #     with open("Detailed_Design_Documentation.md", "w", encoding="utf-8") as f:
# #         f.write(design_res["doc"])

#     modules = merge_designs(modules_design["overall_design"].modules, design_res["detailed_design"].detailed_modules)
#     collaboration = modules_design["overall_design"].collaboration

#     design_res["detailed_design"] = DetailedDesign(modules=modules, collaboration=collaboration)

#     return design_res