from Integration.agents import IntegrationAgent, integration_agent
from utils.config_log import config, tracer


@tracer
def integrate_code(requirement: dict, modules: dict) -> str:
    """
    Integrates code modules based on user requirements to produce a final code system.
    """
    
    res = {}
    integrated_code = integration_agent.integrate_code(requirement, modules)

    res["integrated_code"] = integrated_code
    return res

@tracer
def integration_document(requirement: dict, modules: dict) -> str:
    """
    Generates a structured documentation string including the integrated code.
    """
    integration_res = integrate_code(requirement, modules)
    
#     document = f"""
# # Final Integrated Code Documentation
# ## 1. Introduction
# This document provides the final integrated code system based on the user's original requirements and the completed modules. It includes the complete code that can be used as per the function signatures specified in the requirements.

# ## 2. Integrated Code
# {integration_res["integrated_code"]}
#     """
    
#     with open("Final_Integrated_Code_Documentation.md", "w", encoding="utf-8") as f:
#         f.write(document)
        
    # integration_res["doc"] = document
    return integration_res