


#  ……

# ...


MOD_DECOMPOSE_PROMPT = '''
You are acting as a senior software architect and requirements engineer.
Your job is to produce the final flat list of modules (no hierarchy or sub-modules) based on the Functional Requirements (FR) and the Raw Requirement Text (RAW). For each module, you must define its clear boundaries and responsibilities.

Principles:
Information priority: Use FR as the primary source; supplement with RAW only to refine boundaries and rules.
No limit on module count: Aim for high cohesion and low coupling. Simple, closely related capabilities can be merged into one module.
No duplication: A core responsibility must appear in exactly one module.
Traceability: Map each module back to the original requirements, using FR numbers as references.
No invention: Do not introduce functions or external systems that are not specified.

Output Format
Follow this structure exactly, without adding other sections or tables.
Module List (flat)
For each module, use the following card style:

Module 1
Mapped Requirements: FR1, FR3, FR5 … (list all relevant FR numbers)
Inputs:
 Field A: Type (size/range); Description (optional)
 Field B: Type (size/range); Description (optional)
Module Function:
 Brief summary of what the module does (capabilities, responsibilities, boundaries). Avoid implementation details.
Outputs:
 Field X: Type (size/range); Destination/Usage (optional)
 Field Y: Type (size/range); Destination/Usage (optional)

Module 2
...

Partitioning Rationale (text)
 Summarize the key basis for this partitioning: main data objects, business capabilities, and drivers of change (e.g., evolving rules, scaling points).

Collaboration & Call Relationships (text)
 Collaboration (high-level): How modules work together to achieve the main business processes.
 Call relationships (directional): Concise "who calls whom" statements (e.g., "A calls B to fetch …", "C notifies D …").
'''

MOD_DECOMPOSE_INPUT = '''
Raw Requirement Text: {raw}
Functional Requirements: {fr}
'''


# ```

# ```

# ```
# Step 2：……
# ```
DEPENDCY_MAP_PROMPT = '''
You are a system architect / integration designer.
Your job is to map module dependencies based on the given requirements and module partitioning results. The goal is to make dependencies explicit—covering calls, data flows, and control flows—and to provide a concise overview of how the modules work together as a whole.

Inputs you will receive
1. User's original requirement text
2. Functional requirements list (FRs)
3. Module list with responsibilities (derived from the requirements)

What you need to do
1. Analyze dependencies
 Use each module's Inputs/Outputs, Functions, and Collaboration description to identify what it needs from other modules (services, data, control).
2. Check consistency
 Every dependency must reference a valid module from the list.
 No self-dependencies are allowed.
 Dependency types must match the module's defined Inputs/Outputs and collaboration text.
 Major interactions must align with the Collaboration & Call Relationships section.
3. Document the relationships
 Starting from the user's input data, explain step by step how the modules collaborate until the business process closes the loop.
 Highlight key data being passed, transformed, or consumed along the way.
 Avoid implementation details.

Output format
Part 1: External dependencies (per module)
For each module, list what it needs from other modules and why.
If a module has no dependencies, explicitly state so. Keep the style short and plain.
Example:
[Module 1]
- From Module 2: needs … (purpose/usage, ≤40 chars)
- From Module 3: needs … (purpose/usage, ≤40 chars)

[Module B2]
- No external dependencies

Part 2: Closed-loop collaboration (stepwise flow)
Start by listing the user-facing input fields (from Stage 1 "Inputs" that come from user/external sources).
Then describe how the modules interact step by step until the business process is complete. Each step should be concise, showing which module calls which, and what data is passed/produced/consumed.
Example:
User Input: <Field1>, <Field2> … (Source: User/External)  
Step 1: <Module A> → <Module B>: purpose / data / output(≤80 chars)
Step 2: <Module B> → <Module C>: …
Step N: … (closure, e.g., persistence complete / notification delivered)

If there are multiple main flows, label them as Main Flow A, Main Flow B, etc. Keep it compact and readable.
'''

DEPENDCY_MAP_INPUT = '''
Raw Requirement Text: {raw}
Functional Requirements: {fr}
Module Partitioning and Rationale: {modules}
'''


INTERFACE_DEFINE_PROMPT = '''
You are a system architect and interface designer.
Your job is to define the interfaces and data exchanges between modules, using the provided requirements, module breakdown, and dependency relationships.

What you'll work with
 Functional requirements
 Tech stack requirements (language, framework, coding style)
 Module list with partitioning rationale
 High-level dependencies and call relationships between modules
 
Guidelines

1.Stick to the given modules — no renaming, no adding new ones. Interfaces must align with dependencies and the main process flow.
2.Name each module using a verb-object style function name that reflects its responsibility (e.g., createOrder, generateReport). Use snake_case for Python/Rust. Use lowerCamelCase for Java/Kotlin/TypeScript/Go/C#.
3.For each module, define inputs and outputs.
 Specify field type and size/range (e.g., string(1-128), int[0,1e6], ISO8601 datetime, decimal(10,2), UUID, email, enum{A|B|C}).
 Add a short note or usage/destination if needed.
4.Provide a brief description of what the module does (responsibility, scope, boundaries). Keep it at the capability level — no implementation details.
5.Write a function signature in the target language, based on the tech stack. Include parameters and return type. Use async, generics, annotations, etc. if they are standard in that language.
6.Based on the technology stack requirements, provide the programming languages, frameworks, libraries, tools, methods, and other technologies used by the module, for example: ["Python", "NumPy"].
7.Keep everything short, precise, and easy to review. 
'''

INTERFACE_DEFINE_INPUT = '''
Functional Requirements: {fr}
Tech Stack Requirements: {tech_stack}
Module Partitioning and Rationale: {modules}
Inter-Module Dependencies: {dependency}
'''



NON_FUNCTION_PROMPT = '''
You are a system architecture and non-functional design expert. Your task is to supplement the possible non-functional requirements for each module based on the user's original requirements, the module design results, and the given set of non-functional requirements:
 nonfunctional_notes: Non-functional design points corresponding to this module (e.g., test cases and test strategies, time complexity, space complexity, security and privacy requirements, concurrency requirements, etc.).
 
 Context Available
 Original user requirements
 Non-functional requirements
 Module design results
 
Rules for the Output
1) Module relevance: For each module, select only those non-functional requirements from the given set that are directly relevant to its design and its upstream/downstream responsibilities. Avoid writing generic or system-wide summaries.
2) Strict mapping: You may only reference the non-functional requirements explicitly provided in the input. Do not alter, rephrase, or invent any new requirements.
3) Module alignment: The output must correspond one-to-one with the input module IDs. Do not add or omit any modules.
4) Allow empty: If no relevant non-functional requirements can be mapped for a module, set nonfunctional_notes to "".
'''

NON_FUNCTION_INPUT = '''
Raw Requirement Text: {raw}
Non-Functional Requirements: {nfr}
Module Design Results: {modules}
'''


# MODULE_DESIGN_PROMPT = '''
# You are a system architect and requirements engineer, responsible for designing the software system based on the provided user requirement analysis. Your task is to transform requirements into clear module partitions and define the interactions and collaboration between modules. Ultimately, you need to output the detailed design for each module, including inputs and outputs, non-functional requirements, tech stack, and other relevant information, while also defining the collaboration relationships between the modules.

# Principles:
# 1. Module Design and Interface Definition
# - No limit on module count: Aim for high cohesion and low coupling. Simple, closely related capabilities can be merged into one module.
# - No invention: Do not introduce functions or external systems that are not specified.
# - For each module, define inputs and outputs. Enumerate ALL admissible data types for each field.
# - Provide a brief description of what the module does (responsibility, scope, boundaries). Keep it at the capability level — no implementation details.
# - Write a function signature for each module in the target programming language.
# - Supplement the possible non-functional requirements for each module based on the requirements.

# 2. Module Collaboration and Call Relationships
# - Analyze dependencies: Use each module's Inputs/Outputs, Functions, and Collaboration description to identify what it needs from other modules (services, data, control).
# - Starting from the user's input data, explain step by step how the modules collaborate until the business process closes the loop. Highlight key data being passed, transformed, or consumed along the way. Avoid implementation details.
# '''


MODULE_DESIGN_PROMPT = '''
You are a system architect engineer. Your task is to design the appropriate plan to solve a given problem using the **{lang}** programming language.
'''


TOOL_INPUT = '''
You have access to the tool:
- web_search: Performs a duckduckgo web search based on your query (think a Google search) then returns the top search results.

--------
- Decide whether web searching is necessary in order to gather more information about:
  - Suitable algorithms for solving the problem
  - Relevant {lang} libraries and functions
  - Best-practice approaches used in similar tasks
'''


MODULE_DESIGN_INPUT = '''
## Problem
{prompt}

## Analysis
{analysis}


**Expected Output:**

Your response must be structured as follows:

### Algorithm, libraries and functions to solve problem
- Write down the algorithm, libraries and functions, which are well suited for problem
- Give some tutorials to about the algorithm, libraries and functions for example:
    - How to approach these type of algorithm, libraries and functions
    - Important things to consider

### Plan
- Write down a detailed, step-by-step plan to solve the **original problem**.

--------
**Important Instruction:**
- Strictly follow the instructions.
- Do not generate code.
'''


MODULE_REDESIGN_INPUT = '''
## Problem
{prompt}

## Analysis
{analysis}

## Lessons from Previous Failed Attempts
{failure_experience}


**Expected Output:**

Your response must be structured as follows:

### Algorithm, libraries and functions to solve problem
- Reconsider the algorithm, libraries and functions in light of the failure lessons above.
- Explain the important edge cases, invariants, and pitfalls that the new design must handle.

### Plan
- Write down a new detailed, step-by-step plan to solve the **original problem**.
- Explicitly avoid the design defects identified by the previous failed attempts.
- Do not merely repeat a previously failed plan.

--------
**Important Instruction:**
- Treat the requirement analysis as fixed; redesign the solution rather than re-analyzing the requirements.
- Strictly follow the instructions.
- Do not generate code.
'''


FAILURE_FEEDBACK_SYSTEM = '''
You are a failure-retrospective agent for {lang} problem solving. Analyze why an attempted
solution still failed after its debugging trajectory, with emphasis on defects in the code
design rather than isolated syntax or implementation mistakes. Produce task-specific lessons
that can directly guide the next design. Do not generate code.
'''


FAILURE_FEEDBACK_INPUT = '''
## Problem
{prompt}

## Fixed Requirement Analysis
{analysis}

## Previous Code Design
{design}

## Failure Trajectory
{failure_trajectory}

**Expected Output:**

### Design Defects
- Identify incorrect assumptions, missing cases, invalid algorithm choices, or weak invariants in the design.
- Distinguish design defects from implementation-only symptoms.

### Evidence from the Failure Trajectory
- Connect each important conclusion to concrete code, execution-trace, or test-failure evidence.

### Lessons for the Next Design
- Give concise and actionable constraints for the next overall design.
- State what must change and what failed approaches must not be repeated.

--------
**Important Instructions:**
- Focus only on this task instance and the evidence provided.
- Do not redo the requirement analysis.
- Do not generate code or a complete replacement plan.
'''


SMOL_CODE_DESIGN = '''
Your task is to design the appropriate plan to solve a given problem using the **python** programming language.

## Problem
{raw}

## Analysis
{analysis}

**Expected Output:**

Your response must be structured as follows:

### Algorithm, libraries and functions to solve problem
- Write down the algorithm, libraries and functions, which are well suited for problem
- Give some tutorials to about the algorithm, libraries and functions for example:
    - How to approach these type of algorithm, libraries and functions
    - Important things to consider

### Plan
- Write down a detailed, step-by-step plan to solve the **original problem**.

--------
**Important Instruction:**
- Strictly follow the instructions.
- Do not generate code.
- Decide whether web searching is necessary in order to gather more information about:
  - Suitable algorithms for solving the problem
  - Relevant Python libraries and functions
  - Best-practice approaches used in similar tasks
'''



SIMULATION_SYSTEM = '''
You are a programmer tasked with verifying a plan to solve a given problem using the **{lang}** programming language.
'''

SIMULATION_INPUT = '''
## Problem
{prompt}

## Plan
{design}

**Expected Output:**

Your response must be structured as follows:

### Simulation

- Take a sample input and apply plan step by step to get the output. Do not generate code do it manually by applying reasoning.
- Compare the generated output with the sample output to verify if your plan works as expected.

### Plan Evaluation

- If the simulation is successful write **No Need to Modify Plan**.
- Otherwise write **Plan Modification Needed**.
'''



REFINEMENT_SYSTEM = '''
You are a programmer tasked with generating an appropriate plan to solve a given problem using the **{lang}** programming language. You already have a wrong plan. Correct it so that it can generate a correct plan.
'''

REFINEMENT_INPUT = '''
## Problem
{prompt}

## Wrong Plan
{wrong_plan}

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
'''
