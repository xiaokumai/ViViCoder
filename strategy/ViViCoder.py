"""Executable control loop for the ViViCoder method described in ``main.tex``.

The implementation follows the paper's ``ViViCoder`` section as follows:

* ``_run_vivicoder`` implements the Generation Stream
  ``G_req -> G_dsgn -> G_code`` and the Design Verifier.
* ``_debug_with_icecream`` implements the Trace-Driven Debugging operator
  ``Phi_trace`` used for implementation-level repair.
* ``failure_feedback`` plus the next outer attempt implement design-level
  escalation through the structured feedback ``epsilon_d``.
* ``_debug_pbt_with_icecream`` implements the Requirement Validator, including
  the public-test regression checkpoint described in the paper.

Comments below cite the corresponding paper subsection or displayed equation.
They document the method-level control flow; imported agent implementations
contain the prompt-level details of each specialized agent.
"""

from utils.config_log import tracer, config
from requimentAnal.analysis import analysis
from HighLevel_Design.overall_design import overall_design, simulate, refine
from HighLevel_Design.failure_feedback import failure_feedback
from Coding.coding import code_generation
from utils.vivicoder_runner import evaluate_sample_io
from debug.debugging import debug_code, add_debug_code
from tester.test import generate_test, run_test
import json
from loguru import logger
from utils.modules_text import filter_assert_lines
from HighLevel_Design.tool import DuckDuckGoSearchTool
from value_show.show_value import show_value, run_ic
from utils.local_runner import parse_response
from strategy.vanilla import vanilla
from utils.language import get_language, language_fence, uses_standard_input


def process_test_log(test_logs: str):
    """Reduce runner output to the public-test failures used for repair.

    Paper reference: ``Design Verifier`` defines the public suite ``T_pub`` as
    the first verification signal.  This adapter keeps syntax errors intact and
    extracts failing assertions so that ``G_fix`` receives that signal without
    unrelated runner output.
    """
    # A syntax failure has no meaningful assertion/trace to extract, so it is
    # forwarded verbatim to the syntax-repair branch of ``Phi_trace``.
    if 'Syntax Error' in test_logs:
        return test_logs

    # For function-style benchmarks, retain precisely the failed public-test
    # assertions that instantiate ``T_pub`` in the Design Verifier subsection.
    failed_test_cases = []
    for test_log in test_logs.splitlines():
        if test_log.startswith("Failed"):
            failed_test_cases.append(test_log[test_log.index("assert"):])

    failed_test_cases_str = "\n".join(failed_test_cases)
    return f"### Test Cases where the generated code failed to generate the expected output:\n{failed_test_cases_str}"


@tracer
def check_sample_io(question: dict, code: str):
    """Execute candidate ``code`` against the paper's public suite ``T_pub``.

    Paper reference: ``Design Verifier``,
    ``c_ver = Phi_trace(c, d, T_pub)``.  The function returns the pass flag,
    normalized feedback consumed by the repair agent, and failed cases needed
    to reproduce concrete runtime traces.
    """
    # ``evaluate_sample_io`` is the concrete ``Exec(c, T_pub)`` operation.
    passed, details, falied = evaluate_sample_io(question, code)

    # Standard-input tasks already expose a structured failure block.  Other
    # function-style tasks are reduced to failed assertions by the adapter
    # above; EvoCodeBench retains its repository-level diagnostic format.
    dataset_name = config.get("dataset", {}).get("name", "humaneval")
    if uses_standard_input(question):
        details = details[details.find("## Tests failed:"):]
    elif dataset_name != 'evocodebench':
        details = process_test_log(details)

    return passed, details, falied
    
# Paper references: ``Trace-Driven Debugging`` bounds local repairs by
# N_debug, while ``Design Verifier`` bounds complete design/implementation
# cycles by N_attempt.  The experiment section uses five for both by default.
max_debug_attempt = config['debug']
max_attempt = config['attempt']


def _debug_with_icecream(
    question,
    prompt,
    design,
    code,
    test_log,
    failed,
    failure_trajectory=None,
):
    """Apply implementation-level trace-driven repair for one fixed design.

    Paper reference: ``Trace-Driven Debugging``, especially
    ``c_(i+1) = G_fix(c_i, d, Exec(G_inj(c_i), T))``.  ``show_value`` is the
    concrete ``G_inj`` instrumentation step, ``run_ic`` executes the probes,
    and ``debug_code`` is ``G_fix``.  The caller owns ``d`` and never changes it
    inside this loop, matching the paper's fixed-design repair constraint.

    ``failure_trajectory`` records the chronological implementation and runtime
    evidence later summarized as ``H_trace`` for design-level escalation.
    """
    passed = False
    for debug_attempt in range(1, max_debug_attempt + 1):
        # G_inj(c_i): ask the instrumentation agent to expose intermediate
        # values in the current implementation.
        ic_code = show_value(question, prompt, code, test_log)

        if 'Syntax Error' in test_log:
            # Non-executable programs cannot produce runtime values.  Preserve
            # the compiler/parser feedback and invoke G_fix without trace mode.
            debug_feedback = test_log
            code = debug_code(question, prompt, design, code, test_log, False)
        else:
            # Exec(G_inj(c_i), T_pub): run the instrumented implementation on
            # the failed cases and feed its concrete observations to G_fix.
            debug_feedback = run_ic(question, code, ic_code, failed)
            code = debug_code(
                question, prompt, design, code, debug_feedback, True
            )

        # Re-run T_pub after every repair; a passing c_i becomes c_ver and ends
        # the Design Verifier's implementation-level loop.
        passed, test_log, failed = check_sample_io(question, code)
        if failure_trajectory is not None:
            # This ordered record is the executable counterpart of H_trace in
            # the paper's design-level escalation equation.
            failure_trajectory.append(
                {
                    "stage": "debug",
                    "debug_attempt": debug_attempt,
                    "debug_feedback": debug_feedback,
                    "code_after_debug": code,
                    "passed": passed,
                    "test_log": test_log,
                    "failed_cases": failed,
                }
            )
        if passed:
            break

    return code, passed, test_log, failed


def _check_pbt_with_regression(question: dict, code: str, pbt_code: str):
    """Evaluate the Requirement Validator's combined validation gate.

    Paper reference: ``Requirement Validator`` evaluates repairs against
    ``T_pub union T_pbt``.  The suites use different runners here, so their
    conjunction implements the union: a candidate passes only when both the
    generated properties and the public regression anchor pass.
    """
    # T_pub remains active during final validation to prevent a hallucinated or
    # overly restrictive generated property from silently regressing c_ver.
    regression_passed, regression_log, failed = check_sample_io(question, code)
    # T_pbt is generated by G_pbt from the requirement artifact r.
    pbt_passed, pbt_log = run_test(code + '\n\n' + pbt_code)

    # Keep the two failure sources labelled because Phi_trace must decide which
    # suite(s) require probe execution in the next repair step.
    failure_logs = []
    if not pbt_passed:
        failure_logs.append(f"### Generated PBT Failures\n{pbt_log}")
    if not regression_passed:
        failure_logs.append(f"### Public Sample Regression Failures\n{regression_log}")

    combined_log = "\n\n".join(failure_logs)
    return (
        pbt_passed and regression_passed,
        pbt_passed,
        regression_passed,
        combined_log,
        failed,
    )


def _debug_pbt_with_icecream(
    question: dict,
    prompt: str,
    design: str,
    code: str,
    pbt_code: str,
):
    """Run Requirement Validator repairs with a public-test checkpoint.

    Paper reference: the final paragraph of ``Requirement Validator``.  It
    applies ``Phi_trace`` to counterexamples from ``T_pub union T_pbt``, keeps
    ``d_ver`` fixed, updates the checkpoint whenever ``T_pub`` passes, and
    returns the latest checkpoint when ``N_debug`` is exhausted.  Consequently
    this function intentionally performs no design-level escalation.
    """
    # c_ver is known to pass T_pub when entering this stage and therefore forms
    # the initial regression-safe checkpoint specified in the paper.
    latest_regression_passing_code = code
    (
        all_passed,
        pbt_passed,
        regression_passed,
        test_log,
        failed,
    ) = _check_pbt_with_regression(question, code, pbt_code)

    if all_passed:
        return code

    for _ in range(1, max_debug_attempt + 1):
        # Reuse the same G_inj component as the Design Verifier, as required by
        # the shared Phi_trace operator in the Verification/Validation Stream.
        ic_code = show_value(question, prompt, code, test_log)

        if 'Syntax Error' in test_log:
            # Syntax failures are repaired directly because instrumented code
            # cannot be executed until parsing succeeds.
            debug_feedback = test_log
            code = debug_code(
                question, prompt, design, code, debug_feedback, False
            )
        else:
            trace_logs = []
            if not pbt_passed:
                # Execute the injected program with T_pbt to obtain the PBT
                # counterexample trace consumed by G_fix.
                _, pbt_trace = run_test(ic_code + '\n\n' + pbt_code)
                trace_logs.append(
                    f"### Generated PBT Icecream Trace\n{pbt_trace or test_log}"
                )
            if not regression_passed:
                # Execute the injected program on failed T_pub cases so public
                # behavior remains part of the same repair signal.
                regression_trace = run_ic(question, code, ic_code, failed)
                trace_logs.append(
                    f"### Public Sample Icecream Trace\n{regression_trace}"
                )

            debug_feedback = "\n\n".join(trace_logs) or test_log
            # G_fix receives all currently available observations while design
            # d_ver (the ``design`` argument) remains unchanged.
            code = debug_code(
                question, prompt, design, code, debug_feedback, True
            )

        (
            all_passed,
            pbt_passed,
            regression_passed,
            test_log,
            failed,
        ) = _check_pbt_with_regression(question, code, pbt_code)

        if regression_passed:
            # Update the paper's regression checkpoint even if T_pbt still
            # fails; this is the safest candidate to return on budget expiry.
            latest_regression_passing_code = code
        if all_passed:
            return code

    # Requirement validation never escalates to G_dsgn.  On exhaustion, return
    # the latest code known to preserve T_pub exactly as specified in the paper.
    return latest_regression_passing_code


def _run_vivicoder(question: dict, prompt: str, dataset_name: str):
    """Execute ViViCoder's generation, verification, and escalation topology.

    Paper references:

    * ``Generation Stream``: construct ``r``, ``d``, and ``c`` through
      ``G_req``, ``G_dsgn``, and ``G_code``.
    * ``System Architect Agent``: review each draft through data-flow
      simulation and refine it when the review requests modification.
    * ``Design Verifier``: repair against ``T_pub`` for at most ``N_debug``
      steps, then turn ``H_trace`` into ``epsilon_d`` and regenerate from a
      revised design, for at most ``N_attempt`` complete attempts.
    * ``Requirement Validator``: after public verification, generate PBTs and
      validate with a public-test regression anchor.

    ``dataset_name`` is retained in the orchestration signature for dataset-
    specific callers; language and runner selection are derived from
    ``question`` by the helpers used below.
    """
    # K in the System Architect equation is supplied through the bounded search
    # tool shared by the requirement and design agents.
    search_tool = DuckDuckGoSearchTool(max_results=5, rate_limit=2.0)
    language = get_language(question)
    code = ''

    # Generation Stream, stage 1 -- r = G_req(u).  This artifact is produced
    # once and remains the semantic anchor across all design attempts.
    requirement = analysis(prompt, search_tool, language=language)

    # epsilon_d is empty on the first attempt and is populated only after local
    # trace-driven repair exhausts its budget, matching the architect equation.
    failure_experience = None

    for attempt in range(1, max_attempt + 1):
        if failure_experience:
            # Generation Stream, stage 2 -- revise d = G_dsgn(r, K, epsilon_d),
            # using the latest failed trajectory as a negative constraint.
            design = overall_design(
                prompt,
                requirement,
                search_tool,
                failure_experience=failure_experience,
                language=language,
            )
        else:
            # Initial design: d = G_dsgn(r, K, empty epsilon_d).
            design = overall_design(
                prompt, requirement, search_tool, language=language
            )

        # R_sim reviews the draft design by simulating its data flow, as defined
        # in the System Architect subsection.
        simulation = simulate(prompt, design, language=language)

        if "Plan Modification Needed" in simulation and "No Plan Modification Needed" not in simulation:
            # Apply the review feedback to obtain the refined design d that is
            # handed to the developer agent.
            design = refine(prompt, design, simulation, language=language)

        # Generation Stream, stage 3 -- c = G_code(d), conditioned on r so the
        # implementation preserves the analyzed I/O and constraints.
        code = code_generation(question, prompt, design, requirement, search_tool)

        # Design Verifier -- execute the initial c against T_pub before deciding
        # whether Phi_trace is needed.
        passed, test_log, failed = check_sample_io(question, code)
        failure_trajectory = []

        if not passed:
            # Seed H_trace with the initial failed implementation.  Subsequent
            # repaired candidates and observations are appended by Phi_trace.
            failure_trajectory.append(
                {
                    "stage": "initial_generation",
                    "code": code,
                    "passed": passed,
                    "test_log": test_log,
                    "failed_cases": failed,
                }
            )
            code, passed, test_log, failed = _debug_with_icecream(
                question,
                prompt,
                design,
                code,
                test_log,
                failed,
                failure_trajectory=failure_trajectory,
            )

        if passed:
            # The candidate is c_ver; retain its associated current design as
            # d_ver for the Requirement Validator.
            break

        if attempt < max_attempt:
            # Design-level escalation -- G_crit(d, H_trace, T_pub, r) distills
            # the failed trajectory into epsilon_d.  The next loop iteration
            # routes it to G_dsgn and regenerates c from the revised design.
            failure_experience = failure_feedback(
                prompt,
                requirement,
                design,
                failure_trajectory,
                language=language,
            )

    # Requirement Validator -- G_pbt currently emits executable Hypothesis
    # properties, so this realization of T_pbt applies only to Python.  Contest
    # C++/Java tasks retain the verified public/hidden executable-I/O path.
    if passed and language == "python":
        # T_pbt = G_pbt(r): derive candidate behavioral properties from the
        # requirement artifact and the publicly verified implementation.
        pbt_code = generate_test(prompt, requirement, code)
        # Validate against T_pub union T_pbt while keeping d_ver fixed and
        # preserving the latest T_pub-passing regression checkpoint.
        code = _debug_pbt_with_icecream(
            question, prompt, design, code, pbt_code
        )

    return code



@tracer
def ViViCoder(question: dict):
    """Public entry point for the deterministic ViViCoder agent topology.

    Paper reference: ``Multi-Agent Communication``.  The method uses an
    explicit feed-forward generation sequence and conditional verification
    cycles rather than emergent agent routing.  The returned Markdown fence is
    an output adapter and does not alter the generated implementation.
    """
    dataset_name = config.get("dataset", {}).get("name", "humaneval").lower()
    prompt = question['prompt']

    # Delegate all paper-defined state transitions to the explicit controller.
    code = _run_vivicoder(question, prompt, dataset_name)

    # Preserve the benchmark harness's expected language-labelled code block.
    return f'```{language_fence(get_language(question))}\n{code}\n```'
    
    
    

    
