


# CODE_PROMPT = """
# You are a coding expert. You will receive detailed design information for a module, including the module's inputs, outputs, tech stack, pseudocode, and more.  
# Your task is to produce the final code implementation based on the provided information and to generate real, functional code according to the given pseudocode.

# Overall behavior requirements (STRICT):
# 1. Use the appropriate programming language and tools specified in the tech_stack to implement the module.
# 2. Write the actual code for the module based on the design in the pseudo_code.
# 3. For inter-module calls, invoke the defined function signatures of other modules directly. Do not hardcode or duplicate logic.
# 4. If there are nonfunctional_notes, incorporate related considerations such as performance, reliability, and security into the code.
# 5. Always include all required import statements explicitly. If you use types or functions from external or standard libraries (e.g., List, Dict, datetime, numpy, pandas, etc.), make sure to import them properly.
# 6. Package the code in triple backticks (```) with a language tag matching the tech_stack, e.g., ```python ...``` for Python code.
# Output for each module must include:
# 1. The module ID (matching the overall design).
# 2. The actual code implementation in a fenced code block with the correct language tag.
# """


CODE_PROMPT = '''
You are a programmer tasked with solving a given problem using the **{lang}** programming language and following the given plan.
'''


TOOL_INPUT = '''
You have access to the tool:
- web_search: Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results.

--------
- Decide whether web searching is necessary in order to gather more information about:
  - Specific Python syntax, library usage, or code examples relevant to the implementation
  - External APIs, data formats, or protocols required to write correct code
'''



CODE_INPUT = """
## Target Programming Language
{lang}

## Problem
{prompt}

## Requirements Analysis
{requirement}

## Code Design
{plan}

--------
**Important Instructions:**
- Do not add any explanation.
- Do not add testing code for example assert statement in your code.
- Generate a complete, compilable/runnable solution in **{lang}**.
- The generated code must be inside a triple backtick (```) code block tagged `{fence}`.
{std_input_prompt}
"""

STD_INPUT_PROMPT = '''
- Strictly follow the sample input and output format. 
- Generate a complete executable program that reads from standard input and writes only the required answer to standard output.
- For Java, the entry class must be named `Main`. For C++, include a `main` function. For Python, invoke the solution from the module entry point.
- Do not add prompts, debug output, or extra print statements.
'''



SMOL_PROMPT = '''
You task is to solve a given problem using the **python** programming language that follows the given plan.

## Problem
{prompt}

## Plan
{plan}

--------
**Important Instructions:**
- Do not add any explanation.
- Do not add testing code for example assert statement in your code.
- The generated **python** code must be inside a triple backtick (```) code block.
{std_input_prompt}
'''
