from __future__ import annotations

import inspect
import json
from typing import Any, List

import dspy
from dspy.primitives import Example, Module, Prediction
from dspy.teleprompt.teleprompt import Teleprompter


class RewriteInstructionFromFeedback(dspy.Signature):
    """Improve a DSPy predictor instruction using per-example metric feedback.

    Given the current instruction, a training example, model output, evaluation feedback,
    and history of previous attempts, write a better instruction that generalizes to future examples.

    Rules:
    - Keep the instruction general; do not mention this specific example.
    - Preserve any formatting / schema constraints implied by the task.
    - Learn from previous attempts - avoid repeating approaches that scored poorly.
    - Return only the new instruction text.
    """

    pred_name: str = dspy.InputField(desc="Name of the predictor being optimized.")
    current_instruction: str = dspy.InputField(desc="Current instruction text.")
    example_inputs: str = dspy.InputField(desc="JSON string of the example inputs.")
    model_output: str = dspy.InputField(desc="JSON string of the model output for this example.")
    feedback: str = dspy.InputField(desc="Metric feedback describing what went wrong/right.")
    previous_attempts: str = dspy.InputField(
        desc="JSON list of previous attempts for this example, each with instruction, score, and feedback. Empty list if first attempt."
    )

    new_instruction: str = dspy.OutputField(desc="Improved instruction text.")


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _prediction_to_dict(pred: Any) -> Any:
    if pred is None:
        return None
    if isinstance(pred, Prediction):
        return {k: v for k, v in pred.items()}
    if hasattr(pred, "model_dump"):
        return pred.model_dump()
    if hasattr(pred, "dict"):
        return pred.dict()
    return pred


def _normalize_metric_output(metric_output: Any) -> tuple[float, str]:
    if isinstance(metric_output, (bool, int, float)):
        score = float(metric_output)
        return score, f"This trajectory got a score of {score}."

    if isinstance(metric_output, dict):
        if "score" not in metric_output:
            raise ValueError("Metric returned a dict but it is missing required key 'score'.")
        score = float(metric_output["score"])
        feedback = metric_output.get("feedback")
        if feedback is None:
            feedback = f"This trajectory got a score of {score}."
        return score, str(feedback)

    if isinstance(metric_output, Prediction):
        if not hasattr(metric_output, "score") and "score" not in metric_output:
            raise ValueError("When metric returns dspy.Prediction, it must include a 'score' field.")
        score = float(metric_output["score"] if "score" in metric_output else metric_output.score)
        feedback = None
        if "feedback" in metric_output:
            feedback = metric_output["feedback"]
        elif hasattr(metric_output, "feedback"):
            feedback = getattr(metric_output, "feedback")
        if feedback is None:
            feedback = f"This trajectory got a score of {score}."
        return score, str(feedback)

    raise ValueError("Metric must return a number, dict(score, feedback), or dspy.Prediction(score, feedback).")


class SequentialFeedbackOptimizer(Teleprompter):
    def __init__(
        self,
        *,
        metric,
        reflection_lm,
        max_retries: int = 3,
        perfect_score: float = 1.0,
    ) -> None:
        try:
            inspect.signature(metric).bind(None, None, None, None, None)
        except TypeError as e:
            raise TypeError(
                "SequentialFeedbackOptimizer metric must accept five arguments: "
                "(gold, pred, trace, pred_name, pred_trace)."
            ) from e

        if reflection_lm is None:
            raise ValueError("SequentialFeedbackOptimizer requires reflection_lm to be provided.")

        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")

        self.metric_fn = metric
        self.reflection_lm = reflection_lm
        self.max_retries = max_retries
        self.perfect_score = perfect_score

    def _run_and_evaluate(
        self,
        program: Module,
        example: Example,
        pred_name: str,
        predictor,
    ) -> tuple[Any, Any, float, str]:
        """Run program on example and evaluate the specific predictor."""
        with dspy.context(trace=[]):
            prediction = program(**example.inputs())
            trace = dspy.settings.trace.copy()

        pred_trace = [t for t in trace if t[0] is predictor]
        metric_out = self.metric_fn(example, prediction, trace, pred_name, pred_trace)
        score, feedback = _normalize_metric_output(metric_out)

        return prediction, trace, score, feedback

    def compile(
        self,
        student: Module,
        *,
        trainset: list[Example],
        teacher: Module | None = None,
        valset: list[Example] | None = None,
        **_kwargs,
    ) -> Module:
        if teacher is not None:
            raise ValueError("SequentialFeedbackOptimizer does not support teacher.")
        if trainset is None or len(trainset) == 0:
            raise ValueError("Trainset must be provided and non-empty.")

        program = student.deepcopy()
        rewriter = dspy.Predict(RewriteInstructionFromFeedback)

        history: list[dict[str, Any]] = []
        total_examples = len(trainset)

        for example_idx, example in enumerate(trainset):
            for pred_name, predictor in program.named_predictors():
                # Track attempts for this example/predictor pair
                attempts: List[dict[str, Any]] = []
                best_score = -float("inf")
                best_instruction = predictor.signature.instructions or ""
                starting_instruction = best_instruction

                for attempt_num in range(self.max_retries):
                    current_instruction = predictor.signature.instructions or ""

                    # Run and evaluate
                    prediction, trace, score, feedback = self._run_and_evaluate(
                        program, example, pred_name, predictor
                    )

                    # Record this attempt
                    attempts.append({
                        "attempt": attempt_num + 1,
                        "instruction": current_instruction,
                        "score": score,
                        "feedback": feedback,
                    })

                    # Track best instruction
                    if score > best_score:
                        best_score = score
                        best_instruction = current_instruction

                    # If perfect score achieved, we're done with this example
                    if score >= self.perfect_score:
                        break

                    # If this is the last retry, don't bother generating a new instruction
                    if attempt_num == self.max_retries - 1:
                        break

                    # Generate new instruction using reflection LM
                    with dspy.context(lm=self.reflection_lm):
                        rewritten = rewriter(
                            pred_name=pred_name,
                            current_instruction=current_instruction,
                            example_inputs=_to_json(example.inputs()),
                            model_output=_to_json(_prediction_to_dict(prediction)),
                            feedback=str(feedback),
                            previous_attempts=_to_json(attempts),
                        )

                    new_instruction = str(rewritten.new_instruction).strip()
                    if not new_instruction:
                        raise ValueError("Reflection LM produced an empty new instruction.")

                    # Update predictor with new instruction for next attempt
                    predictor.signature = predictor.signature.with_instructions(new_instruction)

                # After all retries, use the best instruction found
                predictor.signature = predictor.signature.with_instructions(best_instruction)

                # Record history for this example/predictor
                history.append({
                    "example_idx": example_idx,
                    "pred_name": pred_name,
                    "starting_instruction": starting_instruction,
                    "final_instruction": best_instruction,
                    "best_score": best_score,
                    "num_attempts": len(attempts),
                    "attempts": attempts,
                    "achieved_perfect": best_score >= self.perfect_score,
                })

                # Progress logging
                perfect_count = sum(1 for h in history if h["achieved_perfect"])
                avg_score = sum(h["best_score"] for h in history) / len(history)
                print(
                    f"[{example_idx + 1}/{total_examples}] {pred_name}: "
                    f"score={best_score:.3f}, attempts={len(attempts)}, "
                    f"perfect={best_score >= self.perfect_score} | "
                    f"Running: avg={avg_score:.3f}, perfect={perfect_count}/{len(history)}"
                )

        program.sequential_feedback_history = history
        return program
