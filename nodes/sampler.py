from __future__ import annotations

import dataclasses
import logging
import os
import random as random_module
from abc import ABC, abstractproperty
from collections.abc import Iterable
from hashlib import sha256
from itertools import cycle as itertools_cycle
from pathlib import Path
from typing import cast

from dynamicprompts.commands import VariantCommand, WildcardCommand
from dynamicprompts.enums import SamplingMethod
from dynamicprompts.samplers import CombinatorialSampler, RandomSampler
from dynamicprompts.samplers.cycle import CyclicalSampler, _get_combination_samples
from dynamicprompts.samplers.utils import get_wildcard_not_found_fallback, wildcard_to_variant
from dynamicprompts.sampling_context import SamplingContext
from dynamicprompts.sampling_result import SamplingResult
from dynamicprompts.types import ResultGen, to_result_gen
from dynamicprompts.utils import next_sampler_next_value
from dynamicprompts.wildcards import WildcardManager

logger = logging.getLogger(__name__)


def _split_by_pipe_at_depth0(content: str) -> list[str]:
    """Split content by | at brace depth 0, respecting nested {…} blocks."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in content:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth -= 1
            current.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def _preprocess_shuffle_syntax(text: str, rand: random_module.Random) -> str:
    """Replace {& …} variant markers with {@ …} with options shuffled.

    Used when the global sampling mode is *not* shuffle so that the standard
    CyclicalSampler cycles through an already-shuffled option list.
    """
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i : i + 2] == "{&":
            # Find the matching closing brace.
            depth = 1
            j = i + 2
            while j < len(text) and depth > 0:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            content = text[i + 2 : j - 1]
            options = _split_by_pipe_at_depth0(content)
            rand.shuffle(options)
            result.append("{@" + "|".join(options) + "}")
            i = j
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


class ShuffleSampler(CyclicalSampler):
    """Cycles through variant/wildcard values in a seeded-random shuffled order.

    The shuffle permutation is determined once when the generator is first
    advanced (using the seeded ``context.rand``), and the same order repeats
    on every subsequent cycle.
    """

    def _get_variant(
        self,
        command: VariantCommand,
        sampling_context: SamplingContext,
    ) -> ResultGen:
        is_wildcard_variant = len(command.values) == 1 and isinstance(
            command.values[0], WildcardCommand
        )

        if len(command.values) == 0:
            return
        elif is_wildcard_variant:
            wildcard_command = cast(WildcardCommand, command.values[0])
            wildcard_variant = wildcard_to_variant(
                wildcard_command,
                context=sampling_context,
                min_bound=command.min_bound,
                max_bound=command.max_bound,
                separator=command.separator,
            )
            yield from self._get_variant(wildcard_variant, sampling_context)
        else:
            command = command.adjust_range()

            # Shuffle the variant list once using the seeded RNG.
            shuffled_variants = list(command.variants)
            sampling_context.rand.shuffle(shuffled_variants)
            shuffled_command = dataclasses.replace(command, variants=shuffled_variants)

            combinations = (
                combo
                for bound in range(shuffled_command.min_bound, shuffled_command.max_bound + 1)
                for combo in shuffled_command.get_value_combinations(bound)
            )
            combination_samplers = (
                (
                    SamplingResult.joined(sample, separator=command.separator)
                    for sample in _get_combination_samples(combo, sampling_context)
                )
                for combo in combinations
            )
            while True:
                yield from next_sampler_next_value(itertools_cycle(combination_samplers))

    def _get_wildcard(
        self,
        command: WildcardCommand,
        context: SamplingContext,
    ) -> ResultGen:
        wc_values = context.wildcard_manager.get_values(command.wildcard)
        new_context = context.with_variables(command.variables).with_sampling_method(
            SamplingMethod.CYCLICAL
        )
        if len(wc_values) == 0:
            yield from get_wildcard_not_found_fallback(command, new_context)
            return

        # Shuffle the wildcard values once using the seeded RNG.
        all_values = list(wc_values.iterate_string_values_weighted())
        context.rand.shuffle(all_values)

        value_samplers = (new_context.sample_prompts(val) for val in all_values)
        value_result_gens = [to_result_gen(val) for val in value_samplers]
        yield from next_sampler_next_value(value_result_gens)


class DPAbstractSamplerNodeAdvanced(ABC):
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "display": "number"}),
                "sampling_mode": (["random", "combinatorial", "shuffle"], {"default": "random"}),
                "refresh_mode": (["always", "on_value_change"], {"default": "on_value_change"}),
                "console_output": (["off", "new_prompt", "debug"], {"default": "off"})
            },
        }

    @classmethod
    def IS_CHANGED(cls, text: str, seed: int, sampling_mode: str, refresh_mode: str, console_output: str):
        if refresh_mode == "always":
            # Force re-evaluation of the node, (original default behavior)
            return float("NaN")
        else:
            # Re-evaluate only in case of change in the input values
            m = sha256()
            m.update(str(seed).encode())
            m.update(sampling_mode.encode())
            m.update(refresh_mode.encode())
            m.update(console_output.encode())
            m.update("".encode() if text is None else text.encode())
            folder = cls._find_wildcards_folder()
            m.update(str(cls._get_wildcards_mtime(folder)).encode())
            if (console_output == "debug"):
                truncated_text = (text[:50] + '...') if len(text) > 50 else text
                print(f"DPAbstractSamplerNode.IS_CHANGED: hash={m.hexdigest()} <- {{seed={str(seed)}, sampling_mode={sampling_mode}, refresh_mode={refresh_mode}, console_output={console_output}, text (truncated): \"{truncated_text}\"}}")
            return m.hexdigest()

    RETURN_TYPES = ("STRING",)
    FUNCTION = "get_prompt"
    CATEGORY = "Dynamic Prompts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialise_wildcard_manager()
        self._sampling_mode = ""

    @staticmethod
    def _get_wildcards_mtime(folder: Path) -> int:
        """Return the most recent modification time (ns) of any file under folder, or 0 if none."""
        most_recent = 0
        for root, dirs, files in os.walk(folder):
            for filename in files:
                try:
                    mtime = os.stat(os.path.join(root, filename)).st_mtime_ns
                    if mtime > most_recent:
                        most_recent = mtime
                except OSError:
                    pass
        return most_recent

    def _initialise_wildcard_manager(self):
        """
        Initialise the wildcard manager.
        """
        wildcards_folder = self._find_wildcards_folder()
        print(f"Loading wildcard manager from {wildcards_folder}")
        self._wildcard_manager = WildcardManager(path=wildcards_folder)
        self._wildcard_manager._sort_wildcards = False
        self._wildcard_manager.clear_cache()
        self._current_prompt = None
        self._wildcard_mtime = self._get_wildcards_mtime(wildcards_folder)

    def _reload_wildcards_if_changed(self) -> bool:
        """Reload the wildcard manager if any wildcard files have changed on disk. Returns True if reloaded."""
        folder = self._find_wildcards_folder()
        current_mtime = self._get_wildcards_mtime(folder)
        if current_mtime != self._wildcard_mtime:
            changed_file = None
            for root, dirs, files in os.walk(folder):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    try:
                        if os.stat(filepath).st_mtime_ns == current_mtime:
                            changed_file = filepath
                            break
                    except OSError:
                        pass
                if changed_file:
                    break
            print(f"Wildcard file changed (stored={self._wildcard_mtime}, current={current_mtime}), reloading: {changed_file}")
            self._initialise_wildcard_manager()
            return True
        return False

    @staticmethod
    def _find_wildcards_folder() -> Path | None:
        """
        Find the wildcards folder.
        First look in the comfy_dynamicprompts folder, then in the custom_nodes folder, then in the Comfui base folder.
        """
        from folder_paths import base_path, folder_names_and_paths

        wildcard_path = Path(base_path) / "wildcards"

        if wildcard_path.exists():
            return wildcard_path

        extension_path = (
            Path(folder_names_and_paths["custom_nodes"][0][0])
            / "comfyui-dynamicprompts"
        )
        wildcard_path = extension_path / "wildcards"
        wildcard_path.mkdir(parents=True, exist_ok=True)

        return wildcard_path

    def _get_next_prompt(self, prompts: Iterable[str], current_prompt: str, sampling_mode:str) -> str:
        """
        Get the next prompt from the prompts generator.
        """
        try:
            return next(prompts)
        except (StopIteration, RuntimeError):
            self._prompts = self.context(sampling_mode).sample_prompts(current_prompt)
            try:
                return next(self._prompts)
            except StopIteration:
                logger.exception("No more prompts to generate!")
                return ""

    def has_prompt_changed(self, text: str) -> bool:
        """
        Check if the prompt has changed.
        """
        return self._current_prompt != text

    def _preprocess_prompt(self, text: str, sampling_mode: str) -> str:
        """Handle {& …} shuffle-variant syntax before passing to the library.

        In shuffle mode the ShuffleSampler handles the shuffling itself, so
        {& …} is simply rewritten as {@ …} (cyclical).  In other modes the
        options are shuffled here at parse-time so the standard CyclicalSampler
        can cycle through the pre-shuffled order.
        """
        if "{&" not in text:
            return text
        if sampling_mode == "shuffle":
            return text.replace("{&", "{@")
        return _preprocess_shuffle_syntax(text, self.context(sampling_mode).rand)

    def context(self, sampling_mode: str) -> SamplingContext:
        if sampling_mode == "random":
            return SamplingContext(
                wildcard_manager=self._wildcard_manager,
                default_sampling_method=SamplingMethod.RANDOM,
            )
        elif sampling_mode == "combinatorial":
            return SamplingContext(
                wildcard_manager=self._wildcard_manager,
                default_sampling_method=SamplingMethod.COMBINATORIAL,
            )
        elif sampling_mode == "shuffle":
            return SamplingContext(
                wildcard_manager=self._wildcard_manager,
                default_sampling_method=SamplingMethod.CYCLICAL,
                samplers={
                    SamplingMethod.RANDOM: RandomSampler(),
                    SamplingMethod.COMBINATORIAL: CombinatorialSampler(),
                    SamplingMethod.CYCLICAL: ShuffleSampler(),
                },
            )

    def get_prompt(self, text: str, seed: int, sampling_mode: str, refresh_mode: str, console_output: str) -> tuple[str]:
        """
        Main entrypoint for this node.
        Using the sampling context, generate a new prompt.
        """

        self._reload_wildcards_if_changed()
        if self._sampling_mode != sampling_mode:
            self._sampling_mode = sampling_mode
            self._initialise_wildcard_manager()

        if seed > 0:
            self.context(sampling_mode).rand.seed(seed)

        if text.strip() == "":
            return ("",)

        if self.has_prompt_changed(text):
            self._current_prompt = text
            processed = self._preprocess_prompt(text, sampling_mode)
            self._prompts = self.context(sampling_mode).sample_prompts(processed)

        if self._prompts is None:
            logger.exception("Something went wrong. Prompts is None!")
            return ("",)

        if self._current_prompt is None:
            logger.exception("Something went wrong. Current prompt is None!")
            return ("",)

        new_prompt = self._get_next_prompt(self._prompts, self._current_prompt, sampling_mode)
        if (console_output != "off"):
            print(f"New prompt: {new_prompt}")

        return (str(new_prompt),)

class DPAbstractSamplerNode(DPAbstractSamplerNodeAdvanced):
    DEFAULT_SAMPLING_MODE = "random"
    DEFAULT_REFRESH_MODE = "on_value_change"
    DEFAULT_CONSOLE_OUTPUT = "off"

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "display": "number"})
            },
        }

    @classmethod
    def IS_CHANGED(cls, text: str, seed: int):
        return super().IS_CHANGED(text, seed, sampling_mode=cls.DEFAULT_SAMPLING_MODE, refresh_mode=cls.DEFAULT_REFRESH_MODE, console_output=cls.DEFAULT_CONSOLE_OUTPUT)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_prompt(self, text: str, seed: int) -> tuple[str]:
        return super().get_prompt(text, seed, sampling_mode=self.DEFAULT_SAMPLING_MODE, refresh_mode=self.DEFAULT_SAMPLING_MODE, console_output=self.DEFAULT_CONSOLE_OUTPUT)
