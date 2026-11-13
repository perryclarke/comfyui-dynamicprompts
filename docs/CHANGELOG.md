## perryclarke fork

Changes on top of [cbaoth/comfyui-dynamicprompts](https://github.com/cbaoth/comfyui-dynamicprompts) (based on 0.2.1). The version number has not been changed. Details are in the README under [Changes in this fork](../README.md#changes-in-this-fork-perryclarke).

- 2026-11-12 - Saved prompts: drag the ⠿ handle next to 🗑 to reorder prompts, so `go to next prompt` runs them in a chosen order. The open prompt stays open after a move.
- 2026-11-11 - Saved prompts: **After each run** setting. `go to next prompt` opens the next non-empty prompt after each queued run, wrapping at the end; batch count steps through the list. Default `stay on this prompt` keeps the old behaviour.
- 2026-11-10 - Saved prompts: `Random Prompts Advanced` holds a list of prompts stored with the workflow (`dp_prompts` node property). The open prompt is used for the run and is mirrored into the `text` input, so the API format and older copies of the extension still see a single prompt. New browser extension `web/prompt_list.js` (`WEB_DIRECTORY` added to `__init__.py`).
- 2026-02-27 - Wildcard filters: commas in a filter act as OR and each term is a case-insensitive regex (`__name?two,seven__`, `__name?^five__`).
- 2026-02-27 - Wildcard filters: `__name?filter__` keeps only the values of a wildcard that match the filter. Works with sampler prefixes (`__&name?x__`) and inside variants (`{__name?x__}`).
- 2026-02-22 - Shuffle sampling: new `shuffle` option for `sampling_mode` on `Random Prompts Advanced`. Visits every variant/wildcard value once in a seeded-random order, then repeats that order. New inline prefix `{&a|b|c}` shuffles a single variant list in any mode or node.
- 2026-02-22 - Wildcard auto-reload: wildcard files changed on disk are reloaded on the next run without restarting ComfyUI. The newest file modification time is included in the node's change hash, so editing a wildcard re-runs the node under `refresh_mode = on_value_change`.

## cbaoth fork

Changes by [cbaoth](https://github.com/cbaoth/comfyui-dynamicprompts) on top of 0.2.1 (sampling/refresh/console modes, `Random Prompts Advanced` node) are described in the README under [Updates by cbaoth](../README.md#updates-by-cbaoth-2024-11-13).

## Original releases

- 0.2.1 - Fixed a bug due to a backwards incompatible change in the latest version of dynamicprompts that returns a SampleResult instead of a str
- 0.2.0 - Nodes now have settable seeds for reproducibility. Thanks to [@romeobuilderotti](https://github.com/romeobuilderotti/) for the inspiration for the inspiration. Also upgraded dynamicprompts to v0.30.1
- 0.1.3 - Wildcards in the ComfUI root are also supported for backwards compatibility
- 0.1.2 - The extension now looks for wildcards in custom_nodes/comfyui_dynamicprompts/wildcards
- 0.1.1 - Changed to relative imports - fixes [#1](https://github.com/adieyal/comfyui-dynamicprompts/issues/1)
- 0.1.0 - First release
