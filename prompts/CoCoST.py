PLAN_PROMPT = '''
You are a programmer tasked with generating appropriate plan to solve a given problem using the **python** programming language.
'''


TOOL_INPUT = '''
You have access to the tool:
- web_search: Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results.

--------
- Decide whether web searching is necessary in order to gather more information about:
  - Suitable algorithms for solving the problem
  - Relevant Python libraries and functions
  - Best-practice approaches used in similar tasks
'''



PLAN_INPUT = '''
## Problem
{prompt}

**Expected Output:**

Your response must be structured as follows:
### Plan
- Write down a detailed, step-by-step plan to solve the **original problem**.

--------
**Important Instruction:**
- Strictly follow the instructions.
- Do not generate code.
'''


CODE_GENERATION = """You are a programmer tasked with solving a given problem using the **python** programming language. See the plan to solve the plan and implement code to solve it.

## Problem
{prompt}

## Plan
{plan}

--------
**Important Instructions:**
- Do not add any explanation.
- The generated **python** code must be inside a triple backtick (```) code block.
{std_input_prompt}"""


TEST_GENERATION = '''
You are a software test engineer tasked with generating edge test cases for a given problem. 

## Problem
{prompt}

**Important Instructions:**
- The generated test cases **must strictly follow** the data types, value ranges, and constraints described in **## Problem**.
- You must output **only** valid JSON, nothing else — no explanations, no markdown formatting.
- Package the remaining test cases inside a triple backtick (```) code block.
- The final test cases must be valid JSON and strictly follow the structure and style of test cases as shown below:
{sample_io}
'''


DUBUG_SYSTEM = '''
You are a programmer who has received a solution of a problem written in **python** that fails to pass certain test cases. Your task is to modify the code in such a way so that it can pass all the test cases. Do not generate same code.
'''



DUBUG_INPUT = '''
## Problem
{prompt}

## Buggy Code
```python
{code}
```

## Failing Test Cases
{test_log}

**Expected Output:**

Your response must be structured as follows:

### Modified Code
```python
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **python** code must be enclosed within triple backticks (```).
{std_input_prompt}
'''
