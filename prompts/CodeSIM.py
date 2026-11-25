PROMPT_FOR_PLANNING = """You are a programmer tasked with generating appropriate plan to solve a given problem using the **{lang}** programming language.

## Problem

{problem}

**Expected Output:**

Your response must be structured as follows:

### Problem Understanding

- Think about the original problem. Develop an initial understanding about the problem.

### Recall Example Problem

Recall a relevant and distinct problems (different from problem mentioned above) and
- Describe it
- Generate {lang} code step by step to solve that problem
- Discuss the algorithm to solve this problem
- Finally generate a planning to solve that problem

### Algorithm to solve the original problem

- Write down the algorithm that is well suited for the original problem
- Give some tutorials to about the algorithm for example:
    - How to approach this type of algorithm
    - Important things to consider

### Plan

- Write down a detailed, step-by-step plan to solve the **original problem**.

--------
**Important Instruction:**
- Strictly follow the instructions.
- Do not generate code.
"""



PROMPT_FOR_SIMULATION = """You are a programmer tasked with verifying a plan to solve a given problem using the **{lang}** programming language.

{problem_with_planning}

**Expected Output:**

Your response must be structured as follows:

### Simulation

- Take a sample input and apply plan step by step to get the output. Do not generate code do it manually by applying reasoning.
- Compare the generated output with the sample output to verify if your plan works as expected.

### Plan Evaluation

- If the simulation is successful write **No Need to Modify Plan**.
- Otherwise write **Plan Modification Needed**.

"""



PROMPT_FOR_REFINEMENT = """You are a programmer tasked with generating appropriate plan to solve a given problem using the **{lang}** programming language. You already have a wrong plan. Correct it so that it can generate correct plan.

{problem_with_planning}

## Plan Critique

{critique}

**Expected Output:**

Your response must be structured as follows:

## New Plan

- Write down a detailed, step-by-step modified plan to solve the **original problem**.
- Ensure each step logically follows from the previous one.

--------
**Important Instruction:**
- Your response must contain only the plan.
- Do not add any explanation.
- Do not generate code.
"""


PROMPT_FOR_CODE_GENERATION = """You are a programmer tasked with solving a given problem using the **{lang}** programming language. See the plan and implement code to solve it.

{problem_with_planning}

--------
**Important Instructions:**
- Do not add any explanation.
- The generated **{lang}** code must be inside a triple backtick (```) code block.
{std_input_prompt}"""



PROMPT_FOR_DEBUGGING = """You are a programmer who has received a solution of a problem written in **{lang}** that fails to pass certain test cases. Your task is to modify the code in such a way so that it can pass all the test cases. Do not generate same code.

{problem_with_planning}

### Buggy Code
```{fence}
{code}
```

{test_log}

**Expected Output:**

Your response must be structured as follows:

### Simulation with failed test case
To detect where is the bug follow following steps:
    - Take a sample test case where it fails.
    - Take the input go through each step according to the plan
    - You will get a output that must be different from the expected output.

### Debugging Notes
- Based on this simulation detect any of the following cases:
    - Plan is wrong
    - Plan is correct but plan to code generation is wrong.
- Finally, discuss how to correct this code.

### Modified Code

```{fence}
# Your corrected code, with comments explaining each correction.
```

--------
**Important Instructions:**
- Strictly follow the instructions.
- Do not add testing code for example assert statement in your code.
- Do not be overconfident that the generated code is correct. It is wrong.
- The modified **{lang}** code must be enclosed within triple backticks (```) tagged `{fence}`.
- Your response must contain **Simulation with failed test case**, **Debugging Notes**,
and **Modified Code** section.
{std_input_prompt}"""
