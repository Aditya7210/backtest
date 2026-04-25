C:\Users\aggar\PROJECTS\Algo_Trading_System\Strategies\Strategy_codes this folder will only contain the algorithm strategies

C:\Users\aggar\PROJECTS\Algo_Trading_System\Strategies\Strategy_files this folder contain the explanation of the code written in the Strategy_codes folder

C:\Users\aggar\PROJECTS\Algo_Trading_System\Backtesting this folder contains the execution script, the algo will be taken from the strategies folder

C:\Users\aggar\PROJECTS\Algo_Trading_System\Data\testing_data\Data_files this folder contains the data files for testing the strategies, it contains various sub folders as well to segregate data based on data source

C:\Users\aggar\PROJECTS\Algo_Trading_System\Data\testing_data\data_pull_scripts this folder contains the python scripts to download data from various data sources like jugaad-data and Yahoo Finance, etc

C:\Users\aggar\PROJECTS\Algo_Trading_System\Indicators this folder contains custom made indicators

C:\Users\aggar\PROJECTS\Algo_Trading_System\Guide this folder contains important information on various libraries and how to efficiently use them.

C:\Users\aggar\PROJECTS\Algo_Trading_System\Dashboard\dashboard.py file contains the dashboard layout that will show the result of the backtests, the data contained in this folders C:\Users\aggar\PROJECTS\Algo_Trading_System\Data\testing_data\Data_files will be used to make the candle stick charts and the data contained in C:\Users\aggar\PROJECTS\Algo_Trading_System\Data\Logs\Backtesting_result_log will be used to add further details to the chart

C:\Users\aggar\PROJECTS\Algo_Trading_System\requirements.txt this file contains the various libraries that we are utilzing this project, if any additional library is required them add them in this file and add comment regarding the use of that specific library.

This entire project is in docker and no native python is downloaded

Use Cython in places where calculation needs to be done to increase the speed of the system.

```
SYSTEM PRINCIPLE

- Separate 3 layers:
  1. File System = source of truth
  2. Session State = UI memory
  3. Execution Engine = external processor

- UI must NEVER assume save success unless file is written
- Do NOT mix execution logic inside Streamlit UI
```

---

```
STATE MANAGEMENT (MANDATORY)

Initialize once:

- current_strategy_file
- editor_content
- saved_content
- is_dirty
- versioning_enabled
- selected_data_files
- selected_strategy_files
- is_executing
- logs_cache

Rules:

- Do NOT reset state on rerun
- Only update state on user action
- Only load file when strategy changes
```

---

```
EDITOR SYSTEM

- Use: streamlit-ace (recommended)

Flow:

1. Load file
   - saved_content = file content
   - editor_content = file content
   - is_dirty = False

2. On edit:
   - update editor_content
   - compare with saved_content
   - if different → is_dirty = True
   - else → is_dirty = False

Critical Rule:
- NEVER directly bind editor to file
- Always go through session_state
```

---

```
INDICATOR LOGIC (GREEN / RED DOT)

- GREEN:
  editor_content == saved_content

- RED:
  editor_content != saved_content

- Update dynamically on every edit

DO NOT:
- manually toggle indicator
- rely on button clicks
```

---

```
STRATEGY NAME EDITING

- Keep 2 variables:
  - display_name (editable)
  - actual_file_name (system)

Flow:

1. User edits name
2. On save:
   - if name changed:
       rename file
       update file list
       update current_strategy_file

Important:
- Never rename instantly on typing
- Only rename on SAVE
```

---

```
SAVE BUTTON LOGIC

Conditions:

- If versioning_enabled == True AND is_dirty == False
  → disable save button

On Click:

IF versioning OFF:
  - overwrite existing file
  - saved_content = editor_content
  - is_dirty = False

IF versioning ON:
  - detect latest version
  - increment version
  - create new file
  - update dropdown list
  - set new file as selected
  - saved_content = editor_content
  - is_dirty = False
```

---

```
VERSIONING SYSTEM

Naming format:
- StrategyName_v1.py
- StrategyName_v2.py

Steps:

1. Scan existing files
2. Extract version numbers
3. Get max version
4. Create next version

Rules:

- Always increment
- Never overwrite old versions
- Auto-select newest version after save
```

---

```
DATA SELECTION (MULTISELECT)

- Load available files once
- Store in session_state

Rules:

- Do NOT rescan folder every rerun
- Refresh only when needed

Selections:
- selected_data_files
- selected_strategy_files
```

---

```
EXECUTE BUTTON (CRITICAL)

On Click:

1. Check:
   - not already executing

2. Set:
   - is_executing = True

3. Trigger execution:
   - call execution_engine.py via subprocess

4. DO NOT run backtest inside Streamlit

5. After completion:
   - is_executing = False

Important:

- Disable button while running
- Prevent double execution
```

---

```
TERMINAL WINDOW (LOG VIEWER)

Source:
- read from /Logs/*.log

Display:

- last N lines (10–20)
- auto refresh using container

Rules:

- NEVER simulate logs manually
- ALWAYS read from actual file

Optional:
- add "View Full Log" button
```

---

```
LAYOUT STRUCTURE

TOP BAR:
- Strategy Name (editable)
- Indicator (left of save)
- Save Button

MAIN AREA:
LEFT:
- Code Editor

RIGHT:
- Data Selection
- Strategy Selection
- Version Toggle
- AI Refiner (disabled)
- Execute Button
- Create Strategy
- Result Loader (disabled)

BOTTOM:
- Terminal Window

Use:
- st.columns
- st.container
```

---

```
CREATE NEW STRATEGY

On Click:

1. Create new file:
   - Strategy_new.py

2. Set:
   - current_strategy_file = new file
   - editor_content = empty template
   - saved_content = empty template
   - is_dirty = True

Rule:
- Must rename before proper saving
```

---

```
AI REFINER BUTTON

- Disabled (grey)
- On click:
  show error:
  "Feature currently in development"
```

---

```
RESULT LOADER BUTTON

- Disabled (grey)
- On click:
  show error:
  "Feature currently in development"
```

---

```
FILE SAFETY RULES

- Always check file exists before reading
- Always handle exceptions on save
- Never assume rename success
```

---

```
EXECUTION SAFETY

- Prevent double clicks
- Lock execution using is_executing
- Optional: add timeout handling
```

---

```
PERFORMANCE RULES

- Cache file lists
- Avoid heavy operations in UI loop
- Read logs efficiently (tail only)
```

---

```
COMMON FAILURE POINTS (AVOID THESE)

- Editor resets on every rerun
- Indicator not synced with actual content
- Version overwrite instead of increment
- Multiple executions triggered
- Logs duplicated or stale
- File rename breaking selection
```
