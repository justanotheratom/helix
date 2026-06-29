from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dspy
from gepa.core.adapter import ProposalFn
from gepa.strategies.instruction_proposal import InstructionProposalSignature


def _instruction_proposal_placeholders() -> tuple[str, str]:
    template = getattr(InstructionProposalSignature, "default_prompt_template", "") or ""
    if "<curr_param>" in template and "<side_info>" in template:
        return "<curr_param>", "<side_info>"
    return "<curr_instructions>", "<inputs_outputs_feedback>"


def _build_generalizing_prompt_template() -> str:
    current_instruction_placeholder, side_info_placeholder = _instruction_proposal_placeholders()
    return f"""You are an expert at reflecting on task performance and proposing prompt improvements.

CRITICAL GUIDELINES FOR PROMPT EVOLUTION:
1. Abstract patterns, not examples. Identify general reasoning patterns, strategies, and principles from the feedback.
2. Meta-level strategies. Focus on high-level problem-solving approaches that generalize across instances.
3. Avoid memorization. Never include example-specific names, numbers, brands, or verbatim content from the dataset.
4. General instructions only. Describe the TYPE of reasoning needed, not example-specific facts.
5. Allowed domain generalizations. You MAY include high-confidence, broadly applicable domain facts that improve generalization
   (e.g., common ingredient classes, additive-code families, or processing-derived risks like extracts containing alcohol),
   but avoid long enumerations and anything tied to a specific example.
6. Ambiguity discipline. If a rule depends on typical or common sourcing, keep outcomes as uncertain unless the input explicitly states a disallowed source.
7. Structural improvements. Improve the structure of reasoning and decision rules when recurring errors are observed.
8. Minimal edits. Preserve good rules and add only what fixes recurring errors.

I provided an assistant with the following instructions to perform a task for me:
```
{current_instruction_placeholder}
```

The following are examples of different task inputs provided to the assistant along with the assistant's response for each of them, and some feedback on how the assistant's response could be better:
```
{side_info_placeholder}
```

Your task is to write a new instruction for the assistant. Do not copy examples or include data-specific lists.
Provide the new instructions within ``` blocks."""


GENERALIZING_PROMPT_TEMPLATE = _build_generalizing_prompt_template()


class GeneralizingInstructionProposer(ProposalFn):
    """Custom instruction proposer that encourages generalized, non-memorized prompts.

    If `log_dir` is provided, dumps each reflection call to
    `{log_dir}/reflection/iter_{N}.json` capturing the rendered prompt,
    raw LM response, parsed proposal, and reflective_dataset. This is the
    only place GEPA's reflection signal is observable post-hoc — the
    default gepa_state.bin records scores but not what the reflection LM
    actually saw or wrote.
    """

    def __init__(
        self,
        prompt_template: str | None = None,
        log_dir: str | Path | None = None,
    ) -> None:
        self.prompt_template = prompt_template or GENERALIZING_PROMPT_TEMPLATE
        InstructionProposalSignature.validate_prompt_template(self.prompt_template)
        self.log_dir = Path(log_dir) / "reflection" if log_dir else None
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        self._call_idx = 0

    def __call__(
        self,
        candidate: dict[str, str],
        reflective_dataset: dict[str, list[dict[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        reflection_lm = dspy.settings.lm
        if reflection_lm is None:
            raise ValueError("GeneralizingInstructionProposer requires dspy.settings.lm to be set.")

        new_texts: dict[str, str] = {}
        for name in components_to_update:
            if name not in candidate or name not in reflective_dataset:
                continue
            dataset_with_feedback = reflective_dataset.get(name, [])
            if not dataset_with_feedback:
                continue

            base_instruction = candidate[name]
            input_dict = {
                "current_instruction_doc": base_instruction,
                "dataset_with_feedback": dataset_with_feedback,
                "prompt_template": self.prompt_template,
            }

            captured: dict[str, Any] = {"raw_response": None}

            def logging_lm(x, captured=captured):
                resp = reflection_lm(x)
                out = resp[0] if isinstance(resp, list) and resp else resp
                # Reasoning models (e.g. deepseek-v4-pro) may return
                # {"content": "...", "reasoning_content": "..."} instead of
                # a plain string. Downstream code calls .strip() on this.
                if isinstance(out, dict):
                    out = out.get("content") or out.get("text") or ""
                captured["raw_response"] = out
                return out

            result = InstructionProposalSignature.run(lm=logging_lm, input_dict=input_dict)
            new_instruction = result.get("new_instruction", "")
            if isinstance(new_instruction, str) and new_instruction.strip():
                new_texts[name] = new_instruction.strip()

            if self.log_dir is not None:
                try:
                    rendered_prompt = InstructionProposalSignature.prompt_renderer(input_dict)
                except Exception as e:
                    rendered_prompt = f"<prompt_renderer failed: {type(e).__name__}: {e}>"
                record = {
                    "call_idx": self._call_idx,
                    "component": name,
                    "current_instruction": base_instruction,
                    "reflective_dataset": dataset_with_feedback,
                    "rendered_prompt": rendered_prompt,
                    "raw_response": captured["raw_response"],
                    "new_instruction": new_instruction,
                }
                out = self.log_dir / f"iter_{self._call_idx:03d}_{name.replace('.', '_')}.json"
                try:
                    out.write_text(json.dumps(record, indent=2, default=str))
                except Exception as e:
                    print(f"[instruction_proposer] failed to dump reflection log: {e}")
                self._call_idx += 1

        return new_texts
