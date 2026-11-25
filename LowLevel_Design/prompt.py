


# DETAILED_PROMPT = """
# You are a senior software architect and full-stack development expert. Your task is to generate detailed pseudo-code designs for system modules based on the user's original requirements and the overall design of the module.
# Follow these rules strictly:
#  Respect module boundaries exactly as defined in the overall design.
#  Align pseudo-code with the specified tech stack: use its language style, built-in functions, standard libraries, or mature third-party libraries; if you use any third-party library, explicitly include the corresponding import statements. Do not invent non-existent functions or reimplement existing functionality.
#  Ensure consistency: function signatures must match the provided definitions (inputs/outputs, naming conventions, style).
#  For inter-module calls, invoke the defined function signatures of other modules directly. Do not hardcode or duplicate logic.
#  Keep logic clear, concise, and maintainable, with readable names and feasible processes.
# Output for each module must include:
# 1. The module ID (matching the overall design).
# 2. Pseudo-code in a fenced code block with the correct language tag. Syntax should be close to real code but may omit low-level details. Show main logic, data flow, error handling, and key algorithms. Add comments where necessary.

# Important: You are producing pseudo-code, not production code. However, it must use real library calls or built-ins from the tech stack whenever possible, so it can be quickly translated into working code.
# """


DETAILED_PROMPT = '''
You are a programmer tasked with solving a given problem using pseudo-code. See the plan to solve the plan and implement pseudo-code to solve it.
'''



DETAILED_INPUT = """
Please generate pseudo-code for the problem:

## Problem
{raw}

## Plan:

{plan}
--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
"""
