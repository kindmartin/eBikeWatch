# Refactor plan for `t` runtime module

The `inDev/t.py` entrypoint has grown to ~70 KB and mixes UI, PR bridge, guard logic, and CLI APIs. To keep evolving toward the final ESP32 main firmware we should break the module into cohesive packages and centralize hardware utilities. Below is the staged plan.

## 1. Split responsibilities

1. **Runtime manager package**
   - `runtime/manager/app.py`: orchestration (`_main_async`, task tracking, startup/shutdown hooks).
   - `runtime/manager/pr_thread.py`: PR bridge thread creation, stop/start helpers, `_wait_for_pr_thread_idle`.
   - `runtime/manager/sleep.py`: `_prepare_for_battery_sleep`, async UART release helper, wake pulse scheduling.
2. **PR bridge API**
   - Move `pr_*` helper functions (ping/status/version/snapshot/sleep/wake/poll control) into `runtime/pr_bridge_api.py`, wrapping `runtime.phaserunner_worker`.
   - Keep `t.py` as a thin facade re-exporting these.
3. **Dashboard/UI loader**
   - Create `UI_helpers/dashboard_loader.py` (or `ui/dashboard_loader.py`) that parses `dashboard_order.json`, instantiates dashboards, and keeps references to active screens.
4. **CLI/front-facing API**
   - Leave `t.py` as user-facing commands only, delegating to new modules. Target file size < 15 KB.

## 2. Centralize hardware definitions

- Ensure every GPIO constant lives in `HW.py`. If other files hardcode numbers, replace them with `HW` constants.
- Add helper functions in `HW.py` (e.g., `init_pr_uart`, `release_pr_uart`) so upper layers no longer import `machine` directly.

## 3. Migration steps

1. **Phase 1 — Infrastructure copy-out**
   - Create new modules and move code blocks verbatim.
   - Update `t.py` imports to use the new modules. No behavior changes.
2. **Phase 2 — Cleanup**
   - Remove dead code, tighten imports, and split UI-specific utilities.
   - Document new module boundaries in `README` or docstring comments.
3. **Phase 3 — Optimization**
   - Once modules are in place, profile memory/boot time.
   - Consider lazy-loading dashboards or adding `__all__` for clarity.

## 4. Testing impact

- After each phase, verify:
  - `import t; t.print_status()` works.
  - Sleep guard still triggers after USB loss.
  - PR bridge commands (ping, sleep, wake) behave as before.

This plan keeps the API stable while progressively modularizing the runtime and preparing for the eventual dedicated `main.py` firmware.
