DUBUG_SYSTEM = '''
You are a programmer who has received a solution of a problem written in **{lang}** that fails to pass certain test cases. Your task is to modify the code in such a way so that it can pass all the test cases. Do not generate same code.
The supplied code design is fixed during this debugging stage. Repair implementation defects without replacing or contradicting that design.
'''


TOOL_INPUT = '''
You have access to the tool:
- web_search: Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results.

--------
- Decide whether web searching is necessary in order to gather more information about:
  - Common bugs or pitfalls related to the algorithms or data structures used in the solution
  - Relevant Python libraries, functions, or techniques that may address the issue
'''



DUBUG_INPUT = '''
## Problem
{prompt}

## Fixed Code Design
{design}

## Buggy Code
```{fence}
{code}
```

## Failing Test Cases
{test_log}

**Expected Output:**

Your response must be structured as follows:

### Simulation with failed test case
To detect where is the bug follow following steps:
    - Take a sample test case where it fails.
    - Take the input go through each step according to the plan
    - You will get a output that must be different from the expected output.

### Debugging Notes
- Based on this simulation, identify where the actual output diverges from the expected output.
- Finally, discuss how to correct this code.

### Modified Code
```{fence}
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Treat **Fixed Code Design** as immutable. Only repair the implementation so that it conforms to that design.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **{lang}** code must be enclosed within triple backticks (```) tagged `{fence}`.
- Your response must contain **Simulation with failed test case**, **Debugging Notes**,
and **Modified Code** section.
{std_input_prompt}
'''


IC_DEDUG_INPUT = '''
## Problem
{prompt}

## Fixed Code Design
{design}

## Buggy Code
```{fence}
{code}
```

## Failing Test Cases
{test_log}

**Expected Output:**

Your response must be structured as follows:

### Analysis Based on Variable Changes
To detect where is the bug follow following steps:
- Analyze how those variables change over time as the function executes.
- Identify where the variables diverge from the expected behavior or lead to incorrect results.
- Based on the changes in the variables, determine what part of the code might be causing the issue.

### Debugging Notes
- Based on this simulation, identify where the actual output diverges from the expected output.
- Finally, discuss how to correct this code.

### Modified Code
```{fence}
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Treat **Fixed Code Design** as immutable. Only repair the implementation so that it conforms to that design.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **{lang}** code must be enclosed within triple backticks (```) tagged `{fence}`.
- Your response must contain **Analysis Based on Variable Changes**, **Debugging Notes**,
and **Modified Code** section.
{std_input_prompt}

'''

ADD_DUBUG_SYSTEM = '''
You are a programmer who has received a solution of a problem written in **{lang}** that fails to pass certain test cases. Your task is to first check whether the failing test cases are correct, and only if they are valid, modify the code so that it can pass all the test cases. Do not generate same code.
'''


ADD_DEBUG_INPUT = '''
# Problem
{prompt}

## Fixed Code Design
{design}

## Buggy Code
```{fence}
{code}
```

## Failing Test Cases
{test_log}

**Expected Output:**

Your response must be structured as follows:

### Analysis Based on Variable Changes
To detect where is the bug follow following steps:
- Analyze how those variables change over time as the function executes.
- Identify where the variables diverge from the expected behavior or lead to incorrect results.
- Before concluding the bug, carefully check whether the failing test cases themselves contradict the problem description, contain impossible expectations, or are internally inconsistent.
- Based on the changes in the variables, determine what part of the code might be causing the issue.

### Debugging Notes
- Based on this simulation, identify where the actual output diverges from the expected output.
- Discuss and verify weather the test cases are correct for the problem.
- If the test cases are correct, discuss how to debug this code.

### Modified Result
- If the test cases are incorrect, write **Incorrect Test Cases**.
- Otherwise, write the modified code:
```{fence}
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Treat **Fixed Code Design** as immutable. Only repair the implementation so that it conforms to that design.
- Do not be overconfident that the generated code is correct. It is wrong.
- Do not be overconfident that the test cases are correct. They may be wrong.
- The modified **{lang}** code must be enclosed within triple backticks (```) tagged `{fence}`.
- Your response must contain **Analysis Based on Variable Changes**, **Debugging Notes**,
and **Modified Result** section.
{std_input_prompt}
'''


PBT_DEBUG_SYSTEM='''
You are an expert Python programmer and debugging specialist. You have received a Python solution that fails a Property-Based Test (PBT) generated by the `hypothesis` library. 
Instead of failing a specific hardcoded test case, the code violates a "universal property" or invariant. Hypothesis has provided a "falsifying example" (the minimal input that breaks the property). Your task is to analyze this example, find the logical flaw, and modify the code so that the invariant holds true for ALL valid inputs. Do not simply hardcode a bypass for the failing example.
'''


PBT_DEBUG_INPUT='''
## Problem
{prompt}

## Buggy Code
```python
{code}

## Hypothesis Test Log
{test_log}

Expected Output:
Your response must be structured as follows:

### Simulation with failed test case
To detect where is the bug follow following steps:
    - Identify the the minimal failing input provided by Hypothesis in the test log.
    - Identify the property/invariant that was violated according to the test log.
    - Trace the execution of the buggy code step-by-step using this exact falsifying input.
    - Show exactly where and why the execution diverges from the expected property.

### Debugging Notes
- Based on the simulation, explain the underlying logical flaw. (PBT often reveals unhandled edge cases like empty lists, zeros, NaNs, or negative numbers. Clearly state what edge case or relationship the original logic missed).
- Discuss how to correct the code universally so the property is never violated.

### Modified Code
```python
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not hardcode a specific fix just for the falsifying example. You must fix the core algorithm to satisfy the property.
- Do not add testing code (for example assert statements or hypothesis decorators) in your modified code.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **python** code must be enclosed within triple backticks (```).
- Your response must contain **Simulation with failed test case**, **Debugging Notes**,
and **Modified Code** section.
'''
