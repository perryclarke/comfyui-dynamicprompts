"""Run from the repo root with ComfyUI's embedded Python:

    python_embeded\\python.exe -m unittest discover -s tests

The node module is loaded directly so ComfyUI itself is not needed; only
folder_paths is stubbed, pointing at an empty temporary wildcards folder.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


_TMP = tempfile.TemporaryDirectory()  # removed when the test process exits


def _load_sampler_module():
    tmp = _TMP.name
    (Path(tmp) / "wildcards").mkdir()
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.base_path = tmp
    folder_paths.folder_names_and_paths = {"custom_nodes": [[tmp], set()]}
    sys.modules["folder_paths"] = folder_paths
    spec = importlib.util.spec_from_file_location("dp_sampler_under_test", REPO / "nodes" / "sampler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sampler = _load_sampler_module()


def run_node(text: str, mode: str, runs: int, seed: int = 100) -> list[str]:
    """Simulate queuing the same prompt `runs` times with an incrementing seed."""
    node = sampler.DPAbstractSamplerNodeAdvanced()
    return [node.get_prompt(text, seed + i, mode, "on_value_change", "off")[0] for i in range(runs)]


class ImmediateVariablesInStatefulModes(unittest.TestCase):
    PROMPT = "${n=!{1|2|3|4}}A=${n} B=${n}"

    def pairs(self, outs):
        return [tuple(part.split("=")[1] for part in o.split()) for o in outs]

    def test_shuffle_mode_visits_every_value_once_per_cycle(self):
        for seed in (1, 50, 900):
            pairs = self.pairs(run_node(self.PROMPT, "shuffle", 8, seed))
            firsts = [a for a, _ in pairs]
            self.assertEqual(sorted(firsts[:4]), ["1", "2", "3", "4"], pairs)
            self.assertEqual(firsts[4:], firsts[:4], pairs)

    def test_shuffle_mode_every_access_gets_the_same_value(self):
        for a, b in self.pairs(run_node(self.PROMPT, "shuffle", 8)):
            self.assertEqual(a, b)

    def test_random_mode_with_inline_shuffle_visits_every_value(self):
        prompt = "${n=!{&1|2|3|4}}A=${n} B=${n}"
        pairs = self.pairs(run_node(prompt, "random", 4, seed=7))
        self.assertEqual(sorted(a for a, _ in pairs), ["1", "2", "3", "4"], pairs)
        for a, b in pairs:
            self.assertEqual(a, b)

    def test_two_variables_each_cycle_independently(self):
        prompt = "${n=!{1|2|3|4}}${c=!{red|green}}${n} ${c} ${n} ${c}"
        outs = [o.split() for o in run_node(prompt, "shuffle", 4)]
        for n1, c1, n2, c2 in outs:
            self.assertEqual((n1, c1), (n2, c2))
        self.assertEqual(sorted(o[0] for o in outs), ["1", "2", "3", "4"])
        self.assertEqual(sorted(o[1] for o in outs), ["green", "green", "red", "red"])

    def test_other_shuffled_variants_keep_cycling(self):
        prompt = "${n=!{1|2|3|4}}${n} {red|green|blue}"
        colours = [o.split()[1] for o in run_node(prompt, "shuffle", 6)]
        self.assertEqual(sorted(colours[:3]), ["blue", "green", "red"])
        self.assertEqual(colours[3:], colours[:3])


class ExistingBehaviourUnchanged(unittest.TestCase):
    def test_plain_shuffle_variant_cycles(self):
        outs = run_node("{a|b|c}", "shuffle", 6)
        self.assertEqual(sorted(outs[:3]), ["a", "b", "c"])
        self.assertEqual(outs[3:], outs[:3])

    def test_random_mode_immediate_variable_is_consistent(self):
        for out in run_node("${n=!{1|2|3|4}}${n}-${n}", "random", 6):
            a, b = out.split("-")
            self.assertEqual(a, b)

    def test_literal_immediate_variable(self):
        self.assertEqual(run_node("${x=!hello}${x} ${x}", "shuffle", 2), ["hello hello"] * 2)

    def test_same_level_reassignment_last_wins(self):
        # Library behaviour: ?= only sees variables from an enclosing context,
        # so at the same level the later assignment still wins.
        self.assertEqual(run_node("${x=!one}${x?=!two}${x}", "shuffle", 2), ["two"] * 2)

    def test_non_immediate_variable_resamples_each_access(self):
        outs = run_node("${n={1|2|3|4}}${n}${n}", "shuffle", 2)
        self.assertEqual(len(outs[0]), 2)


if __name__ == "__main__":
    unittest.main()
